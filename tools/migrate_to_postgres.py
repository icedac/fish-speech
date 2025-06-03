#!/usr/bin/env python3
"""Migrate VoiceReel database from SQLite to PostgreSQL."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

import psycopg2
import psycopg2.extras
from loguru import logger

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voicereel.db_postgres import PostgreSQLDatabase


def migrate_speakers(sqlite_conn, postgres_db):
    """Migrate speakers table."""
    logger.info("Migrating speakers...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT id, name, lang FROM speakers")
    speakers = sqlite_cur.fetchall()
    
    speaker_id_map = {}
    
    for old_id, name, lang in speakers:
        # Create speaker in PostgreSQL
        new_id = postgres_db.create_speaker(
            name=name,
            lang=lang,
            metadata={"migrated_from_sqlite": True, "old_id": old_id}
        )
        speaker_id_map[old_id] = new_id
        logger.debug(f"Migrated speaker {old_id} -> {new_id}: {name}")
    
    logger.info(f"Migrated {len(speakers)} speakers")
    return speaker_id_map


def migrate_jobs(sqlite_conn, postgres_db):
    """Migrate jobs table."""
    logger.info("Migrating jobs...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
        SELECT id, type, status, audio_url, caption_path, caption_format
        FROM jobs
    """)
    jobs = sqlite_cur.fetchall()
    
    job_id_map = {}
    
    with postgres_db.get_cursor() as pg_cur:
        for old_id, job_type, status, audio_url, caption_path, caption_format in jobs:
            # Insert with specific UUID
            pg_cur.execute("""
                INSERT INTO jobs (id, type, status, audio_url, caption_path, caption_format, metadata)
                VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                job_type,
                status,
                audio_url,
                caption_path,
                caption_format,
                psycopg2.extras.Json({"migrated_from_sqlite": True, "old_id": old_id})
            ))
            new_id = str(pg_cur.fetchone()[0])
            job_id_map[old_id] = new_id
            logger.debug(f"Migrated job {old_id} -> {new_id}")
    
    logger.info(f"Migrated {len(jobs)} jobs")
    return job_id_map


def migrate_usage(sqlite_conn, postgres_db, job_id_map, speaker_id_map):
    """Migrate usage table."""
    logger.info("Migrating usage records...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT ts, length FROM usage")
    usage_records = sqlite_cur.fetchall()
    
    count = 0
    with postgres_db.get_cursor() as pg_cur:
        for ts_str, length in usage_records:
            # Parse timestamp
            try:
                ts = datetime.fromisoformat(ts_str)
            except:
                ts = datetime.now()  # Fallback
            
            # Insert usage record
            pg_cur.execute("""
                INSERT INTO usage (ts, length, metadata)
                VALUES (%s, %s, %s)
            """, (
                ts,
                length,
                psycopg2.extras.Json({"migrated_from_sqlite": True})
            ))
            count += 1
    
    logger.info(f"Migrated {count} usage records")


def verify_migration(sqlite_conn, postgres_db):
    """Verify migration was successful."""
    logger.info("Verifying migration...")
    
    sqlite_cur = sqlite_conn.cursor()
    
    # Check counts
    checks = []
    
    # Speakers
    sqlite_cur.execute("SELECT COUNT(*) FROM speakers")
    sqlite_speakers = sqlite_cur.fetchone()[0]
    
    with postgres_db.get_cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM speakers")
        pg_speakers = pg_cur.fetchone()[0]
    
    checks.append(("Speakers", sqlite_speakers, pg_speakers))
    
    # Jobs
    sqlite_cur.execute("SELECT COUNT(*) FROM jobs")
    sqlite_jobs = sqlite_cur.fetchone()[0]
    
    with postgres_db.get_cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM jobs")
        pg_jobs = pg_cur.fetchone()[0]
    
    checks.append(("Jobs", sqlite_jobs, pg_jobs))
    
    # Usage
    sqlite_cur.execute("SELECT COUNT(*) FROM usage")
    sqlite_usage = sqlite_cur.fetchone()[0]
    
    with postgres_db.get_cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM usage")
        pg_usage = pg_cur.fetchone()[0]
    
    checks.append(("Usage", sqlite_usage, pg_usage))
    
    # Print results
    all_good = True
    for table, sqlite_count, pg_count in checks:
        status = "✅" if sqlite_count == pg_count else "❌"
        logger.info(f"{status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        if sqlite_count != pg_count:
            all_good = False
    
    return all_good


def main():
    parser = argparse.ArgumentParser(
        description="Migrate VoiceReel database from SQLite to PostgreSQL"
    )
    parser.add_argument(
        "--sqlite",
        default=":memory:",
        help="Path to SQLite database (default: :memory:)"
    )
    parser.add_argument(
        "--postgres-dsn",
        help="PostgreSQL DSN (default: from VR_POSTGRES_DSN env)"
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop existing PostgreSQL tables before migration"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify migration without performing it"
    )
    args = parser.parse_args()
    
    # Get PostgreSQL DSN
    postgres_dsn = args.postgres_dsn or os.getenv("VR_POSTGRES_DSN")
    if not postgres_dsn:
        logger.error("PostgreSQL DSN not provided. Use --postgres-dsn or set VR_POSTGRES_DSN")
        sys.exit(1)
    
    # Connect to SQLite
    logger.info(f"Connecting to SQLite database: {args.sqlite}")
    sqlite_conn = sqlite3.connect(args.sqlite)
    
    # Connect to PostgreSQL
    logger.info(f"Connecting to PostgreSQL...")
    postgres_db = PostgreSQLDatabase(dsn=postgres_dsn)
    
    try:
        if args.drop_existing and not args.verify_only:
            logger.warning("Dropping existing PostgreSQL tables...")
            with postgres_db.get_cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS usage CASCADE")
                cur.execute("DROP TABLE IF EXISTS jobs CASCADE")
                cur.execute("DROP TABLE IF EXISTS speakers CASCADE")
                cur.execute("DROP TABLE IF EXISTS api_keys CASCADE")
            postgres_db._init_schema()
        
        if args.verify_only:
            # Just verify
            success = verify_migration(sqlite_conn, postgres_db)
        else:
            # Perform migration
            speaker_id_map = migrate_speakers(sqlite_conn, postgres_db)
            job_id_map = migrate_jobs(sqlite_conn, postgres_db)
            migrate_usage(sqlite_conn, postgres_db, job_id_map, speaker_id_map)
            
            # Verify
            success = verify_migration(sqlite_conn, postgres_db)
        
        if success:
            logger.success("Migration completed successfully! ✅")
        else:
            logger.error("Migration verification failed! ❌")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        sqlite_conn.close()
        postgres_db.close()


if __name__ == "__main__":
    main()