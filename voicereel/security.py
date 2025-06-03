"""Security middleware and utilities for VoiceReel."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Import logger conditionally
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiting middleware with sliding window algorithm."""
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        cleanup_interval: int = 300,  # 5 minutes
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.cleanup_interval = cleanup_interval
        
        # Store request timestamps per IP
        self.requests_by_ip: Dict[str, deque] = defaultdict(deque)
        self.last_cleanup = time.time()
    
    def is_allowed(self, client_ip: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed for given IP.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            Tuple of (allowed, info_dict)
        """
        now = time.time()
        
        # Cleanup old entries periodically
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries(now)
            self.last_cleanup = now
        
        # Get request history for this IP
        ip_requests = self.requests_by_ip[client_ip]
        
        # Count requests in the last minute and hour
        minute_ago = now - 60
        hour_ago = now - 3600
        
        minute_count = sum(1 for req_time in ip_requests if req_time > minute_ago)
        hour_count = sum(1 for req_time in ip_requests if req_time > hour_ago)
        
        # Check limits
        if minute_count >= self.requests_per_minute:
            return False, {
                "error": "RATE_LIMIT_EXCEEDED",
                "limit_type": "per_minute",
                "limit": self.requests_per_minute,
                "current": minute_count,
                "reset_time": int(minute_ago + 60),
            }
        
        if hour_count >= self.requests_per_hour:
            return False, {
                "error": "RATE_LIMIT_EXCEEDED", 
                "limit_type": "per_hour",
                "limit": self.requests_per_hour,
                "current": hour_count,
                "reset_time": int(hour_ago + 3600),
            }
        
        # Record this request
        ip_requests.append(now)
        
        # Keep only last hour of requests for efficiency
        while ip_requests and ip_requests[0] <= hour_ago:
            ip_requests.popleft()
        
        return True, {
            "requests_remaining_minute": self.requests_per_minute - minute_count - 1,
            "requests_remaining_hour": self.requests_per_hour - hour_count - 1,
        }
    
    def _cleanup_old_entries(self, now: float) -> None:
        """Remove old request entries to prevent memory bloat."""
        hour_ago = now - 3600
        
        for ip, requests in list(self.requests_by_ip.items()):
            # Remove requests older than an hour
            while requests and requests[0] <= hour_ago:
                requests.popleft()
            
            # Remove IPs with no recent requests
            if not requests:
                del self.requests_by_ip[ip]
        
        logger.debug(f"Rate limiter cleanup: {len(self.requests_by_ip)} active IPs")


class CORSHandler:
    """CORS policy handler for VoiceReel API."""
    
    def __init__(
        self,
        allowed_origins: Optional[List[str]] = None,
        allowed_methods: Optional[List[str]] = None,
        allowed_headers: Optional[List[str]] = None,
        max_age: int = 86400,  # 24 hours
        allow_credentials: bool = True,
    ):
        self.allowed_origins = set(allowed_origins or ["*"])
        self.allowed_methods = allowed_methods or ["GET", "POST", "DELETE", "OPTIONS"]
        self.allowed_headers = allowed_headers or [
            "Content-Type", 
            "Authorization", 
            "X-VR-APIKEY", 
            "X-VR-SIGN",
            "X-Requested-With",
        ]
        self.max_age = max_age
        self.allow_credentials = allow_credentials
    
    def handle_preflight(self, handler: BaseHTTPRequestHandler) -> bool:
        """
        Handle CORS preflight request.
        
        Args:
            handler: HTTP request handler
            
        Returns:
            True if this was a preflight request, False otherwise
        """
        if handler.command != "OPTIONS":
            return False
        
        origin = handler.headers.get("Origin")
        if not self._is_origin_allowed(origin):
            handler.send_response(403)
            handler.end_headers()
            return True
        
        # Send CORS preflight response
        handler.send_response(200)
        self._add_cors_headers(handler, origin)
        
        # Add preflight-specific headers
        if "Access-Control-Request-Method" in handler.headers:
            method = handler.headers["Access-Control-Request-Method"]
            if method in self.allowed_methods:
                handler.send_header("Access-Control-Allow-Methods", ", ".join(self.allowed_methods))
        
        if "Access-Control-Request-Headers" in handler.headers:
            handler.send_header("Access-Control-Allow-Headers", ", ".join(self.allowed_headers))
        
        handler.send_header("Access-Control-Max-Age", str(self.max_age))
        handler.end_headers()
        return True
    
    def add_cors_headers(self, handler: BaseHTTPRequestHandler) -> None:
        """Add CORS headers to response."""
        origin = handler.headers.get("Origin")
        if self._is_origin_allowed(origin):
            self._add_cors_headers(handler, origin)
    
    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if origin is allowed."""
        if not origin:
            return True  # Allow same-origin requests
        
        if "*" in self.allowed_origins:
            return True
        
        return origin in self.allowed_origins
    
    def _add_cors_headers(self, handler: BaseHTTPRequestHandler, origin: Optional[str]) -> None:
        """Add CORS headers to handler."""
        if origin and "*" in self.allowed_origins:
            handler.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in self.allowed_origins:
            handler.send_header("Access-Control-Allow-Origin", origin)
        
        if self.allow_credentials:
            handler.send_header("Access-Control-Allow-Credentials", "true")


class InputValidator:
    """Input validation utilities for VoiceReel API."""
    
    # Dangerous patterns that could indicate injection attempts
    SQL_INJECTION_PATTERNS = [
        r"(\b(union|select|insert|update|delete|drop|create|alter)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(or|and)\s+\d+\s*=\s*\d+)",
        r"(\b(true|false)\b)",
        r"(\'|\"|`)",
    ]
    
    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
    ]
    
    def __init__(self):
        self.sql_regex = re.compile("|".join(self.SQL_INJECTION_PATTERNS), re.IGNORECASE)
        self.xss_regex = re.compile("|".join(self.XSS_PATTERNS), re.IGNORECASE)
    
    def validate_speaker_name(self, name: str) -> Tuple[bool, str]:
        """Validate speaker name."""
        if not name or not isinstance(name, str):
            return False, "Speaker name is required"
        
        name = name.strip()
        if len(name) < 1 or len(name) > 100:
            return False, "Speaker name must be 1-100 characters"
        
        if self.xss_regex.search(name):
            return False, "Speaker name contains invalid characters"
        
        # Allow letters, numbers, spaces, and common punctuation
        if not re.match(r"^[a-zA-Z0-9\s\-_\.\'\"]+$", name):
            return False, "Speaker name contains invalid characters"
        
        return True, ""
    
    def validate_language_code(self, lang: str) -> Tuple[bool, str]:
        """Validate language code."""
        if not lang or not isinstance(lang, str):
            return False, "Language code is required"
        
        allowed_langs = {"en", "ko", "ja", "zh", "de", "fr", "es", "it", "ru", "pt"}
        if lang not in allowed_langs:
            return False, f"Unsupported language. Allowed: {', '.join(sorted(allowed_langs))}"
        
        return True, ""
    
    def validate_script_text(self, text: str) -> Tuple[bool, str]:
        """Validate script text."""
        if not text or not isinstance(text, str):
            return False, "Script text is required"
        
        text = text.strip()
        if len(text) < 1:
            return False, "Script text cannot be empty"
        
        if len(text) > 10000:  # 10KB limit
            return False, "Script text too long (max 10,000 characters)"
        
        # Check for potential XSS
        if self.xss_regex.search(text):
            return False, "Script text contains potentially dangerous content"
        
        return True, ""
    
    def validate_synthesis_script(self, script: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Validate synthesis script."""
        if not script or not isinstance(script, list):
            return False, "Script must be a non-empty list"
        
        if len(script) > 1000:  # Reasonable limit
            return False, "Script too long (max 1,000 segments)"
        
        for i, segment in enumerate(script):
            if not isinstance(segment, dict):
                return False, f"Segment {i} must be an object"
            
            # Validate speaker_id
            speaker_id = segment.get("speaker_id")
            if not speaker_id:
                return False, f"Segment {i} missing speaker_id"
            
            # Validate text
            text = segment.get("text", "")
            is_valid, error = self.validate_script_text(text)
            if not is_valid:
                return False, f"Segment {i}: {error}"
        
        return True, ""
    
    def validate_output_format(self, format_str: str) -> Tuple[bool, str]:
        """Validate output format."""
        if not format_str or not isinstance(format_str, str):
            return False, "Output format is required"
        
        allowed_formats = {"wav", "mp3", "flac", "ogg"}
        if format_str.lower() not in allowed_formats:
            return False, f"Unsupported format. Allowed: {', '.join(sorted(allowed_formats))}"
        
        return True, ""
    
    def validate_sample_rate(self, sample_rate: int) -> Tuple[bool, str]:
        """Validate sample rate."""
        if not isinstance(sample_rate, int):
            return False, "Sample rate must be an integer"
        
        allowed_rates = {8000, 16000, 22050, 24000, 44100, 48000, 96000}
        if sample_rate not in allowed_rates:
            return False, f"Unsupported sample rate. Allowed: {', '.join(map(str, sorted(allowed_rates)))}"
        
        return True, ""
    
    def check_sql_injection(self, text: str) -> bool:
        """Check if text contains potential SQL injection."""
        if not text:
            return False
        return bool(self.sql_regex.search(text))
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        if not filename:
            return "unknown"
        
        # Remove path components
        filename = filename.split("/")[-1].split("\\")[-1]
        
        # Remove dangerous characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_len = 255 - len(ext) - 1 if ext else 255
            filename = name[:max_name_len] + ('.' + ext if ext else '')
        
        return filename or "unknown"


class SecurityHeaders:
    """Security headers for HTTP responses."""
    
    @staticmethod
    def add_security_headers(handler: BaseHTTPRequestHandler) -> None:
        """Add security headers to HTTP response."""
        # Prevent clickjacking
        handler.send_header("X-Frame-Options", "DENY")
        
        # Prevent MIME type sniffing
        handler.send_header("X-Content-Type-Options", "nosniff")
        
        # XSS protection
        handler.send_header("X-XSS-Protection", "1; mode=block")
        
        # Referrer policy
        handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        
        # Content Security Policy (restrictive for API)
        handler.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        
        # HSTS (only if HTTPS)
        # handler.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


class APIKeyValidator:
    """Enhanced API key validation."""
    
    def __init__(self, api_key: Optional[str] = None, hmac_secret: Optional[str] = None):
        self.api_key = api_key
        self.hmac_secret = hmac_secret
        
        # Track failed authentication attempts
        self.failed_attempts: Dict[str, List[float]] = defaultdict(list)
        self.lockout_duration = 300  # 5 minutes
        self.max_attempts = 5
    
    def validate_request(
        self, 
        handler: BaseHTTPRequestHandler, 
        body: bytes = b"",
        client_ip: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate API key and HMAC signature.
        
        Args:
            handler: HTTP request handler
            body: Request body for HMAC validation
            client_ip: Client IP address
            
        Returns:
            Tuple of (is_valid, error_info)
        """
        client_ip = client_ip or handler.client_address[0]
        
        # Check if IP is locked out
        if self._is_ip_locked_out(client_ip):
            return False, {
                "error": "TOO_MANY_FAILED_ATTEMPTS",
                "message": "IP temporarily locked due to too many failed authentication attempts",
                "retry_after": self.lockout_duration,
            }
        
        # Skip validation if no API key is configured
        if not self.api_key:
            return True, None
        
        # Check API key
        provided_key = handler.headers.get("X-VR-APIKEY")
        if provided_key != self.api_key:
            self._record_failed_attempt(client_ip)
            return False, {"error": "INVALID_API_KEY"}
        
        # Check HMAC signature if configured
        if self.hmac_secret:
            provided_signature = handler.headers.get("X-VR-SIGN")
            if not provided_signature:
                self._record_failed_attempt(client_ip)
                return False, {"error": "MISSING_SIGNATURE"}
            
            expected_signature = hmac.new(
                self.hmac_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            if provided_signature != expected_signature:
                self._record_failed_attempt(client_ip)
                return False, {"error": "INVALID_SIGNATURE"}
        
        # Authentication successful
        return True, None
    
    def _is_ip_locked_out(self, ip: str) -> bool:
        """Check if IP is currently locked out."""
        now = time.time()
        failed_attempts = self.failed_attempts.get(ip, [])
        
        # Clean old attempts
        recent_attempts = [t for t in failed_attempts if now - t < self.lockout_duration]
        self.failed_attempts[ip] = recent_attempts
        
        return len(recent_attempts) >= self.max_attempts
    
    def _record_failed_attempt(self, ip: str) -> None:
        """Record a failed authentication attempt."""
        now = time.time()
        self.failed_attempts[ip].append(now)
        
        # Keep only recent attempts
        self.failed_attempts[ip] = [
            t for t in self.failed_attempts[ip] 
            if now - t < self.lockout_duration
        ]


def get_client_ip(handler: BaseHTTPRequestHandler) -> str:
    """Extract client IP address, handling proxies."""
    # Check for forwarded headers (be careful in production)
    forwarded_for = handler.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (closest to client)
        return forwarded_for.split(",")[0].strip()
    
    real_ip = handler.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct connection
    return handler.client_address[0]


class SecurityMiddleware:
    """Combined security middleware for VoiceReel."""
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        cors_handler: Optional[CORSHandler] = None,
        input_validator: Optional[InputValidator] = None,
        api_key_validator: Optional[APIKeyValidator] = None,
    ):
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cors_handler = cors_handler or CORSHandler()
        self.input_validator = input_validator or InputValidator()
        self.api_key_validator = api_key_validator or APIKeyValidator()
    
    def process_request(
        self, 
        handler: BaseHTTPRequestHandler, 
        body: bytes = b""
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Process incoming request through security middleware.
        
        Args:
            handler: HTTP request handler
            body: Request body
            
        Returns:
            Tuple of (should_continue, error_response)
        """
        client_ip = get_client_ip(handler)
        
        # Handle CORS preflight
        if self.cors_handler.handle_preflight(handler):
            return False, None  # Request handled
        
        # Check rate limiting
        allowed, rate_info = self.rate_limiter.is_allowed(client_ip)
        if not allowed:
            return False, rate_info
        
        # Validate API key and signature
        auth_valid, auth_error = self.api_key_validator.validate_request(
            handler, body, client_ip
        )
        if not auth_valid:
            return False, auth_error
        
        return True, None
    
    def add_response_headers(self, handler: BaseHTTPRequestHandler) -> None:
        """Add security headers to response."""
        SecurityHeaders.add_security_headers(handler)
        self.cors_handler.add_cors_headers(handler)