"""Tests for VoiceReel security enhancements."""

import json
import time
from unittest.mock import patch

import pytest

from voicereel.security import (
    RateLimiter,
    CORSHandler,
    InputValidator,
    APIKeyValidator,
    SecurityMiddleware,
    get_client_ip,
)


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        limiter = RateLimiter(requests_per_minute=2, requests_per_hour=5)
        
        # First request should be allowed
        allowed, info = limiter.is_allowed("192.168.1.1")
        assert allowed is True
        assert info["requests_remaining_minute"] == 1
        assert info["requests_remaining_hour"] == 4
        
        # Second request should be allowed
        allowed, info = limiter.is_allowed("192.168.1.1")
        assert allowed is True
        assert info["requests_remaining_minute"] == 0
        assert info["requests_remaining_hour"] == 3
        
        # Third request should be blocked (exceeds per-minute limit)
        allowed, info = limiter.is_allowed("192.168.1.1")
        assert allowed is False
        assert info["error"] == "RATE_LIMIT_EXCEEDED"
        assert info["limit_type"] == "per_minute"
    
    def test_different_ips(self):
        """Test that different IPs have separate limits."""
        limiter = RateLimiter(requests_per_minute=1, requests_per_hour=2)
        
        # First IP
        allowed, _ = limiter.is_allowed("192.168.1.1")
        assert allowed is True
        
        # Second IP should still be allowed
        allowed, _ = limiter.is_allowed("192.168.1.2")
        assert allowed is True
        
        # First IP should be blocked
        allowed, _ = limiter.is_allowed("192.168.1.1")
        assert allowed is False
    
    def test_cleanup(self):
        """Test that old entries are cleaned up."""
        limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20, cleanup_interval=0)
        
        # Make some requests
        limiter.is_allowed("192.168.1.1")
        limiter.is_allowed("192.168.1.2")
        
        assert len(limiter.requests_by_ip) == 2
        
        # Force cleanup with future time
        with patch('time.time', return_value=time.time() + 7200):  # 2 hours later
            limiter._cleanup_old_entries(time.time() + 7200)
        
        assert len(limiter.requests_by_ip) == 0


