"""Fish-Speech model integration for VoiceReel."""

from __future__ import annotations

import json
import os
import tempfile
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from loguru import logger

# Fish-Speech imports
from fish_speech.models.text2semantic.inference import (
    load_model as load_text2semantic_model,
    generate_long,
    encode_tokens,
)
from fish_speech.models.vqgan.inference import load_model as load_vqgan_model
from fish_speech.inference_engine.reference_loader import ReferenceLoader
from fish_speech.tokenizer import FishTokenizer


class FishSpeechEngine:
    """Fish-Speech TTS engine for VoiceReel."""
    
    def __init__(
        self,
        llama_checkpoint_path: str,
        vqgan_checkpoint_path: str,
        vqgan_config_name: str = "firefly_gan_vq",
        device: str = "cuda",
        precision: str = "half",
        compile_model: bool = False,
        sample_rate: int = 44100,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.precision = torch.float16 if precision == "half" else torch.float32
        
        logger.info(f"Initializing Fish-Speech engine on {device}")
        
        # Load models
        self.llama_model, self.decode_one_token = self._load_llama_model(
            llama_checkpoint_path, compile_model
        )
        self.vqgan_model = self._load_vqgan_model(
            vqgan_config_name, vqgan_checkpoint_path
        )
        
        # Initialize tokenizer from LLaMA checkpoint
        tokenizer_path = f"{llama_checkpoint_path}/tokenizer.tiktoken"
        self.tokenizer = FishTokenizer(tokenizer_path)
        
        # Initialize reference loader for audio processing
        self.reference_loader = ReferenceLoader()
        
        logger.info("Fish-Speech engine initialized successfully")
    
    def _load_llama_model(
        self, checkpoint_path: str, compile_model: bool = False
    ) -> Tuple[Any, Any]:
        """Load the text-to-semantic LLaMA model."""
        try:
            model, decode_fn = load_text2semantic_model(
                checkpoint_path=checkpoint_path,
                device=self.device,
                precision=self.precision,
                compile=compile_model,
            )
            logger.info(f"Loaded LLaMA model from {checkpoint_path}")
            return model, decode_fn
        except Exception as e:
            logger.error(f"Failed to load LLaMA model: {e}")
            raise
    
    def _load_vqgan_model(self, config_name: str, checkpoint_path: str) -> Any:
        """Load the VQGAN audio codec model."""
        try:
            model = load_vqgan_model(
                config_name=config_name,
                checkpoint_path=checkpoint_path,
                device=self.device,
            )
            logger.info(f"Loaded VQGAN model from {checkpoint_path}")
            return model
        except Exception as e:
            logger.error(f"Failed to load VQGAN model: {e}")
            raise
    
    def extract_speaker_features(
        self, 
        audio_path: str, 
        reference_text: str
    ) -> Dict[str, Any]:
        """
        Extract speaker features from reference audio.
        
        Args:
            audio_path: Path to reference audio file
            reference_text: Transcription of reference audio
            
        Returns:
            Dict containing speaker features and metadata
        """
        try:
            # Load and preprocess audio
            audio_data = self.reference_loader.load_audio(audio_path, self.sample_rate)
            
            # Convert to tensor and encode with VQGAN
            audio_tensor = torch.from_numpy(audio_data).to(self.device)
            audio_tensor = audio_tensor[None, None, :]  # Add batch and channel dims
            
            # Get audio length
            audio_length = torch.tensor([audio_data.shape[0]], device=self.device)
            
            # Encode audio to VQ tokens
            with torch.no_grad():
                encoded_audio = self.vqgan_model.encode(audio_tensor, audio_length)
                vq_tokens = encoded_audio[0][0]  # Extract tokens
            
            # Encode reference text
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
                "audio_duration": len(audio_data) / self.sample_rate,
                "sample_rate": self.sample_rate,
            }
            
            logger.info(f"Extracted features for audio duration: {features['audio_duration']:.2f}s")
            return features
            
        except Exception as e:
            logger.error(f"Failed to extract speaker features: {e}")
            raise
    
    def synthesize_speech(
        self,
        script: List[Dict[str, str]],
        speaker_features: Dict[str, Dict[str, Any]],
        output_format: str = "wav",
        max_new_tokens: int = 2048,
        top_p: float = 0.7,
        temperature: float = 0.7,
        repetition_penalty: float = 1.5,
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Synthesize multi-speaker speech from script.
        
        Args:
            script: List of {"speaker_id": str, "text": str} segments
            speaker_features: Dict mapping speaker_id to their extracted features
            output_format: Output audio format
            max_new_tokens: Maximum tokens to generate
            top_p: Top-p sampling parameter
            temperature: Temperature for sampling
            repetition_penalty: Repetition penalty
            
        Returns:
            Tuple of (audio_array, caption_data)
        """
        try:
            all_audio_segments = []
            caption_data = []
            current_time = 0.0
            
            for segment in script:
                speaker_id = segment["speaker_id"]
                text = segment["text"]
                
                if speaker_id not in speaker_features:
                    raise ValueError(f"Speaker {speaker_id} not found in speaker_features")
                
                # Get speaker's VQ tokens
                features = speaker_features[speaker_id]
                vq_tokens = torch.tensor(features["vq_tokens"], device=self.device)
                reference_text = features.get("reference_text", "")
                
                # Generate semantic tokens from text
                logger.info(f"Generating speech for speaker {speaker_id}: '{text[:50]}...'")
                
                # Prepare prompt tokens (speaker conditioning)
                prompt_tokens = [vq_tokens] if vq_tokens.numel() > 0 else None
                prompt_text = [reference_text] if reference_text else None
                
                # Generate semantic tokens
                generated_tokens = []
                for response in generate_long(
                    model=self.llama_model,
                    device=self.device,
                    decode_one_token=self.decode_one_token,
                    text=text,
                    prompt_tokens=prompt_tokens,
                    prompt_text=prompt_text,
                    max_new_tokens=max_new_tokens,
                    top_p=top_p,
                    temperature=temperature,
                    repetition_penalty=repetition_penalty,
                ):
                    if hasattr(response, 'tokens'):
                        generated_tokens.append(response.tokens)
                
                if not generated_tokens:
                    logger.warning(f"No tokens generated for segment: {text}")
                    continue
                
                # Concatenate all generated tokens
                semantic_tokens = torch.cat(generated_tokens, dim=-1)
                
                # Decode to audio using VQGAN
                with torch.no_grad():
                    audio_length = torch.tensor([semantic_tokens.shape[-1]], device=self.device)
                    decoded_audio = self.vqgan_model.decode(
                        indices=semantic_tokens[None],  # Add batch dim
                        feature_lengths=audio_length,
                    )[0, 0]  # Remove batch and channel dims
                
                # Convert to numpy
                audio_segment = decoded_audio.cpu().numpy()
                segment_duration = len(audio_segment) / self.sample_rate
                
                # Add caption data
                caption_data.append({
                    "start": current_time,
                    "end": current_time + segment_duration,
                    "speaker": speaker_id,
                    "text": text,
                })
                
                all_audio_segments.append(audio_segment)
                current_time += segment_duration
                
                logger.info(f"Generated {segment_duration:.2f}s audio for speaker {speaker_id}")
            
            # Concatenate all audio segments
            if all_audio_segments:
                final_audio = np.concatenate(all_audio_segments)
            else:
                final_audio = np.array([])
            
            logger.info(f"Synthesis complete. Total duration: {current_time:.2f}s")
            return final_audio, caption_data
            
        except Exception as e:
            logger.error(f"Failed to synthesize speech: {e}")
            raise
    
    def save_audio(
        self, 
        audio_data: np.ndarray, 
        output_path: str, 
        format: str = "wav"
    ) -> str:
        """Save audio data to file."""
        try:
            import soundfile as sf
            
            # Ensure audio is in the right format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Normalize audio to prevent clipping
            max_val = np.abs(audio_data).max()
            if max_val > 1.0:
                audio_data = audio_data / max_val
            
            # Save audio file
            sf.write(output_path, audio_data, self.sample_rate, format=format.upper())
            logger.info(f"Saved audio to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise
    
    def estimate_processing_time(self, text_length: int) -> float:
        """Estimate processing time based on text length."""
        # Rough estimate: ~0.1-0.2 seconds per character
        base_time = text_length * 0.15
        # Add model overhead
        overhead = 2.0
        return base_time + overhead
    
    def cleanup_temp_files(self, temp_paths: List[str]) -> None:
        """Clean up temporary files."""
        for path in temp_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {path}: {e}")


class SpeakerManager:
    """Manages speaker registrations and features."""
    
    def __init__(self, storage_path: str = "/tmp/voicereel_speakers"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
    
    def save_speaker_features(
        self, 
        speaker_id: int, 
        features: Dict[str, Any]
    ) -> str:
        """Save speaker features to disk."""
        feature_path = self.storage_path / f"speaker_{speaker_id}.json"
        
        try:
            with open(feature_path, 'w') as f:
                json.dump(features, f, indent=2)
            logger.info(f"Saved speaker {speaker_id} features to {feature_path}")
            return str(feature_path)
        except Exception as e:
            logger.error(f"Failed to save speaker features: {e}")
            raise
    
    def load_speaker_features(self, speaker_id: int) -> Dict[str, Any]:
        """Load speaker features from disk."""
        feature_path = self.storage_path / f"speaker_{speaker_id}.json"
        
        try:
            with open(feature_path, 'r') as f:
                features = json.load(f)
            logger.info(f"Loaded speaker {speaker_id} features")
            return features
        except Exception as e:
            logger.error(f"Failed to load speaker features: {e}")
            raise
    
    def delete_speaker_features(self, speaker_id: int) -> bool:
        """Delete speaker features from disk."""
        feature_path = self.storage_path / f"speaker_{speaker_id}.json"
        
        try:
            if feature_path.exists():
                feature_path.unlink()
                logger.info(f"Deleted speaker {speaker_id} features")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete speaker features: {e}")
            return False


# Global engine instance (initialized when needed)
_fish_speech_engine: Optional[FishSpeechEngine] = None
_speaker_manager: Optional[SpeakerManager] = None


def get_fish_speech_engine(
    llama_checkpoint_path: Optional[str] = None,
    vqgan_checkpoint_path: Optional[str] = None,
    **kwargs
) -> FishSpeechEngine:
    """Get global Fish-Speech engine instance."""
    global _fish_speech_engine
    
    if _fish_speech_engine is None:
        from .config import config
        
        # Use provided paths or config defaults
        llama_path = llama_checkpoint_path or config.FISH_SPEECH_LLAMA_PATH
        vqgan_path = vqgan_checkpoint_path or config.FISH_SPEECH_VQGAN_PATH
        
        # Check if models exist
        if not os.path.exists(llama_path):
            raise FileNotFoundError(f"LLaMA model not found: {llama_path}")
        if not os.path.exists(vqgan_path):
            raise FileNotFoundError(f"VQGAN model not found: {vqgan_path}")
        
        # Merge config with kwargs
        engine_kwargs = {
            "device": config.DEVICE,
            "precision": config.PRECISION,
            "compile_model": config.COMPILE_MODEL,
            "sample_rate": config.SAMPLE_RATE,
            "vqgan_config_name": config.FISH_SPEECH_VQGAN_CONFIG,
        }
        engine_kwargs.update(kwargs)
        
        _fish_speech_engine = FishSpeechEngine(
            llama_checkpoint_path=llama_path,
            vqgan_checkpoint_path=vqgan_path,
            **engine_kwargs
        )
    
    return _fish_speech_engine


def get_speaker_manager() -> SpeakerManager:
    """Get global speaker manager instance."""
    global _speaker_manager
    
    if _speaker_manager is None:
        from .config import config
        _speaker_manager = SpeakerManager(config.SPEAKER_STORAGE_PATH)
    
    return _speaker_manager