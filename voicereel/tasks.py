"""Celery tasks for VoiceReel."""

import os
import tempfile
import time
from typing import Any, Dict, List

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .caption import export_captions
from .celery_app import app
from .db import init_db
from .fish_speech_integration import get_fish_speech_engine, get_speaker_manager
# Try to import optimized engine, fall back to regular if not available
try:
    from .fish_speech_optimized import get_optimized_engine
    OPTIMIZED_ENGINE_AVAILABLE = True
except ImportError:
    OPTIMIZED_ENGINE_AVAILABLE = False
from .s3_storage import get_storage_manager


class DatabaseTask(Task):
    """Base task with database connection."""

    _db = None

    @property
    def db(self):
        if self._db is None:
            dsn = os.getenv("VR_DSN", ":memory:")
            self._db = init_db(dsn)
        return self._db


@app.task(bind=True, base=DatabaseTask, name="voicereel.tasks.register_speaker")
def register_speaker(
    self, job_id: str, speaker_id: int, audio_path: str, script: str, lang: str
) -> Dict[str, Any]:
    """Process speaker registration.

    Args:
        job_id: Job identifier
        speaker_id: Speaker database ID
        audio_path: Path to reference audio file
        script: Reference script text
        lang: Language code (ISO 639-1)

    Returns:
        Dict with processing results
    """
    try:
        # Update job status to processing
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("processing", job_id))
        self.db.commit()

        logger.info(f"Starting speaker registration for job {job_id}, speaker {speaker_id}")

        # Use optimized engine if available
        use_optimized = OPTIMIZED_ENGINE_AVAILABLE and os.getenv("VOICEREEL_USE_OPTIMIZED", "true").lower() == "true"
        
        if use_optimized:
            logger.info("Using optimized Fish-Speech engine for feature extraction")
            engine = get_optimized_engine()
            speaker_manager = get_speaker_manager()
        else:
            # Get regular Fish-Speech engine and speaker manager
            engine = get_fish_speech_engine()
            speaker_manager = get_speaker_manager()

        # Extract speaker features from reference audio
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Reference audio file not found: {audio_path}")

        # Extract features using optimized method if available
        if use_optimized and hasattr(engine, 'extract_speaker_features_fast'):
            features = engine.extract_speaker_features_fast(audio_path, script, use_chunking=True)
        else:
            features = engine.extract_speaker_features(audio_path, script)
        
        # Save speaker features to storage
        feature_path = speaker_manager.save_speaker_features(speaker_id, features)
        
        # Update database with feature path
        cur.execute(
            "UPDATE speakers SET metadata=? WHERE id=?", 
            (feature_path, speaker_id)
        )

        # Mark job as succeeded
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("succeeded", job_id))
        self.db.commit()

        logger.info(f"Speaker registration completed for speaker {speaker_id}")
        
        return {
            "status": "succeeded",
            "speaker_id": speaker_id,
            "features_extracted": True,
            "feature_path": feature_path,
            "audio_duration": features.get("audio_duration", 0),
        }

    except SoftTimeLimitExceeded:
        # Handle timeout
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
        self.db.commit()
        raise

    except Exception as e:
        # Handle other errors
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
        self.db.commit()

        # Log error details
        self.retry(exc=e, countdown=60)


