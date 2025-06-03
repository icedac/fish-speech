<div align="center">
<h1>Fish Speech</h1>

**English** | [简体中文](docs/README.zh.md) | [Portuguese](docs/README.pt-BR.md) | [日本語](docs/README.ja.md) | [한국어](docs/README.ko.md) <br>

<a href="https://www.producthunt.com/posts/fish-speech-1-4?embed=true&utm_source=badge-featured&utm_medium=badge&utm_souce=badge-fish&#0045;speech&#0045;1&#0045;4" target="_blank">
    <img src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=488440&theme=light" alt="Fish&#0032;Speech&#0032;1&#0046;4 - Open&#0045;Source&#0032;Multilingual&#0032;Text&#0045;to&#0045;Speech&#0032;with&#0032;Voice&#0032;Cloning | Product Hunt" style="width: 250px; height: 54px;" width="250" height="54" />
</a>
<a href="https://trendshift.io/repositories/7014" target="_blank">
    <img src="https://trendshift.io/api/badge/repositories/7014" alt="fishaudio%2Ffish-speech | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/>
</a>
<br>
</div>
<br>

<div align="center">
    <img src="https://count.getloli.com/get/@fish-speech?theme=asoul" /><br>
</div>

<br>

<div align="center">
    <a target="_blank" href="https://discord.gg/Es5qTB9BcN">
        <img alt="Discord" src="https://img.shields.io/discord/1214047546020728892?color=%23738ADB&label=Discord&logo=discord&logoColor=white&style=flat-square"/>
    </a>
    <a target="_blank" href="https://hub.docker.com/r/fishaudio/fish-speech">
        <img alt="Docker" src="https://img.shields.io/docker/pulls/fishaudio/fish-speech?style=flat-square&logo=docker"/>
    </a>
    <a target="_blank" href="https://huggingface.co/spaces/fishaudio/fish-speech-1">
        <img alt="Huggingface" src="https://img.shields.io/badge/🤗%20-space%20demo-yellow"/>
    </a>
    <a target="_blank" href="https://pd.qq.com/s/bwxia254o">
      <img alt="QQ Channel" src="https://img.shields.io/badge/QQ-blue?logo=tencentqq">
    </a>
</div>

This codebase is released under Apache License and all model weights are released under CC-BY-NC-SA-4.0 License. Please refer to [LICENSE](LICENSE) for more details.

