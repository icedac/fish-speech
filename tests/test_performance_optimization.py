"""Tests for VoiceReel performance optimization."""

import os
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from voicereel.performance_optimizer import (
    CUDAOptimizer,
    MemoryManager,
    ModelCache,
    PerformanceMonitor,
    get_optimal_chunk_size,
    setup_optimizations,
)
from voicereel.fish_speech_optimized import OptimizedFishSpeechEngine


class TestModelCache:
    """Test model caching functionality."""
    
    def test_cache_hit(self):
        """Test that cached models are returned."""
        cache = ModelCache(device="cpu", enable_compile=False)
        
        # Mock model
        mock_model = MagicMock()
        load_fn = MagicMock(return_value=mock_model)
        
        # First load
        model1 = cache.get_or_load("test_model", load_fn)
        assert load_fn.call_count == 1
        
        # Second load should use cache
        model2 = cache.get_or_load("test_model", load_fn)
        assert load_fn.call_count == 1  # Not called again
        assert model1 == model2
    
    def test_cache_clear(self):
        """Test cache clearing."""
        cache = ModelCache(device="cpu", enable_compile=False)
        
        mock_model = MagicMock()
        load_fn = MagicMock(return_value=mock_model)
        
        # Load model
        cache.get_or_load("test_model", load_fn)
        assert "test_model" in cache.cache
        
        # Clear cache
        cache.clear()
        assert len(cache.cache) == 0
        assert len(cache._compile_cache) == 0
    
    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_model_compilation(self):
        """Test model compilation with torch.compile."""
        cache = ModelCache(device="cuda", enable_compile=True)
        
        # Create a simple model
        model = torch.nn.Linear(10, 10).cuda()
        load_fn = MagicMock(return_value=model)
        
        # Load with compilation
        compiled_model = cache.get_or_load("test_model", load_fn, compile_mode="reduce-overhead")
        
        # Should be cached
        assert "test_model" in cache.cache


class TestCUDAOptimizer:
    """Test CUDA optimization utilities."""
    
    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_cuda_setup(self):
        """Test CUDA optimization setup."""
        # Should not raise
        CUDAOptimizer.setup()
        
        # Check settings
        if hasattr(torch.backends.cudnn, "benchmark"):
            assert torch.backends.cudnn.benchmark == True
    
    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_optimal_batch_size(self):
        """Test optimal batch size calculation."""
        # Create a simple model
        model = torch.nn.Linear(10, 10).cuda()
        sample_input = torch.randn(1, 10).cuda()
        
        # Find optimal batch size
        batch_size = CUDAOptimizer.optimize_batch_size(model, sample_input, target_time=8.0)
        
        assert isinstance(batch_size, int)
        assert batch_size >= 1
    
    def test_cpu_fallback(self):
        """Test CPU fallback when CUDA not available."""
        with patch("torch.cuda.is_available", return_value=False):
            CUDAOptimizer.setup()  # Should not raise
            
            model = MagicMock()
            batch_size = CUDAOptimizer.optimize_batch_size(model, None)
            assert batch_size == 1


class TestMemoryManager:
    """Test memory management utilities."""
    
    def test_context_manager(self):
        """Test memory manager context."""
        with MemoryManager(device="cpu") as mem:
            # Should track memory
            assert mem.peak_memory == 0
        
        # After exit, peak memory might be set
        assert hasattr(mem, "peak_memory")
    
    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_gpu_memory_tracking(self):
        """Test GPU memory tracking."""
        with MemoryManager(device="cuda") as mem:
            # Allocate some GPU memory
            tensor = torch.randn(1000, 1000).cuda()
            del tensor
        
        # Should have recorded peak memory
        assert mem.peak_memory >= 0


