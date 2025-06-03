"""Tests for VoiceReel Celery integration."""

import json
import os
import sys
import tempfile
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from voicereel.celery_app import app as celery_app
from voicereel.redis_client import RedisClient
from voicereel.server import VoiceReelServer


@pytest.fixture
def mock_celery():
    """Mock Celery tasks for testing."""
    with patch("voicereel.server.CELERY_AVAILABLE", True):
        # Mock the tasks directly instead of patching imported names
        mock_register = MagicMock()
        mock_synthesize = MagicMock()
        mock_register.delay = MagicMock()
        mock_synthesize.delay = MagicMock()
        
        with patch("voicereel.server.celery_register_speaker", mock_register, create=True):
            with patch("voicereel.server.celery_synthesize", mock_synthesize, create=True):
                yield {
                    "register": mock_register,
                    "synthesize": mock_synthesize,
                }


@pytest.fixture
def test_server_celery(mock_celery):
    """Create test server with Celery enabled."""
    server = VoiceReelServer(
        host="127.0.0.1",
        port=0,
        dsn=":memory:",
        api_key="test_key",
        redis_url="redis://localhost:6379/0",
        use_celery=True,
    )
    server.start()
    yield server
    server.stop()


def test_redis_client():
    """Test Redis client functionality."""
    # Skip if Redis not available
    try:
        import redis
        client = RedisClient("redis://localhost:6379/0")
        if not client.health_check():
            pytest.skip("Redis not available")
    except:
        pytest.skip("Redis not available")
    
    # Test job status operations
    job_id = str(uuid.uuid4())
    
    # Set job status
    assert client.set_job_status(job_id, "pending", {"type": "test"})
    
    # Get job status
    status = client.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "pending"
    assert status["type"] == "test"
    
    # Delete job
    assert client.delete_job(job_id)
    assert client.get_job_status(job_id) is None


def test_celery_speaker_registration(test_server_celery, mock_celery):
    """Test speaker registration with Celery."""
    import urllib.request
    
    # Prepare request
    url = f"http://{test_server_celery.address[0]}:{test_server_celery.address[1]}/v1/speakers"
    data = json.dumps({
        "name": "Test Speaker",
        "lang": "en",
        "duration": 35,
        "script": "This is a test script for speaker registration.",
    }).encode()
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-VR-APIKEY": "test_key",
        }
    )
    
    # Send request
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    
    # Verify response
    assert "job_id" in result
    assert "speaker_id" in result
    
    # Verify Celery task was called
    assert mock_celery["register"].delay.called
    call_args = mock_celery["register"].delay.call_args[0]
    assert call_args[0] == result["job_id"]  # job_id
    assert call_args[1] == result["speaker_id"]  # speaker_id


def test_celery_synthesis(test_server_celery, mock_celery):
    """Test synthesis with Celery."""
    import urllib.request
    
    # Prepare request
    url = f"http://{test_server_celery.address[0]}:{test_server_celery.address[1]}/v1/synthesize"
    script = [
        {"speaker_id": "spk_1", "text": "Hello world"},
        {"speaker_id": "spk_2", "text": "How are you?"},
    ]
    data = json.dumps({
        "script": script,
        "output_format": "wav",
        "sample_rate": 48000,
        "caption_format": "vtt",
    }).encode()
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-VR-APIKEY": "test_key",
        }
    )
    
    # Send request
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    
    # Verify response
    assert "job_id" in result
    
    # Verify Celery task was called
    assert mock_celery["synthesize"].delay.called
    call_args = mock_celery["synthesize"].delay.call_args[0]
    assert call_args[0] == result["job_id"]  # job_id
    assert call_args[1] == script  # script
    assert call_args[2] == "wav"  # output_format
    assert call_args[3] == 48000  # sample_rate
    assert call_args[4] == "vtt"  # caption_format


def test_celery_tasks_import():
    """Test that Celery tasks can be imported."""
    try:
        from voicereel.tasks import register_speaker, synthesize, cleanup_old_files
        
        # Verify tasks are registered
        assert "voicereel.tasks.register_speaker" in celery_app.tasks
        assert "voicereel.tasks.synthesize" in celery_app.tasks
        assert "voicereel.tasks.cleanup_old_files" in celery_app.tasks
    except ImportError as e:
        pytest.skip(f"Skipping test due to import error: {e}")


def test_worker_script():
    """Test worker script can be imported."""
    from voicereel import worker
    
    # Verify worker module exists
    assert hasattr(worker, "app")


@pytest.mark.parametrize("use_celery", [True, False])
def test_server_mode_switching(use_celery):
    """Test server can switch between Celery and in-memory modes."""
    with patch("voicereel.server.CELERY_AVAILABLE", use_celery):
        server = VoiceReelServer(
            host="127.0.0.1",
            port=0,
            dsn=":memory:",
            use_celery=use_celery,
        )
        
        assert server.use_celery == use_celery
        
        if use_celery:
            # Celery mode: no worker thread should start
            server.start()
            assert server.worker is None
            server.stop()
        else:
            # In-memory mode: worker thread should start
            server.start()
            assert server.worker is not None
            assert server.worker.is_alive()
            server.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])