"""Tests for VoiceReel PostgreSQL implementation."""

import os
import tempfile
import time
import uuid
from datetime import datetime

import pytest
from unittest.mock import patch, MagicMock

# Skip tests if PostgreSQL dependencies are not available
try:
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

if POSTGRES_AVAILABLE:
    from voicereel.db_postgres import PostgreSQLDatabase
    from voicereel.server_postgres import VoiceReelPostgresServer
    from voicereel.tasks_postgres import register_speaker, synthesize


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL dependencies not available")
class TestPostgreSQLDatabase:
    """Test PostgreSQL database operations."""
    
    @pytest.fixture
    def test_db(self):
        """Create a test database instance."""
        # Use in-memory SQLite as a fallback for testing without real PostgreSQL
        db = PostgreSQLDatabase(dsn="dbname=test user=test host=localhost")
        
        # Mock the connection pool for testing
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        db.pool = mock_pool
        
        yield db
        db.close()
    
    def test_create_speaker(self, test_db):
        """Test creating a speaker."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = [1]
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            speaker_id = test_db.create_speaker("Test Speaker", "en")
            assert speaker_id == 1
            mock_cursor.execute.assert_called()
    
    def test_get_speaker(self, test_db):
        """Test retrieving a speaker."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1, "Test Speaker", "en", None, datetime.now())
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            speaker = test_db.get_speaker(1)
            assert speaker["id"] == 1
            assert speaker["name"] == "Test Speaker"
            assert speaker["lang"] == "en"
    
    def test_create_job(self, test_db):
        """Test creating a job."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ["test-job-id"]
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            job_id = test_db.create_job("synthesize", metadata={"test": True})
            assert job_id == "test-job-id"
            mock_cursor.execute.assert_called()
    
    def test_update_job(self, test_db):
        """Test updating a job."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            test_db.update_job("test-job-id", status="processing")
            mock_cursor.execute.assert_called()
    
    def test_record_usage(self, test_db):
        """Test recording usage."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            test_db.record_usage(30.5, job_id="test-job", speaker_id=1)
            mock_cursor.execute.assert_called()
    
    def test_get_usage_stats(self, test_db):
        """Test getting usage statistics."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (5, 150.5)
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            stats = test_db.get_usage_stats(2024, 1)
            assert stats["count"] == 5
            assert stats["total_length"] == 150.5
    
    def test_cleanup_old_jobs(self, test_db):
        """Test cleaning up old jobs."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [["job1"], ["job2"]]
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            deleted = test_db.cleanup_old_jobs(days=2)
            assert deleted == ["job1", "job2"]
            mock_cursor.execute.assert_called()
    
    def test_health_check(self, test_db):
        """Test database health check."""
        with patch.object(test_db, 'get_cursor') as mock_get_cursor:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ["PostgreSQL 15.0"]
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            
            with patch.object(test_db.pool, 'getconn') as mock_getconn:
                mock_getconn.return_value = MagicMock()
                
                health = test_db.get_health_status()
                assert health["status"] == "healthy"
                assert "version" in health
                assert "pool_stats" in health


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL dependencies not available")
class TestVoiceReelPostgresServer:
    """Test PostgreSQL server implementation."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_health_status.return_value = {"status": "healthy", "version": "15.0"}
        db.create_speaker.return_value = 1
        db.create_job.return_value = "test-job-id"
        db.get_job.return_value = {
            "id": "test-job-id",
            "type": "synthesize",
            "status": "succeeded",
            "audio_url": "s3://bucket/audio.wav",
            "caption_path": "s3://bucket/captions.json",
            "caption_format": "json",
            "created_at": datetime.now(),
            "completed_at": datetime.now(),
        }
        db.get_speaker.return_value = {
            "id": 1,
            "name": "Test Speaker",
            "lang": "en",
            "created_at": datetime.now(),
        }
        db.list_speakers.return_value = [
            {"id": 1, "name": "Speaker 1", "lang": "en", "created_at": datetime.now()},
            {"id": 2, "name": "Speaker 2", "lang": "es", "created_at": datetime.now()},
        ]
        db.get_usage_stats.return_value = {"count": 10, "total_length": 300.5}
        return db
    
    @pytest.fixture
    def server(self, mock_db):
        """Create a test server instance."""
        with patch('voicereel.server_postgres.PostgreSQLDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db
            
            server = VoiceReelPostgresServer(
                host="127.0.0.1",
                port=0,
                postgres_dsn="dbname=test",
                use_celery=False
            )
            yield server
            server.stop()
    
    def test_server_initialization(self, server):
        """Test server initialization."""
        assert server.host == "127.0.0.1"
        assert server.port == 0
        assert not server.use_celery
        assert server.db is not None
    
    def test_health_endpoint(self, server):
        """Test health check endpoint."""
        server.start()
        
        import urllib.request
        url = f"http://{server.address[0]}:{server.address[1]}/health"
        
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            data = response.read()
            assert b"ok" in data or b"healthy" in data
    
    def test_speaker_creation(self, server):
        """Test speaker creation endpoint."""
        server.start()
        
        import urllib.request
        import json
        
        url = f"http://{server.address[0]}:{server.address[1]}/v1/speakers"
        data = json.dumps({
            "name": "Test Speaker",
            "lang": "en",
            "duration": 30,
            "script": "Test script"
        }).encode()
        
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req) as response:
            assert response.status == 202
            result = json.loads(response.read())
            assert "job_id" in result
            assert "speaker_id" in result
    
    def test_job_retrieval(self, server):
        """Test job retrieval endpoint."""
        server.start()
        
        import urllib.request
        url = f"http://{server.address[0]}:{server.address[1]}/v1/jobs/test-job-id"
        
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            data = json.loads(response.read())
            assert data["id"] == "test-job-id"
            assert data["status"] == "succeeded"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL dependencies not available")
