# VoiceReel Celery/Redis Implementation

This document describes the Celery/Redis task queue implementation for VoiceReel, which replaces the in-memory queue for production use.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API       │────▶│    Redis    │────▶│   Celery    │
│  Server     │     │   Broker    │     │  Workers    │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                         │
       ▼                                         ▼
┌─────────────┐                         ┌─────────────┐
│ PostgreSQL  │◀────────────────────────│   Models    │
│  Database   │                         │ (fish_speech)│
└─────────────┘                         └─────────────┘
```

## Components

### 1. **Redis** - Message Broker & Result Backend
- Stores task messages and results
- Provides pub/sub for real-time updates
- Caches job status for fast retrieval

### 2. **Celery Workers** - Task Processors
- **Speaker Registration Queue**: Processes speaker enrollment
- **Synthesis Queue**: Handles TTS generation (GPU-enabled)
- Automatic retry with exponential backoff

### 3. **PostgreSQL** - Persistent Storage
- Stores speaker profiles
- Tracks job history
- Records usage metrics

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -e ".[celery,redis,postgres]"
```

### 2. Start Services with Docker Compose

```bash
# Start all services
docker-compose -f docker-compose.voicereel.yml up -d

# View logs
docker-compose -f docker-compose.voicereel.yml logs -f

# Stop services
docker-compose -f docker-compose.voicereel.yml down
```

### 3. Environment Variables

```bash
export VR_REDIS_URL="redis://localhost:6379/0"
export VR_DSN="postgresql://voicereel:voicereel_pass@localhost:5432/voicereel"
export VR_API_KEY="your_api_key"
export VR_HMAC_SECRET="your_hmac_secret"
```

### 4. Run Workers Manually (Development)

```bash
# Speaker registration worker
python -m voicereel.worker --queue speakers --concurrency 2

# Synthesis worker (requires GPU)
python -m voicereel.worker --queue synthesis --concurrency 1

# Run all queues
python -m voicereel.worker --queue all
```

## Task Definitions

### 1. Speaker Registration Task

```python
@app.task(name="voicereel.tasks.register_speaker")
def register_speaker(job_id, speaker_id, audio_path, script, lang):
    # 1. Load reference audio
    # 2. Extract acoustic features
    # 3. Save speaker embeddings
    # 4. Update job status
```

### 2. Synthesis Task

```python
@app.task(name="voicereel.tasks.synthesize")
def synthesize(job_id, script, output_format, sample_rate, caption_format):
    # 1. Load speaker embeddings
    # 2. Generate semantic tokens
    # 3. Synthesize audio with VQGAN
    # 4. Generate captions with timing
    # 5. Upload to S3 (future)
```

### 3. Cleanup Task

```python
@app.task(name="voicereel.tasks.cleanup_old_files")
def cleanup_old_files(max_age_hours=48):
    # Remove old audio files and job records
```

## Monitoring

### 1. Flower Web UI

Access Celery monitoring at http://localhost:5555

### 2. Redis CLI

```bash
# Connect to Redis
redis-cli

# Monitor tasks
MONITOR

# Check queue sizes
LLEN celery
LLEN speakers
LLEN synthesis
```

### 3. PostgreSQL Queries

```sql
-- Active jobs
SELECT * FROM jobs WHERE status IN ('pending', 'processing');

-- Usage statistics
SELECT DATE(ts) as day, SUM(length) as total_seconds
FROM usage
GROUP BY DATE(ts)
ORDER BY day DESC;

-- Speaker list
SELECT id, name, lang, created_at FROM speakers;
```

## Migration from SQLite

```bash
# Migrate existing SQLite database to PostgreSQL
python voicereel/migrate_to_postgres.py \
    --sqlite voicereel.db \
    --postgres "postgresql://voicereel:voicereel_pass@localhost/voicereel"
```

## Performance Tuning

### Worker Configuration

```python
# celery_app.py
app.conf.update(
    # Prefetch only 1 task at a time for long-running tasks
    worker_prefetch_multiplier=1,
    
    # Restart worker after N tasks to prevent memory leaks
    worker_max_tasks_per_child=100,
    
    # Task time limits
    task_time_limit=300,  # 5 min hard limit
    task_soft_time_limit=240,  # 4 min soft limit
)
```

### Redis Optimization

```bash
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save ""  # Disable persistence for cache-only mode
```

### PostgreSQL Tuning

```sql
-- Increase connection pool
ALTER SYSTEM SET max_connections = 200;

-- Optimize for SSD
ALTER SYSTEM SET random_page_cost = 1.1;

-- Increase shared buffers
ALTER SYSTEM SET shared_buffers = '256MB';
```

## Troubleshooting

### Common Issues

1. **Workers not picking up tasks**
   - Check Redis connectivity: `redis-cli ping`
   - Verify queue names match
   - Check worker logs for errors

2. **Database connection errors**
   - Verify PostgreSQL is running
   - Check connection string format
   - Ensure database exists

3. **Task timeouts**
   - Increase `task_time_limit` for long synthesis
   - Add GPU resources for synthesis workers
   - Monitor memory usage

### Debug Mode

```bash
# Run worker with debug logging
python -m voicereel.worker --loglevel DEBUG

# Enable SQL logging
export VR_DEBUG_SQL=1
```

## Production Deployment

### 1. Use Supervisor or systemd

```ini
# /etc/supervisor/conf.d/voicereel-worker.conf
[program:voicereel-speaker-worker]
command=/usr/bin/python -m voicereel.worker --queue speakers
directory=/app
user=voicereel
autostart=true
autorestart=true
stderr_logfile=/var/log/voicereel/speaker-worker.err.log
stdout_logfile=/var/log/voicereel/speaker-worker.out.log
```

### 2. Enable GPU for Synthesis Workers

```yaml
# docker-compose.yml
worker_synthesis:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### 3. Set Resource Limits

```yaml
# docker-compose.yml
worker_synthesis:
  mem_limit: 8g
  cpus: '4.0'
```

## Future Improvements

1. **S3 Integration**: Store audio files in S3 with presigned URLs
2. **Kubernetes Deployment**: Auto-scaling with HPA
3. **Distributed Tracing**: OpenTelemetry integration
4. **Real-time Updates**: WebSocket notifications via Redis pub/sub