#!/usr/bin/env python3
"""Test two-speaker dialogue synthesis."""

import requests
import json
import time
import subprocess
import sys
import os

API_URL = "http://localhost:8080"
API_KEY = "test-api-key-12345"

headers = {
    "X-VR-APIKEY": API_KEY,
    "Content-Type": "application/json"
}

# Sample dialogue script
WEATHER_DIALOGUE = [
    ("speaker1", "안녕하세요, 시청자 여러분. 오늘의 날씨를 전해드리겠습니다."),
    ("speaker2", "네, 안녕하세요. 오늘은 전국적으로 맑은 날씨가 이어지겠습니다."),
    ("speaker1", "그렇군요. 미세먼지 상황은 어떤가요?"),
    ("speaker2", "다행히 미세먼지 농도는 '좋음' 수준을 유지하고 있어요. 야외 활동하기 좋은 날씨입니다."),
    ("speaker1", "좋은 소식이네요. 이번 주말 날씨는 어떨까요?"),
    ("speaker2", "주말에도 화창한 날씨가 계속될 예정입니다. 나들이 계획이 있으신 분들께는 희소식이네요."),
    ("speaker1", "감사합니다. 좋은 하루 보내세요!"),
    ("speaker2", "네, 여러분도 즐거운 하루 되세요!")
]

CASUAL_DIALOGUE = [
    ("speaker1", "오랜만이야! 어떻게 지냈어?"),
    ("speaker2", "잘 지냈지! 너는 어때?"),
    ("speaker1", "나도 잘 지냈어. 요즘 뭐하고 지내?"),
    ("speaker2", "새로운 프로젝트 준비하고 있어. 인공지능 관련된 거야."),
    ("speaker1", "오, 흥미롭네! 어떤 프로젝트인데?"),
    ("speaker2", "음성 합성 기술을 활용한 서비스를 만들고 있어."),
    ("speaker1", "대단하다! 나중에 자세히 들려줘."),
    ("speaker2", "그래, 꼭 얘기해줄게!")
]


def get_speakers():
    """Get list of registered speakers."""
    response = requests.get(f"{API_URL}/v1/speakers", headers=headers)
    if response.status_code == 200:
        return response.json()["speakers"]
    else:
        print(f"❌ Failed to get speakers: {response.text}")
        return []


def create_dialogue_script(dialogue, speaker_mapping):
    """Create dialogue script with speaker IDs."""
    script = []
    for speaker_key, text in dialogue:
        if speaker_key in speaker_mapping:
            script.append({
                "speaker_id": speaker_mapping[speaker_key],
                "text": text
            })
        else:
            print(f"⚠️  Warning: Speaker '{speaker_key}' not found in mapping")
    return script


def synthesize_dialogue(script, output_filename="dialogue_output"):
    """Request dialogue synthesis."""
    synthesis_request = {
        "script": script,
        "output_format": "wav",
        "sample_rate": 44100,
        "caption_format": "vtt"
    }
    
    print("🎙️  Requesting dialogue synthesis...")
    response = requests.post(
        f"{API_URL}/v1/synthesize",
        headers=headers,
        json=synthesis_request
    )
    
    if response.status_code == 202:
        job_id = response.json()["job_id"]
        print(f"✅ Synthesis job created: {job_id}")
        
        # Poll for completion
        start_time = time.time()
        while True:
            time.sleep(2)
            response = requests.get(f"{API_URL}/v1/jobs/{job_id}", headers=headers)
            job_status = response.json()
            
            elapsed = time.time() - start_time
            print(f"⏳ Status: {job_status['status']} ({elapsed:.1f}s)")
            
            if job_status["status"] == "succeeded":
                return process_results(job_status, output_filename)
                
            elif job_status["status"] == "failed":
                print(f"❌ Synthesis failed: {job_status.get('error', 'Unknown error')}")
                return False
                
            elif elapsed > 300:  # 5 minute timeout
                print("❌ Synthesis timeout (5 minutes)")
                return False
    else:
        print(f"❌ Request failed: {response.text}")
        return False


