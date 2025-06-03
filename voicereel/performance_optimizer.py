"""Performance optimization utilities for VoiceReel TTS engine."""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from loguru import logger

from fish_speech.models.text2semantic.llama import DualARTransformer, NaiveTransformer
from fish_speech.models.vqgan.modules.firefly import FireflyArchitecture


class ModelCache:
    """Cache for pre-loaded models with optimizations."""
    
    def __init__(self, device: str = "cuda", enable_compile: bool = True):
        self.device = device
        self.enable_compile = enable_compile
        self._cache = {}
        self._compiled_models = {}
    
    @lru_cache(maxsize=1)
    def get_llama_model(self, checkpoint_path: str) -> nn.Module:
        """Get cached and optimized LLaMA model."""
        if checkpoint_path in self._cache:
            return self._cache[checkpoint_path]
        
        logger.info(f"Loading LLaMA model from {checkpoint_path}")
        start_time = time.time()
        
        # Load checkpoint
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        model_config = checkpoint.get("config", {})
        
        # Create model
        if model_config.get("dual_ar", False):
            model = DualARTransformer(**model_config)
        else:
            model = NaiveTransformer(**model_config)
        
        # Load state dict
        if "state_dict" in checkpoint:
            model.load_state_dict(checkpoint["state_dict"])
        elif "model" in checkpoint:
            model.load_state_dict(checkpoint["model"])
        else:
            model.load_state_dict(checkpoint)
        
        model = model.to(self.device)
        model.eval()
        
        # Apply optimizations
        if self.device == "cuda":
            # Enable TF32 for Ampere GPUs
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            
            # Set cudnn benchmarking
            torch.backends.cudnn.benchmark = True
            
            # Compile model if available (PyTorch 2.0+)
            if self.enable_compile and hasattr(torch, "compile"):
                logger.info("Compiling model with torch.compile()")
                model = torch.compile(model, mode="reduce-overhead")
                self._compiled_models[checkpoint_path] = True
        
        load_time = time.time() - start_time
        logger.info(f"Model loaded in {load_time:.2f}s")
        
        self._cache[checkpoint_path] = model
        return model
    
    @lru_cache(maxsize=1)
    def get_vqgan_model(self, checkpoint_path: str, config_name: str) -> nn.Module:
        """Get cached and optimized VQGAN model."""
        cache_key = f"{checkpoint_path}:{config_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        logger.info(f"Loading VQGAN model from {checkpoint_path}")
        start_time = time.time()
        
        # Create model based on config
        model = FireflyArchitecture(
            backbone_type="llama",
            backbone=dict(
                num_layers=12,
                num_heads=16,
                dim=1024,
                codebook_size=1024,
                codebook_groups=4,
            ),
            head=dict(
                output_channels=1,
                n_fft=1024,
                hop_length=256,
                padding="same",
            ),
        )
        
        # Load checkpoint
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        if "state_dict" in checkpoint:
            model.load_state_dict(checkpoint["state_dict"])
        else:
            model.load_state_dict(checkpoint)
        
        model = model.to(self.device)
        model.eval()
        
        # Apply optimizations
        if self.device == "cuda" and self.enable_compile and hasattr(torch, "compile"):
            logger.info("Compiling VQGAN model")
            model = torch.compile(model, mode="reduce-overhead")
        
        load_time = time.time() - start_time
        logger.info(f"VQGAN model loaded in {load_time:.2f}s")
        
        self._cache[cache_key] = model
        return model


class BatchProcessor:
    """Batch processing for efficient multi-speaker synthesis."""
    
    def __init__(self, batch_size: int = 4, max_workers: int = 2):
        self.batch_size = batch_size
        self.max_workers = max_workers
    
    def process_segments_parallel(
        self,
        segments: List[Dict[str, Any]],
        process_fn: callable,
        **kwargs
    ) -> List[Tuple[np.ndarray, float]]:
        """
        Process segments in parallel batches.
        
        Args:
            segments: List of segments to process
            process_fn: Function to process each segment
            **kwargs: Additional arguments for process_fn
            
        Returns:
            List of (audio_array, duration) tuples
        """
        results = [None] * len(segments)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks in batches
            future_to_idx = {}
            
            for i in range(0, len(segments), self.batch_size):
                batch = segments[i:i + self.batch_size]
                for j, segment in enumerate(batch):
                    future = executor.submit(process_fn, segment, **kwargs)
                    future_to_idx[future] = i + j
            
            # Collect results
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Error processing segment {idx}: {e}")
                    results[idx] = (np.array([]), 0.0)
        
        return results


class CudaMemoryManager:
    """Manage CUDA memory for optimal performance."""
    
    @staticmethod
    def optimize_memory():
        """Optimize CUDA memory usage."""
        if torch.cuda.is_available():
            # Clear cache
            torch.cuda.empty_cache()
            
            # Set memory fraction
            torch.cuda.set_per_process_memory_fraction(0.9)
            
            # Enable memory efficient attention if available
            if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
                os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb=512"
    
    @staticmethod
    def get_optimal_batch_size(model_size_gb: float = 2.0) -> int:
        """Calculate optimal batch size based on available GPU memory."""
        if not torch.cuda.is_available():
            return 1
        
        # Get available memory in GB
        gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        available_memory_gb = gpu_memory_gb * 0.8  # Use 80% of total memory
        
        # Estimate batch size (rough heuristic)
        batch_size = int(available_memory_gb / model_size_gb)
        return max(1, min(batch_size, 8))  # Cap at 8 for stability


