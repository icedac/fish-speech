"""TLS certificate management for VoiceReel production deployment."""

import os
import ssl
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from loguru import logger


class TLSCertificateManager:
    """Manage TLS certificates for VoiceReel API server."""
    
    def __init__(self, cert_dir: str = "/etc/voicereel/certs"):
        """Initialize TLS certificate manager.
        
        Args:
            cert_dir: Directory to store certificates
        """
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Certificate file paths
        self.private_key_path = self.cert_dir / "voicereel.key"
        self.certificate_path = self.cert_dir / "voicereel.crt"
        self.ca_bundle_path = self.cert_dir / "ca-bundle.crt"
        self.fullchain_path = self.cert_dir / "fullchain.pem"
    
    def generate_self_signed_cert(self, 
                                 domain: str = "localhost",
                                 days_valid: int = 365,
                                 key_size: int = 2048) -> Tuple[str, str]:
        """Generate self-signed certificate for development.
        
        Args:
            domain: Domain name for certificate
            days_valid: Certificate validity in days
            key_size: RSA key size
            
        Returns:
            Tuple of (certificate_path, private_key_path)
        """
        logger.info(f"Generating self-signed certificate for {domain}")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        
        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VoiceReel"),
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=days_valid)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(domain),
                x509.DNSName(f"*.{domain}"),
                x509.DNSName("localhost"),
                x509.IPAddress("127.0.0.1"),
            ]),
            critical=False,
        ).add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        ).add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
            ]),
            critical=True,
        ).sign(private_key, hashes.SHA256())
        
        # Write private key
        with open(self.private_key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Write certificate
        with open(self.certificate_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Set proper permissions
        os.chmod(self.private_key_path, 0o600)
        os.chmod(self.certificate_path, 0o644)
        
        logger.info(f"Generated self-signed certificate: {self.certificate_path}")
        logger.info(f"Private key: {self.private_key_path}")
        
        return str(self.certificate_path), str(self.private_key_path)
    
    def setup_letsencrypt_cert(self, 
                              domain: str,
                              email: str,
                              staging: bool = False) -> Tuple[str, str]:
        """Setup Let's Encrypt certificate using certbot.
        
        Args:
            domain: Domain name for certificate
            email: Email for Let's Encrypt registration
            staging: Use staging environment for testing
            
        Returns:
            Tuple of (certificate_path, private_key_path)
        """
        logger.info(f"Setting up Let's Encrypt certificate for {domain}")
        
        # Check if certbot is available
        try:
            subprocess.run(["certbot", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("certbot not found. Install with: apt-get install certbot")
        
        # Build certbot command
        cmd = [
            "certbot", "certonly",
            "--standalone",
            "--non-interactive",
            "--agree-tos",
            "--email", email,
            "-d", domain,
            "--cert-path", str(self.certificate_path),
            "--key-path", str(self.private_key_path),
        ]
        
        if staging:
            cmd.append("--staging")
        
        # Run certbot
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Let's Encrypt certificate obtained successfully")
            logger.debug(f"Certbot output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Certbot failed: {e.stderr}")
            raise RuntimeError(f"Failed to obtain Let's Encrypt certificate: {e}")
        
        # Copy certificates to our directory if certbot used default location
        default_cert_dir = Path(f"/etc/letsencrypt/live/{domain}")
        if default_cert_dir.exists():
            # Copy fullchain and private key
            import shutil
            shutil.copy2(default_cert_dir / "fullchain.pem", self.certificate_path)
            shutil.copy2(default_cert_dir / "privkey.pem", self.private_key_path)
            
            # Set permissions
            os.chmod(self.private_key_path, 0o600)
            os.chmod(self.certificate_path, 0o644)
        
        return str(self.certificate_path), str(self.private_key_path)
    
    def load_existing_cert(self, cert_path: str, key_path: str) -> Tuple[str, str]:
        """Load existing certificate files.
        
        Args:
            cert_path: Path to certificate file
            key_path: Path to private key file
            
        Returns:
            Tuple of (certificate_path, private_key_path)
        """
        logger.info("Loading existing certificate files")
        
        # Validate files exist
        if not os.path.exists(cert_path):
            raise FileNotFoundError(f"Certificate file not found: {cert_path}")
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"Private key file not found: {key_path}")
        
        # Copy to our cert directory
        import shutil
        shutil.copy2(cert_path, self.certificate_path)
        shutil.copy2(key_path, self.private_key_path)
        
        # Set permissions
        os.chmod(self.private_key_path, 0o600)
        os.chmod(self.certificate_path, 0o644)
        
        return str(self.certificate_path), str(self.private_key_path)
    
    def validate_certificate(self) -> Dict[str, any]:
        """Validate the current certificate.
        
        Returns:
            Dict with certificate information and validation status
        """
        if not self.certificate_path.exists():
            return {"valid": False, "error": "Certificate file not found"}
        
        try:
            # Load certificate
            with open(self.certificate_path, "rb") as f:
                cert_data = f.read()
            
            cert = x509.load_pem_x509_certificate(cert_data)
            
            # Get certificate info
            now = datetime.utcnow()
            expires = cert.not_valid_after
            days_until_expiry = (expires - now).days
            
            # Check if expired
            is_expired = now > expires
            is_expiring_soon = days_until_expiry <= 30
            
            # Get subject info
            subject = cert.subject
            common_name = None
            for attribute in subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    common_name = attribute.value
                    break
            
            # Get SAN (Subject Alternative Names)
            san_domains = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                san_domains = [name.value for name in san_ext.value]
            except x509.ExtensionNotFound:
                pass
            
            return {
                "valid": not is_expired,
                "expired": is_expired,
                "expiring_soon": is_expiring_soon,
                "days_until_expiry": days_until_expiry,
                "expires": expires.isoformat(),
                "common_name": common_name,
                "san_domains": san_domains,
                "serial_number": str(cert.serial_number),
                "issuer": cert.issuer.rfc4514_string(),
            }
            
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def create_ssl_context(self, 
                          protocol: int = ssl.PROTOCOL_TLS_SERVER,
                          ciphers: Optional[str] = None) -> ssl.SSLContext:
        """Create SSL context for HTTPS server.
        
        Args:
            protocol: SSL protocol version
            ciphers: Cipher suite string
            
        Returns:
            Configured SSL context
        """
        if not self.certificate_path.exists() or not self.private_key_path.exists():
            raise RuntimeError("Certificate or private key not found. Generate or load certificates first.")
        
        # Create SSL context
        context = ssl.SSLContext(protocol)
        
        # Load certificate and key
        context.load_cert_chain(str(self.certificate_path), str(self.private_key_path))
        
        # Set security options for TLS 1.3
        context.minimum_version = ssl.TLSVersion.TLSv1_2  # Minimum TLS 1.2
        context.maximum_version = ssl.TLSVersion.TLSv1_3  # Prefer TLS 1.3
        
        # Security options
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        context.options |= ssl.OP_SINGLE_DH_USE
        context.options |= ssl.OP_SINGLE_ECDH_USE
        
        # Set cipher suites (prefer TLS 1.3 ciphers)
        if ciphers:
            context.set_ciphers(ciphers)
        else:
            # Modern cipher suite that prioritizes TLS 1.3
            modern_ciphers = ":".join([
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256", 
                "TLS_AES_128_GCM_SHA256",
                "ECDHE+AESGCM",
                "ECDHE+CHACHA20",
                "DHE+AESGCM",
                "DHE+CHACHA20",
                "!aNULL",
                "!MD5",
                "!DSS"
            ])
            context.set_ciphers(modern_ciphers)
        
        # Verify mode
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        logger.info("SSL context created with TLS 1.3 support")
        return context
    
    def get_cert_info(self) -> Dict[str, any]:
        """Get certificate information for monitoring/debugging.
        
        Returns:
            Dict with certificate paths and validation info
        """
        return {
            "cert_dir": str(self.cert_dir),
            "certificate_path": str(self.certificate_path),
            "private_key_path": str(self.private_key_path),
            "certificate_exists": self.certificate_path.exists(),
            "private_key_exists": self.private_key_path.exists(),
            "validation": self.validate_certificate(),
        }


def get_tls_manager(cert_dir: Optional[str] = None) -> TLSCertificateManager:
    """Get TLS certificate manager instance.
    
    Args:
        cert_dir: Certificate directory (defaults to env var or /etc/voicereel/certs)
        
    Returns:
        TLS certificate manager instance
    """
    if cert_dir is None:
        cert_dir = os.getenv("VOICEREEL_CERT_DIR", "/etc/voicereel/certs")
    
    return TLSCertificateManager(cert_dir)


def setup_development_certs(domain: str = "localhost") -> Tuple[str, str]:
    """Quick setup for development certificates.
    
    Args:
        domain: Domain for certificate
        
    Returns:
        Tuple of (certificate_path, private_key_path)
    """
    manager = get_tls_manager()
    return manager.generate_self_signed_cert(domain)


def setup_production_certs(domain: str, email: str, staging: bool = False) -> Tuple[str, str]:
    """Quick setup for production certificates using Let's Encrypt.
    
    Args:
        domain: Domain for certificate
        email: Email for Let's Encrypt registration
        staging: Use staging environment
        
    Returns:
        Tuple of (certificate_path, private_key_path)
    """
    manager = get_tls_manager()
    return manager.setup_letsencrypt_cert(domain, email, staging)