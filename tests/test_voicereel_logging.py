"""Tests for VoiceReel structured logging system."""

import json
import os
import tempfile
import time
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from loguru import logger

from voicereel.debug_config import DebugConfig, get_debug_config
from voicereel.error_responses import (
    APIError,
    ErrorCode,
    InvalidInputError,
    NotFoundError,
    handle_exception,
    validate_request_data,
)
from voicereel.json_logger import (
    AuditLogger,
    RequestLogger,
    api_key_id,
    configure_json_logging,
    log_performance,
    request_id,
    user_id,
)


class TestJSONLogger(unittest.TestCase):
    """Test JSON logging functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Capture log output
        self.log_output = StringIO()
        logger.remove()  # Remove default handlers
        
    def test_json_log_format(self):
        """Test JSON log output format."""
        # Configure JSON logging to StringIO
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
        
        # Log a test message
        logger.info("Test message", extra={"custom_field": "value"})
        
        # Parse output
        log_line = self.log_output.getvalue().strip()
        log_data = json.loads(log_line)
        
        # Verify structure
        assert "timestamp" in log_data
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert log_data["service"] == "voicereel-api"
        assert "source" in log_data
        assert log_data["extra"]["custom_field"] == "value"
    
    def test_context_variables(self):
        """Test context variable logging."""
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
        
        # Set context variables
        request_id.set("req-123")
        user_id.set("user-456")
        api_key_id.set("key-789")
        
        # Log message
        logger.info("Context test")
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify context
        assert log_data["request_id"] == "req-123"
        assert log_data["user_id"] == "user-456"
        assert log_data["api_key_id"] == "key-789"
        
        # Clear context
        request_id.set(None)
        user_id.set(None)
        api_key_id.set(None)
    
    def test_exception_logging(self):
        """Test exception logging in JSON format."""
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("Error occurred", exc_info=True)
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify exception info
        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert log_data["exception"]["message"] == "Test exception"
        assert isinstance(log_data["exception"]["traceback"], list)
    
    def test_performance_decorator(self):
        """Test performance logging decorator."""
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
        
        @log_performance("test_operation")
        def slow_function():
            time.sleep(0.1)
            return "result"
        
        # Call function
        result = slow_function()
        assert result == "result"
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify performance data
        assert "test_operation completed" in log_data["message"]
        assert log_data["extra"]["operation"] == "test_operation"
        assert log_data["extra"]["duration_ms"] >= 100
        assert log_data["extra"]["status"] == "success"


class TestRequestLogger(unittest.TestCase):
    """Test request/response logging."""
    
    def setUp(self):
        """Set up test environment."""
        self.log_output = StringIO()
        logger.remove()
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
    
    def test_request_logging(self):
        """Test HTTP request logging."""
        RequestLogger.log_request(
            method="POST",
            path="/v1/speakers",
            headers={
                "Content-Type": "application/json",
                "X-VR-APIKEY": "secret-key-12345",
                "User-Agent": "TestClient/1.0",
            },
            body_size=1024,
            remote_addr="192.168.1.100",
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify request data
        assert "HTTP Request: POST /v1/speakers" in log_data["message"]
        http_data = log_data["extra"]["http"]
        assert http_data["method"] == "POST"
        assert http_data["path"] == "/v1/speakers"
        assert http_data["body_size"] == 1024
        assert http_data["remote_addr"] == "192.168.1.100"
        
        # Verify sensitive headers are removed
        assert "X-VR-APIKEY" not in http_data["headers"]
        assert "User-Agent" in http_data["headers"]
    
    def test_response_logging(self):
        """Test HTTP response logging."""
        RequestLogger.log_response(
            status_code=201,
            duration_ms=156.78,
            body_size=2048,
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify response data
        assert "HTTP Response: 201" in log_data["message"]
        http_data = log_data["extra"]["http"]
        assert http_data["status_code"] == 201
        assert http_data["duration_ms"] == 156.78
        assert http_data["body_size"] == 2048
        assert http_data["direction"] == "response"
    
    def test_error_response_logging(self):
        """Test error response logging."""
        RequestLogger.log_response(
            status_code=500,
            duration_ms=10.5,
            error="Internal server error",
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify error level
        assert log_data["level"] == "ERROR"
        assert log_data["extra"]["http"]["error"] == "Internal server error"


class TestAuditLogger(unittest.TestCase):
    """Test audit logging functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.log_output = StringIO()
        logger.remove()
        from voicereel.json_logger import LoguruJSONSink
        json_sink = LoguruJSONSink(stream=self.log_output)
        logger.add(json_sink, format="{message}")
    
    def test_authentication_logging(self):
        """Test authentication audit logging."""
        AuditLogger.log_authentication(
            success=True,
            method="api_key",
            api_key_id="key-123",
            user_id="user-456",
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify audit data
        assert "Authentication succeeded" in log_data["message"]
        audit_data = log_data["extra"]["audit"]
        assert audit_data["type"] == "authentication"
        assert audit_data["success"] is True
        assert audit_data["method"] == "api_key"
        assert audit_data["api_key_id"] == "key-123"
    
    def test_authorization_logging(self):
        """Test authorization audit logging."""
        AuditLogger.log_authorization(
            success=False,
            resource="speaker",
            action="delete",
            user_id="user-789",
            reason="Insufficient permissions",
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify audit data
        assert "Authorization denied" in log_data["message"]
        audit_data = log_data["extra"]["audit"]
        assert audit_data["type"] == "authorization"
        assert audit_data["success"] is False
        assert audit_data["resource"] == "speaker"
        assert audit_data["action"] == "delete"
        assert audit_data["reason"] == "Insufficient permissions"
    
    def test_data_access_logging(self):
        """Test data access audit logging."""
        AuditLogger.log_data_access(
            resource_type="audio_file",
            resource_id="file-abc123",
            action="download",
            user_id="user-999",
        )
        
        # Parse output
        log_data = json.loads(self.log_output.getvalue().strip())
        
        # Verify audit data
        assert "Data access: download audio_file/file-abc123" in log_data["message"]
        audit_data = log_data["extra"]["audit"]
        assert audit_data["type"] == "data_access"
        assert audit_data["resource_type"] == "audio_file"
        assert audit_data["resource_id"] == "file-abc123"
        assert audit_data["action"] == "download"


class TestErrorResponses(unittest.TestCase):
    """Test standardized error responses."""
    
    def test_api_error_format(self):
        """Test API error response format."""
        error = InvalidInputError(
            "Missing required field: name",
            details={"field": "name", "type": "required"}
        )
        
        error_dict = error.to_dict()
        
        # Verify structure
        assert "error" in error_dict
        assert error_dict["error"]["code"] == "INVALID_INPUT"
        assert error_dict["error"]["message"] == "Missing required field: name"
        assert error_dict["error"]["status"] == 400
        assert error_dict["error"]["details"]["field"] == "name"
    
    def test_not_found_error(self):
        """Test not found error."""
        error = NotFoundError("speaker", "spk-123")
        
        error_dict = error.to_dict()
        
        assert error_dict["error"]["code"] == "NOT_FOUND"
        assert error_dict["error"]["status"] == 404
        assert "speaker not found: spk-123" in error_dict["error"]["message"]
        assert error_dict["error"]["details"]["resource_type"] == "speaker"
        assert error_dict["error"]["details"]["resource_id"] == "spk-123"
    
    def test_exception_handling(self):
        """Test exception handling."""
        # Test known API error
        api_error = InvalidInputError("Test error")
        error_dict, status = handle_exception(api_error)
        
        assert status == 400
        assert error_dict["error"]["code"] == "INVALID_INPUT"
        
        # Test unknown exception
        unknown_error = RuntimeError("Unexpected error")
        error_dict, status = handle_exception(unknown_error)
        
        assert status == 500
        assert error_dict["error"]["code"] == "INTERNAL_ERROR"
        
        # Test with traceback
        error_dict, status = handle_exception(unknown_error, include_traceback=True)
        assert "traceback" in error_dict["error"]["details"]
    
    def test_request_validation(self):
        """Test request data validation."""
        # Valid data
        data = {"name": "Test", "age": 25}
        validate_request_data(data, {"name": str, "age": int})
        
        # Missing required field
        with self.assertRaises(InvalidInputError) as cm:
            validate_request_data({}, {"name": str})
        
        error = cm.exception
        assert "validation_errors" in error.details
        assert "name" in error.details["validation_errors"]
        
        # Wrong type
        with self.assertRaises(InvalidInputError) as cm:
            validate_request_data({"age": "25"}, {"age": int})
        
        error = cm.exception
        assert "age" in error.details["validation_errors"]


class TestDebugConfig(unittest.TestCase):
    """Test debug configuration."""
    
    def setUp(self):
        """Set up test environment."""
        # Save original env vars
        self.original_env = os.environ.copy()
    
    def tearDown(self):
        """Restore environment."""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_debug_disabled(self):
        """Test debug mode disabled by default."""
        os.environ["VR_DEBUG"] = "false"
        config = DebugConfig()
        
        assert not config.enabled
        assert not config.is_feature_enabled("verbose_logging")
    
    def test_debug_enabled(self):
        """Test debug mode enabled."""
        os.environ["VR_DEBUG"] = "true"
        os.environ["VR_DEBUG_VERBOSE_LOGGING"] = "true"
        os.environ["VR_DEBUG_SQL_ECHO"] = "true"
        
        config = DebugConfig()
        
        assert config.enabled
        assert config.is_feature_enabled("verbose_logging")
        assert config.is_feature_enabled("sql_echo")
        assert not config.is_feature_enabled("disable_auth")
    
    def test_debug_config_application(self):
        """Test applying debug config to app."""
        os.environ["VR_DEBUG"] = "true"
        os.environ["VR_DEBUG_DISABLE_RATE_LIMITING"] = "true"
        
        config = DebugConfig()
        
        # Mock Flask app
        app = MagicMock()
        app.config = {}
        
        config.apply_to_app(app)
        
        assert app.debug is True
        assert app.config["RATELIMIT_ENABLED"] is False
    
    def test_debug_database_config(self):
        """Test applying debug config to database."""
        os.environ["VR_DEBUG"] = "true"
        os.environ["VR_DEBUG_SQL_ECHO"] = "true"
        
        config = DebugConfig()
        db_config = {}
        
        modified_config = config.apply_to_database(db_config)
        
        assert modified_config["echo"] is True
        assert modified_config["echo_pool"] is True


if __name__ == "__main__":
    unittest.main()