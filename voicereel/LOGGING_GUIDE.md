# VoiceReel Structured Logging Guide

This guide covers the structured JSON logging system implemented for VoiceReel production deployment.

## Overview

VoiceReel uses structured JSON logging for:
- **Centralized log aggregation** (ELK, Datadog, CloudWatch)
- **Request tracing** with unique request IDs
- **Performance monitoring** and profiling
- **Security auditing** for compliance
- **Debug mode** for development

## Configuration

### Environment Variables

```bash
# Logging configuration
VR_LOG_LEVEL=INFO              # Log level: DEBUG, INFO, WARNING, ERROR
VR_LOG_FILE=/var/log/voicereel/api.log  # Log file path (optional)
VR_LOG_CONSOLE=true            # Enable console logging
VR_DEBUG=false                 # Enable debug mode

# Debug mode features (when VR_DEBUG=true)
VR_DEBUG_VERBOSE_LOGGING=false      # Verbose debug logs
VR_DEBUG_SQL_ECHO=false            # Echo SQL queries
VR_DEBUG_REQUEST_BODY_LOGGING=false # Log request bodies (security risk!)
VR_DEBUG_TRACEBACK_IN_ERRORS=false # Include traceback in error responses
VR_DEBUG_DISABLE_RATE_LIMITING=false # Disable rate limiting
VR_DEBUG_PROFILE_REQUESTS=false    # Profile request performance
```

### Basic Usage

```python
from voicereel.json_logger import configure_json_logging, get_logger

# Configure logging on startup
configure_json_logging(
    level="INFO",
    log_file="/var/log/voicereel/api.log",
    enable_console=True,
    enable_debug=False
)

# Get logger instance
logger = get_logger("voicereel.module_name")

# Log with structured data
logger.info(
    "Speaker registered",
    extra={
        "speaker_id": "spk-123",
        "user_id": "user-456",
        "language": "ko",
        "duration_ms": 245.6
    }
)
```

## Log Format

All logs are output as single-line JSON:

```json
{
  "timestamp": "2025-06-03T10:15:30.123Z",
  "level": "INFO",
  "logger": "voicereel",
  "message": "Speaker registered",
  "service": "voicereel-api",
  "hostname": "api-server-1",
  "pid": 12345,
  "thread": 139865432,
  "thread_name": "MainThread",
  "request_id": "req-abc123",
  "user_id": "user-456",
  "api_key_id": "key-789...",
  "source": {
    "file": "/app/voicereel/handlers.py",
    "line": 156,
    "function": "register_speaker",
    "module": "handlers"
  },
  "extra": {
    "speaker_id": "spk-123",
    "language": "ko",
    "duration_ms": 245.6
  }
}
```

## Request/Response Logging

HTTP requests and responses are automatically logged:

### Request Log
```json
{
  "message": "HTTP Request: POST /v1/speakers",
  "extra": {
    "http": {
      "method": "POST",
      "path": "/v1/speakers",
      "headers": {
        "Content-Type": "application/json",
        "User-Agent": "VoiceReelClient/1.0"
      },
      "body_size": 2048,
      "remote_addr": "192.168.1.100",
      "direction": "request"
    }
  }
}
```

### Response Log
```json
{
  "message": "HTTP Response: 201",
  "extra": {
    "http": {
      "status_code": 201,
      "duration_ms": 156.78,
      "body_size": 512,
      "direction": "response"
    }
  }
}
```

## Error Handling

### Standardized Error Format

