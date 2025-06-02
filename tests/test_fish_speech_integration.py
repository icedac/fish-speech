"""Tests for Fish-Speech integration in VoiceReel."""

import json
import os
import sys
import tempfile
import pytest
from unittest.mock import MagicMock, patch, Mock

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def mock_torch():
    """Mock torch for testing without GPU dependencies."""
    with patch.dict(sys.modules, {
        'torch': Mock(),
        'numpy': Mock(),
        'soundfile': Mock(),
    }):
        yield


@pytest.fixture
def mock_fish_speech_models():
    """Mock Fish-Speech model imports."""
    mock_modules = {
        'fish_speech.models.text2semantic.inference': Mock(),
        'fish_speech.models.vqgan.inference': Mock(),
        'fish_speech.inference_engine.utils': Mock(),
        'fish_speech.tokenizer': Mock(),
    }
    
    with patch.dict(sys.modules, mock_modules):
        yield mock_modules


@pytest.fixture
def temp_audio_file():
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        f.write(b'fake_audio_data')
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_config_module():
    """Test configuration module."""
    from voicereel.config import VoiceReelConfig, config
    
    # Test default values
    assert hasattr(config, 'FISH_SPEECH_LLAMA_PATH')
    assert hasattr(config, 'FISH_SPEECH_VQGAN_PATH')
    assert hasattr(config, 'DEVICE')
    
    # Test model status check
    status = config.check_model_files()
    assert isinstance(status, dict)
    assert 'models_ready' in status
    assert 'llama_exists' in status
    assert 'vqgan_exists' in status


def test_speaker_manager():
    """Test speaker manager functionality."""
    from voicereel.fish_speech_integration import SpeakerManager
    
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = SpeakerManager(temp_dir)
        
        # Test save/load features
        speaker_id = 123
        features = {
            "vq_tokens": [[1, 2, 3], [4, 5, 6]],
            "reference_text": "Hello world",
            "audio_duration": 2.5,
            "sample_rate": 44100,
        }
        
        # Save features
        feature_path = manager.save_speaker_features(speaker_id, features)
        assert os.path.exists(feature_path)
        
        # Load features
        loaded_features = manager.load_speaker_features(speaker_id)
        assert loaded_features == features
        
        # Delete features
        success = manager.delete_speaker_features(speaker_id)
        assert success
        assert not os.path.exists(feature_path)


@patch('voicereel.fish_speech_integration.load_text2semantic_model')
@patch('voicereel.fish_speech_integration.load_vqgan_model')
@patch('voicereel.fish_speech_integration.AutoTokenizer')
def test_fish_speech_engine_init(mock_tokenizer, mock_vqgan, mock_llama, mock_torch):
    """Test Fish-Speech engine initialization."""
    from voicereel.fish_speech_integration import FishSpeechEngine
    
    # Mock model loading
    mock_llama.return_value = (Mock(), Mock())
    mock_vqgan.return_value = Mock()
    mock_tokenizer.return_value = Mock()
    
    # Create engine
    engine = FishSpeechEngine(
        llama_checkpoint_path="fake_llama.pth",
        vqgan_checkpoint_path="fake_vqgan.pth",
        device="cpu",
    )
    
    assert engine.device == "cpu"
    assert engine.sample_rate == 44100
    assert engine.llama_model is not None
    assert engine.vqgan_model is not None
    assert engine.tokenizer is not None


def test_multipart_parser():
    """Test multipart form parser."""
    from voicereel.multipart_parser import MultipartParser, parse_multipart_form
    
    # Create test multipart data
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content_type = f"multipart/form-data; boundary={boundary}"
    
    data = f"""------WebKitFormBoundary7MA4YWxkTrZu0gW\r
Content-Disposition: form-data; name="name"\r
\r
Test Speaker\r
------WebKitFormBoundary7MA4YWxkTrZu0gW\r
Content-Disposition: form-data; name="reference_audio"; filename="test.wav"\r
Content-Type: audio/wav\r
\r
fake_audio_data\r
------WebKitFormBoundary7MA4YWxkTrZu0gW--\r
""".encode()
    
    # Parse data
    form_fields, file_paths = parse_multipart_form(data, content_type)
    
    assert "name" in form_fields
    assert form_fields["name"] == "Test Speaker"
    assert "reference_audio" in file_paths
    assert os.path.exists(file_paths["reference_audio"])
    
    # Cleanup
    os.remove(file_paths["reference_audio"])


