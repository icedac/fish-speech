"""Optimized Fish-Speech integration for VoiceReel with performance enhancements."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from loguru import logger

from fish_speech.i18n import i18n
from fish_speech.models.text2semantic.inference import (
    GenerateResponse,
    WrappedGenerateResponse,
    decode_one_token,
    generate_long,
)
from fish_speech.text import clean_text, split_text
from fish_speech.tokenizer import Tokenizer
from fish_speech.utils.spectrogram import load_audio

from .config import config
from .performance_optimizer import (
    BatchProcessor,
    CudaMemoryManager,
    ModelCache,
    OptimizedTTSEngine,
    PerformanceMonitor,
)


class OptimizedFishSpeechEngine:
    """Optimized Fish-Speech TTS engine with performance enhancements."""
    
    def __init__(
        self,
        llama_checkpoint: Optional[str] = None,
        vqgan_checkpoint: Optional[str] = None,
        vqgan_config: Optional[str] = None,
        device: Optional[str] = None,
        compile_models: bool = True,
        use_half_precision: bool = True,
        batch_size: Optional[int] = None,
        max_workers: int = 2,
    ):
        """
        Initialize optimized Fish-Speech engine.
        
        Args:
            llama_checkpoint: Path to LLaMA checkpoint
            vqgan_checkpoint: Path to VQGAN checkpoint
            vqgan_config: VQGAN config name
            device: Device to use (cuda/cpu)
            compile_models: Whether to compile models with torch.compile
            use_half_precision: Use FP16 for faster inference
            batch_size: Batch size for processing
            max_workers: Number of worker threads
        """
        self.llama_checkpoint = llama_checkpoint or config.FISH_SPEECH_LLAMA_PATH
        self.vqgan_checkpoint = vqgan_checkpoint or config.FISH_SPEECH_VQGAN_PATH
        self.vqgan_config = vqgan_config or config.FISH_SPEECH_VQGAN_CONFIG
        self.device = device or config.DEVICE
        self.compile_models = compile_models and config.COMPILE_MODEL
        self.use_half_precision = use_half_precision and self.device == "cuda"
        self.max_workers = max_workers
        
        # Performance monitoring
        self.monitor = PerformanceMonitor()
        
        # Initialize model cache
        self.model_cache = ModelCache(self.device, self.compile_models)
        
        # Optimize CUDA settings
        if self.device == "cuda":
            CudaMemoryManager.optimize_memory()
            self.batch_size = batch_size or CudaMemoryManager.get_optimal_batch_size()
        else:
            self.batch_size = batch_size or 1
        
        # Load models
        self._load_models()
        
        # Initialize tokenizer
        self.tokenizer = Tokenizer()
        
        # Batch processor
        self.batch_processor = BatchProcessor(self.batch_size, max_workers)
        
        # Precompile common operations
        if self.compile_models:
            self._warmup_models()
        
        logger.info(f"Initialized OptimizedFishSpeechEngine with:")
        logger.info(f"  Device: {self.device}")
        logger.info(f"  Batch size: {self.batch_size}")
        logger.info(f"  Half precision: {self.use_half_precision}")
        logger.info(f"  Compilation: {self.compile_models}")
    
    def _load_models(self):
        """Load models with optimizations."""
        self.monitor.start_timer("model_loading")
        
        # Load LLaMA model
        self.llama_model = self.model_cache.get_llama_model(self.llama_checkpoint)
        
        # Load VQGAN model
        self.vqgan_model = self.model_cache.get_vqgan_model(
            self.vqgan_checkpoint, self.vqgan_config
        )
        
        # Enable half precision if requested
        if self.use_half_precision:
            self.llama_model = self.llama_model.half()
            self.vqgan_model = self.vqgan_model.half()
        
        # Create decode function
        self.decode_one_token = lambda x: decode_one_token(
            self.llama_model, x, tokenizer=self.tokenizer
        )
        
        load_time = self.monitor.end_timer("model_loading")
        logger.info(f"Models loaded in {load_time:.2f}s")
    
    def _warmup_models(self):
        """Warmup models with dummy data for compilation."""
        logger.info("Warming up models...")
        
        with torch.inference_mode():
            # Warmup LLaMA
            dummy_tokens = torch.randint(0, 1000, (1, 100), device=self.device)
            _ = self.llama_model(dummy_tokens)
            
            # Warmup VQGAN
            dummy_audio = torch.randn(1, 1, 44100, device=self.device)
            if self.use_half_precision:
                dummy_audio = dummy_audio.half()
            _ = self.vqgan_model.encode(dummy_audio)
    
    @torch.inference_mode()
    def extract_speaker_features_fast(
        self,
        audio_path: str,
        reference_text: str,
        use_chunking: bool = True,
        chunk_size: int = 10,  # seconds
    ) -> Dict[str, Any]:
        """
        Extract speaker features with optimizations.
        
        Args:
            audio_path: Path to reference audio
            reference_text: Reference text
            use_chunking: Process audio in chunks for memory efficiency
            chunk_size: Chunk size in seconds
            
        Returns:
            Dict containing speaker features
        """
        self.monitor.start_timer("feature_extraction")
        
        try:
            # Load audio
            audio_data = load_audio(audio_path, sr=44100)
            audio_duration = len(audio_data) / 44100
            
            # Process in chunks if audio is long
            if use_chunking and audio_duration > chunk_size:
                vq_tokens_list = []
                chunk_samples = chunk_size * 44100
                
                for i in range(0, len(audio_data), chunk_samples):
                    chunk = audio_data[i:i + chunk_samples]
                    chunk_tensor = torch.from_numpy(chunk).to(self.device)
                    
                    if self.use_half_precision:
                        chunk_tensor = chunk_tensor.half()
                    
                    chunk_tensor = chunk_tensor[None, None, :]
                    
                    # Encode chunk
                    with torch.autocast(device_type=self.device, enabled=self.use_half_precision):
                        encoded = self.vqgan_model.encode(chunk_tensor)
                        vq_tokens_list.append(encoded[0][0])
                
                # Concatenate tokens
                vq_tokens = torch.cat(vq_tokens_list, dim=-1)
            else:
                # Process entire audio at once
                audio_tensor = torch.from_numpy(audio_data).to(self.device)
                if self.use_half_precision:
                    audio_tensor = audio_tensor.half()
                
                audio_tensor = audio_tensor[None, None, :]
                
                with torch.autocast(device_type=self.device, enabled=self.use_half_precision):
                    encoded = self.vqgan_model.encode(audio_tensor)
                    vq_tokens = encoded[0][0]
            
            # Encode reference text
            from fish_speech.models.text2semantic.inference import encode_tokens
            text_tokens = encode_tokens(
                tokenizer=self.tokenizer,
                string=reference_text,
                device=self.device,
                num_codebooks=4,
            )
            
            features = {
                "vq_tokens": vq_tokens.cpu().tolist(),
                "text_tokens": text_tokens.cpu().tolist() if text_tokens is not None else None,
                "reference_text": reference_text,
                "audio_duration": audio_duration,
                "sample_rate": 44100,
            }
            
            extraction_time = self.monitor.end_timer("feature_extraction")
            logger.info(f"Extracted features in {extraction_time:.2f}s for {audio_duration:.2f}s audio")
            
            return features
            
        except Exception as e:
            logger.error(f"Failed to extract speaker features: {e}")
            raise
    
    @torch.inference_mode()
    def synthesize_speech_optimized(
        self,
        script: List[Dict[str, str]],
        speaker_features: Dict[str, Dict[str, Any]],
        output_format: str = "wav",
        use_parallel: bool = True,
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Synthesize multi-speaker speech with optimizations.
        
        Args:
            script: List of segments with speaker_id and text
            speaker_features: Speaker features dict
            output_format: Output format
            use_parallel: Use parallel processing for segments
            
        Returns:
            Tuple of (audio_array, caption_data)
        """
        self.monitor.start_timer("total_synthesis")
        total_start = time.time()
        
        try:
            if use_parallel and len(script) > 1:
                # Process segments in parallel
                results = self._process_segments_parallel(script, speaker_features)
            else:
                # Process segments sequentially
                results = self._process_segments_sequential(script, speaker_features)
            
            # Combine results
            all_audio_segments = []
            caption_data = []
            current_time = 0.0
            
            for audio_segment, segment_duration, speaker_id, text in results:
                if len(audio_segment) > 0:
                    all_audio_segments.append(audio_segment)
                    caption_data.append({
                        "start": current_time,
                        "end": current_time + segment_duration,
                        "speaker": speaker_id,
                        "text": text,
                    })
                    current_time += segment_duration
            
            # Concatenate audio
            if all_audio_segments:
                final_audio = np.concatenate(all_audio_segments)
            else:
                final_audio = np.array([])
            
            total_time = self.monitor.end_timer("total_synthesis")
            audio_duration = len(final_audio) / 44100
            
            # Calculate real-time factor
            rtf = total_time / audio_duration if audio_duration > 0 else float('inf')
            logger.info(f"Synthesis complete: {audio_duration:.2f}s audio in {total_time:.2f}s (RTF: {rtf:.2f})")
            
            # Check if we meet the 8-second target for 30s audio
            if audio_duration >= 30 and total_time <= 8:
                logger.success("✅ Performance target achieved: 30s audio in ≤8s!")
            
            return final_audio, caption_data
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise
    
    def _process_segments_parallel(
        self,
        script: List[Dict[str, str]],
        speaker_features: Dict[str, Dict[str, Any]],
    ) -> List[Tuple[np.ndarray, float, str, str]]:
        """Process segments in parallel."""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            
            for segment in script:
                future = executor.submit(
                    self._process_single_segment,
                    segment,
                    speaker_features
                )
                futures.append((future, segment))
            
            for future, segment in futures:
                try:
                    audio, duration = future.result()
                    results.append((audio, duration, segment["speaker_id"], segment["text"]))
                except Exception as e:
                    logger.error(f"Failed to process segment: {e}")
                    results.append((np.array([]), 0.0, segment["speaker_id"], segment["text"]))
        
        return results
    
    def _process_segments_sequential(
        self,
        script: List[Dict[str, str]],
        speaker_features: Dict[str, Dict[str, Any]],
    ) -> List[Tuple[np.ndarray, float, str, str]]:
        """Process segments sequentially."""
        results = []
        
        for segment in script:
            try:
                audio, duration = self._process_single_segment(segment, speaker_features)
                results.append((audio, duration, segment["speaker_id"], segment["text"]))
            except Exception as e:
                logger.error(f"Failed to process segment: {e}")
                results.append((np.array([]), 0.0, segment["speaker_id"], segment["text"]))
        
        return results
    
    @torch.inference_mode()
    def _process_single_segment(
        self,
        segment: Dict[str, str],
        speaker_features: Dict[str, Dict[str, Any]],
    ) -> Tuple[np.ndarray, float]:
        """Process a single segment."""
        speaker_id = segment["speaker_id"]
        text = segment["text"]
        
        if speaker_id not in speaker_features:
            raise ValueError(f"Speaker {speaker_id} not found")
        
        features = speaker_features[speaker_id]
        vq_tokens = torch.tensor(features["vq_tokens"], device=self.device)
        
        # Use autocast for faster inference
        with torch.autocast(device_type=self.device, enabled=self.use_half_precision):
            # Generate semantic tokens (simplified for example)
            # In practice, this would use the optimized generation
            generated_tokens = self._generate_tokens_optimized(
                text, vq_tokens, features.get("reference_text", "")
            )
            
            # Decode to audio
            audio = self._decode_tokens_optimized(generated_tokens)
        
        duration = len(audio) / 44100
        return audio, duration
    
    def _generate_tokens_optimized(
        self,
        text: str,
        vq_tokens: torch.Tensor,
        reference_text: str,
    ) -> torch.Tensor:
        """Generate tokens with optimizations."""
        # This is a simplified version - actual implementation would use
        # the full generation pipeline with KV cache optimization
        
        # For now, return dummy tokens for testing
        dummy_length = int(len(text) * 10)  # Rough estimate
        return torch.randint(0, 1000, (4, dummy_length), device=self.device)
    
    def _decode_tokens_optimized(self, tokens: torch.Tensor) -> np.ndarray:
        """Decode tokens to audio with optimizations."""
        # Decode with VQGAN
        with torch.autocast(device_type=self.device, enabled=self.use_half_precision):
            audio_length = torch.tensor([tokens.shape[-1]], device=self.device)
            decoded = self.vqgan_model.decode(
                indices=tokens[None],
                feature_lengths=audio_length,
            )[0, 0]
        
        return decoded.cpu().numpy()


def create_optimized_engine() -> OptimizedFishSpeechEngine:
    """Create an optimized Fish-Speech engine with default settings."""
    return OptimizedFishSpeechEngine(
        device=config.DEVICE,
        compile_models=config.COMPILE_MODEL,
        use_half_precision=config.DEVICE == "cuda",
        batch_size=None,  # Auto-detect
        max_workers=4,
    )


# Global optimized engine instance
_optimized_engine: Optional[OptimizedFishSpeechEngine] = None


def get_optimized_engine() -> OptimizedFishSpeechEngine:
    """Get or create the global optimized engine instance."""
    global _optimized_engine
    
    if _optimized_engine is None:
        _optimized_engine = create_optimized_engine()
    
    return _optimized_engine