@app.task(bind=True, base=DatabaseTask, name="voicereel.tasks.synthesize")
def synthesize(
    self,
    job_id: str,
    script: List[Dict[str, str]],
    output_format: str = "wav",
    sample_rate: int = 48000,
    caption_format: str = "json",
) -> Dict[str, Any]:
    """Process multi-speaker synthesis.

    Args:
        job_id: Job identifier
        script: List of segments with speaker_id and text
        output_format: Audio format (wav/mp3)
        sample_rate: Output sample rate
        caption_format: Caption format (json/vtt/srt)

    Returns:
        Dict with synthesis results
    """
    try:
        # Update job status
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("processing", job_id))
        self.db.commit()

        logger.info(f"Starting synthesis for job {job_id} with {len(script)} segments")

        # Use optimized engine if available
        use_optimized = OPTIMIZED_ENGINE_AVAILABLE and os.getenv("VOICEREEL_USE_OPTIMIZED", "true").lower() == "true"
        
        if use_optimized:
            logger.info("Using optimized Fish-Speech engine for better performance")
            engine = get_optimized_engine()
            speaker_manager = get_speaker_manager()
        else:
            # Get regular Fish-Speech engine and speaker manager
            engine = get_fish_speech_engine()
            speaker_manager = get_speaker_manager()

        # Load speaker features for all speakers in script
        speaker_features = {}
        unique_speakers = set(segment.get("speaker_id") for segment in script)
        
        for speaker_id in unique_speakers:
            if not speaker_id:
                continue
            try:
                # Extract numeric ID if speaker_id is string like "spk_1" 
                if isinstance(speaker_id, str) and speaker_id.startswith("spk_"):
                    numeric_id = int(speaker_id.split("_")[1])
                else:
                    numeric_id = int(speaker_id)
                
                features = speaker_manager.load_speaker_features(numeric_id)
                speaker_features[speaker_id] = features
                logger.info(f"Loaded features for speaker {speaker_id}")
            except Exception as e:
                logger.error(f"Failed to load features for speaker {speaker_id}: {e}")
                raise ValueError(f"Speaker {speaker_id} not found or invalid")

        # Synthesize speech using Fish-Speech
        if use_optimized and hasattr(engine, 'synthesize_speech_optimized'):
            # Use optimized synthesis method
            audio_data, caption_units = engine.synthesize_speech_optimized(
                script=script,
                speaker_features=speaker_features,
                output_format=output_format,
                use_parallel=True,  # Enable parallel processing
            )
        else:
            # Use regular synthesis method
            audio_data, caption_units = engine.synthesize_speech(
                script=script,
                speaker_features=speaker_features,
                output_format=output_format,
            )

        # Save audio file to temporary location first
        temp_audio_path = os.path.join(tempfile.gettempdir(), f"{job_id}.{output_format}")
        engine.save_audio(audio_data, temp_audio_path, output_format)

        # Export captions to temporary file
        caption_text = export_captions(caption_units, caption_format)
        temp_caption_path = os.path.join(tempfile.gettempdir(), f"{job_id}.{caption_format}")
        with open(temp_caption_path, "w", encoding="utf-8") as f:
            f.write(caption_text)

        # Upload files to S3 or local storage
        storage_manager = get_storage_manager()
        
        # Upload audio file
        audio_key = f"synthesis/{job_id}/audio.{output_format}"
        audio_url = storage_manager.upload_file(
            temp_audio_path,
            key=audio_key,
            metadata={
                "job_id": job_id,
                "type": "synthesis_audio",
                "num_segments": str(len(script)),
                "speakers": ",".join(unique_speakers),
            }
        )
        
        # Upload caption file
        caption_key = f"synthesis/{job_id}/captions.{caption_format}"
        caption_url = storage_manager.upload_file(
            temp_caption_path,
            key=caption_key,
            metadata={
                "job_id": job_id,
                "type": "synthesis_captions",
                "format": caption_format,
            }
        )

        # Calculate total duration
        total_duration = caption_units[-1]["end"] if caption_units else 0.0

        # Clean up temporary files
        try:
            os.remove(temp_audio_path)
            os.remove(temp_caption_path)
        except Exception as e:
            logger.warning(f"Failed to clean up temp files: {e}")

        # Update job with results
        cur.execute(
            """UPDATE jobs 
               SET status=?, audio_url=?, caption_path=?, caption_format=? 
               WHERE id=?""",
            ("succeeded", audio_url, caption_url, caption_format, job_id),
        )

        # Record usage
        cur.execute(
            "INSERT INTO usage (ts, length) VALUES (datetime('now'), ?)",
            (total_duration,),
        )
        self.db.commit()

        logger.info(f"Synthesis completed for job {job_id}. Duration: {total_duration:.2f}s")

        return {
            "status": "succeeded",
            "audio_path": audio_path,
            "caption_path": caption_path,
            "duration": total_duration,
            "num_segments": len(script),
            "speakers_used": list(unique_speakers),
        }

    except SoftTimeLimitExceeded:
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
        self.db.commit()
        raise

    except Exception as e:
        cur = self.db.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
        self.db.commit()

        self.retry(exc=e, countdown=60)


@app.task(name="voicereel.tasks.cleanup_old_files")
def cleanup_old_files(max_age_hours: float = 48) -> Dict[str, int]:
    """Clean up old audio and caption files.

    Args:
        max_age_hours: Maximum age in hours before deletion

    Returns:
        Dict with cleanup statistics
    """
    import time

    dsn = os.getenv("VR_DSN", ":memory:")
    db = init_db(dsn)

    cutoff = time.time() - max_age_hours * 3600
    cur = db.cursor()

    # Find old succeeded jobs
    cur.execute("SELECT id, audio_url, caption_path FROM jobs WHERE status='succeeded'")

    deleted_files = 0
    deleted_jobs = 0

    for job_id, audio_path, caption_path in cur.fetchall():
        keep = False

        for path in (audio_path, caption_path):
            if path and os.path.exists(path):
                if os.path.getmtime(path) < cutoff:
                    try:
                        os.remove(path)
                        deleted_files += 1
                    except FileNotFoundError:
                        pass
                else:
                    keep = True

        if not keep:
            cur.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            deleted_jobs += 1

    db.commit()

    return {"deleted_files": deleted_files, "deleted_jobs": deleted_jobs}
