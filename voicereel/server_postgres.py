"""PostgreSQL-compatible VoiceReel server implementation."""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import time
import urllib.parse
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from .caption import export_captions
from .db_postgres import PostgreSQLDatabase, get_postgres_db
from .s3_storage import get_storage_manager, parse_storage_url
from .security import SecurityMiddleware, InputValidator, get_client_ip

# Try to import Celery tasks
try:
    from .tasks import register_speaker as celery_register_speaker
    from .tasks import synthesize as celery_synthesize

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


class VoiceReelPostgresServer:
    """VoiceReel server with PostgreSQL backend."""

    PRESIGNED_TTL = 15 * 60  # 15 minutes

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        postgres_dsn: str | None = None,
        api_key: str | None = None,
        hmac_secret: str | None = None,
        redis_url: str | None = None,
        use_celery: bool = None,
    ):
        self.host = host
        self.port = port
        self.job_queue: queue.Queue = queue.Queue()
        self.api_key = api_key or os.getenv("VR_API_KEY")
        self.hmac_secret = hmac_secret or os.getenv("VR_HMAC_SECRET")
        self.redis_url = redis_url or os.getenv("VR_REDIS_URL")
        
        # Initialize security middleware
        from .security import RateLimiter, CORSHandler, APIKeyValidator, SecurityMiddleware
        self.security_middleware = SecurityMiddleware(
            api_key_validator=APIKeyValidator(self.api_key, self.hmac_secret)
        )

        # Determine whether to use Celery
        if use_celery is None:
            # Auto-detect: use Celery if available and Redis URL is configured
            self.use_celery = CELERY_AVAILABLE and bool(self.redis_url)
        else:
            self.use_celery = use_celery and CELERY_AVAILABLE

        # Initialize PostgreSQL database
        postgres_dsn = postgres_dsn or os.getenv("VR_POSTGRES_DSN") or os.getenv("DATABASE_URL")
        if postgres_dsn:
            self.db = PostgreSQLDatabase(postgres_dsn)
        else:
            raise ValueError("PostgreSQL DSN not provided. Set VR_POSTGRES_DSN or DATABASE_URL")
        
        handler = self._make_handler()
        self.httpd = HTTPServer((self.host, self.port), handler)
        self.thread: threading.Thread | None = None
        self.worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, code: int, body: dict) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                server.security_middleware.add_response_headers(self)
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def _error(self, code: int, name: str, message: str = "") -> None:
                body = {"error": name}
                if message:
                    body["message"] = message
                self._json(code, body)

            def _check_security(self, body: bytes = b"") -> bool:
                """Check security middleware (rate limiting, auth, etc.)."""
                allowed, error_info = server.security_middleware.process_request(self, body)
                if not allowed and error_info:
                    if error_info.get("error") == "RATE_LIMIT_EXCEEDED":
                        self._json(429, error_info)
                    else:
                        self._json(401, error_info)
                    return False
                return allowed

            def do_GET(self):
                if not self._check_security():
                    return
                    
                if self.path == "/health":
                    # Get database health
                    db_health = server.db.get_health_status()
                    
                    health_data = {
                        "status": "ok" if db_health["status"] == "healthy" else "degraded",
                        "database": db_health,
                        "security": {
                            "rate_limiting_enabled": True,
                            "cors_enabled": True,
                            "input_validation_enabled": True,
                            "api_key_required": bool(server.api_key),
                            "hmac_verification": bool(server.hmac_secret),
                        },
                        "celery_enabled": server.use_celery,
                    }
                    self._json(200, health_data)
                    
                elif self.path.startswith("/v1/jobs/"):
                    job_id = self.path.rsplit("/", 1)[-1]
                    job = server.db.get_job(job_id)
                    
                    if job:
                        # Generate presigned URLs
                        audio_url = server._presign_path(job.get("audio_url"))
                        caption_url = server._presign_path(job.get("caption_path"))
                        
                        response = {
                            "id": job["id"],
                            "type": job["type"],
                            "status": job["status"],
                            "audio_url": audio_url,
                            "caption_url": caption_url,
                            "caption_format": job.get("caption_format"),
                            "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
                            "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else None,
                        }
                        self._json(200, response)
                    else:
                        self._error(404, "NOT_FOUND")
                        
                elif self.path.startswith("/v1/speakers/"):
                    if self.path.endswith("/speakers"):
                        # List speakers
                        query = urllib.parse.urlparse(self.path).query
                        params = urllib.parse.parse_qs(query)
                        page = int(params.get("page", ["1"])[0])
                        page_size = int(params.get("page_size", ["10"])[0])
                        offset = (page - 1) * page_size
                        
                        speakers = server.db.list_speakers(limit=page_size, offset=offset)
                        response = {
                            "speakers": [
                                {
                                    "id": s["id"],
                                    "name": s["name"],
                                    "lang": s["lang"],
                                    "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
                                }
                                for s in speakers
                            ],
                            "page": page,
                            "page_size": page_size,
                        }
                        self._json(200, response)
                    else:
                        # Get specific speaker
                        speaker_id = int(self.path.rsplit("/", 1)[-1])
                        speaker = server.db.get_speaker(speaker_id)
                        
                        if speaker:
                            response = {
                                "id": speaker["id"],
                                "name": speaker["name"],
                                "lang": speaker["lang"],
                                "created_at": speaker["created_at"].isoformat() if speaker.get("created_at") else None,
                            }
                            self._json(200, response)
                        else:
                            self._error(404, "NOT_FOUND")
                            
                elif self.path == "/v1/usage":
                    # Get usage statistics
                    query = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(query)
                    year = int(params.get("year", [datetime.now().year])[0])
                    month = int(params.get("month", [datetime.now().month])[0])
                    
                    stats = server.db.get_usage_stats(year, month)
                    self._json(200, stats)
                    
                else:
                    self._error(404, "NOT_FOUND")

            def do_DELETE(self):
                if not self._check_security():
                    return
                    
                if self.path.startswith("/v1/jobs/"):
                    job_id = self.path.rsplit("/", 1)[-1]
                    job = server.db.get_job(job_id)
                    
                    if not job:
                        self._error(404, "NOT_FOUND")
                        return
                    
                    # Delete associated files
                    storage_manager = get_storage_manager()
                    for url in [job.get("audio_url"), job.get("caption_path")]:
                        if url:
                            try:
                                storage_type, key = parse_storage_url(url)
                                if storage_type == "s3":
                                    storage_manager.delete_file(key)
                                elif storage_type == "local" and os.path.exists(url):
                                    os.remove(url)
                            except Exception:
                                pass  # Best effort
                    
                    # Delete job record
                    server.db.delete_job(job_id)
                    self.send_response(204)
                    self.end_headers()
                else:
                    self._error(404, "NOT_FOUND")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                if length > 30 * 1024 * 1024:
                    self._error(413, "PAYLOAD_TOO_LARGE")
                    _ = self.rfile.read(length)
                    return
                    
                raw = self.rfile.read(length)
                if not self._check_security(raw):
                    return
                    
                if self.path == "/v1/speakers":
                    content_type = self.headers.get("Content-Type", "")
                    
                    if content_type.startswith("multipart/form-data"):
                        # Handle multipart form upload
                        try:
                            from .multipart_parser import parse_multipart_form
                            form_fields, file_paths = parse_multipart_form(raw, content_type)
                            
                            name = form_fields.get("name", "unknown")
                            lang = form_fields.get("lang", "en")
                            script = form_fields.get("reference_script", "")
                            audio_path = file_paths.get("reference_audio")
                            duration = 30.0  # Default for multipart
                            
                            if not audio_path:
                                self._error(400, "INVALID_INPUT", "Reference audio required")
                                return
                                
                        except Exception as e:
                            self._error(400, "INVALID_INPUT", str(e))
                            return
                    else:
                        # Handle JSON payload (legacy)
                        try:
                            payload = json.loads(raw.decode()) if raw else {}
                        except json.JSONDecodeError:
                            self._error(400, "INVALID_INPUT", "Invalid JSON")
                            return

                        duration = float(payload.get("duration", 0))
                        script = payload.get("script", "")
                        name = payload.get("name", "unknown")
                        lang = payload.get("lang", "en")
                        audio_path = "dummy.wav"  # Dummy for backward compatibility
                    
                    # Validate inputs using security middleware
                    validator = server.security_middleware.input_validator
                    
                    valid, error = validator.validate_speaker_name(name)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return
                    
                    valid, error = validator.validate_language_code(lang)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return
                    
                    valid, error = validator.validate_script_text(script)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return
                    
                    # Check reference audio duration
                    if duration < 30:
                        self._error(422, "INSUFFICIENT_REF", "Reference audio must be at least 30 seconds")
                        return
                    
                    # Create speaker and job
                    speaker_id = server.db.create_speaker(name, lang)
                    job_id = server.db.create_job("register_speaker", metadata={
                        "speaker_id": speaker_id,
                        "audio_path": audio_path,
                        "script": script,
                    })
                    
                    # Queue the task
                    if server.use_celery:
                        # Use Celery for async processing
                        celery_register_speaker.delay(
                            job_id,
                            speaker_id,
                            audio_path,
                            script,
                            lang,
                        )
                    else:
                        # Use in-memory queue
                        server.job_queue.put((
                            "register_speaker",
                            job_id,
                            speaker_id,
                            audio_path,
                            script,
                            lang,
                        ))

                    response = {
                        "job_id": job_id,
                        "speaker_id": speaker_id,
                    }
                    self._json(202, response)  # Accepted
                    
                elif self.path == "/v1/synthesize":
                    try:
                        payload = json.loads(raw.decode()) if raw else {}
                    except json.JSONDecodeError:
                        self._error(400, "INVALID_INPUT", "Invalid JSON")
                        return

                    script = payload.get("script")
                    caption_format = payload.get("caption_format", "json")
                    output_format = payload.get("output_format", "wav")
                    sample_rate = payload.get("sample_rate", 48000)
                    
                    # Validate inputs using security middleware
                    validator = server.security_middleware.input_validator
                    
                    valid, error = validator.validate_synthesis_script(script)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return
                    
                    valid, error = validator.validate_output_format(output_format)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return
                    
                    valid, error = validator.validate_sample_rate(sample_rate)
                    if not valid:
                        self._error(400, "INVALID_INPUT", error)
                        return

                    # Create job
                    job_id = server.db.create_job("synthesize", metadata={
                        "script": script,
                        "output_format": output_format,
                        "sample_rate": sample_rate,
                        "caption_format": caption_format,
                    })
                    
                    # Queue the synthesis task
                    if server.use_celery:
                        # Use Celery for async processing
                        celery_synthesize.delay(
                            job_id, script, output_format, sample_rate, caption_format
                        )
                    else:
                        # Use in-memory queue
                        server.job_queue.put((
                            "synthesize",
                            job_id,
                            script,
                            output_format,
                            sample_rate,
                            caption_format,
                        ))

                    response = {"job_id": job_id}
                    self._json(202, response)  # Accepted
                    
                else:
                    self._error(404, "NOT_FOUND")

        def log_message(self, format: str, *args) -> None:
            # Suppress default logging
            return

        return Handler

    def _worker_loop(self) -> None:
        """Worker loop for in-memory queue processing."""
        while not self._stop_event.is_set():
            try:
                item = self.job_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                continue
                
            # Process different job types
            if item[0] == "register_speaker":
                _, job_id, speaker_id, audio_path, script, lang = item
                # In real implementation, this would call the actual processing
                self.db.update_job(job_id, status="succeeded")
                self.db.record_usage(30.0, job_id=job_id, speaker_id=speaker_id)
                
            elif item[0] == "synthesize":
                _, job_id, script, output_format, sample_rate, caption_format = item
                # In real implementation, this would call the actual synthesis
                audio_length = len(script) * 2.0  # Dummy calculation
                self.db.update_job(
                    job_id,
                    status="succeeded",
                    audio_url=f"dummy://{job_id}.{output_format}",
                    caption_path=f"dummy://{job_id}.{caption_format}",
                    caption_format=caption_format,
                )
                self.db.record_usage(audio_length, job_id=job_id)
                
            self.job_queue.task_done()

    # Public methods
    @property
    def address(self) -> tuple[str, int]:
        return self.httpd.server_address

    def start(self) -> None:
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        self.thread.start()

        # Only start worker thread if not using Celery
        if not self.use_celery:
            self.worker = threading.Thread(target=self._worker_loop)
            self.worker.daemon = True
            self.worker.start()

    def stop(self) -> None:
        if self.thread:
            self.httpd.shutdown()
            self.thread.join()
            self.thread = None
        if self.worker:
            self._stop_event.set()
            self.job_queue.put(None)
            self.worker.join()
            self.worker = None
            self._stop_event.clear()
        if hasattr(self, 'db'):
            self.db.close()

    def wait_all_jobs(self, timeout: float = 1.0) -> None:
        end = datetime.now().timestamp() + timeout
        while datetime.now().timestamp() < end:
            if self.job_queue.empty():
                return
            time.sleep(0.01)

    def _presign_path(self, path: str | None) -> str | None:
        """Generate presigned URL for storage path."""
        if not path:
            return None
        
        try:
            storage_manager = get_storage_manager()
            storage_type, key = parse_storage_url(path)
            
            if storage_type == "s3":
                # Generate S3 presigned URL
                return storage_manager.generate_presigned_url(
                    key, expires_in=self.PRESIGNED_TTL
                )
            else:
                # For local files, return the file:// URL directly
                return path
                
        except Exception as e:
            # Fallback to simple expiry parameter for backward compatibility
            expiry = int(time.time()) + self.PRESIGNED_TTL
            return f"{path}?expires={expiry}"