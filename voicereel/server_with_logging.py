"""VoiceReel server with structured JSON logging and error handling."""

import json
import os
from typing import Optional

from loguru import logger

from .error_responses import ErrorHandlerMixin, handle_exception
from .json_logger import api_key_id, configure_json_logging, user_id
from .logging_middleware import create_logged_handler
from .server_postgres import VoiceReelRequestHandler, VoiceReelServer


class VoiceReelLoggingHandler(VoiceReelRequestHandler, ErrorHandlerMixin):
    """Request handler with integrated logging and error handling."""
    
    def handle_one_request(self):
        """Override to add error handling."""
        try:
            super().handle_one_request()
        except Exception as e:
            # Handle unexpected errors
            error_dict, status_code = handle_exception(
                e, 
                include_traceback=self.server.debug_mode
            )
            
            # Send error response
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(error_dict).encode())
    
    def authenticate_request(self):
        """Override to add user context."""
        result = super().authenticate_request()
        
        # Set user context if authenticated
        if result and hasattr(self, "_current_api_key"):
            # In a real implementation, you'd look up the user ID
            # For now, we'll use a placeholder
            user_id.set(f"user_{self._current_api_key[:8]}")
        
        return result


class VoiceReelServerWithLogging(VoiceReelServer):
    """VoiceReel server with integrated JSON logging."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        *,
        dsn: Optional[str] = None,
        api_key: Optional[str] = None,
        hmac_secret: Optional[str] = None,
        redis_url: Optional[str] = None,
        use_celery: Optional[bool] = None,
        # Logging configuration
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        enable_console_log: bool = True,
        debug_mode: bool = False,
    ):
        """Initialize server with logging.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            dsn: Database connection string
            api_key: API key for authentication
            hmac_secret: HMAC secret for request signing
            redis_url: Redis URL for Celery
            use_celery: Whether to use Celery for async tasks
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Optional log file path
            enable_console_log: Enable console logging
            debug_mode: Enable debug mode with detailed logs
        """
        # Configure JSON logging
        configure_json_logging(
            level=log_level,
            enable_console=enable_console_log,
            log_file=log_file,
            enable_debug=debug_mode,
        )
        
        # Store debug mode
        self.debug_mode = debug_mode
        
        # Log server startup
        logger.info(
            "Starting VoiceReel server with structured logging",
            extra={
                "host": host,
                "port": port,
                "log_level": log_level,
                "debug_mode": debug_mode,
                "has_database": bool(dsn),
                "has_redis": bool(redis_url),
                "use_celery": use_celery,
            }
        )
        
        # Initialize base server
        super().__init__(
            host=host,
            port=port,
            dsn=dsn,
            api_key=api_key,
            hmac_secret=hmac_secret,
            redis_url=redis_url,
            use_celery=use_celery,
        )
    
    def _make_handler(self):
        """Create request handler with logging middleware."""
        # Create base handler with our logging handler
        base_handler = type(
            "Handler",
            (VoiceReelLoggingHandler,),
            {
                "flask_app": self.flask_app,
                "server": self,
            }
        )
        
        # Apply logging middleware
        return create_logged_handler(base_handler)
    
    def log_server_info(self):
        """Log server configuration and status."""
        info = {
            "server": {
                "host": self.host,
                "port": self.port,
                "version": "1.0.0",
                "debug_mode": self.debug_mode,
            },
            "features": {
                "database": "PostgreSQL" if "postgresql" in str(self.dsn) else "SQLite",
                "queue": "Celery" if self.use_celery else "In-Memory",
                "storage": "S3" if os.getenv("VR_S3_BUCKET") else "Local",
                "authentication": bool(self.api_key),
                "hmac_signing": bool(self.hmac_secret),
            },
            "configuration": {
                "max_upload_size": self.flask_app.config.get("MAX_CONTENT_LENGTH", 0),
                "cors_enabled": bool(self.flask_app.config.get("CORS_ENABLED")),
                "rate_limiting": bool(self.flask_app.config.get("RATELIMIT_ENABLED")),
            }
        }
        
        logger.info("VoiceReel server configuration", extra=info)
    
    def start(self):
        """Start the server with logging."""
        self.log_server_info()
        
        logger.info(
            f"VoiceReel server listening on http://{self.host}:{self.port}",
            extra={
                "event": "server_start",
                "pid": os.getpid(),
            }
        )
        
        super().start()
    
    def stop(self):
        """Stop the server with logging."""
        logger.info(
            "Stopping VoiceReel server",
            extra={
                "event": "server_stop",
                "pid": os.getpid(),
            }
        )
        
        super().stop()
        
        logger.info("VoiceReel server stopped successfully")


def create_server_from_env():
    """Create server instance from environment variables."""
    # Get logging configuration from environment
    log_config = {
        "log_level": os.getenv("VR_LOG_LEVEL", "INFO"),
        "log_file": os.getenv("VR_LOG_FILE"),
        "enable_console_log": os.getenv("VR_LOG_CONSOLE", "true").lower() == "true",
        "debug_mode": os.getenv("VR_DEBUG", "false").lower() == "true",
    }
    
    # Get server configuration
    server_config = {
        "host": os.getenv("VR_HOST", "0.0.0.0"),
        "port": int(os.getenv("VR_PORT", "8080")),
        "dsn": os.getenv("VR_DSN") or os.getenv("VR_POSTGRES_DSN"),
        "api_key": os.getenv("VR_API_KEY"),
        "hmac_secret": os.getenv("VR_HMAC_SECRET"),
        "redis_url": os.getenv("VR_REDIS_URL"),
        "use_celery": os.getenv("VR_USE_CELERY", "true").lower() == "true",
    }
    
    # Combine configurations
    config = {**server_config, **log_config}
    
    return VoiceReelServerWithLogging(**config)


def run_server():
    """Run VoiceReel server with logging from environment configuration."""
    server = create_server_from_env()
    
    try:
        server.start()
        
        # Keep server running
        if server.thread:
            server.thread.join()
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Server crashed: {e}", exc_info=True)
    finally:
        server.stop()


if __name__ == "__main__":
    run_server()