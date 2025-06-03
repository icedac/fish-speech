"""Standardized error responses for VoiceReel API."""

import json
import traceback
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from .json_logger import request_id


class ErrorCode(Enum):
    """Standard error codes for VoiceReel API."""
    
    # Client errors (4xx)
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNPROCESSABLE_ENTITY = "UNPROCESSABLE_ENTITY"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # Specific validation errors
    INSUFFICIENT_REF = "INSUFFICIENT_REFERENCE_AUDIO"
    INVALID_SPEAKER_ID = "INVALID_SPEAKER_ID"
    INVALID_JOB_ID = "INVALID_JOB_ID"
    INVALID_AUDIO_FORMAT = "INVALID_AUDIO_FORMAT"
    INVALID_API_KEY = "INVALID_API_KEY"
    
    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    
    # Business logic errors
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    SPEAKER_LIMIT_REACHED = "SPEAKER_LIMIT_REACHED"
    CONCURRENT_JOB_LIMIT = "CONCURRENT_JOB_LIMIT"


class APIError(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize API error.
        
        Args:
            status_code: HTTP status code
            error_code: Error code enum
            message: Human-readable error message
            details: Additional error details
        """
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON response."""
        error_dict = {
            "error": {
                "code": self.error_code.value,
                "message": self.message,
                "status": self.status_code,
            }
        }
        
        # Add request ID if available
        if req_id := request_id.get():
            error_dict["error"]["request_id"] = req_id
        
        # Add details if present
        if self.details:
            error_dict["error"]["details"] = self.details
        
        return error_dict
    
    def to_json(self) -> str:
        """Convert error to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


# Predefined error classes
class InvalidInputError(APIError):
    """400 Bad Request - Invalid input parameters."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(400, ErrorCode.INVALID_INPUT, message, details)


class UnauthorizedError(APIError):
    """401 Unauthorized - Authentication failed."""
    
    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(401, ErrorCode.UNAUTHORIZED, message, details)


class ForbiddenError(APIError):
    """403 Forbidden - Access denied."""
    
    def __init__(self, message: str = "Access denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(403, ErrorCode.FORBIDDEN, message, details)


class NotFoundError(APIError):
    """404 Not Found - Resource not found."""
    
    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} not found: {resource_id}"
        details = {
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        super().__init__(404, ErrorCode.NOT_FOUND, message, details)


class PayloadTooLargeError(APIError):
    """413 Payload Too Large - Request body too large."""
    
    def __init__(self, max_size: int, actual_size: int):
        message = f"Payload size {actual_size} bytes exceeds maximum {max_size} bytes"
        details = {
            "max_size": max_size,
            "actual_size": actual_size,
        }
        super().__init__(413, ErrorCode.PAYLOAD_TOO_LARGE, message, details)


class UnprocessableEntityError(APIError):
    """422 Unprocessable Entity - Business logic error."""
    
    def __init__(self, error_code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(422, error_code, message, details)


class RateLimitError(APIError):
    """429 Too Many Requests - Rate limit exceeded."""
    
    def __init__(self, limit: int, window: str, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded: {limit} requests per {window}"
        details = {
            "limit": limit,
            "window": window,
        }
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(429, ErrorCode.RATE_LIMIT_EXCEEDED, message, details)


class InternalServerError(APIError):
    """500 Internal Server Error."""
    
    def __init__(self, message: str = "An unexpected error occurred", details: Optional[Dict[str, Any]] = None):
        super().__init__(500, ErrorCode.INTERNAL_ERROR, message, details)


class ServiceUnavailableError(APIError):
    """503 Service Unavailable."""
    
    def __init__(self, message: str = "Service temporarily unavailable", retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(503, ErrorCode.SERVICE_UNAVAILABLE, message, details)


def create_error_response(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create standardized error response.
    
    Args:
        status_code: HTTP status code
        error_code: Error code enum
        message: Error message
        details: Additional error details
        
    Returns:
        Error response dictionary
    """
    error = APIError(status_code, error_code, message, details)
    return error.to_dict()


def handle_exception(
    exception: Exception,
    include_traceback: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Handle exception and return error response.
    
    Args:
        exception: The exception to handle
        include_traceback: Include traceback in response (debug mode)
        
    Returns:
        Tuple of (error_dict, status_code)
    """
    # Handle known API errors
    if isinstance(exception, APIError):
        return exception.to_dict(), exception.status_code
    
    # Log unexpected exceptions
    logger.error(
        f"Unhandled exception: {type(exception).__name__}",
        exc_info=True,
        extra={
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
        }
    )
    
    # Create generic error response
    error = InternalServerError()
    error_dict = error.to_dict()
    
    # Add traceback in debug mode
    if include_traceback:
        if "details" not in error_dict["error"]:
            error_dict["error"]["details"] = {}
        error_dict["error"]["details"]["traceback"] = traceback.format_exc().split("\n")
    
    return error_dict, 500


class ErrorHandlerMixin:
    """Mixin for HTTP handlers to add error handling."""
    
    def send_error_response(self, error: APIError):
        """Send standardized error response.
        
        Args:
            error: APIError instance
        """
        # Log error
        logger.warning(
            f"API Error: {error.error_code.value}",
            extra={
                "error_code": error.error_code.value,
                "status_code": error.status_code,
                "message": error.message,
                "details": error.details,
            }
        )
        
        # Send response
        self.send_response(error.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(error.to_json().encode())
    
    def handle_api_error(self, func):
        """Decorator to handle API errors.
        
        Args:
            func: Function to wrap
            
        Returns:
            Wrapped function
        """
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except APIError as e:
                self.send_error_response(e)
            except Exception as e:
                # Log unexpected error
                logger.error(
                    f"Unhandled exception in {func.__name__}",
                    exc_info=True
                )
                
                # Send generic error
                error = InternalServerError()
                self.send_error_response(error)
        
        return wrapper


def validate_request_data(
    data: Dict[str, Any],
    required_fields: Dict[str, type],
    optional_fields: Optional[Dict[str, type]] = None,
) -> None:
    """Validate request data against schema.
    
    Args:
        data: Request data dictionary
        required_fields: Required fields with expected types
        optional_fields: Optional fields with expected types
        
    Raises:
        InvalidInputError: If validation fails
    """
    errors = {}
    
    # Check required fields
    for field, expected_type in required_fields.items():
        if field not in data:
            errors[field] = "Field is required"
        elif not isinstance(data[field], expected_type):
            errors[field] = f"Expected {expected_type.__name__}, got {type(data[field]).__name__}"
    
    # Check optional fields
    if optional_fields:
        for field, expected_type in optional_fields.items():
            if field in data and not isinstance(data[field], expected_type):
                errors[field] = f"Expected {expected_type.__name__}, got {type(data[field]).__name__}"
    
    # Raise error if validation failed
    if errors:
        raise InvalidInputError("Request validation failed", {"validation_errors": errors})


# Export error handling components
__all__ = [
    "ErrorCode",
    "APIError",
    "InvalidInputError",
    "UnauthorizedError", 
    "ForbiddenError",
    "NotFoundError",
    "PayloadTooLargeError",
    "UnprocessableEntityError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "create_error_response",
    "handle_exception",
    "ErrorHandlerMixin",
    "validate_request_data",
]