class TestInputValidator:
    """Test input validation functionality."""
    
    def test_speaker_name_validation(self):
        """Test speaker name validation."""
        validator = InputValidator()
        
        # Valid names
        assert validator.validate_speaker_name("John Doe")[0] is True
        assert validator.validate_speaker_name("Alice-123")[0] is True
        assert validator.validate_speaker_name("Speaker_1")[0] is True
        
        # Invalid names
        assert validator.validate_speaker_name("")[0] is False
        assert validator.validate_speaker_name(None)[0] is False
        assert validator.validate_speaker_name("a" * 101)[0] is False  # Too long
        assert validator.validate_speaker_name("<script>alert('xss')</script>")[0] is False
        assert validator.validate_speaker_name("user@domain.com")[0] is False  # Invalid chars
    
    def test_language_validation(self):
        """Test language code validation."""
        validator = InputValidator()
        
        # Valid languages
        assert validator.validate_language_code("en")[0] is True
        assert validator.validate_language_code("ko")[0] is True
        assert validator.validate_language_code("ja")[0] is True
        
        # Invalid languages
        assert validator.validate_language_code("")[0] is False
        assert validator.validate_language_code("invalid")[0] is False
        assert validator.validate_language_code(None)[0] is False
    
    def test_script_validation(self):
        """Test script text validation."""
        validator = InputValidator()
        
        # Valid scripts
        assert validator.validate_script_text("Hello world")[0] is True
        assert validator.validate_script_text("안녕하세요")[0] is True
        
        # Invalid scripts
        assert validator.validate_script_text("")[0] is False
        assert validator.validate_script_text(None)[0] is False
        assert validator.validate_script_text("a" * 10001)[0] is False  # Too long
        assert validator.validate_script_text("<script>alert('xss')</script>")[0] is False
    
    def test_synthesis_script_validation(self):
        """Test synthesis script validation."""
        validator = InputValidator()
        
        # Valid script
        valid_script = [
            {"speaker_id": "spk_1", "text": "Hello"},
            {"speaker_id": "spk_2", "text": "World"},
        ]
        assert validator.validate_synthesis_script(valid_script)[0] is True
        
        # Invalid scripts
        assert validator.validate_synthesis_script([])[0] is False  # Empty
        assert validator.validate_synthesis_script(None)[0] is False
        assert validator.validate_synthesis_script("not a list")[0] is False
        
        # Missing speaker_id
        invalid_script = [{"text": "Hello"}]
        assert validator.validate_synthesis_script(invalid_script)[0] is False
        
        # XSS in text
        xss_script = [{"speaker_id": "spk_1", "text": "<script>alert('xss')</script>"}]
        assert validator.validate_synthesis_script(xss_script)[0] is False
    
    def test_output_format_validation(self):
        """Test output format validation."""
        validator = InputValidator()
        
        # Valid formats
        assert validator.validate_output_format("wav")[0] is True
        assert validator.validate_output_format("mp3")[0] is True
        assert validator.validate_output_format("flac")[0] is True
        
        # Invalid formats
        assert validator.validate_output_format("")[0] is False
        assert validator.validate_output_format("exe")[0] is False
        assert validator.validate_output_format(None)[0] is False
    
    def test_sample_rate_validation(self):
        """Test sample rate validation."""
        validator = InputValidator()
        
        # Valid rates
        assert validator.validate_sample_rate(44100)[0] is True
        assert validator.validate_sample_rate(48000)[0] is True
        
        # Invalid rates
        assert validator.validate_sample_rate("44100")[0] is False  # String
        assert validator.validate_sample_rate(12345)[0] is False  # Unsupported rate
    
    def test_sql_injection_detection(self):
        """Test SQL injection detection."""
        validator = InputValidator()
        
        # Safe text
        assert validator.check_sql_injection("Hello world") is False
        
        # Potential SQL injection
        assert validator.check_sql_injection("1' OR '1'='1") is True
        assert validator.check_sql_injection("'; DROP TABLE users; --") is True
        assert validator.check_sql_injection("UNION SELECT * FROM passwords") is True
    
    def test_filename_sanitization(self):
        """Test filename sanitization."""
        validator = InputValidator()
        
        # Safe filename
        assert validator.sanitize_filename("document.txt") == "document.txt"
        
        # Dangerous filename
        assert validator.sanitize_filename("../../../etc/passwd") == "passwd"
        assert validator.sanitize_filename("file<>:\"/\\|?*.txt") == "file_________.txt"
        
        # Long filename
        long_name = "a" * 300 + ".txt"
        sanitized = validator.sanitize_filename(long_name)
        assert len(sanitized) <= 255


class TestAPIKeyValidator:
    """Test API key validation."""
    
    def test_no_api_key_configured(self):
        """Test when no API key is configured."""
        validator = APIKeyValidator()
        
        class MockHandler:
            def __init__(self):
                self.headers = {}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        valid, error = validator.validate_request(handler, b"test")
        assert valid is True
        assert error is None
    
    def test_valid_api_key(self):
        """Test with valid API key."""
        validator = APIKeyValidator(api_key="secret123")
        
        class MockHandler:
            def __init__(self):
                self.headers = {"X-VR-APIKEY": "secret123"}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        valid, error = validator.validate_request(handler, b"test")
        assert valid is True
        assert error is None
    
    def test_invalid_api_key(self):
        """Test with invalid API key."""
        validator = APIKeyValidator(api_key="secret123")
        
        class MockHandler:
            def __init__(self):
                self.headers = {"X-VR-APIKEY": "wrong"}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        valid, error = validator.validate_request(handler, b"test")
        assert valid is False
        assert error["error"] == "INVALID_API_KEY"
    
    def test_hmac_validation(self):
        """Test HMAC signature validation."""
        import hashlib
        import hmac
        
        validator = APIKeyValidator(api_key="secret123", hmac_secret="hmac_secret")
        body = b"test message"
        signature = hmac.new(b"hmac_secret", body, hashlib.sha256).hexdigest()
        
        class MockHandler:
            def __init__(self):
                self.headers = {
                    "X-VR-APIKEY": "secret123",
                    "X-VR-SIGN": signature,
                }
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        valid, error = validator.validate_request(handler, body)
        assert valid is True
        assert error is None
    
    def test_rate_limiting_failed_attempts(self):
        """Test rate limiting of failed authentication attempts."""
        validator = APIKeyValidator(api_key="secret123", max_attempts=2, lockout_duration=10)
        
        class MockHandler:
            def __init__(self):
                self.headers = {"X-VR-APIKEY": "wrong"}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        
        # First failed attempt
        valid, error = validator.validate_request(handler, b"test", "127.0.0.1")
        assert valid is False
        
        # Second failed attempt
        valid, error = validator.validate_request(handler, b"test", "127.0.0.1")
        assert valid is False
        
        # Third attempt should be locked out
        valid, error = validator.validate_request(handler, b"test", "127.0.0.1")
        assert valid is False
        assert error["error"] == "TOO_MANY_FAILED_ATTEMPTS"


