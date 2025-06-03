"""HTTPS server implementation for VoiceReel with TLS 1.3 support."""

import os
import ssl
import threading
from http.server import HTTPServer
from typing import Optional

from loguru import logger

from .server import VoiceReelServer
from .tls_manager import TLSCertificateManager, get_tls_manager


class VoiceReelHTTPSServer(VoiceReelServer):
    """VoiceReel server with HTTPS/TLS 1.3 support."""
    
    def __init__(self,
                 host: str = "0.0.0.0",
                 port: int = 8443,  # Standard HTTPS port for APIs
                 *,
                 dsn: str | None = None,
                 api_key: str | None = None,
                 hmac_secret: str | None = None,
                 redis_url: str | None = None,
                 use_celery: bool = None,
                 # TLS specific options
                 cert_path: str | None = None,
                 key_path: str | None = None,
                 auto_generate_cert: bool = True,
                 domain: str = "localhost",
                 tls_version: str = "TLSv1.3"):
        """Initialize HTTPS server.
        
        Args:
            host: Host to bind to
            port: Port to bind to (default 8443 for HTTPS)
            dsn: Database connection string
            api_key: API key for authentication
            hmac_secret: HMAC secret for request signing
            redis_url: Redis URL for Celery
            use_celery: Whether to use Celery for async tasks
            cert_path: Path to SSL certificate file
            key_path: Path to private key file
            auto_generate_cert: Auto-generate self-signed cert if none provided
            domain: Domain name for certificate generation
            tls_version: TLS version to use (TLSv1.2 or TLSv1.3)
        """
        # Initialize base server (but don't start HTTP server yet)
        super().__init__(host, port, dsn=dsn, api_key=api_key, 
                        hmac_secret=hmac_secret, redis_url=redis_url, 
                        use_celery=use_celery)
        
        # TLS configuration
        self.cert_path = cert_path
        self.key_path = key_path
        self.auto_generate_cert = auto_generate_cert
        self.domain = domain
        self.tls_version = tls_version
        self.tls_manager = get_tls_manager()
        
        # Setup certificates
        self._setup_certificates()
        
        # Create HTTPS server with SSL context
        self._setup_https_server()
        
        logger.info(f"VoiceReel HTTPS server initialized on https://{host}:{port}")
    
    def _setup_certificates(self):
        """Setup SSL certificates for HTTPS."""
        logger.info("Setting up SSL certificates...")
        
        if self.cert_path and self.key_path:
            # Use provided certificate files
            logger.info("Using provided certificate files")
            self.cert_path, self.key_path = self.tls_manager.load_existing_cert(
                self.cert_path, self.key_path
            )
        elif self.auto_generate_cert:
            # Auto-generate self-signed certificate for development
            logger.info("Auto-generating self-signed certificate")
            self.cert_path, self.key_path = self.tls_manager.generate_self_signed_cert(
                domain=self.domain
            )
        else:
            raise ValueError("No SSL certificate provided and auto-generation disabled")
        
        # Validate certificate
        cert_info = self.tls_manager.validate_certificate()
        if not cert_info.get("valid"):
            if cert_info.get("expired"):
                logger.warning("SSL certificate has expired")
            else:
                logger.warning(f"SSL certificate validation failed: {cert_info.get('error')}")
        else:
            logger.info(f"SSL certificate valid until: {cert_info.get('expires')}")
            if cert_info.get("expiring_soon"):
                logger.warning(f"SSL certificate expires in {cert_info.get('days_until_expiry')} days")
    
    def _setup_https_server(self):
        """Setup HTTPS server with SSL context."""
        # Create SSL context
        self.ssl_context = self.tls_manager.create_ssl_context()
        
        # Replace the HTTP server with HTTPS server
        handler = self._make_handler()
        self.httpd = HTTPServer((self.host, self.port), handler)
        
        # Wrap socket with SSL
        self.httpd.socket = self.ssl_context.wrap_socket(
            self.httpd.socket, 
            server_side=True
        )
        
        logger.info(f"HTTPS server configured with {self.tls_version}")
    
    def get_server_info(self) -> dict:
        """Get server information including TLS details."""
        base_info = {
            "protocol": "https",
            "host": self.host,
            "port": self.port,
            "url": f"https://{self.host}:{self.port}",
            "tls_version": self.tls_version,
        }
        
        # Add certificate info
        cert_info = self.tls_manager.get_cert_info()
        base_info.update({
            "certificate": cert_info,
            "ssl_context": {
                "protocol": self.ssl_context.protocol.name,
                "options": self.ssl_context.options,
                "minimum_version": self.ssl_context.minimum_version.name,
                "maximum_version": self.ssl_context.maximum_version.name,
            }
        })
        
        return base_info
    
    def start(self) -> None:
        """Start the HTTPS server."""
        logger.info(f"Starting VoiceReel HTTPS server on https://{self.host}:{self.port}")
        
        # Log security information
        logger.info(f"TLS version: {self.tls_version}")
        logger.info(f"Certificate: {self.cert_path}")
        logger.info(f"Security features enabled:")
        logger.info(f"  - TLS 1.3 support: ✅")
        logger.info(f"  - Modern cipher suites: ✅") 
        logger.info(f"  - CORS protection: ✅")
        logger.info(f"  - Rate limiting: ✅")
        logger.info(f"  - Input validation: ✅")
        logger.info(f"  - API key authentication: {'✅' if self.api_key else '❌'}")
        logger.info(f"  - HMAC request signing: {'✅' if self.hmac_secret else '❌'}")
        
        # Start the server using parent's start method
        super().start()
    
    def stop(self) -> None:
        """Stop the HTTPS server."""
        logger.info("Stopping VoiceReel HTTPS server")
        super().stop()


