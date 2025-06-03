"""Structured JSON logging system for VoiceReel production deployment."""

import json
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger


# Context variables for request tracing
request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
api_key_id: ContextVar[Optional[str]] = ContextVar("api_key_id", default=None)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self):
        super().__init__()
        self.hostname = self._get_hostname()
        self.service_name = "voicereel-api"
    
    @staticmethod
    def _get_hostname():
        """Get hostname for logging."""
        import socket
        try:
            return socket.gethostname()
        except:
            return "unknown"
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "hostname": self.hostname,
            "pid": record.process,
            "thread": record.thread,
            "thread_name": record.threadName,
        }
        
        # Add context variables
        if req_id := request_id.get():
            log_entry["request_id"] = req_id
        if u_id := user_id.get():
            log_entry["user_id"] = u_id
        if key_id := api_key_id.get():
            log_entry["api_key_id"] = key_id
        
        # Add source location
        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
            "module": record.module,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }
        
        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry["extra"] = record.extra_fields
        
        # Add performance metrics if present
        if hasattr(record, "duration_ms"):
            log_entry["performance"] = {
                "duration_ms": record.duration_ms
            }
        
        return json.dumps(log_entry, ensure_ascii=False)


class LoguruJSONSink:
    """Custom Loguru sink for JSON output."""
    
    def __init__(self, stream=sys.stdout):
        self.stream = stream
        self.hostname = JSONFormatter._get_hostname()
        self.service_name = "voicereel-api"
    
    def write(self, message):
        """Write structured JSON log entry."""
        record = message.record
        
        # Build log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record["level"].name,
            "logger": "voicereel",
            "message": record["message"],
            "service": self.service_name,
            "hostname": self.hostname,
            "pid": record["process"].id,
            "thread": record["thread"].id,
            "thread_name": record["thread"].name,
        }
        
        # Add context variables
        if req_id := request_id.get():
            log_entry["request_id"] = req_id
        if u_id := user_id.get():
            log_entry["user_id"] = u_id
        if key_id := api_key_id.get():
            log_entry["api_key_id"] = key_id
        
        # Add source location
        log_entry["source"] = {
            "file": record["file"].path,
            "line": record["line"],
            "function": record["function"],
            "module": record["module"],
        }
        
        # Add extra fields
        extra = record["extra"]
        
        # Add exception info if present
        if record["exception"]:
            exc = record["exception"]
            log_entry["exception"] = {
                "type": exc.type.__name__ if exc.type else "Unknown",
                "message": str(exc.value) if exc.value else "",
                "traceback": exc.traceback.split('\n') if exc.traceback else [],
            }
        elif extra.get("exc_info"):
            # Handle exc_info=True case by capturing current exception
            import traceback
            import sys
            exc_info = sys.exc_info()
            if exc_info[0] is not None:
                log_entry["exception"] = {
                    "type": exc_info[0].__name__,
                    "message": str(exc_info[1]),
                    "traceback": traceback.format_tb(exc_info[2]),
                }
        if extra:
            # Handle nested extra structure from loguru
            if "extra" in extra and isinstance(extra["extra"], dict):
                # Use the nested extra data
                extra_data = extra["extra"]
            else:
                # Use the extra data directly
                extra_data = extra
            
            # Filter out loguru internal fields
            extra_fields = {k: v for k, v in extra_data.items() 
                          if not k.startswith("_") and k not in 
                          ["request_id", "user_id", "api_key_id"]}
            if extra_fields:
                log_entry["extra"] = extra_fields
        
        # Write JSON line
        json_line = json.dumps(log_entry, ensure_ascii=False) + "\n"
        self.stream.write(json_line)
        self.stream.flush()


