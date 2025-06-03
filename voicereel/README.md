# VoiceReel - Multi-Speaker TTS API

VoiceReel은 Fish-Speech 1.5 엔진을 기반으로 한 엔터프라이즈급 다중 화자 TTS (Text-to-Speech) API 서비스입니다.

## 🌟 주요 기능

- **다중 화자 합성**: 한 번의 API 호출로 여러 화자의 대화 생성
- **음성 복제**: 30초 이상의 레퍼런스 오디오로 화자 등록
- **자막 생성**: WebVTT, SRT, JSON 형식의 시간 동기화된 자막
- **비동기 처리**: Celery + Redis를 통한 확장 가능한 작업 큐
- **프로덕션 준비**: PostgreSQL, S3 스토리지, TLS 1.3, 구조화된 로깅

## 📋 요구사항

- Python 3.10+
- PostgreSQL 15+
- Redis 7+
- CUDA 지원 GPU (권장)
- 16GB+ RAM

## 🚀 빠른 시작

### 1. 설치

```bash
# VoiceReel 패키지 설치
pip install -e .

# 추가 의존성 설치
pip install redis celery psycopg2-binary boto3
```

### 2. 환경 설정

```bash
# 필수 환경 변수
export VR_POSTGRES_DSN="postgresql://user:pass@localhost:5432/voicereel"
export VR_REDIS_URL="redis://localhost:6379/0"
export VR_API_KEY="your-secure-api-key"

# 선택적 환경 변수
export VR_S3_BUCKET="voicereel-audio"
export VR_LOG_LEVEL="INFO"
export VR_DEBUG="false"
```

### 3. 데이터베이스 초기화

```bash
# PostgreSQL 마이그레이션 실행
python ../tools/migrate_to_postgres.py
```

### 4. 서비스 시작

```bash
# Celery 워커 시작 (터미널 1)
celery -A voicereel.tasks worker --loglevel=info

# API 서버 시작 (터미널 2)
python -m voicereel.server_postgres
```

## 🔌 API 사용법

### 화자 등록

```python
import requests

# 화자 등록
with open("speaker_audio.wav", "rb") as audio_file:
    response = requests.post(
        "http://localhost:8080/v1/speakers",
        headers={"X-VR-APIKEY": "your-api-key"},
        files={"reference_audio": audio_file},
        data={
            "name": "김철수",
            "lang": "ko",
            "reference_script": "안녕하세요. 저는 김철수입니다..."
        }
    )
    
job_id = response.json()["job_id"]
```

### 다중 화자 합성

```python
# 대화 스크립트 생성
dialogue = [
    {"speaker_id": "spk_123", "text": "안녕하세요, 오늘의 뉴스입니다."},
    {"speaker_id": "spk_456", "text": "네, 주요 소식을 전해드리겠습니다."}
]

# 합성 요청
response = requests.post(
    "http://localhost:8080/v1/synthesize",
    headers={
        "X-VR-APIKEY": "your-api-key",
        "Content-Type": "application/json"
    },
    json={
        "script": dialogue,
        "output_format": "wav",
        "caption_format": "vtt"
    }
)

synthesis_job_id = response.json()["job_id"]
```

### 결과 확인

```python
# 작업 상태 확인
response = requests.get(
    f"http://localhost:8080/v1/jobs/{synthesis_job_id}",
    headers={"X-VR-APIKEY": "your-api-key"}
)

if response.json()["status"] == "succeeded":
    audio_url = response.json()["audio_url"]
    captions = response.json()["captions"]
```

## 🧪 로컬 테스트

### 테스트 환경 설정

```bash
# Docker Compose로 서비스 시작
docker-compose -f ../docker-compose.dev.yml up -d

# 테스트 오디오 생성
python ../examples/create_test_audio.py

# 화자 등록 테스트
python ../examples/test_register_speakers.py

# 대화 합성 테스트
python ../examples/test_dialogue.py
```

### 테스트 시나리오

1. **2인 대화 (날씨 예보)**
   ```python
   dialogue = [
       {"speaker_id": "spk_1", "text": "오늘의 날씨를 전해드리겠습니다."},
       {"speaker_id": "spk_2", "text": "전국적으로 맑은 날씨가 이어지겠습니다."}
   ]
   ```

