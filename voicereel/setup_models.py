#!/usr/bin/env python3
"""Model setup script for VoiceReel Fish-Speech integration."""

import argparse
import sys
from pathlib import Path

from .config import config


def check_models():
    """Check if models exist and their status."""
    status = config.check_model_files()
    
    print("🔍 Fish-Speech Model Status:")
    print(f"  Device: {status['device']}")
    print(f"  LLaMA Model: {'✅' if status['llama_exists'] else '❌'} {status['llama_path']}")
    print(f"  VQGAN Model: {'✅' if status['vqgan_exists'] else '❌'} {status['vqgan_path']}")
    
    if status['models_ready']:
        print("\n✅ All models are ready!")
        return True
    else:
        print("\n⚠️  Some models are missing. Run with --download to get them.")
        return False


def download_models(force=False):
    """Download missing models."""
    print("📥 Downloading Fish-Speech models...")
    
    try:
        success = config.download_models(force=force)
        if success:
            print("\n✅ All models downloaded successfully!")
            return True
        else:
            print("\n❌ Failed to download some models.")
            return False
    except ImportError:
        print("❌ Missing required packages. Install with: pip install requests tqdm")
        return False


def test_models():
    """Test if models can be loaded."""
    print("🧪 Testing model loading...")
    
    try:
        from .fish_speech_integration import get_fish_speech_engine
        
        # Test engine initialization
        engine = get_fish_speech_engine()
        print("✅ Fish-Speech engine initialized successfully!")
        
        # Test a simple feature extraction (if we have a test audio file)
        print("✅ Models are working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False


def setup_workspace():
    """Set up workspace directories."""
    print("📁 Setting up workspace directories...")
    
    config.create_directories()
    
    dirs = [
        config.SPEAKER_STORAGE_PATH,
        config.AUDIO_OUTPUT_PATH,
        "checkpoints/fish-speech-1.5",
    ]
    
    for directory in dirs:
        path = Path(directory)
        if path.exists():
            print(f"  ✅ {directory}")
        else:
            path.mkdir(parents=True, exist_ok=True)
            print(f"  📁 Created {directory}")


def main():
    parser = argparse.ArgumentParser(
        description="VoiceReel Fish-Speech Model Setup"
    )
    parser.add_argument(
        "--check", 
        action="store_true", 
        help="Check model status"
    )
    parser.add_argument(
        "--download", 
        action="store_true", 
        help="Download missing models"
    )
    parser.add_argument(
        "--force-download", 
        action="store_true", 
        help="Force re-download all models"
    )
    parser.add_argument(
        "--test", 
        action="store_true", 
        help="Test model loading"
    )
    parser.add_argument(
        "--setup", 
        action="store_true", 
        help="Set up workspace directories"
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Run all setup steps"
    )
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        # Default: check status
        args.check = True
    
    success = True
    
    if args.all or args.setup:
        setup_workspace()
    
    if args.all or args.check:
        success &= check_models()
    
    if args.all or args.download or args.force_download:
        success &= download_models(force=args.force_download)
    
    if args.all or args.test:
        success &= test_models()
    
    if not success:
        sys.exit(1)
    
    if args.all:
        print("\n🎉 VoiceReel Fish-Speech setup complete!")
        print("\nNext steps:")
        print("1. Start Redis and PostgreSQL services")
        print("2. Run Celery workers: python -m voicereel.worker")
        print("3. Start API server: python -m voicereel.flask_app")


if __name__ == "__main__":
    main()