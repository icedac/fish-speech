#!/usr/bin/env python3
"""Migrate VoiceReel database from SQLite to PostgreSQL."""

import argparse
import os
import sqlite3
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor


def create_postgres_schema(pg_conn):
    """Create PostgreSQL schema with proper types."""
    with pg_conn.cursor() as cur:
        # Create speakers table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS speakers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                lang VARCHAR(10) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{}'::jsonb
            )
        """)
        
        # Create jobs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id UUID PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                audio_url TEXT,
                caption_path TEXT,
                caption_format VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{}'::jsonb
            )
        """)
        
        # Create usage table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP NOT NULL,
                length REAL NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb
            )
        """)
        
        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts)")
        
        pg_conn.commit()


def migrate_data(sqlite_path: str, pg_dsn: str):
    """Migrate data from SQLite to PostgreSQL."""
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(pg_dsn)
    
    try:
        # Create schema
        create_postgres_schema(pg_conn)
        
        # Migrate speakers
        print("Migrating speakers...")
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute("SELECT id, name, lang FROM speakers")
        
        with pg_conn.cursor() as pg_cur:
            for row in sqlite_cur:
                pg_cur.execute(
                    """
                    INSERT INTO speakers (id, name, lang) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET name = EXCLUDED.name, lang = EXCLUDED.lang
                    """,
                    (row['id'], row['name'], row['lang'])
                )
        
        # Reset sequence
        with pg_conn.cursor() as pg_cur:
            pg_cur.execute("""
                SELECT setval('speakers_id_seq', 
                    (SELECT MAX(id) FROM speakers), true)
            """)
        
        # Migrate jobs
        print("Migrating jobs...")
        sqlite_cur.execute("""
            SELECT id, type, status, audio_url, caption_path, caption_format 
            FROM jobs
        """)
        
        with pg_conn.cursor() as pg_cur:
            for row in sqlite_cur:
                # Convert job_id to UUID format if needed
                job_id = row['id']
                if len(job_id) == 32 and '-' not in job_id:
                    # Add hyphens to make it a valid UUID
                    job_id = f"{job_id[:8]}-{job_id[8:12]}-{job_id[12:16]}-{job_id[16:20]}-{job_id[20:]}"
                
                pg_cur.execute(
                    """
                    INSERT INTO jobs (id, type, status, audio_url, caption_path, caption_format)
                    VALUES (%s::uuid, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET type = EXCLUDED.type,
                        status = EXCLUDED.status,
                        audio_url = EXCLUDED.audio_url,
                        caption_path = EXCLUDED.caption_path,
                        caption_format = EXCLUDED.caption_format
                    """,
                    (job_id, row['type'], row['status'], row['audio_url'], 
                     row['caption_path'], row['caption_format'])
                )
        
        # Migrate usage
        print("Migrating usage data...")
        sqlite_cur.execute("SELECT ts, length FROM usage")
        
        with pg_conn.cursor() as pg_cur:
            for row in sqlite_cur:
                pg_cur.execute(
                    """
                    INSERT INTO usage (ts, length)
                    VALUES (%s::timestamp, %s)
                    """,
                    (row['ts'], row['length'])
                )
        
        pg_conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        pg_conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate VoiceReel SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default="voicereel.db",
        help="Path to SQLite database file"
    )
    parser.add_argument(
        "--postgres",
        default=os.getenv("VR_DSN", "postgresql://voicereel:voicereel_pass@localhost/voicereel"),
        help="PostgreSQL connection string"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.sqlite):
        print(f"SQLite database not found: {args.sqlite}")
        return
    
    migrate_data(args.sqlite, args.postgres)


if __name__ == "__main__":
    main()