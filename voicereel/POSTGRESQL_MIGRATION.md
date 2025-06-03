# VoiceReel PostgreSQL Migration Guide

This guide covers migrating VoiceReel from SQLite to PostgreSQL for production deployment.

## Overview

VoiceReel now supports PostgreSQL as the primary database backend, providing:
- Better concurrency and performance
- Connection pooling for scalability
- JSONB support for flexible metadata storage
- Production-ready features (triggers, indexes, constraints)

## Prerequisites

- PostgreSQL 12+ (recommended: PostgreSQL 15)
- Python packages: `psycopg2-binary` or `psycopg2`
- Existing VoiceReel SQLite database (optional, for migration)

## Quick Start

### 1. PostgreSQL Setup

```bash
# Using Docker
docker run -d \
  --name voicereel-postgres \
  -e POSTGRES_USER=voicereel \
  -e POSTGRES_PASSWORD=your_secure_password \
  -e POSTGRES_DB=voicereel \
  -p 5432:5432 \
  postgres:15-alpine

# Or using docker-compose
docker-compose -f docker-compose.dev.yml up -d postgres
```

### 2. Environment Configuration

Set the PostgreSQL connection string:

```bash
# Standard PostgreSQL DSN format
export VR_POSTGRES_DSN="postgresql://voicereel:password@localhost:5432/voicereel"

# Or use DATABASE_URL (Heroku-style)
export DATABASE_URL="postgresql://voicereel:password@localhost:5432/voicereel"
```

### 3. Database Migration

#### Option A: Fresh Installation

If starting fresh, the PostgreSQL schema will be created automatically when you first run the server:

```python
from voicereel.server_postgres import VoiceReelPostgresServer

server = VoiceReelPostgresServer(
    postgres_dsn="postgresql://voicereel:password@localhost:5432/voicereel"
)
server.start()
```

#### Option B: Migrate from SQLite

Use the migration tool to transfer existing data:

```bash
# Basic migration
python tools/migrate_to_postgres.py \
  --sqlite /path/to/voicereel.db \
  --postgres-dsn "postgresql://voicereel:password@localhost:5432/voicereel"

# Drop existing PostgreSQL tables and migrate fresh
python tools/migrate_to_postgres.py \
  --sqlite /path/to/voicereel.db \
  --postgres-dsn "postgresql://voicereel:password@localhost:5432/voicereel" \
  --drop-existing

# Verify migration without performing it
python tools/migrate_to_postgres.py \
  --sqlite /path/to/voicereel.db \
  --postgres-dsn "postgresql://voicereel:password@localhost:5432/voicereel" \
  --verify-only
```

## Using PostgreSQL with VoiceReel

### Server Implementation

```python
from voicereel.server_postgres import VoiceReelPostgresServer

# Create server with PostgreSQL backend
server = VoiceReelPostgresServer(
    host="0.0.0.0",
    port=8000,
    postgres_dsn="postgresql://voicereel:password@localhost:5432/voicereel",
    api_key="your-api-key",
    use_celery=True,  # Enable Celery for async tasks
    redis_url="redis://localhost:6379/0"
)

# Start server
server.start()
```

### Celery Tasks with PostgreSQL

```python
# Configure Celery to use PostgreSQL tasks
from voicereel.celery_app import app

# Tasks will automatically use PostgreSQL when available
app.conf.update(
    task_routes={
        'voicereel.tasks_postgres.*': {'queue': 'voicereel'},
    }
)
```

### Direct Database Access

```python
from voicereel.db_postgres import PostgreSQLDatabase

# Create database instance
db = PostgreSQLDatabase("postgresql://voicereel:password@localhost:5432/voicereel")

# Create a speaker
speaker_id = db.create_speaker("John Doe", "en", metadata={"voice_type": "narrator"})

# Create a job
job_id = db.create_job("synthesize", metadata={"priority": "high"})

# Record usage
db.record_usage(30.5, job_id=job_id, speaker_id=speaker_id)

# Get usage statistics
stats = db.get_usage_stats(2024, 1)
print(f"January 2024: {stats['count']} jobs, {stats['total_length']}s total")

# Clean up old jobs
deleted = db.cleanup_old_jobs(days=7)
print(f"Deleted {len(deleted)} old jobs")
```

## Database Schema

The PostgreSQL schema includes:

### Tables

1. **speakers**
   - `id`: SERIAL PRIMARY KEY
   - `name`: VARCHAR(255)
   - `lang`: VARCHAR(10)
   - `metadata`: JSONB (speaker features, settings)
   - `created_at`: TIMESTAMP

