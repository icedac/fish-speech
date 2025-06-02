"""Redis client utilities for VoiceReel."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis
from redis.exceptions import RedisError


class RedisClient:
    """Wrapper for Redis operations with job state management."""
    
    def __init__(self, url: Optional[str] = None):
        self.url = url or os.getenv("VR_REDIS_URL", "redis://localhost:6379/0")
        self._client = None
        
    @property
    def client(self) -> redis.Redis:
        """Lazy Redis client initialization."""
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
        return self._client
    
    def set_job_status(
        self, 
        job_id: str, 
        status: str, 
        metadata: Optional[dict] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set job status in Redis.
        
        Args:
            job_id: Job identifier
            status: Job status (pending/processing/succeeded/failed)
            metadata: Additional job metadata
            ttl: Time-to-live in seconds
            
        Returns:
            True if successful
        """
        try:
            key = f"voicereel:job:{job_id}"
            data = {
                "status": status,
                "updated_at": self.client.time()[0],
            }
            if metadata:
                data.update(metadata)
                
            self.client.hset(key, mapping={
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in data.items()
            })
            
            if ttl:
                self.client.expire(key, ttl)
                
            return True
        except RedisError:
            return False
    
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get job status from Redis.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job data dict or None if not found
        """
        try:
            key = f"voicereel:job:{job_id}"
            data = self.client.hgetall(key)
            
            if not data:
                return None
                
            # Parse JSON fields
            result = {}
            for k, v in data.items():
                try:
                    result[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[k] = v
                    
            return result
        except RedisError:
            return None
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job data from Redis."""
        try:
            key = f"voicereel:job:{job_id}"
            return bool(self.client.delete(key))
        except RedisError:
            return False
    
    def get_queue_size(self, queue_name: str = "celery") -> int:
        """Get number of tasks in queue."""
        try:
            return self.client.llen(queue_name)
        except RedisError:
            return -1
    
    def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self.client.ping()
        except RedisError:
            return False