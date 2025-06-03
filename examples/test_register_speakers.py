#!/usr/bin/env python3
"""Register two speakers for dialogue testing."""

import requests
import time
import sys

API_URL = "http://localhost:8080"
API_KEY = "test-api-key-12345"

headers = {
    "X-VR-APIKEY": API_KEY
}

def register_speaker(name, lang, audio_path, script_path):
    """Register a single speaker."""
    try:
        with open(audio_path, "rb") as audio_file:
            with open(script_path, "r", encoding="utf-8") as script_file:
                files = {
                    "reference_audio": (audio_path.split("/")[-1], audio_file, "audio/wav"),
                }
                data = {
                    "name": name,
                    "lang": lang,
                    "reference_script": script_file.read()
                }
                
                response = requests.post(
                    f"{API_URL}/v1/speakers",
                    headers=headers,
                    files=files,
                    data=data
                )
                
                if response.status_code == 202:
                    job_id = response.json()["job_id"]
                    print(f"✅ Speaker '{name}' registration started: {job_id}")
                    return job_id
                else:
                    print(f"❌ Failed to register '{name}': {response.text}")
                    return None
                    
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        return None
    except Exception as e:
        print(f"❌ Error registering speaker: {e}")
        return None


def wait_for_jobs(job_ids):
    """Wait for registration jobs to complete."""
    print("\n⏳ Waiting for speaker registration to complete...")
    
    for i in range(30):  # Wait up to 30 seconds
        all_done = True
        for job_id in job_ids:
            response = requests.get(f"{API_URL}/v1/jobs/{job_id}", headers=headers)
            if response.status_code == 200:
                status = response.json()["status"]
                if status == "pending" or status == "processing":
                    all_done = False
                elif status == "failed":
                    print(f"❌ Job {job_id} failed: {response.json().get('error', 'Unknown error')}")
            else:
                print(f"❌ Failed to check job {job_id}: {response.text}")
        
        if all_done:
            break
        
        time.sleep(1)
        sys.stdout.write(".")
        sys.stdout.flush()
    
    print("\n")


def main():
    print("🎤 VoiceReel Speaker Registration Test")
    print("=" * 50)
    
    # Check if API is accessible
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code != 200:
            print("❌ VoiceReel API is not accessible at", API_URL)
            print("Please start the server first:")
            print("  python -m voicereel.server_postgres")
            return
    except:
        print("❌ Cannot connect to VoiceReel API at", API_URL)
        print("Please start the server first:")
        print("  python -m voicereel.server_postgres")
        return
    
    # Register speakers
    job_ids = []
    
    # Speaker 1: Male anchor
    job_id = register_speaker(
        name="김민수 (남성 앵커)",
        lang="ko",
        audio_path="test_audio/speaker1_male.wav",
        script_path="test_audio/speaker1_script.txt"
    )
    if job_id:
        job_ids.append(job_id)
    
    # Speaker 2: Female host
    job_id = register_speaker(
        name="이수진 (여성 진행자)",
        lang="ko", 
        audio_path="test_audio/speaker2_female.wav",
        script_path="test_audio/speaker2_script.txt"
    )
    if job_id:
        job_ids.append(job_id)
    
    if not job_ids:
        print("\n❌ No speakers were registered successfully")
        return
    
    # Wait for completion
    wait_for_jobs(job_ids)
    
    # Get speaker list
    response = requests.get(f"{API_URL}/v1/speakers", headers=headers)
    if response.status_code == 200:
        speakers = response.json()["speakers"]
        print("✅ Registered speakers:")
        for speaker in speakers:
            print(f"   - {speaker['name']}: {speaker['id']}")
            print(f"     Language: {speaker['lang']}")
            print(f"     Created: {speaker['created_at']}")
        
        print(f"\n📝 Total speakers: {len(speakers)}")
        print("\n🎯 Next step: Run test_dialogue.py to test multi-speaker synthesis")
    else:
        print(f"❌ Failed to get speaker list: {response.text}")


if __name__ == "__main__":
    main()