class TestPerformanceMonitor:
    """Test performance monitoring."""
    
    def test_metric_recording(self):
        """Test recording and retrieving metrics."""
        monitor = PerformanceMonitor()
        
        # Record some metrics
        monitor.record("inference_time", 1.5)
        monitor.record("inference_time", 2.0)
        monitor.record("inference_time", 1.8)
        
        # Get statistics
        stats = monitor.get_stats("inference_time")
        assert stats["count"] == 3
        assert stats["mean"] == pytest.approx(1.77, rel=0.01)
        assert stats["min"] == 1.5
        assert stats["max"] == 2.0
        assert stats["total"] == 5.3
    
    def test_empty_metrics(self):
        """Test empty metric handling."""
        monitor = PerformanceMonitor()
        stats = monitor.get_stats("nonexistent")
        assert stats == {}


class TestOptimizedEngine:
    """Test optimized Fish-Speech engine."""
    
    @patch("voicereel.fish_speech_optimized.setup_optimizations")
    def test_engine_initialization(self, mock_setup):
        """Test engine initialization."""
        engine = OptimizedFishSpeechEngine(
            device="cpu",
            use_fp16=False,
            enable_compile=False,
            max_workers=2
        )
        
        assert engine.device == "cpu"
        assert engine.use_fp16 == False
        assert engine.max_workers == 2
        mock_setup.assert_called_once()
    
    def test_parallel_vs_sequential(self):
        """Test parallel vs sequential processing decision."""
        engine = OptimizedFishSpeechEngine(device="cpu", max_workers=4)
        
        # Small script should use sequential
        small_script = [{"speaker_id": "spk_1", "text": "Hello"}]
        
        # Large script should use parallel (if enabled)
        large_script = [
            {"speaker_id": f"spk_{i%3}", "text": f"Segment {i}"}
            for i in range(10)
        ]
        
        # Mock speaker features
        speaker_features = {
            "spk_0": {"features": "test"},
            "spk_1": {"features": "test"},
            "spk_2": {"features": "test"},
        }
        
        with patch.object(engine, '_sequential_synthesis') as mock_seq:
            with patch.object(engine, '_parallel_synthesis') as mock_par:
                mock_seq.return_value = ([], [])
                mock_par.return_value = ([], [])
                
                # Test small script
                engine.synthesize_speech_optimized(
                    small_script, speaker_features, use_parallel=True
                )
                mock_seq.assert_called_once()
                mock_par.assert_not_called()
                
                # Reset mocks
                mock_seq.reset_mock()
                mock_par.reset_mock()
                
                # Test large script
                engine.synthesize_speech_optimized(
                    large_script, speaker_features, use_parallel=True
                )
                mock_par.assert_called_once()
                mock_seq.assert_not_called()
    
    def test_performance_target_check(self):
        """Test performance target checking."""
        engine = OptimizedFishSpeechEngine(device="cpu")
        
        # Mock a 30-second synthesis in 6 seconds (should pass)
        script = [{"speaker_id": "spk_1", "text": "Long text " * 100}]
        speaker_features = {"spk_1": {"features": "test"}}
        
        with patch.object(engine, '_sequential_synthesis') as mock_syn:
            # Create 30 seconds of dummy audio
            audio = np.zeros(30 * 48000, dtype=np.float32)
            captions = [{"start": 0, "end": 30, "text": "...", "speaker": "spk_1"}]
            mock_syn.return_value = ([audio], captions)
            
            with patch('time.time') as mock_time:
                # Simulate 6 second synthesis time
                mock_time.side_effect = [0, 6]
                
                audio_data, caption_units = engine.synthesize_speech_optimized(
                    script, speaker_features
                )
                
                # Should have logged success
                # (In real test, would check logger output)
                assert len(audio_data) == 30 * 48000


def test_optimal_chunk_size():
    """Test optimal chunk size calculation."""
    # Short audio
    chunk_size = get_optimal_chunk_size(5.0)
    assert chunk_size == 1024
    
    # Medium audio
    chunk_size = get_optimal_chunk_size(20.0)
    assert chunk_size == 2048
    
    # Long audio
    chunk_size = get_optimal_chunk_size(60.0)
    assert chunk_size == 4096
    
    # Test caching
    chunk_size2 = get_optimal_chunk_size(60.0)
    assert chunk_size == chunk_size2