All API errors follow a consistent format:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Missing required field: name",
    "status": 400,
    "request_id": "req-abc123",
    "details": {
      "validation_errors": {
        "name": "Field is required",
        "age": "Expected int, got str"
      }
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_INPUT` | 400 | Invalid request parameters |
| `UNAUTHORIZED` | 401 | Authentication failed |
| `FORBIDDEN` | 403 | Access denied |
| `NOT_FOUND` | 404 | Resource not found |
| `PAYLOAD_TOO_LARGE` | 413 | Request body too large |
| `UNPROCESSABLE_ENTITY` | 422 | Business logic error |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

### Using Error Responses

```python
from voicereel.error_responses import (
    InvalidInputError,
    NotFoundError,
    validate_request_data
)

# Validate request data
try:
    validate_request_data(
        request_data,
        required_fields={"name": str, "language": str},
        optional_fields={"description": str}
    )
except InvalidInputError as e:
    # Automatically returns structured error response
    raise

# Raise specific errors
if not speaker:
    raise NotFoundError("speaker", speaker_id)
```

## Audit Logging

For security-sensitive operations:

```python
from voicereel.json_logger import AuditLogger

# Log authentication
AuditLogger.log_authentication(
    success=True,
    method="api_key",
    api_key_id="key-123",
    user_id="user-456"
)

# Log authorization
AuditLogger.log_authorization(
    success=False,
    resource="speaker",
    action="delete",
    user_id="user-456",
    reason="Not owner of speaker"
)

# Log data access (for compliance)
AuditLogger.log_data_access(
    resource_type="audio_file",
    resource_id="file-789",
    action="download",
    user_id="user-456"
)
```

## Performance Monitoring

### Automatic Performance Logging

```python
from voicereel.json_logger import log_performance

@log_performance("speaker_registration")
def register_speaker(audio_file, transcript):
    # Function execution time is automatically logged
    # Logs: "speaker_registration completed" with duration_ms
    pass
```

### Manual Performance Tracking

```python
import time
start_time = time.time()

# Do work...

duration_ms = (time.time() - start_time) * 1000
logger.info(
    "Audio synthesis completed",
    extra={
        "operation": "synthesis",
        "duration_ms": duration_ms,
        "audio_length_sec": 30,
        "speakers_count": 3
    }
)
```

## Debug Mode

### Enabling Debug Mode

```bash
# Enable debug mode
export VR_DEBUG=true

# Enable specific debug features
export VR_DEBUG_VERBOSE_LOGGING=true
export VR_DEBUG_SQL_ECHO=true
export VR_DEBUG_PROFILE_REQUESTS=true
```

### Debug Endpoints

When debug mode is enabled:

- `GET /_debug/config` - Show debug configuration
- `GET /_debug/health` - Detailed health check with CPU, memory, disk, GPU

### Debug Decorators

```python
from voicereel.debug_config import DebugDecorators

@DebugDecorators.profile_function
def expensive_operation():
    # Execution time logged in debug mode
    pass

@DebugDecorators.trace_calls
def critical_function(param1, param2):
    # Function calls traced with arguments in debug mode
    pass
```

## Integration with Logging Services

### ELK Stack

Configure Filebeat to ship logs:

```yaml
filebeat.inputs:
- type: log
  paths:
    - /var/log/voicereel/*.log
  json.keys_under_root: true
  json.add_error_key: true
  fields:
    service: voicereel
    environment: production
```

### CloudWatch Logs

Use CloudWatch agent with JSON parsing:

```json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/voicereel/api.log",
            "log_group_name": "/aws/voicereel/api",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC",
            "multi_line_start_pattern": "{",
            "encoding": "utf-8"
          }
        ]
      }
    }
  }
}
```

### Datadog

Configure Datadog agent:

```yaml
logs:
  - type: file
    path: /var/log/voicereel/api.log
    service: voicereel
    source: python
    sourcecategory: api
    tags:
      - env:production
      - app:voicereel
```

## Best Practices

1. **Always include context**: Add relevant IDs (speaker_id, job_id) to log extras
2. **Use appropriate log levels**:
   - DEBUG: Detailed diagnostic info
   - INFO: General operational events
   - WARNING: Recoverable issues
   - ERROR: Errors requiring attention
3. **Don't log sensitive data**: API keys, passwords, audio content
4. **Use structured extras**: Pass data as `extra` dict, not in message
5. **Include timing data**: Log duration_ms for operations
6. **Use request_id**: For tracing requests across services

## Example: Complete Request Flow

```python
# 1. Request arrives - middleware sets context
request_id.set("req-123")
api_key_id.set("key-789...")

# 2. Log request
RequestLogger.log_request("POST", "/v1/speakers", headers, body_size)

# 3. Authenticate
AuditLogger.log_authentication(True, "api_key", api_key_id="key-789")

# 4. Process with performance tracking
@log_performance("speaker_registration")
def register():
    # 5. Log business events
    logger.info("Processing speaker registration", 
                extra={"language": "ko", "audio_duration": 45.2})
    
    # 6. Handle errors
    try:
        validate_audio(audio)
    except Exception as e:
        logger.error("Audio validation failed", exc_info=True)
        raise InvalidInputError("Invalid audio format")
    
    # 7. Log data access
    AuditLogger.log_data_access("speaker", "spk-123", "create")
    
    return speaker_id

# 8. Log response
RequestLogger.log_response(201, duration_ms=156.78)
```

## Troubleshooting

### No logs appearing

1. Check environment variables are set correctly
2. Verify log file permissions
3. Check logger configuration is called on startup

### Performance impact

- Use `enqueue=True` for async logging
- Rotate logs regularly (100MB default)
- Disable debug features in production

### Missing request IDs

Ensure middleware is properly applied:

```python
from voicereel.logging_middleware import create_logged_handler
handler_class = create_logged_handler(BaseHandler)
```

### Debug logs in production

Always check `VR_DEBUG=false` in production to avoid:
- Performance overhead
- Security risks (request body logging)
- Excessive log volume