@patch('voicereel.tasks.get_fish_speech_engine')
@patch('voicereel.tasks.get_speaker_manager')
def test_speaker_registration_task(mock_speaker_manager, mock_engine, temp_audio_file):
    """Test speaker registration Celery task."""
    from voicereel.tasks import register_speaker
    
    # Mock objects
    mock_engine_instance = Mock()
    mock_engine.return_value = mock_engine_instance
    
    mock_manager_instance = Mock()
    mock_speaker_manager.return_value = mock_manager_instance
    
    # Mock database
    mock_db = Mock()
    mock_cursor = Mock()
    mock_db.cursor.return_value = mock_cursor
    
    # Mock feature extraction
    features = {
        "vq_tokens": [[1, 2, 3]],
        "audio_duration": 2.5,
    }
    mock_engine_instance.extract_speaker_features.return_value = features
    mock_manager_instance.save_speaker_features.return_value = "/tmp/speaker_123.json"
    
    # Create task instance with mocked db
    task = register_speaker
    task.db = mock_db
    
    # Run task
    result = task(
        job_id="test_job_123",
        speaker_id=123,
        audio_path=temp_audio_file,
        script="Hello world",
        lang="en"
    )
    
    # Verify results
    assert result["status"] == "succeeded"
    assert result["speaker_id"] == 123
    assert result["features_extracted"] is True
    
    # Verify database calls
    assert mock_cursor.execute.call_count >= 2  # Status updates
    assert mock_db.commit.call_count >= 2


@patch('voicereel.tasks.get_fish_speech_engine')
@patch('voicereel.tasks.get_speaker_manager')
def test_synthesis_task(mock_speaker_manager, mock_engine):
    """Test synthesis Celery task."""
    from voicereel.tasks import synthesize
    
    # Mock objects
    mock_engine_instance = Mock()
    mock_engine.return_value = mock_engine_instance
    
    mock_manager_instance = Mock()
    mock_speaker_manager.return_value = mock_manager_instance
    
    # Mock database
    mock_db = Mock()
    mock_cursor = Mock()
    mock_db.cursor.return_value = mock_cursor
    
    # Mock synthesis
    import numpy as np
    audio_data = np.array([0.1, 0.2, 0.3])
    caption_data = [
        {"start": 0.0, "end": 1.0, "speaker": "spk_1", "text": "Hello"},
        {"start": 1.0, "end": 2.0, "speaker": "spk_2", "text": "World"},
    ]
    mock_engine_instance.synthesize_speech.return_value = (audio_data, caption_data)
    mock_engine_instance.save_audio.return_value = "/tmp/test_job.wav"
    
    # Mock speaker features
    speaker_features = {
        "vq_tokens": [[1, 2, 3]],
        "reference_text": "Test",
    }
    mock_manager_instance.load_speaker_features.return_value = speaker_features
    
    # Create task instance with mocked db
    task = synthesize
    task.db = mock_db
    
    # Test script
    script = [
        {"speaker_id": "spk_1", "text": "Hello"},
        {"speaker_id": "spk_2", "text": "World"},
    ]
    
    # Run task
    result = task(
        job_id="test_job_456",
        script=script,
        output_format="wav",
        sample_rate=44100,
        caption_format="json"
    )
    
    # Verify results
    assert result["status"] == "succeeded"
    assert result["num_segments"] == 2
    assert "speakers_used" in result
    assert "spk_1" in result["speakers_used"]
    assert "spk_2" in result["speakers_used"]


def test_model_setup_script():
    """Test model setup script functionality."""
    from voicereel.setup_models import check_models, setup_workspace
    
    # Test check_models (should not crash)
    result = check_models()
    assert isinstance(result, bool)
    
    # Test setup_workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        # Temporarily override config paths
        from voicereel import config
        original_speaker_path = config.config.SPEAKER_STORAGE_PATH
        original_audio_path = config.config.AUDIO_OUTPUT_PATH
        
        config.config.SPEAKER_STORAGE_PATH = os.path.join(temp_dir, "speakers")
        config.config.AUDIO_OUTPUT_PATH = os.path.join(temp_dir, "audio")
        
        try:
            setup_workspace()
            assert os.path.exists(config.config.SPEAKER_STORAGE_PATH)
            assert os.path.exists(config.config.AUDIO_OUTPUT_PATH)
        finally:
            config.config.SPEAKER_STORAGE_PATH = original_speaker_path
            config.config.AUDIO_OUTPUT_PATH = original_audio_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])