#!/usr/bin/env python3
"""Create test audio files for speaker registration."""

import os
import numpy as np
import wave
import sys

def create_sine_wave_audio(filename, duration_sec=30, sample_rate=44100, frequency=440):
    """Create a sine wave audio file for testing.
    
    Note: This creates synthetic audio for testing only.
    For best results, use real voice recordings.
    """
    # Generate sine wave
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec))
    audio_data = np.sin(2 * np.pi * frequency * t)
    
    # Add some variation to make it more interesting
    # Add harmonics
    audio_data += 0.3 * np.sin(2 * np.pi * frequency * 2 * t)
    audio_data += 0.2 * np.sin(2 * np.pi * frequency * 3 * t)
    
    # Add envelope
    envelope = np.exp(-t / (duration_sec * 0.8))
    audio_data *= envelope
    
    # Normalize
    audio_data = audio_data / np.max(np.abs(audio_data))
    audio_data = (audio_data * 32767).astype(np.int16)
    
    # Write WAV file
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)   # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    
    print(f"✅ Created: {filename} ({duration_sec}s, {sample_rate}Hz)")


def main():
    print("🎵 Creating Test Audio Files for VoiceReel")
    print("=" * 50)
    print("⚠️  Note: These are synthetic test files.")
    print("   For best TTS results, use real voice recordings!")
    print()
    
    # Create test_audio directory
    os.makedirs("test_audio", exist_ok=True)
    
    # Create test audio files
    create_sine_wave_audio("test_audio/speaker1_male.wav", 
                          duration_sec=35, 
                          frequency=220)  # Lower frequency for "male"
    
    create_sine_wave_audio("test_audio/speaker2_female.wav", 
                          duration_sec=35, 
                          frequency=440)  # Higher frequency for "female"
    
    # Create matching transcript files
    with open("test_audio/speaker1_script.txt", "w", encoding="utf-8") as f:
        f.write("안녕하세요. 저는 첫 번째 화자입니다. 오늘은 날씨가 정말 좋네요. "
                "이 음성은 제 목소리 샘플입니다. 테스트를 위한 음성 파일입니다. "
                "약 30초 정도의 길이로 녹음되었습니다. 감사합니다.")
    print("✅ Created: test_audio/speaker1_script.txt")
    
    with open("test_audio/speaker2_script.txt", "w", encoding="utf-8") as f:
        f.write("반갑습니다. 저는 두 번째 화자예요. 맞아요, 정말 화창한 날씨네요. "
                "제 목소리도 잘 들리시나요? 이 파일은 음성 합성 테스트용입니다. "
                "충분한 음성 샘플을 제공하기 위해 30초 이상 녹음했습니다.")
    print("✅ Created: test_audio/speaker2_script.txt")
    
    print("\n📁 Test files created in: test_audio/")
    print("\n🎯 Next steps:")
    print("   1. Replace these synthetic files with real voice recordings")
    print("   2. Run: python examples/test_register_speakers.py")
    print("   3. Run: python examples/test_dialogue.py")
    
    print("\n💡 Tips for recording real audio:")
    print("   - Use a quiet environment")
    print("   - Speak clearly and naturally")
    print("   - Record at least 30 seconds")
    print("   - Save as WAV format (44.1kHz, 16-bit)")
    print("   - Match the transcript to what you actually say")


if __name__ == "__main__":
    # Check if numpy is available
    try:
        import numpy as np
    except ImportError:
        print("❌ NumPy is required to create test audio files")
        print("   Install with: pip install numpy")
        sys.exit(1)
    
    main()