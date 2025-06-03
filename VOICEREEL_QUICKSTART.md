# VoiceReel Quick Start Guide 🚀

VoiceReel을 사용한 다중 화자 TTS (Text-to-Speech) 로컬 테스트 가이드입니다.

## 📋 전제 조건

- Python 3.10+
- Conda (Miniconda/Anaconda)
- Docker (선택사항, 서비스 실행용)
- CUDA 지원 GPU (선택사항, 성능 향상)

## 🎯 5분 안에 시작하기

### 1. 자동 설정 (권장)

```bash
# 설정 스크립트 실행
bash examples/setup_test_env.sh
```

이 스크립트는 다음을 자동으로 수행합니다:
- ✅ Conda 환경 생성
- ✅ 의존성 패키지 설치
- ✅ Fish-Speech 모델 다운로드
- ✅ 테스트 오디오 파일 생성
- ✅ Docker로 PostgreSQL/Redis 시작 (선택사항)

### 2. 서비스 시작

**터미널 1 - Celery Worker:**
```bash
./start_celery_worker.sh
```

**터미널 2 - API Server:**
```bash
./start_voicereel_server.sh
```

### 3. 화자 등록

```bash
python examples/test_register_speakers.py
```

출력 예시:
```
🎤 VoiceReel Speaker Registration Test
==================================================
✅ Speaker '김민수 (남성 앵커)' registration started: job_123
✅ Speaker '이수진 (여성 진행자)' registration started: job_456
⏳ Waiting for speaker registration to complete...
✅ Registered speakers:
   - 김민수 (남성 앵커): spk_abc123
   - 이수진 (여성 진행자): spk_def456
```

### 4. 대화 합성 테스트

```bash
python examples/test_dialogue.py
```

대화 선택:
1. 날씨 예보 (격식체)
2. 일상 대화 (비격식체)

출력 예시:
```
🎭 VoiceReel Two-Speaker Dialogue Test
==================================================
📖 Select dialogue:
   1. Weather forecast (formal)
   2. Casual conversation (informal)

Enter choice (1 or 2, default=1): 1

🎙️  Requesting dialogue synthesis...
✅ Synthesis job created: job_789
⏳ Status: processing (5.2s)
✅ Synthesis completed!
💾 Audio saved as: weather_dialogue.wav
📝 Captions saved as: weather_dialogue.vtt

🎬 Dialogue Timing:
     0.00s -   2.45s : 안녕하세요, 시청자 여러분. 오늘의 날씨를 전해드리겠습니다.
     2.50s -   5.20s : 네, 안녕하세요. 오늘은 전국적으로 맑은 날씨가 이어지겠습니다.
```

## 🎤 실제 음성으로 테스트하기

### 1. 음성 녹음 준비

각 화자별로 30초 이상의 음성 샘플이 필요합니다:

**macOS/Linux:**
```bash
# sox 설치 (macOS)
brew install sox

# 녹음 (30초)
rec -r 44100 -c 1 -b 16 test_audio/my_voice.wav trim 0 30
```

**Windows:**
- Windows 음성 녹음기 사용
- Audacity 등 오디오 편집 프로그램 사용

### 2. 녹음 가이드라인

- 🎙️ **조용한 환경**에서 녹음
- 🗣️ **자연스럽고 명확하게** 발음
- ⏱️ **최소 30초** 이상 녹음
- 📝 **녹음한 내용을 정확히 텍스트로** 작성
- 🎵 **44.1kHz, 16-bit WAV** 형식 권장

### 3. 파일 교체

```bash
# 기존 테스트 파일을 실제 녹음으로 교체
cp my_recording1.wav test_audio/speaker1_male.wav
cp my_recording2.wav test_audio/speaker2_female.wav

# 텍스트 파일도 실제 녹음 내용으로 수정
echo "실제 녹음한 내용..." > test_audio/speaker1_script.txt
echo "실제 녹음한 내용..." > test_audio/speaker2_script.txt
```

## 🛠️ 문제 해결

### "Connection refused" 오류
```bash
# 서비스 상태 확인
docker ps
lsof -i :8080,5432,6379

# Docker 서비스 재시작
docker-compose -f docker-compose.dev.yml restart
```

### "Speaker registration failed" 오류
- 오디오 파일이 30초 이상인지 확인
- WAV 형식인지 확인 (MP3 변환 필요시: `ffmpeg -i input.mp3 output.wav`)
- 텍스트가 실제 음성 내용과 일치하는지 확인

### GPU 사용 확인
```bash
# CUDA 사용 가능 여부
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# GPU 메모리 사용량 모니터링
nvidia-smi -l 1
```

## 📊 성능 최적화

### 환경 변수 설정
```bash
# GPU 지정
export CUDA_VISIBLE_DEVICES=0

# 성능 최적화 활성화
export VOICEREEL_USE_OPTIMIZED=true
export VOICEREEL_USE_FP16=true
export VOICEREEL_ENABLE_COMPILE=true
```

### 배치 처리
```python
# 여러 대화를 동시에 처리
dialogues = [dialogue1, dialogue2, dialogue3]
job_ids = []
for dialogue in dialogues:
    response = requests.post(f"{API_URL}/v1/synthesize", ...)
    job_ids.append(response.json()["job_id"])
```

## 🔍 디버깅

### 상세 로그 활성화
```bash
export VR_DEBUG=true
export VR_LOG_LEVEL=DEBUG
export VR_DEBUG_VERBOSE_LOGGING=true
```

### 로그 확인
```bash
# API 서버 로그
tail -f voicereel.log | jq '.'

# Celery 작업 로그
celery -A voicereel.tasks worker --loglevel=debug
```

### 디버그 엔드포인트
```bash
# 설정 확인
curl http://localhost:8080/_debug/config

# 상태 확인
curl http://localhost:8080/_debug/health
```

## 📚 다음 단계

1. **다중 화자 확장**: 3-5명 대화 테스트
2. **다국어 지원**: 영어, 일본어, 중국어 테스트
3. **감정 표현**: 다양한 감정 톤 실험
4. **Web UI 구축**: Gradio/Streamlit UI 추가
5. **프로덕션 배포**: HTTPS, 인증, 모니터링 설정

## 🤝 도움말

- **문서**: [VoiceReel PRD](voicereel/PRD.md)
- **API 명세**: [API 엔드포인트](voicereel/PRD.md#10-api-설계)
- **문제 신고**: [GitHub Issues](https://github.com/icedac/fish-speech/issues)

---

Happy Testing! 🎉