def configure_json_logging(
    level: str = "INFO",
    enable_console: bool = True,
    log_file: Optional[str] = None,
    enable_debug: bool = False
):
    """Configure JSON structured logging for VoiceReel.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        enable_console: Enable console output
        log_file: Optional log file path
        enable_debug: Enable debug mode with detailed logs
    """
    # Remove default loguru handler
    logger.remove()
    
    # Set level based on debug mode
    if enable_debug:
        level = "DEBUG"
    
    # Add JSON console handler
    if enable_console:
        logger.add(
            LoguruJSONSink(sys.stdout),
            level=level,
            format="{message}",
            enqueue=True,  # Thread-safe logging
            catch=True,    # Prevent logger crashes
        )
    
    # Add JSON file handler
    if log_file:
        logger.add(
            LoguruJSONSink(open(log_file, "a")),
            level=level,
            format="{message}",
            rotation="100 MB",
            retention="7 days",
            compression="gz",
            enqueue=True,
            catch=True,
        )
    
    # Configure standard library logging to use JSON
    json_formatter = JSONFormatter()
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(json_formatter)
        logging.root.addHandler(console_handler)
    
    # File handler
    if log_file:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=7
        )
        file_handler.setFormatter(json_formatter)
        logging.root.addHandler(file_handler)
    
    # Set logging level
    logging.root.setLevel(getattr(logging, level))
    
    # Log startup
    logger.info(
        "VoiceReel JSON logging configured",
        extra={
            "level": level,
            "console": enable_console,
            "file": log_file,
            "debug": enable_debug,
        }
    )


def log_with_context(**context):
    """Add context to log messages.
    
    Example:
        log_with_context(user_id="123", action="synthesis")
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Add context to logger
            with logger.contextualize(**context):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def log_performance(operation: str):
    """Log performance metrics for an operation.
    
    Example:
        @log_performance("speaker_registration")
        def register_speaker(...):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                logger.info(
                    f"{operation} completed",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "status": "success",
                    }
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                
                logger.error(
                    f"{operation} failed",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "status": "error",
                        "error_type": type(e).__name__,
                    },
                    exc_info=True
                )
                
                raise
                
        return wrapper
    return decorator


class RequestLogger:
    """HTTP request/response logger."""
    
    @staticmethod
    def log_request(
        method: str,
        path: str,
        headers: Dict[str, str],
        body_size: Optional[int] = None,
        remote_addr: Optional[str] = None,
    ):
        """Log incoming HTTP request."""
        # Sanitize headers (remove sensitive data)
        safe_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ["authorization", "x-vr-apikey", "cookie"]
        }
        
        logger.info(
            f"HTTP Request: {method} {path}",
            extra={
                "http": {
                    "method": method,
                    "path": path,
                    "headers": safe_headers,
                    "body_size": body_size,
                    "remote_addr": remote_addr,
                    "direction": "request",
                }
            }
        )
    
    @staticmethod
    def log_response(
        status_code: int,
        duration_ms: float,
        body_size: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """Log HTTP response."""
        level = "INFO"
        if 400 <= status_code < 500:
            level = "WARNING"
        elif status_code >= 500:
            level = "ERROR"
        
        log_func = getattr(logger, level.lower())
        
        log_func(
            f"HTTP Response: {status_code}",
            extra={
                "http": {
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "body_size": body_size,
                    "error": error,
                    "direction": "response",
                }
            }
        )


class AuditLogger:
    """Audit logger for security-sensitive operations."""
    
    @staticmethod
    def log_authentication(
        success: bool,
        method: str,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        """Log authentication attempts."""
        logger.info(
            f"Authentication {'succeeded' if success else 'failed'}",
            extra={
                "audit": {
                    "type": "authentication",
                    "success": success,
                    "method": method,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "reason": reason,
                }
            }
        )
    
    @staticmethod
    def log_authorization(
        success: bool,
        resource: str,
        action: str,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        """Log authorization checks."""
        logger.info(
            f"Authorization {'granted' if success else 'denied'} for {action} on {resource}",
            extra={
                "audit": {
                    "type": "authorization", 
                    "success": success,
                    "resource": resource,
                    "action": action,
                    "user_id": user_id,
                    "reason": reason,
                }
            }
        )
    
    @staticmethod
    def log_data_access(
        resource_type: str,
        resource_id: str,
        action: str,
        user_id: Optional[str] = None,
    ):
        """Log data access for compliance."""
        logger.info(
            f"Data access: {action} {resource_type}/{resource_id}",
            extra={
                "audit": {
                    "type": "data_access",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "action": action,
                    "user_id": user_id,
                }
            }
        )


# Convenience functions
def get_logger(name: Optional[str] = None) -> logger:
    """Get a logger instance.
    
    Args:
        name: Logger name (optional)
        
    Returns:
        Configured logger instance
    """
    if name:
        return logger.bind(logger_name=name)
    return logger


# Export main components
__all__ = [
    "configure_json_logging",
    "get_logger",
    "log_with_context",
    "log_performance",
    "RequestLogger",
    "AuditLogger",
    "request_id",
    "user_id", 
    "api_key_id",
]