class TestPostgreSQLTasks:
    """Test PostgreSQL Celery tasks."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.update_job = MagicMock()
        db.update_speaker_metadata = MagicMock()
        db.record_usage = MagicMock()
        db.get_speaker.return_value = {"id": 1, "name": "Test", "lang": "en"}
        return db
    
    def test_register_speaker_task(self, mock_db):
        """Test speaker registration task."""
        with patch('voicereel.tasks_postgres.get_postgres_db') as mock_get_db:
            mock_get_db.return_value = mock_db
            
            with patch('voicereel.tasks_postgres.get_fish_speech_engine') as mock_engine:
                mock_engine.return_value.extract_speaker_features.return_value = {
                    "audio_duration": 30.5
                }
                
                with patch('voicereel.tasks_postgres.get_speaker_manager') as mock_manager:
                    mock_manager.return_value.save_speaker_features.return_value = "/path/to/features"
                    
                    # Create temp audio file
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(b"FAKE_AUDIO")
                        audio_path = f.name
                    
                    try:
                        result = register_speaker(
                            job_id="test-job",
                            speaker_id=1,
                            audio_path=audio_path,
                            script="Test script",
                            lang="en"
                        )
                        
                        assert result["status"] == "succeeded"
                        assert result["speaker_id"] == 1
                        assert result["features_extracted"] is True
                        mock_db.update_job.assert_called()
                        mock_db.record_usage.assert_called_with(30.5, job_id="test-job", speaker_id=1, metadata={"type": "speaker_registration"})
                    finally:
                        os.unlink(audio_path)
    
    def test_synthesize_task(self, mock_db):
        """Test synthesis task."""
        with patch('voicereel.tasks_postgres.get_postgres_db') as mock_get_db:
            mock_get_db.return_value = mock_db
            
            with patch('voicereel.tasks_postgres.get_fish_speech_engine') as mock_engine:
                mock_engine.return_value.synthesize_speech.return_value = (
                    b"FAKE_AUDIO",
                    [{"start": 0, "end": 2, "text": "Hello", "speaker": "spk_1"}]
                )
                mock_engine.return_value.save_audio = MagicMock()
                
                with patch('voicereel.tasks_postgres.get_speaker_manager') as mock_manager:
                    mock_manager.return_value.load_speaker_features.return_value = {"features": "test"}
                    
                    with patch('voicereel.tasks_postgres.get_storage_manager') as mock_storage:
                        mock_storage.return_value.upload_file.return_value = "s3://bucket/file"
                        
                        script = [{"speaker_id": "spk_1", "text": "Hello world"}]
                        
                        result = synthesize(
                            job_id="test-job",
                            script=script,
                            output_format="wav",
                            sample_rate=48000,
                            caption_format="json"
                        )
                        
                        assert result["status"] == "succeeded"
                        assert "audio_url" in result
                        assert "caption_url" in result
                        mock_db.update_job.assert_called()
                        mock_db.record_usage.assert_called()