---
## Fish Agent
We are very excited to announce that we have made our self-research agent demo open source, you can now try our agent demo for instant English and Chinese chat locally by following the [docs](https://speech.fish.audio/start_agent/).

You should mention that the content is released under a **CC BY-NC-SA 4.0 licence**. And the demo is an early alpha test version, the inference speed needs to be optimised, and there are a lot of bugs waiting to be fixed. If you've found a bug or want to fix it, we'd be very happy to receive an issue or a pull request.

## Features
### Fish Speech

1. **Zero-shot & Few-shot TTS:** Input a 10 to 30-second vocal sample to generate high-quality TTS output. **For detailed guidelines, see [Voice Cloning Best Practices](https://docs.fish.audio/text-to-speech/voice-clone-best-practices).**

2. **Multilingual & Cross-lingual Support:** Simply copy and paste multilingual text into the input box—no need to worry about the language. Currently supports English, Japanese, Korean, Chinese, French, German, Arabic, and Spanish.

3. **No Phoneme Dependency:** The model has strong generalization capabilities and does not rely on phonemes for TTS. It can handle text in any language script.

4. **Highly Accurate:** Achieves a low CER (Character Error Rate) and WER (Word Error Rate) of around 2% for 5-minute English texts.

5. **Fast:** With fish-tech acceleration, the real-time factor is approximately 1:5 on an Nvidia RTX 4060 laptop and 1:15 on an Nvidia RTX 4090.

6. **WebUI Inference:** Features an easy-to-use, Gradio-based web UI compatible with Chrome, Firefox, Edge, and other browsers.

7. **GUI Inference:** Offers a PyQt6 graphical interface that works seamlessly with the API server. Supports Linux, Windows, and macOS. [See GUI](https://github.com/AnyaCoder/fish-speech-gui).

8. **Deploy-Friendly:** Easily set up an inference server with native support for Linux, Windows and MacOS, minimizing speed loss.

### Fish Agent
1. **Completely End to End:** Automatically integrates ASR and TTS parts, no need to plug-in other models, i.e., true end-to-end, not three-stage (ASR+LLM+TTS).

2. **Timbre Control:** Can use reference audio to control the speech timbre.

3. **Emotional:** The model can generate speech with strong emotion.

## Disclaimer

We do not hold any responsibility for any illegal usage of the codebase. Please refer to your local laws about DMCA and other related laws.

## Online Demo

[Fish Audio](https://fish.audio)

[Fish Agent](https://fish.audio/demo/live)

## Quick Start for Local Inference 

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://github.com/fishaudio/fish-speech/blob/main/inference.ipynb)

## Videos

#### V1.5 Demo Video: [Watch the video on X (Twitter).](https://x.com/FishAudio/status/1864370933496205728)

## Documents

- [English](https://speech.fish.audio/)
- [中文](https://speech.fish.audio/zh/)
- [日本語](https://speech.fish.audio/ja/)
- [Portuguese (Brazil)](https://speech.fish.audio/pt/)

## Samples (2024/10/02 V1.4)

- [English](https://speech.fish.audio/samples/)
- [中文](https://speech.fish.audio/zh/samples/)
- [日本語](https://speech.fish.audio/ja/samples/)
- [Portuguese (Brazil)](https://speech.fish.audio/pt/samples/)

## Credits

- [VITS2 (daniilrobnikov)](https://github.com/daniilrobnikov/vits2)
- [Bert-VITS2](https://github.com/fishaudio/Bert-VITS2)
- [GPT VITS](https://github.com/innnky/gpt-vits)
- [MQTTS](https://github.com/b04901014/MQTTS)
- [GPT Fast](https://github.com/pytorch-labs/gpt-fast)
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)

## Tech Report (V1.4)
```bibtex
@misc{fish-speech-v1.4,
      title={Fish-Speech: Leveraging Large Language Models for Advanced Multilingual Text-to-Speech Synthesis},
      author={Shijia Liao and Yuxuan Wang and Tianyu Li and Yifan Cheng and Ruoyi Zhang and Rongzhi Zhou and Yijin Xing},
      year={2024},
      eprint={2411.01156},
      archivePrefix={arXiv},
      primaryClass={cs.SD},
      url={https://arxiv.org/abs/2411.01156},
}
```

## Sponsor

<div>
  <a href="https://6block.com/">
    <img src="https://avatars.githubusercontent.com/u/60573493" width="100" height="100" alt="6Block Avatar"/>
  </a>
  <br>
  <a href="https://6block.com/">Data Processing sponsor by 6Block</a>
</div>



# Prerequisites
## Miniconda
- https://www.anaconda.com/docs/getting-started/miniconda/main

## Model Downloads
```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli download fishaudio/fish-speech-1.5 --local-dir checkpoints/fish-speech-1.5
```

## Basic Test
```bash
python -m tools.run_webui \
    --llama-checkpoint-path "checkpoints/fish-speech-1.5" \
    --decoder-checkpoint-path "checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth" \
    --decoder-config-name firefly_gan_vq
```

# Local Testing Guide (VoiceReel Multi-Speaker TTS)

## 🚀 Quick Start: Two-Speaker Dialogue Test

This guide will help you test VoiceReel's multi-speaker TTS locally with a two-person dialogue example.

### 1. Environment Setup

```bash
# Create conda environment
conda create -n voicereel python=3.10
conda activate voicereel

# Install dependencies
pip install -e ".[stable]"
pip install redis celery psycopg2-binary boto3

# Install Fish-Speech dependencies
pip install torch torchaudio transformers gradio loguru

# Download Fish-Speech models
huggingface-cli download fishaudio/fish-speech-1.5 --local-dir checkpoints/fish-speech-1.5
```

### 2. Start Required Services

#### Option A: Using Docker Compose (Recommended)
```bash
# Start PostgreSQL, Redis, and VoiceReel
docker-compose -f docker-compose.dev.yml up -d
```

#### Option B: Manual Setup
```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start PostgreSQL (if not installed, use Docker)
docker run -d --name voicereel-postgres \
    -e POSTGRES_USER=voicereel \
    -e POSTGRES_PASSWORD=voicereel \
    -e POSTGRES_DB=voicereel \
    -p 5432:5432 \
    postgres:15-alpine

# Terminal 3: Start Celery Worker
export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"
export VR_REDIS_URL="redis://localhost:6379/0"
celery -A voicereel.tasks worker --loglevel=info
```

### 3. Initialize Database

```bash
# Set database URL
export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"

# Run migration
python tools/migrate_to_postgres.py
```

### 4. Start VoiceReel Server

```bash
# Terminal 4: Start VoiceReel API Server
export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"
export VR_REDIS_URL="redis://localhost:6379/0"
export VR_API_KEY="test-api-key-12345"
export VR_LOG_LEVEL="INFO"
export VR_DEBUG="true"

python -m voicereel.server_postgres
```

### 5. Prepare Reference Audio Files

Create two reference audio files for your speakers:

```bash
# Create test audio directory
mkdir -p test_audio

# Record or download 30-second samples for each speaker
# Speaker 1: Male voice (e.g., news anchor style)
# Save as: test_audio/speaker1_male.wav

# Speaker 2: Female voice (e.g., conversational style)  
# Save as: test_audio/speaker2_female.wav

# Create matching transcripts
echo "안녕하세요. 저는 첫 번째 화자입니다. 오늘은 날씨가 정말 좋네요. 이 음성은 제 목소리 샘플입니다." > test_audio/speaker1_script.txt
echo "반갑습니다. 저는 두 번째 화자예요. 맞아요, 정말 화창한 날씨네요. 제 목소리도 잘 들리시나요?" > test_audio/speaker2_script.txt
```

### 6. Register Speakers

```python
# test_register_speakers.py
import requests
import time

API_URL = "http://localhost:8080"
API_KEY = "test-api-key-12345"

headers = {
    "X-VR-APIKEY": API_KEY
}

# Register Speaker 1 (Male)
with open("test_audio/speaker1_male.wav", "rb") as audio_file:
    with open("test_audio/speaker1_script.txt", "r") as script_file:
        files = {
            "reference_audio": ("speaker1.wav", audio_file, "audio/wav"),
        }
        data = {
            "name": "김민수 (남성 앵커)",
            "lang": "ko",
            "reference_script": script_file.read()
        }
        
        response = requests.post(
            f"{API_URL}/v1/speakers",
            headers=headers,
            files=files,
            data=data
        )
        print("Speaker 1 Registration:", response.json())
        speaker1_job = response.json()["job_id"]

# Register Speaker 2 (Female)
with open("test_audio/speaker2_female.wav", "rb") as audio_file:
    with open("test_audio/speaker2_script.txt", "r") as script_file:
        files = {
            "reference_audio": ("speaker2.wav", audio_file, "audio/wav"),
        }
        data = {
            "name": "이수진 (여성 진행자)",
            "lang": "ko",
            "reference_script": script_file.read()
        }
        
        response = requests.post(
            f"{API_URL}/v1/speakers",
            headers=headers,
            files=files,
            data=data
        )
        print("Speaker 2 Registration:", response.json())
        speaker2_job = response.json()["job_id"]

# Wait for registration to complete
print("\nWaiting for speaker registration...")
time.sleep(10)

# Check registration status
for job_id in [speaker1_job, speaker2_job]:
    response = requests.get(f"{API_URL}/v1/jobs/{job_id}", headers=headers)
    print(f"Job {job_id} status:", response.json())

# Get speaker list
response = requests.get(f"{API_URL}/v1/speakers", headers=headers)
speakers = response.json()["speakers"]
print("\nRegistered speakers:")
for speaker in speakers:
    print(f"- {speaker['name']}: {speaker['id']}")
```

### 7. Test Two-Speaker Dialogue

```python
# test_dialogue.py
import requests
import json
import time
import subprocess

API_URL = "http://localhost:8080"
API_KEY = "test-api-key-12345"

headers = {
    "X-VR-APIKEY": API_KEY,
    "Content-Type": "application/json"
}

# Get speaker IDs
response = requests.get(f"{API_URL}/v1/speakers", headers=headers)
speakers = response.json()["speakers"]
speaker1_id = speakers[0]["id"]  # 김민수
speaker2_id = speakers[1]["id"]  # 이수진

# Create dialogue script
dialogue_script = [
    {"speaker_id": speaker1_id, "text": "안녕하세요, 시청자 여러분. 오늘의 날씨를 전해드리겠습니다."},
    {"speaker_id": speaker2_id, "text": "네, 안녕하세요. 오늘은 전국적으로 맑은 날씨가 이어지겠습니다."},
    {"speaker_id": speaker1_id, "text": "그렇군요. 미세먼지 상황은 어떤가요?"},
    {"speaker_id": speaker2_id, "text": "다행히 미세먼지 농도는 '좋음' 수준을 유지하고 있어요. 야외 활동하기 좋은 날씨입니다."},
    {"speaker_id": speaker1_id, "text": "좋은 소식이네요. 이번 주말 날씨는 어떨까요?"},
    {"speaker_id": speaker2_id, "text": "주말에도 화창한 날씨가 계속될 예정입니다. 나들이 계획이 있으신 분들께는 희소식이네요."},
    {"speaker_id": speaker1_id, "text": "감사합니다. 좋은 하루 보내세요!"},
    {"speaker_id": speaker2_id, "text": "네, 여러분도 즐거운 하루 되세요!"}
]

# Request synthesis
synthesis_request = {
    "script": dialogue_script,
    "output_format": "wav",
    "sample_rate": 44100,
    "caption_format": "vtt"
}

print("Requesting dialogue synthesis...")
response = requests.post(
    f"{API_URL}/v1/synthesize",
    headers=headers,
    json=synthesis_request
)

if response.status_code == 202:
    job_id = response.json()["job_id"]
    print(f"Synthesis job created: {job_id}")
    
    # Poll for completion
    while True:
        time.sleep(3)
        response = requests.get(f"{API_URL}/v1/jobs/{job_id}", headers=headers)
        job_status = response.json()
        
        print(f"Status: {job_status['status']}")
        
        if job_status["status"] == "succeeded":
            audio_url = job_status["audio_url"]
            captions = job_status["captions"]
            
            print(f"\n✅ Synthesis completed!")
            print(f"Audio URL: {audio_url}")
            
            # Download audio file
            audio_response = requests.get(audio_url)
            with open("dialogue_output.wav", "wb") as f:
                f.write(audio_response.content)
            print("Audio saved as: dialogue_output.wav")
            
            # Save captions
            with open("dialogue_output.vtt", "w") as f:
                f.write(captions)
            print("Captions saved as: dialogue_output.vtt")
            
            # Display dialogue timing
            print("\nDialogue Timing:")
            for caption in job_status.get("caption_data", []):
                speaker_name = "김민수" if caption["speaker"] == speaker1_id else "이수진"
                print(f"{caption['start']:.2f}s - {caption['end']:.2f}s [{speaker_name}]: {caption['text']}")
            
            # Play audio (macOS/Linux)
            try:
                if subprocess.run(["which", "afplay"], capture_output=True).returncode == 0:
                    subprocess.run(["afplay", "dialogue_output.wav"])
                elif subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
                    subprocess.run(["aplay", "dialogue_output.wav"])
                else:
                    print("\n🎵 Please play 'dialogue_output.wav' with your audio player")
            except:
                print("\n🎵 Please play 'dialogue_output.wav' with your audio player")
            
            break
            
        elif job_status["status"] == "failed":
            print(f"❌ Synthesis failed: {job_status.get('error', 'Unknown error')}")
            break
else:
    print(f"❌ Request failed: {response.text}")
```

### 8. Alternative: Using VoiceReel Client

```python
# test_with_client.py
from voicereel.client import VoiceReelClient
import asyncio

async def test_dialogue():
    # Initialize client
    client = VoiceReelClient(
        base_url="http://localhost:8080",
        api_key="test-api-key-12345"
    )
    
    # Register speakers (if not already registered)
    # ... (similar to above)
    
    # Get speakers
    speakers = await client.get_speakers()
    print("Available speakers:")
    for speaker in speakers:
        print(f"- {speaker['name']} ({speaker['id']})")
    
    # Create dialogue
    dialogue = [
        {"speaker_id": speakers[0]["id"], "text": "안녕하세요, 오늘의 뉴스입니다."},
        {"speaker_id": speakers[1]["id"], "text": "네, 주요 소식을 전해드리겠습니다."},
    ]
    
    # Synthesize
    job_id = await client.synthesize(dialogue, output_format="wav")
    print(f"Synthesis job: {job_id}")
    
    # Wait for completion
    result = await client.wait_for_job(job_id)
    
    # Download audio
    await client.download_audio(result["audio_url"], "client_output.wav")
    print("✅ Audio saved as: client_output.wav")

# Run the test
asyncio.run(test_dialogue())
```

## 🔍 Troubleshooting

### Common Issues

1. **"Connection refused" error**
   - Check if all services are running (Redis, PostgreSQL, Celery, API server)
   - Verify ports are not in use: `lsof -i :8080,5432,6379`

2. **"Speaker registration failed"**
   - Ensure audio files are at least 30 seconds long
   - Check audio format (WAV, 16kHz+ recommended)
   - Verify transcript matches the audio content

3. **"Synthesis takes too long"**
   - Check GPU availability: `nvidia-smi`
   - Monitor Celery worker logs for errors
   - Reduce dialogue length for initial tests

4. **"No audio output"**
   - Check VoiceReel logs: `export VR_LOG_LEVEL=DEBUG`
   - Verify Fish-Speech models are downloaded correctly
   - Test with single speaker first

### Debug Mode

Enable detailed logging:
```bash
export VR_DEBUG=true
export VR_LOG_LEVEL=DEBUG
export VR_DEBUG_VERBOSE_LOGGING=true
```

View logs in real-time:
```bash
# API server logs
tail -f voicereel.log

# Celery worker logs
celery -A voicereel.tasks worker --loglevel=debug
```

## 📊 Performance Tips

1. **GPU Acceleration**
   - Ensure CUDA is available: `python -c "import torch; print(torch.cuda.is_available())"`
   - Use `export CUDA_VISIBLE_DEVICES=0` to specify GPU

2. **Batch Processing**
   - Process multiple dialogues in parallel
   - Use Redis for distributed task processing

3. **Audio Quality**
   - Use high-quality reference audio (44.1kHz, 16-bit)
   - Keep consistent recording conditions for speakers

## 🎯 Next Steps

- Test with more speakers (3-5 person conversation)
- Try different languages (English, Japanese, Chinese)
- Experiment with emotional expressions
- Build a web UI for easier testing
- Deploy to production with HTTPS
