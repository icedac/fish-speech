"""HTTP request/response logging middleware for VoiceReel."""

import time
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from loguru import logger

from .json_logger import RequestLogger, api_key_id, request_id, user_id


class LoggingMiddleware:
    """Middleware for structured request/response logging."""
    
    def __init__(self, handler_class):
        """Initialize logging middleware.
        
        Args:
            handler_class: The base HTTP request handler class
        """
        self.handler_class = handler_class
    
    def __call__(self, request, client_address, server):
        """Create a wrapped handler with logging."""
        
        class LoggingHandler(self.handler_class):
            """HTTP handler with integrated logging."""
            
            def __init__(self, *args, **kwargs):
                # Generate request ID
                self._request_id = str(uuid.uuid4())
                self._start_time = time.time()
                self._response_size = 0
                super().__init__(*args, **kwargs)
            
            def setup(self):
                """Set up request context."""
                super().setup()
                # Set request ID context
                request_id.set(self._request_id)
            
            def do_GET(self):
                """Handle GET with logging."""
                self._log_request()
                super().do_GET()
                self._log_response()
            
            def do_POST(self):
                """Handle POST with logging."""
                self._log_request()
                super().do_POST()
                self._log_response()
            
            def do_PUT(self):
                """Handle PUT with logging."""
                self._log_request()
                super().do_PUT()
                self._log_response()
            
            def do_DELETE(self):
                """Handle DELETE with logging."""
                self._log_request()
                super().do_DELETE()
                self._log_response()
            
            def do_OPTIONS(self):
                """Handle OPTIONS with logging."""
                self._log_request()
                super().do_OPTIONS()
                self._log_response()
            
            def _log_request(self):
                """Log incoming request details."""
                # Get content length
                content_length = None
                if "content-length" in self.headers:
                    try:
                        content_length = int(self.headers["content-length"])
                    except ValueError:
                        pass
                
                # Get remote address
                remote_addr = self.client_address[0] if self.client_address else None
                
                # Extract API key ID if present
                if api_key := self.headers.get("X-VR-APIKEY"):
                    # Store first 8 chars as ID for logging
                    api_key_id.set(api_key[:8] + "..." if len(api_key) > 8 else api_key)
                
                # Log request
                RequestLogger.log_request(
                    method=self.command,
                    path=self.path,
                    headers=dict(self.headers),
                    body_size=content_length,
                    remote_addr=remote_addr,
                )
            
            def _log_response(self):
                """Log response details."""
                # Calculate duration
                duration_ms = (time.time() - self._start_time) * 1000
                
                # Get response status
                status_code = getattr(self, "_status_code", 200)
                error_message = getattr(self, "_error_message", None)
                
                # Log response
                RequestLogger.log_response(
                    status_code=status_code,
                    duration_ms=duration_ms,
                    body_size=self._response_size,
                    error=error_message,
                )
            
            def send_response(self, code, message=None):
                """Override to capture status code."""
                self._status_code = code
                super().send_response(code, message)
            
            def send_error(self, code, message=None, explain=None):
                """Override to capture error details."""
                self._status_code = code
                self._error_message = message
                super().send_error(code, message, explain)
            
            def wfile_write(self, data):
                """Track response size."""
                if isinstance(data, (bytes, bytearray)):
                    self._response_size += len(data)
                return self.wfile.write(data)
            
            def finish(self):
                """Clean up request context."""
                try:
                    super().finish()
                finally:
                    # Clear context variables
                    request_id.set(None)
                    user_id.set(None)
                    api_key_id.set(None)
        
        # Create and return the logging handler
        return LoggingHandler(request, client_address, server)


def create_logged_handler(base_handler_class):
    """Create a request handler with logging middleware.
    
    Args:
        base_handler_class: The base HTTP request handler class
        
    Returns:
        Handler class with logging middleware applied
    """
    middleware = LoggingMiddleware(base_handler_class)
    
    class LoggedHandler(base_handler_class):
        """Handler with automatic request/response logging."""
        
        def __new__(cls, *args, **kwargs):
            # Use middleware to create wrapped instance
            return middleware(*args, **kwargs)
    
    return LoggedHandler


class FlaskLoggingMiddleware:
    """Flask/WSGI middleware for structured logging."""
    
    def __init__(self, app):
        """Initialize Flask logging middleware.
        
        Args:
            app: Flask application instance
        """
        self.app = app
    
    def __call__(self, environ, start_response):
        """WSGI middleware implementation."""
        # Generate request ID
        req_id = str(uuid.uuid4())
        request_id.set(req_id)
        
        # Track start time
        start_time = time.time()
        
        # Extract request details
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        query_string = environ.get("QUERY_STRING", "")
        if query_string:
            path = f"{path}?{query_string}"
        
        # Get headers
        headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                headers[header_name] = value
        
        # Get content length
        content_length = None
        if "CONTENT_LENGTH" in environ:
            try:
                content_length = int(environ["CONTENT_LENGTH"])
            except ValueError:
                pass
        
        # Get remote address
        remote_addr = environ.get("REMOTE_ADDR")
        
        # Extract API key ID if present
        if api_key := headers.get("X-Vr-Apikey"):
            api_key_id.set(api_key[:8] + "..." if len(api_key) > 8 else api_key)
        
        # Log request
        RequestLogger.log_request(
            method=method,
            path=path,
            headers=headers,
            body_size=content_length,
            remote_addr=remote_addr,
        )
        
        # Track response details
        response_status = None
        response_size = 0
        
        def logging_start_response(status, response_headers):
            nonlocal response_status
            response_status = int(status.split()[0])
            
            # Track content length from response headers
            for name, value in response_headers:
                if name.lower() == "content-length":
                    try:
                        nonlocal response_size
                        response_size = int(value)
                    except ValueError:
                        pass
            
            return start_response(status, response_headers)
        
        try:
            # Call the application
            app_iter = self.app(environ, logging_start_response)
            
            # If no content-length header, calculate from response
            if response_size == 0:
                response_data = list(app_iter)
                response_size = sum(len(data) for data in response_data)
                app_iter = response_data
            
            # Log response
            duration_ms = (time.time() - start_time) * 1000
            RequestLogger.log_response(
                status_code=response_status or 200,
                duration_ms=duration_ms,
                body_size=response_size,
            )
            
            return app_iter
            
        except Exception as e:
            # Log error response
            duration_ms = (time.time() - start_time) * 1000
            RequestLogger.log_response(
                status_code=500,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise
        
        finally:
            # Clear context
            request_id.set(None)
            user_id.set(None)
            api_key_id.set(None)


def apply_flask_logging(app):
    """Apply logging middleware to Flask app.
    
    Args:
        app: Flask application instance
        
    Returns:
        App with logging middleware applied
    """
    app.wsgi_app = FlaskLoggingMiddleware(app.wsgi_app)
    
    # Also add request ID to Flask g object
    @app.before_request
    def set_request_id():
        """Set request ID in Flask context."""
        from flask import g
        g.request_id = request_id.get()
    
    return app


# Export middleware components
__all__ = [
    "LoggingMiddleware",
    "create_logged_handler",
    "FlaskLoggingMiddleware",
    "apply_flask_logging",
]