class TestCORSHandler:
    """Test CORS handling."""
    
    def test_preflight_handling(self):
        """Test CORS preflight request handling."""
        cors = CORSHandler(allowed_origins=["https://example.com"])
        
        class MockHandler:
            def __init__(self):
                self.command = "OPTIONS"
                self.headers = {"Origin": "https://example.com"}
                self.response_sent = False
                self.headers_sent = {}
            
            def send_response(self, code):
                self.response_code = code
            
            def send_header(self, name, value):
                self.headers_sent[name] = value
            
            def end_headers(self):
                self.headers_ended = True
        
        handler = MockHandler()
        is_preflight = cors.handle_preflight(handler)
        assert is_preflight is True
        assert handler.response_code == 200
        assert "Access-Control-Allow-Origin" in handler.headers_sent
    
    def test_origin_validation(self):
        """Test origin validation."""
        cors = CORSHandler(allowed_origins=["https://example.com"])
        
        # Valid origin
        assert cors._is_origin_allowed("https://example.com") is True
        
        # Invalid origin
        assert cors._is_origin_allowed("https://evil.com") is False
        
        # Wildcard
        cors_wildcard = CORSHandler(allowed_origins=["*"])
        assert cors_wildcard._is_origin_allowed("https://anything.com") is True


class TestSecurityMiddleware:
    """Test the combined security middleware."""
    
    def test_request_processing(self):
        """Test full request processing."""
        middleware = SecurityMiddleware()
        
        class MockHandler:
            def __init__(self):
                self.command = "POST"
                self.headers = {}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        should_continue, error = middleware.process_request(handler, b"test")
        assert should_continue is True
        assert error is None
    
    def test_rate_limit_blocking(self):
        """Test that rate limiting blocks requests."""
        # Create strict rate limiter
        rate_limiter = RateLimiter(requests_per_minute=1, requests_per_hour=1)
        middleware = SecurityMiddleware(rate_limiter=rate_limiter)
        
        class MockHandler:
            def __init__(self):
                self.command = "POST"
                self.headers = {}
                self.client_address = ("127.0.0.1", 12345)
        
        handler = MockHandler()
        
        # First request should pass
        should_continue, error = middleware.process_request(handler, b"test")
        assert should_continue is True
        
        # Second request should be blocked
        should_continue, error = middleware.process_request(handler, b"test")
        assert should_continue is False
        assert error["error"] == "RATE_LIMIT_EXCEEDED"


def test_get_client_ip():
    """Test client IP extraction."""
    class MockHandler:
        def __init__(self, headers=None):
            self.headers = headers or {}
            self.client_address = ("192.168.1.1", 12345)
    
    # Direct connection
    handler = MockHandler()
    assert get_client_ip(handler) == "192.168.1.1"
    
    # X-Forwarded-For header
    handler = MockHandler({"X-Forwarded-For": "203.0.113.1, 192.168.1.1"})
    assert get_client_ip(handler) == "203.0.113.1"
    
    # X-Real-IP header
    handler = MockHandler({"X-Real-IP": "203.0.113.2"})
    assert get_client_ip(handler) == "203.0.113.2"


if __name__ == "__main__":
    pytest.main([__file__])