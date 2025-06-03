"""PostgreSQL database implementation for VoiceReel."""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from loguru import logger


class PostgreSQLDatabase:
    """PostgreSQL database manager with connection pooling."""
    
    def __init__(
        self,
        dsn: Optional[str] = None,
        min_connections: int = 2,
        max_connections: int = 10,
    ):
        """
        Initialize PostgreSQL database connection.
        
        Args:
            dsn: PostgreSQL connection string
            min_connections: Minimum pool connections
            max_connections: Maximum pool connections
        """
        self.dsn = dsn or os.getenv("VR_POSTGRES_DSN") or os.getenv("DATABASE_URL")
        if not self.dsn:
            raise ValueError("PostgreSQL DSN not provided")
        
        # Create connection pool
        self.pool = ThreadedConnectionPool(
            min_connections,
            max_connections,
            self.dsn
        )
        
        # Initialize schema
        self._init_schema()
        
        logger.info(f"PostgreSQL database initialized with pool size {min_connections}-{max_connections}")
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """Get a database cursor."""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()
    
    def _init_schema(self):
        """Initialize database schema."""
        with self.get_cursor() as cur:
            # Enable UUID extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
            
            # Speakers table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS speakers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    lang VARCHAR(10) NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_speakers_lang ON speakers(lang);
                CREATE INDEX IF NOT EXISTS idx_speakers_created_at ON speakers(created_at);
            """)
            
            # Jobs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    audio_url TEXT,
                    caption_path TEXT,
                    caption_format VARCHAR(10),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type);
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
            """)
            
            # Usage tracking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    length REAL NOT NULL,
                    job_id UUID REFERENCES jobs(id),
                    speaker_id INTEGER REFERENCES speakers(id),
                    metadata JSONB
                );
                
                CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
                CREATE INDEX IF NOT EXISTS idx_usage_job_id ON usage(job_id);
            """)
            
            # API keys table (for future use)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    key_hash VARCHAR(64) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    metadata JSONB
                );
                
                CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
            """)
            
            # Create update timestamp trigger
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
                
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_speakers_updated_at') THEN
                        CREATE TRIGGER update_speakers_updated_at BEFORE UPDATE ON speakers
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_jobs_updated_at') THEN
                        CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                    END IF;
                END $$;
            """)
            
            logger.info("PostgreSQL schema initialized")
    
    # Speaker operations
    def create_speaker(self, name: str, lang: str, metadata: Optional[Dict] = None) -> int:
        """Create a new speaker."""
        with self.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO speakers (name, lang, metadata)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, lang, psycopg2.extras.Json(metadata or {}))
            )
            return cur.fetchone()[0]
    
    def get_speaker(self, speaker_id: int) -> Optional[Dict[str, Any]]:
        """Get speaker by ID."""
        with self.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM speakers WHERE id = %s",
                (speaker_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    
    def list_speakers(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """List speakers with pagination."""
        with self.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM speakers
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset)
            )
            return [dict(row) for row in cur.fetchall()]
    
    def update_speaker_metadata(self, speaker_id: int, metadata: Dict[str, Any]):
        """Update speaker metadata."""
        with self.get_cursor() as cur:
            cur.execute(
                """
                UPDATE speakers
                SET metadata = metadata || %s
                WHERE id = %s
                """,
                (psycopg2.extras.Json(metadata), speaker_id)
            )
    
    # Job operations
    def create_job(
        self,
        job_type: str,
        status: str = "pending",
        metadata: Optional[Dict] = None
    ) -> str:
        """Create a new job."""
        with self.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (type, status, metadata)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (job_type, status, psycopg2.extras.Json(metadata or {}))
            )
            return str(cur.fetchone()[0])
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        with self.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM jobs WHERE id = %s",
                (job_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    
    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        audio_url: Optional[str] = None,
        caption_path: Optional[str] = None,
        caption_format: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """Update job details."""
        updates = []
        params = []
        
        if status is not None:
            updates.append("status = %s")
            params.append(status)
            if status == "succeeded":
                updates.append("completed_at = NOW()")
        
        if audio_url is not None:
            updates.append("audio_url = %s")
            params.append(audio_url)
        
        if caption_path is not None:
            updates.append("caption_path = %s")
            params.append(caption_path)
        
        if caption_format is not None:
            updates.append("caption_format = %s")
            params.append(caption_format)
        
        if metadata is not None:
            updates.append("metadata = metadata || %s")
            params.append(psycopg2.extras.Json(metadata))
        
        if not updates:
            return
        
        params.append(job_id)
        
        with self.get_cursor() as cur:
            cur.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE id = %s",
                params
            )
    
    def delete_job(self, job_id: str):
        """Delete a job and related data."""
        with self.get_cursor() as cur:
            # Delete related usage records first
            cur.execute("DELETE FROM usage WHERE job_id = %s", (job_id,))
            # Delete the job
            cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
    
    # Usage tracking
    def record_usage(
        self,
        length: float,
        job_id: Optional[str] = None,
        speaker_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ):
        """Record usage statistics."""
        with self.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage (length, job_id, speaker_id, metadata)
                VALUES (%s, %s, %s, %s)
                """,
                (length, job_id, speaker_id, psycopg2.extras.Json(metadata or {}))
            )
    
    def get_usage_stats(self, year: int, month: int) -> Dict[str, Any]:
        """Get usage statistics for a given month."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        with self.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT 
                    COUNT(*) as count,
                    COALESCE(SUM(length), 0) as total_length,
                    COUNT(DISTINCT speaker_id) as unique_speakers
                FROM usage
                WHERE ts >= %s AND ts < %s
                """,
                (start_date, end_date)
            )
            stats = dict(cur.fetchone())
            
            # Get daily breakdown
            cur.execute(
                """
                SELECT 
                    DATE(ts) as date,
                    COUNT(*) as count,
                    SUM(length) as total_length
                FROM usage
                WHERE ts >= %s AND ts < %s
                GROUP BY DATE(ts)
                ORDER BY date
                """,
                (start_date, end_date)
            )
            stats['daily'] = [dict(row) for row in cur.fetchall()]
            
            return stats
    
    # Maintenance operations
    def cleanup_old_jobs(self, days: int = 2):
        """Clean up old completed jobs."""
        with self.get_cursor() as cur:
            cur.execute(
                """
                DELETE FROM jobs
                WHERE status = 'succeeded'
                AND completed_at < NOW() - INTERVAL '%s days'
                RETURNING id
                """,
                (days,)
            )
            deleted_ids = [row[0] for row in cur.fetchall()]
            logger.info(f"Cleaned up {len(deleted_ids)} old jobs")
            return deleted_ids
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get database health status."""
        try:
            with self.get_cursor() as cur:
                # Check connection
                cur.execute("SELECT 1")
                
                # Get table sizes
                cur.execute("""
                    SELECT 
                        relname as table_name,
                        pg_size_pretty(pg_total_relation_size(relid)) as size
                    FROM pg_catalog.pg_statio_user_tables
                    WHERE schemaname = 'public'
                    ORDER BY pg_total_relation_size(relid) DESC
                """)
                table_sizes = dict(cur.fetchall())
                
                # Get connection stats
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_connections,
                        COUNT(*) FILTER (WHERE state = 'active') as active_connections
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)
                conn_stats = dict(cur.fetchone())
                
                return {
                    "status": "healthy",
                    "pool_size": f"{self.pool.minconn}-{self.pool.maxconn}",
                    "table_sizes": table_sizes,
                    "connections": conn_stats,
                }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
            }
    
    def close(self):
        """Close all database connections."""
        if hasattr(self, 'pool'):
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Global database instance
_db: Optional[PostgreSQLDatabase] = None


def get_postgres_db() -> PostgreSQLDatabase:
    """Get or create global PostgreSQL database instance."""
    global _db
    
    if _db is None:
        _db = PostgreSQLDatabase()
    
    return _db


def init_postgres_db(dsn: Optional[str] = None) -> PostgreSQLDatabase:
    """Initialize PostgreSQL database with DSN."""
    global _db
    
    if _db is not None:
        _db.close()
    
    _db = PostgreSQLDatabase(dsn)
    return _db