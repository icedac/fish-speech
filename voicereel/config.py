"""VoiceReel configuration settings."""

import os
from pathlib import Path
from typing import Optional


class VoiceReelConfig:
    """VoiceReel configuration management."""
    
    # Model paths
    FISH_SPEECH_LLAMA_PATH: str = os.getenv(
        "FISH_SPEECH_LLAMA_PATH",
        "checkpoints/fish-speech-1.5/text2semantic-finetune-medium-en+de+zh+ja+ko-2.pth"
    )
    
    FISH_SPEECH_VQGAN_PATH: str = os.getenv(
        "FISH_SPEECH_VQGAN_PATH", 
        "checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
    )
    
    FISH_SPEECH_VQGAN_CONFIG: str = os.getenv(
        "FISH_SPEECH_VQGAN_CONFIG",
        "firefly_gan_vq"
    )
    
    # Device configuration
    DEVICE: str = os.getenv("FISH_SPEECH_DEVICE", "cuda" if os.system("nvidia-smi") == 0 else "cpu")
    PRECISION: str = os.getenv("FISH_SPEECH_PRECISION", "half")
    COMPILE_MODEL: bool = os.getenv("FISH_SPEECH_COMPILE", "false").lower() == "true"
    
    # Audio settings
    SAMPLE_RATE: int = int(os.getenv("VOICEREEL_SAMPLE_RATE", "44100"))
    
    # Generation parameters
    MAX_NEW_TOKENS: int = int(os.getenv("FISH_SPEECH_MAX_TOKENS", "2048"))
    TOP_P: float = float(os.getenv("FISH_SPEECH_TOP_P", "0.7"))
    TEMPERATURE: float = float(os.getenv("FISH_SPEECH_TEMPERATURE", "0.7"))
    REPETITION_PENALTY: float = float(os.getenv("FISH_SPEECH_REP_PENALTY", "1.5"))
    
    # Storage paths
    SPEAKER_STORAGE_PATH: str = os.getenv(
        "VOICEREEL_SPEAKER_STORAGE", 
        "/tmp/voicereel_speakers"
    )
    
    AUDIO_OUTPUT_PATH: str = os.getenv(
        "VOICEREEL_AUDIO_OUTPUT",
        "/tmp/voicereel_audio"
    )
    
    # S3 Storage settings
    S3_BUCKET_NAME: str = os.getenv("VOICEREEL_S3_BUCKET", "voicereel-audio")
    S3_USE_LOCAL_FALLBACK: bool = os.getenv("VOICEREEL_S3_FALLBACK", "true").lower() == "true"
    S3_DEFAULT_EXPIRES_HOURS: int = int(os.getenv("VOICEREEL_S3_EXPIRES_HOURS", "48"))
    S3_PRESIGNED_URL_EXPIRES: int = int(os.getenv("VOICEREEL_S3_PRESIGNED_EXPIRES", "900"))  # 15 minutes
    
    # Model download URLs (for automatic setup)
    MODEL_DOWNLOAD_URLS = {
        "llama": "https://huggingface.co/fishaudio/fish-speech-1.5/resolve/main/text2semantic-finetune-medium-en+de+zh+ja+ko-2.pth",
        "vqgan": "https://huggingface.co/fishaudio/fish-speech-1.5/resolve/main/firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
    }
    
    @classmethod
    def check_model_files(cls) -> dict:
        """Check if model files exist and return status."""
        status = {
            "llama_exists": Path(cls.FISH_SPEECH_LLAMA_PATH).exists(),
            "vqgan_exists": Path(cls.FISH_SPEECH_VQGAN_PATH).exists(),
            "device": cls.DEVICE,
            "llama_path": cls.FISH_SPEECH_LLAMA_PATH,
            "vqgan_path": cls.FISH_SPEECH_VQGAN_PATH,
        }
        
        status["models_ready"] = status["llama_exists"] and status["vqgan_exists"]
        return status
    
    @classmethod
    def create_directories(cls) -> None:
        """Create necessary directories."""
        Path(cls.SPEAKER_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        Path(cls.AUDIO_OUTPUT_PATH).mkdir(parents=True, exist_ok=True)
        
        # Create checkpoints directory if needed
        checkpoints_dir = Path("checkpoints/fish-speech-1.5")
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def download_models(cls, force: bool = False) -> bool:
        """Download model files if they don't exist."""
        import requests
        from tqdm import tqdm
        
        models_to_download = []
        
        if force or not Path(cls.FISH_SPEECH_LLAMA_PATH).exists():
            models_to_download.append(("llama", cls.FISH_SPEECH_LLAMA_PATH))
            
        if force or not Path(cls.FISH_SPEECH_VQGAN_PATH).exists():
            models_to_download.append(("vqgan", cls.FISH_SPEECH_VQGAN_PATH))
        
        if not models_to_download:
            print("All models already exist.")
            return True
        
        cls.create_directories()
        
        for model_type, model_path in models_to_download:
            url = cls.MODEL_DOWNLOAD_URLS[model_type]
            print(f"Downloading {model_type} model to {model_path}...")
            
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                
                with open(model_path, 'wb') as f, tqdm(
                    desc=f"Downloading {model_type}",
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
                
                print(f"✅ Downloaded {model_type} model successfully")
                
            except Exception as e:
                print(f"❌ Failed to download {model_type} model: {e}")
                if Path(model_path).exists():
                    Path(model_path).unlink()  # Remove partial file
                return False
        
        return True


# Global config instance
config = VoiceReelConfig()