2. **jobs**
   - `id`: UUID PRIMARY KEY (auto-generated)
   - `type`: VARCHAR(50)
   - `status`: VARCHAR(20)
   - `audio_url`: TEXT
   - `caption_path`: TEXT
   - `caption_format`: VARCHAR(10)
   - `metadata`: JSONB (job parameters, results)
   - `created_at`: TIMESTAMP
   - `completed_at`: TIMESTAMP

3. **usage**
   - `id`: SERIAL PRIMARY KEY
   - `ts`: TIMESTAMP
   - `length`: REAL
   - `job_id`: UUID (foreign key)
   - `speaker_id`: INTEGER (foreign key)
   - `metadata`: JSONB

4. **api_keys**
   - `id`: SERIAL PRIMARY KEY
   - `key_hash`: VARCHAR(64)
   - `name`: VARCHAR(255)
   - `created_at`: TIMESTAMP
   - `last_used`: TIMESTAMP
   - `is_active`: BOOLEAN
   - `metadata`: JSONB

### Indexes

- `idx_jobs_status`: For quick job status queries
- `idx_jobs_created_at`: For time-based queries
- `idx_usage_ts`: For usage statistics
- `idx_speakers_created_at`: For speaker listing

### Triggers

- `update_jobs_completed_at`: Automatically sets `completed_at` when status changes to 'succeeded' or 'failed'

## Connection Pooling

The PostgreSQL implementation uses connection pooling for better performance:

```python
# Default pool configuration
db = PostgreSQLDatabase(
    dsn="postgresql://...",
    min_connections=2,    # Minimum idle connections
    max_connections=10    # Maximum total connections
)

# Check pool health
health = db.get_health_status()
print(f"Pool: {health['pool_stats']['current']}/{health['pool_stats']['max']} connections")
```

## Production Considerations

### 1. Connection String Security

Never hardcode credentials. Use environment variables:

```bash
# .env file (don't commit!)
VR_POSTGRES_DSN=postgresql://voicereel:secure_password@db.example.com:5432/voicereel?sslmode=require
```

### 2. SSL/TLS Configuration

For production, always use SSL:

```python
dsn = "postgresql://user:pass@host:5432/db?sslmode=require"
```

### 3. Database Backups

```bash
# Backup database
pg_dump $VR_POSTGRES_DSN > voicereel_backup_$(date +%Y%m%d).sql

# Restore database
psql $VR_POSTGRES_DSN < voicereel_backup_20240115.sql
```

### 4. Performance Tuning

```sql
-- Analyze tables for query optimization
ANALYZE speakers;
ANALYZE jobs;
ANALYZE usage;

-- Monitor slow queries
SELECT query, calls, mean_exec_time 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
```

### 5. Monitoring

Use the health check endpoint:

```bash
curl http://localhost:8000/health
```

Response includes database status:
```json
{
  "status": "ok",
  "database": {
    "status": "healthy",
    "version": "PostgreSQL 15.0",
    "pool_stats": {
      "current": 2,
      "available": 8,
      "max": 10
    },
    "tables": {
      "speakers": 150,
      "jobs": 1200,
      "usage": 5000
    }
  }
}
```

## Troubleshooting

### Connection Issues

```python
# Test connection
import psycopg2
try:
    conn = psycopg2.connect("postgresql://...")
    print("Connection successful!")
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
```

### Migration Issues

1. **"relation already exists"**: Use `--drop-existing` flag
2. **"permission denied"**: Check PostgreSQL user permissions
3. **"could not connect"**: Verify PostgreSQL is running and accessible

### Performance Issues

1. Check indexes are created:
   ```sql
   \d jobs  -- Show table structure with indexes
   ```

2. Monitor connection pool:
   ```python
   health = db.get_health_status()
   if health['pool_stats']['available'] == 0:
       print("Connection pool exhausted!")
   ```

## Rollback Plan

If you need to rollback to SQLite:

1. Export data from PostgreSQL (use migration tool in reverse)
2. Update environment to use SQLite:
   ```bash
   export VR_DSN=/path/to/voicereel.db
   ```
3. Use the original `VoiceReelServer` class instead of `VoiceReelPostgresServer`

## Next Steps

- Set up regular database backups
- Configure monitoring and alerting
- Implement read replicas for scaling
- Consider using pgBouncer for additional connection pooling