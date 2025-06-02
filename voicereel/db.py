from __future__ import annotations

import sqlite3
from typing import Any, Optional


def _init_schema(cur, is_postgres: bool = False) -> None:
    """Create required tables using the current cursor."""
    if is_postgres:
        # PostgreSQL schema with proper types
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS speakers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                lang VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{}'::jsonb
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id UUID PRIMARY KEY,
                type VARCHAR(50),
                status VARCHAR(20),
                audio_url TEXT,
                caption_path TEXT,
                caption_format VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{}'::jsonb
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP,
                length REAL,
                metadata JSONB DEFAULT '{}'::jsonb
            )
            """
        )
        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts)")
    else:
        # SQLite schema (existing)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS speakers (
                id INTEGER PRIMARY KEY,
                name TEXT,
                lang TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                type TEXT,
                status TEXT,
                audio_url TEXT,
                caption_path TEXT,
                caption_format TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                ts TEXT,
                length REAL
            )
            """
        )


def init_db(dsn: Optional[str] = None) -> Any:
    """Initialize and return a database connection.

    When the DSN starts with ``postgres://`` or ``postgresql://`` this function
    attempts to connect using :mod:`psycopg2`. Otherwise it falls back to
    SQLite. The same schema is created on the provided connection.
    """

    dsn = dsn or ":memory:"
    if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
        import importlib

        psycopg2 = importlib.import_module("psycopg2")
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        _init_schema(cur, is_postgres=True)
        conn.commit()
        return conn

    conn = sqlite3.connect(dsn, check_same_thread=False)
    cur = conn.cursor()
    _init_schema(cur, is_postgres=False)
    conn.commit()
    return conn


__all__ = ["init_db"]