class PerformanceMonitor:
    """Monitor and log performance metrics."""
    
    def __init__(self):
        self.metrics = {}
    
    def start_timer(self, name: str):
        """Start timing an operation."""
        self.metrics[f"{name}_start"] = time.time()
    
    def end_timer(self, name: str) -> float:
        """End timing and return duration."""
        start_time = self.metrics.pop(f"{name}_start", None)
        if start_time is None:
            return 0.0
        
        duration = time.time() - start_time
        self.metrics[f"{name}_duration"] = duration
        return duration
    
    def log_summary(self):
        """Log performance summary."""
        logger.info("Performance Summary:")
        for key, value in self.metrics.items():
            if key.endswith("_duration"):
                logger.info(f"  {key}: {value:.3f}s")


class OptimizedTTSEngine:
    """Optimized TTS engine with performance enhancements."""
    
    def __init__(
        self,
        llama_checkpoint: str,
        vqgan_checkpoint: str,
        vqgan_config: str,
        device: str = "cuda",
        enable_compile: bool = True,
        batch_size: Optional[int] = None,
    ):
        self.device = device
        self.monitor = PerformanceMonitor()
        
        # Initialize model cache
        self.model_cache = ModelCache(device, enable_compile)
        
        # Optimize CUDA settings
        if device == "cuda":
            CudaMemoryManager.optimize_memory()
        
        # Load models with caching
        self.monitor.start_timer("model_loading")
        self.llama_model = self.model_cache.get_llama_model(llama_checkpoint)
        self.vqgan_model = self.model_cache.get_vqgan_model(vqgan_checkpoint, vqgan_config)
        self.monitor.end_timer("model_loading")
        
        # Set batch size
        if batch_size is None and device == "cuda":
            self.batch_size = CudaMemoryManager.get_optimal_batch_size()
        else:
            self.batch_size = batch_size or 1
        
        logger.info(f"Initialized OptimizedTTSEngine with batch_size={self.batch_size}")
    
    @torch.inference_mode()
    def generate_speech_optimized(
        self,
        text: str,
        speaker_features: Dict[str, Any],
        max_new_tokens: int = 2048,
    ) -> Tuple[np.ndarray, float]:
        """
        Generate speech with optimizations.
        
        Args:
            text: Text to synthesize
            speaker_features: Speaker features dict
            max_new_tokens: Maximum tokens to generate
            
        Returns:
            Tuple of (audio_array, duration)
        """
        self.monitor.start_timer("inference")
        
        try:
            # Use half precision for faster inference
            with torch.autocast(device_type=self.device, dtype=torch.float16):
                # Generate semantic tokens
                # (Implementation would call optimized generation)
                semantic_tokens = self._generate_tokens_fast(text, speaker_features, max_new_tokens)
                
                # Decode to audio
                audio = self._decode_tokens_fast(semantic_tokens)
            
            duration = self.monitor.end_timer("inference")
            audio_duration = len(audio) / 44100  # Assuming 44.1kHz
            
            # Log performance
            rtf = duration / audio_duration if audio_duration > 0 else float('inf')
            logger.info(f"Generated {audio_duration:.2f}s audio in {duration:.2f}s (RTF: {rtf:.2f})")
            
            return audio, audio_duration
            
        except Exception as e:
            logger.error(f"Error in optimized generation: {e}")
            raise
    
    def _generate_tokens_fast(
        self,
        text: str,
        speaker_features: Dict[str, Any],
        max_new_tokens: int,
    ) -> torch.Tensor:
        """Fast token generation with optimizations."""
        # Implementation would include:
        # - KV cache optimization
        # - Attention optimization
        # - Batch processing
        # - Early stopping
        pass
    
    def _decode_tokens_fast(self, tokens: torch.Tensor) -> np.ndarray:
        """Fast audio decoding with optimizations."""
        # Implementation would include:
        # - Chunked decoding
        # - Memory efficient processing
        # - Optimized convolutions
        pass


def benchmark_synthesis(
    engine: OptimizedTTSEngine,
    test_texts: List[str],
    speaker_features: Dict[str, Any],
) -> Dict[str, float]:
    """
    Benchmark synthesis performance.
    
    Args:
        engine: TTS engine to benchmark
        test_texts: List of test texts
        speaker_features: Speaker features
        
    Returns:
        Dict with performance metrics
    """
    total_audio_duration = 0.0
    total_inference_time = 0.0
    
    for text in test_texts:
        start = time.time()
        audio, audio_duration = engine.generate_speech_optimized(text, speaker_features)
        inference_time = time.time() - start
        
        total_audio_duration += audio_duration
        total_inference_time += inference_time
    
    metrics = {
        "total_audio_duration": total_audio_duration,
        "total_inference_time": total_inference_time,
        "average_rtf": total_inference_time / total_audio_duration if total_audio_duration > 0 else float('inf'),
        "texts_processed": len(test_texts),
    }
    
    logger.info(f"Benchmark Results:")
    logger.info(f"  Total audio: {metrics['total_audio_duration']:.2f}s")
    logger.info(f"  Total time: {metrics['total_inference_time']:.2f}s")
    logger.info(f"  Average RTF: {metrics['average_rtf']:.2f}")
    
    return metrics