2. **다중 화자 회의**
   ```python
   meeting = [
       {"speaker_id": "host", "text": "회의를 시작하겠습니다."},
       {"speaker_id": "presenter", "text": "이번 분기 실적을 발표하겠습니다."},
       {"speaker_id": "participant1", "text": "질문이 있습니다."},
       {"speaker_id": "participant2", "text": "추가 의견입니다."}
   ]
   ```

## 📁 프로젝트 구조

```
voicereel/
├── __init__.py              # 패키지 초기화 및 로깅 설정
├── server_postgres.py       # PostgreSQL 기반 API 서버
├── tasks_postgres.py        # Celery 작업 정의
├── db_postgres.py           # PostgreSQL 데이터베이스 레이어
├── fish_speech_optimized.py # 최적화된 Fish-Speech 엔진
├── s3_storage.py           # S3 스토리지 관리
├── security.py             # 보안 미들웨어
├── json_logger.py          # 구조화된 JSON 로깅
├── error_responses.py      # 표준화된 에러 응답
├── client.py               # Python 클라이언트 SDK
└── caption.py              # 자막 생성 유틸리티
```

## 🛠️ 고급 설정

### S3 스토리지 설정

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export VR_S3_BUCKET="voicereel-audio"
export VR_S3_REGION="ap-northeast-2"
```

### TLS/HTTPS 설정

```bash
# 인증서 생성
python ../tools/voicereel_cert.py generate --domain api.example.com

# HTTPS 서버 시작
python -m voicereel.https_server
```

### 성능 최적화

```bash
# GPU 최적화 활성화
export VOICEREEL_USE_OPTIMIZED=true
export VOICEREEL_USE_FP16=true
export VOICEREEL_ENABLE_COMPILE=true

# 워커 수 조정
export VOICEREEL_MAX_WORKERS=4
```

### 디버그 모드

```bash
# 상세 로깅 활성화
export VR_DEBUG=true
export VR_LOG_LEVEL=DEBUG
export VR_DEBUG_VERBOSE_LOGGING=true

# 디버그 엔드포인트 확인
curl http://localhost:8080/_debug/health
curl http://localhost:8080/_debug/config
```

## 📊 모니터링

### 로그 확인

```bash
# JSON 형식 로그 보기
tail -f voicereel.log | jq '.'

# 특정 request_id 추적
grep "req-abc123" voicereel.log | jq '.'
```

### 성능 메트릭

- **합성 속도**: 30초 오디오 ≤ 8초 (p95)
- **동시 처리**: 500 req/s
- **가용성**: 99.9% SLA

## 🔒 보안

- **API 키 인증**: `X-VR-APIKEY` 헤더
- **HMAC 서명**: 요청 무결성 검증
- **Rate Limiting**: IP당 분당 60 요청
- **TLS 1.3**: 모든 통신 암호화
- **CORS 정책**: 허용된 도메인만 접근

## 🐛 문제 해결

### 일반적인 문제

1. **"Connection refused" 오류**
   ```bash
   # 서비스 상태 확인
   systemctl status postgresql redis
   lsof -i :8080,5432,6379
   ```

2. **"Speaker registration failed"**
   - 오디오 파일이 30초 이상인지 확인
   - WAV 형식 (44.1kHz, 16-bit) 권장
   - 텍스트와 오디오 내용 일치 확인

3. **느린 합성 속도**
   - GPU 사용 확인: `nvidia-smi`
   - 모델 컴파일 활성화: `VOICEREEL_ENABLE_COMPILE=true`
   - 배치 크기 조정: `VOICEREEL_BATCH_SIZE=8`

## 📚 추가 문서

- [PRD (Product Requirements)](PRD.md) - 제품 요구사항 명세
- [PostgreSQL 마이그레이션 가이드](POSTGRESQL_MIGRATION.md)
- [로깅 가이드](LOGGING_GUIDE.md)
- [E2E 테스트 문서](e2e.md)

## 🤝 기여하기

1. 이슈 생성 또는 기능 제안
2. 포크 및 브랜치 생성
3. 테스트 작성 및 통과 확인
4. Pull Request 제출

## 📄 라이선스

- 코드: Apache License 2.0
- 모델 가중치: CC-BY-NC-SA-4.0

---

VoiceReel은 Fish-Speech 프로젝트의 일부로 개발되었습니다.