"""Performance optimization utilities for VoiceReel."""

import os
import time
from typing import Any, Dict, Optional
import torch
from loguru import logger
from functools import lru_cache


class ModelCache:
    """Cache for compiled and optimized models."""
    
    def __init__(self, device: str = "cuda", enable_compile: bool = True):
        self.device = device
        self.enable_compile = enable_compile
        self.cache: Dict[str, Any] = {}
        self._compile_cache: Dict[str, Any] = {}
        
    def get_or_load(self, model_id: str, load_fn, compile_mode: str = "reduce-overhead") -> Any:
        """Get model from cache or load and optimize it."""
        if model_id in self.cache:
            logger.debug(f"Using cached model: {model_id}")
            return self.cache[model_id]
        
        logger.info(f"Loading model: {model_id}")
        start_time = time.time()
        
        # Load model
        model = load_fn()
        
        # Move to device
        if hasattr(model, "to"):
            model = model.to(self.device)
            
        # Enable eval mode if available
        if hasattr(model, "eval"):
            model.eval()
            
        # Compile with torch.compile if available and enabled
        if self.device == "cuda" and self.enable_compile and hasattr(torch, "compile"):
            compile_key = f"{model_id}_compiled_{compile_mode}"
            if compile_key not in self._compile_cache:
                logger.info(f"Compiling model with torch.compile(mode='{compile_mode}')")
                try:
                    compiled_model = torch.compile(model, mode=compile_mode)
                    self._compile_cache[compile_key] = compiled_model
                    model = compiled_model
                except Exception as e:
                    logger.warning(f"Failed to compile model: {e}")
            else:
                model = self._compile_cache[compile_key]
        
        # Cache the model
        self.cache[model_id] = model
        load_time = time.time() - start_time
        logger.info(f"Model loaded and optimized in {load_time:.2f}s")
        
        return model
    
    def clear(self):
        """Clear all cached models."""
        self.cache.clear()
        self._compile_cache.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class CUDAOptimizer:
    """CUDA-specific optimizations."""
    
    @staticmethod
    def setup():
        """Setup CUDA optimizations."""
        if not torch.cuda.is_available():
            logger.warning("CUDA not available, skipping GPU optimizations")
            return
            
        # Enable TF32 on Ampere GPUs
        if hasattr(torch.backends.cuda, "matmul"):
            torch.backends.cuda.matmul.allow_tf32 = True
        if hasattr(torch.backends.cudnn, "allow_tf32"):
            torch.backends.cudnn.allow_tf32 = True
            
        # Enable cudnn benchmarking for better performance
        torch.backends.cudnn.benchmark = True
        
        # Set memory fraction if needed
        if os.getenv("VOICEREEL_GPU_MEMORY_FRACTION"):
            fraction = float(os.getenv("VOICEREEL_GPU_MEMORY_FRACTION", "0.9"))
            torch.cuda.set_per_process_memory_fraction(fraction)
            
        logger.info("CUDA optimizations enabled")
    
    @staticmethod
    def optimize_batch_size(model, sample_input, target_time: float = 8.0) -> int:
        """Find optimal batch size for target processing time."""
        if not torch.cuda.is_available():
            return 1
            
        batch_sizes = [1, 2, 4, 8, 16, 32]
        best_batch_size = 1
        
        for batch_size in batch_sizes:
            try:
                # Create batched input
                if isinstance(sample_input, torch.Tensor):
                    batched_input = sample_input.repeat(batch_size, 1)
                else:
                    batched_input = [sample_input] * batch_size
                
                # Warmup
                for _ in range(3):
                    with torch.no_grad():
                        _ = model(batched_input)
                
                # Time the inference
                torch.cuda.synchronize()
                start_time = time.time()
                
                with torch.no_grad():
                    _ = model(batched_input)
                    
                torch.cuda.synchronize()
                inference_time = time.time() - start_time
                
                # Check if this batch size meets target
                time_per_sample = inference_time / batch_size
                if time_per_sample * 30 <= target_time:  # 30 seconds of audio
                    best_batch_size = batch_size
                else:
                    break
                    
            except RuntimeError as e:
                if "out of memory" in str(e):
                    logger.warning(f"Batch size {batch_size} caused OOM")
                    break
                raise
        
        logger.info(f"Optimal batch size: {best_batch_size}")
        return best_batch_size


class MemoryManager:
    """Memory management for efficient processing."""
    
    def __init__(self, device: str = "cuda"):
        self.device = device
        self.peak_memory = 0
        
    def __enter__(self):
        if self.device == "cuda" and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.empty_cache()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.device == "cuda" and torch.cuda.is_available():
            self.peak_memory = torch.cuda.max_memory_allocated() / 1024 / 1024 / 1024  # GB
            torch.cuda.empty_cache()
            logger.debug(f"Peak GPU memory usage: {self.peak_memory:.2f} GB")


class PerformanceMonitor:
    """Monitor and log performance metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, list] = {}
        
    def record(self, metric_name: str, value: float):
        """Record a metric value."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)
        
    def get_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a metric."""
        if metric_name not in self.metrics or not self.metrics[metric_name]:
            return {}
            
        values = self.metrics[metric_name]
        return {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
            "total": sum(values),
        }
    
    def log_summary(self):
        """Log summary of all metrics."""
        for metric_name, values in self.metrics.items():
            if values:
                stats = self.get_stats(metric_name)
                logger.info(f"{metric_name}: mean={stats['mean']:.3f}, min={stats['min']:.3f}, max={stats['max']:.3f}")


# Global instances
_model_cache: Optional[ModelCache] = None
_performance_monitor: Optional[PerformanceMonitor] = None


def get_model_cache() -> ModelCache:
    """Get global model cache instance."""
    global _model_cache
    if _model_cache is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        enable_compile = os.getenv("VOICEREEL_ENABLE_COMPILE", "true").lower() == "true"
        _model_cache = ModelCache(device=device, enable_compile=enable_compile)
    return _model_cache


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def setup_optimizations():
    """Setup all performance optimizations."""
    # Setup CUDA optimizations
    CUDAOptimizer.setup()
    
    # Set threading optimizations
    if hasattr(torch, "set_num_threads"):
        num_threads = int(os.getenv("VOICEREEL_NUM_THREADS", "0"))
        if num_threads > 0:
            torch.set_num_threads(num_threads)
            logger.info(f"Set PyTorch threads to {num_threads}")
    
    # Enable optimizations for inference
    if hasattr(torch, "inference_mode"):
        torch.inference_mode(True)
        
    logger.info("Performance optimizations setup complete")


@lru_cache(maxsize=128)
def get_optimal_chunk_size(audio_length: float, target_time: float = 8.0) -> int:
    """Calculate optimal chunk size for processing."""
    # Estimate based on target processing time
    # Assuming linear relationship between chunk size and processing time
    base_chunk_size = 1024  # samples
    
    if audio_length <= 10:
        return base_chunk_size
    elif audio_length <= 30:
        return base_chunk_size * 2
    else:
        # For longer audio, use larger chunks
        return base_chunk_size * 4