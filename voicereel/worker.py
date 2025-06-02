#!/usr/bin/env python3
"""Celery worker for VoiceReel background tasks."""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from voicereel.celery_app import app

if __name__ == "__main__":
    # Configure worker based on queue type
    import argparse
    
    parser = argparse.ArgumentParser(description="VoiceReel Celery Worker")
    parser.add_argument(
        "--queue",
        choices=["speakers", "synthesis", "all"],
        default="all",
        help="Queue(s) to consume from",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent worker processes",
    )
    parser.add_argument(
        "--loglevel",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    
    args = parser.parse_args()
    
    # Configure worker options
    worker_opts = [
        "--loglevel", args.loglevel,
        "--concurrency", str(args.concurrency),
    ]
    
    if args.queue != "all":
        worker_opts.extend(["--queues", args.queue])
    else:
        worker_opts.extend(["--queues", "speakers,synthesis"])
    
    # Start worker
    app.worker_main(argv=["worker"] + worker_opts)