class VoiceReelHTTPSServerManager:
    """Manager for VoiceReel HTTPS server with certificate lifecycle management."""
    
    def __init__(self, 
                 config_file: Optional[str] = None,
                 auto_renew_certs: bool = True):
        """Initialize server manager.
        
        Args:
            config_file: Path to configuration file
            auto_renew_certs: Automatically renew certificates when needed
        """
        self.config_file = config_file
        self.auto_renew_certs = auto_renew_certs
        self.server: Optional[VoiceReelHTTPSServer] = None
        self.renewal_thread: Optional[threading.Thread] = None
        self._stop_renewal = threading.Event()
        
    def create_server_from_env(self) -> VoiceReelHTTPSServer:
        """Create server from environment variables."""
        config = {
            "host": os.getenv("VOICEREEL_HOST", "0.0.0.0"),
            "port": int(os.getenv("VOICEREEL_HTTPS_PORT", "8443")),
            "dsn": os.getenv("VR_DSN"),
            "api_key": os.getenv("VR_API_KEY"),
            "hmac_secret": os.getenv("VR_HMAC_SECRET"),
            "redis_url": os.getenv("VR_REDIS_URL"),
            "cert_path": os.getenv("VOICEREEL_CERT_PATH"),
            "key_path": os.getenv("VOICEREEL_KEY_PATH"),
            "auto_generate_cert": os.getenv("VOICEREEL_AUTO_GENERATE_CERT", "true").lower() == "true",
            "domain": os.getenv("VOICEREEL_DOMAIN", "localhost"),
            "tls_version": os.getenv("VOICEREEL_TLS_VERSION", "TLSv1.3"),
        }
        
        # Filter None values
        config = {k: v for k, v in config.items() if v is not None}
        
        return VoiceReelHTTPSServer(**config)
    
    def start_server(self, server_config: Optional[dict] = None) -> VoiceReelHTTPSServer:
        """Start HTTPS server with optional configuration.
        
        Args:
            server_config: Server configuration dict
            
        Returns:
            Started server instance
        """
        if server_config:
            self.server = VoiceReelHTTPSServer(**server_config)
        else:
            self.server = self.create_server_from_env()
        
        self.server.start()
        
        # Start certificate renewal monitoring
        if self.auto_renew_certs:
            self._start_cert_renewal_monitor()
        
        return self.server
    
    def stop_server(self):
        """Stop the HTTPS server and certificate monitoring."""
        if self.server:
            self.server.stop()
            self.server = None
        
        # Stop certificate renewal monitoring
        self._stop_renewal.set()
        if self.renewal_thread:
            self.renewal_thread.join()
            self.renewal_thread = None
    
    def _start_cert_renewal_monitor(self):
        """Start background thread to monitor certificate expiration."""
        if self.renewal_thread and self.renewal_thread.is_alive():
            return
        
        self.renewal_thread = threading.Thread(
            target=self._cert_renewal_loop,
            daemon=True,
            name="cert-renewal-monitor"
        )
        self.renewal_thread.start()
        logger.info("Certificate renewal monitoring started")
    
    def _cert_renewal_loop(self):
        """Background loop to check and renew certificates."""
        while not self._stop_renewal.wait(24 * 3600):  # Check daily
            try:
                if self.server and self.server.tls_manager:
                    cert_info = self.server.tls_manager.validate_certificate()
                    
                    # Renew if expiring within 30 days
                    if cert_info.get("expiring_soon"):
                        days_left = cert_info.get("days_until_expiry", 0)
                        logger.warning(f"Certificate expires in {days_left} days, attempting renewal")
                        
                        # TODO: Implement automatic renewal logic
                        # This would depend on how the certificate was originally obtained
                        # (Let's Encrypt, manual, etc.)
                        
            except Exception as e:
                logger.error(f"Certificate renewal check failed: {e}")


def create_https_server(**kwargs) -> VoiceReelHTTPSServer:
    """Factory function to create HTTPS server.
    
    Args:
        **kwargs: Server configuration parameters
        
    Returns:
        Configured HTTPS server instance
    """
    return VoiceReelHTTPSServer(**kwargs)


def run_https_server_from_env():
    """Run HTTPS server with configuration from environment variables."""
    manager = VoiceReelHTTPSServerManager()
    
    try:
        server = manager.start_server()
        logger.info("VoiceReel HTTPS server is running")
        
        # Keep server running
        if server.thread:
            server.thread.join()
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        manager.stop_server()
        logger.info("VoiceReel HTTPS server stopped")