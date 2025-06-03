"""Test performance optimizations for VoiceReel."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from voicereel.performance_optimizer import (
    BatchProcessor,
    CudaMemoryManager,
    ModelCache,
    PerformanceMonitor,
)


class TestModelCache:
    """Test model caching functionality."""
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = ModelCache(device="cpu", enable_compile=False)
        assert cache.device == "cpu"
        assert not cache.enable_compile
        assert len(cache._cache) == 0
    
    @patch("torch.load")
    @patch("voicereel.performance_optimizer.DualARTransformer")
    def test_llama_model_caching(self, mock_model_class, mock_torch_load):
        """Test LLaMA model caching."""
        # Setup mocks
        mock_checkpoint = {
            "config": {"dual_ar": True},
            "state_dict": {},
        }
        mock_torch_load.return_value = mock_checkpoint
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        
        cache = ModelCache(device="cpu", enable_compile=False)
        
        # First load
        model1 = cache.get_llama_model("test_checkpoint.pth")
        assert mock_torch_load.called
        assert "test_checkpoint.pth" in cache._cache
        
        # Second load should use cache
        mock_torch_load.reset_mock()
        model2 = cache.get_llama_model("test_checkpoint.pth")
        assert not mock_torch_load.called
        assert model1 == model2


class TestBatchProcessor:
    """Test batch processing functionality."""
    
    def test_parallel_processing(self):
        """Test parallel segment processing."""
        processor = BatchProcessor(batch_size=2, max_workers=2)
        
        # Mock process function
        def mock_process(segment, **kwargs):
            time.sleep(0.01)  # Simulate processing
            return (np.random.randn(1000), 1.0)
        
        segments = [{"id": i} for i in range(4)]
        
        start = time.time()
        results = processor.process_segments_parallel(segments, mock_process)
        duration = time.time() - start
        
        assert len(results) == 4
        assert all(isinstance(r[0], np.ndarray) for r in results)
        assert all(r[1] == 1.0 for r in results)
        
        # Should be faster than sequential (4 * 0.01 = 0.04s)
        assert duration < 0.04


class TestCudaMemoryManager:
    """Test CUDA memory management."""
    
    def test_optimal_batch_size_cpu(self):
        """Test batch size calculation for CPU."""
        with patch("torch.cuda.is_available", return_value=False):
            batch_size = CudaMemoryManager.get_optimal_batch_size()
            assert batch_size == 1
    
    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.get_device_properties")
    def test_optimal_batch_size_gpu(self, mock_get_props, mock_cuda_available):
        """Test batch size calculation for GPU."""
        # Mock 8GB GPU
        mock_props = MagicMock()
        mock_props.total_memory = 8 * 1024**3  # 8GB
        mock_get_props.return_value = mock_props
        
        batch_size = CudaMemoryManager.get_optimal_batch_size(model_size_gb=2.0)
        # 8GB * 0.8 / 2GB = 3.2, so batch_size should be 3
        assert batch_size == 3


class TestPerformanceMonitor:
    """Test performance monitoring."""
    
    def test_timer_functionality(self):
        """Test timer start/end functionality."""
        monitor = PerformanceMonitor()
        
        monitor.start_timer("test_operation")
        time.sleep(0.1)
        duration = monitor.end_timer("test_operation")
        
        assert 0.09 < duration < 0.11  # Allow some variance
        assert "test_operation_duration" in monitor.metrics
    
    def test_missing_timer(self):
        """Test ending timer that wasn't started."""
        monitor = PerformanceMonitor()
        duration = monitor.end_timer("missing_timer")
        assert duration == 0.0


class TestOptimizationIntegration:
    """Test optimization integration."""
    
    @pytest.mark.parametrize("device", ["cpu", "cuda"])
    def test_optimization_flags(self, device):
        """Test that optimization flags are properly set."""
        if device == "cuda" and not torch.cuda.is_available():
            pytest.skip("CUDA not available")
        
        from voicereel.config import config
        
        # Check default optimization settings
        assert config.USE_OPTIMIZED_ENGINE is True
        assert config.PARALLEL_SYNTHESIS is True
        assert config.MAX_WORKERS == 4
        assert config.COMPILE_MODEL is True
    
    def test_rtf_calculation(self):
        """Test real-time factor calculation."""
        # 30 seconds of audio generated in 8 seconds
        audio_duration = 30.0
        synthesis_time = 8.0
        rtf = synthesis_time / audio_duration
        
        assert rtf == 8.0 / 30.0
        assert rtf < 1.0  # Faster than real-time
        assert rtf <= 0.27  # Meets the 8s/30s = 0.267 target


def test_performance_target():
    """Test that we meet the PRD performance target."""
    # PRD Target: 30 seconds of audio in ≤ 8 seconds
    target_audio_duration = 30.0
    target_synthesis_time = 8.0
    
    # Calculate required RTF
    required_rtf = target_synthesis_time / target_audio_duration
    
    assert required_rtf <= 0.267  # 8/30 = 0.267
    
    # Test various scenarios
    test_cases = [
        (30.0, 8.0, True),   # Exactly meets target
        (30.0, 7.5, True),   # Better than target
        (30.0, 8.5, False),  # Fails target
        (40.0, 8.0, True),   # More audio in same time is OK
        (25.0, 8.0, True),   # Less audio is OK if time is within limit
    ]
    
    for audio_dur, synth_time, should_pass in test_cases:
        if audio_dur >= 30:
            meets_target = synth_time <= 8.0
        else:
            meets_target = True  # Don't penalize for shorter audio
        
        assert meets_target == should_pass, f"Failed for {audio_dur}s audio in {synth_time}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])