def process_results(job_status, output_filename):
    """Download and save synthesis results."""
    audio_url = job_status["audio_url"]
    
    print(f"\n✅ Synthesis completed!")
    print(f"📍 Audio URL: {audio_url}")
    
    # Download audio file
    audio_response = requests.get(audio_url)
    audio_file = f"{output_filename}.wav"
    with open(audio_file, "wb") as f:
        f.write(audio_response.content)
    print(f"💾 Audio saved as: {audio_file}")
    
    # Save captions if available
    if "captions" in job_status:
        caption_file = f"{output_filename}.vtt"
        with open(caption_file, "w", encoding="utf-8") as f:
            f.write(job_status["captions"])
        print(f"📝 Captions saved as: {caption_file}")
    
    # Display dialogue timing
    if "caption_data" in job_status:
        print("\n🎬 Dialogue Timing:")
        for caption in job_status["caption_data"]:
            print(f"   {caption['start']:6.2f}s - {caption['end']:6.2f}s : {caption['text']}")
    
    return audio_file


def play_audio(audio_file):
    """Play the generated audio file."""
    print(f"\n🔊 Playing audio: {audio_file}")
    
    try:
        if sys.platform == "darwin":  # macOS
            subprocess.run(["afplay", audio_file])
        elif sys.platform == "linux":  # Linux
            if subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
                subprocess.run(["aplay", audio_file])
            elif subprocess.run(["which", "paplay"], capture_output=True).returncode == 0:
                subprocess.run(["paplay", audio_file])
            else:
                print("ℹ️  No audio player found. Please play the file manually.")
        elif sys.platform == "win32":  # Windows
            os.startfile(audio_file)
        else:
            print("ℹ️  Please play the audio file manually.")
    except Exception as e:
        print(f"ℹ️  Could not play audio automatically: {e}")
        print("   Please play the file manually.")


def main():
    print("🎭 VoiceReel Two-Speaker Dialogue Test")
    print("=" * 50)
    
    # Check if API is accessible
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code != 200:
            print("❌ VoiceReel API is not accessible at", API_URL)
            return
    except:
        print("❌ Cannot connect to VoiceReel API at", API_URL)
        return
    
    # Get speakers
    speakers = get_speakers()
    if len(speakers) < 2:
        print(f"❌ Need at least 2 speakers, found {len(speakers)}")
        print("   Please run test_register_speakers.py first")
        return
    
    print("\n📢 Available speakers:")
    for i, speaker in enumerate(speakers):
        print(f"   {i+1}. {speaker['name']} ({speaker['id']}) - {speaker['lang']}")
    
    # Create speaker mapping
    speaker_mapping = {
        "speaker1": speakers[0]["id"],
        "speaker2": speakers[1]["id"]
    }
    
    print(f"\n🎬 Using speakers:")
    print(f"   Speaker 1: {speakers[0]['name']}")
    print(f"   Speaker 2: {speakers[1]['name']}")
    
    # Choose dialogue
    print("\n📖 Select dialogue:")
    print("   1. Weather forecast (formal)")
    print("   2. Casual conversation (informal)")
    
    choice = input("\nEnter choice (1 or 2, default=1): ").strip()
    
    if choice == "2":
        dialogue = CASUAL_DIALOGUE
        output_name = "casual_dialogue"
        print("\n🗣️  Selected: Casual conversation")
    else:
        dialogue = WEATHER_DIALOGUE
        output_name = "weather_dialogue"
        print("\n🗣️  Selected: Weather forecast")
    
    # Create script
    script = create_dialogue_script(dialogue, speaker_mapping)
    
    print(f"\n📜 Dialogue script ({len(script)} lines):")
    for i, line in enumerate(script):
        speaker_name = next(s['name'] for s in speakers if s['id'] == line['speaker_id'])
        print(f"   {i+1}. [{speaker_name}] {line['text']}")
    
    # Synthesize
    print("\n" + "=" * 50)
    audio_file = synthesize_dialogue(script, output_name)
    
    if audio_file:
        # Play audio
        play_choice = input("\n▶️  Play audio now? (y/n, default=y): ").strip().lower()
        if play_choice != 'n':
            play_audio(audio_file)
        
        print("\n✨ Test completed successfully!")
        print(f"   Audio file: {audio_file}")
        print(f"   Caption file: {output_name}.vtt")
    else:
        print("\n❌ Test failed")


if __name__ == "__main__":
    main()