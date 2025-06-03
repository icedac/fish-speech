"""S3 storage integration for VoiceReel."""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO, Union
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from loguru import logger

from .config import config


class S3StorageManager:
    """Manages S3 storage operations for VoiceReel."""
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        use_local_fallback: bool = True,
    ):
        self.bucket_name = bucket_name or os.getenv("VOICEREEL_S3_BUCKET", "voicereel-audio")
        self.use_local_fallback = use_local_fallback
        self.local_storage_path = Path(config.AUDIO_OUTPUT_PATH)
        
        # Initialize S3 client
        self.s3_client = None
        self.s3_available = False
        
        try:
            session = boto3.Session(
                aws_access_key_id=aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=aws_region or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
            
            self.s3_client = session.client(
                "s3",
                endpoint_url=endpoint_url or os.getenv("AWS_ENDPOINT_URL"),
            )
            
            # Test S3 connectivity
            self._test_s3_connection()
            self.s3_available = True
            logger.info(f"S3 storage initialized successfully. Bucket: {self.bucket_name}")
            
        except (NoCredentialsError, ClientError) as e:
            logger.warning(f"S3 not available: {e}. Using local storage fallback.")
            self.s3_available = False
        
        # Ensure local storage directory exists
        if self.use_local_fallback:
            self.local_storage_path.mkdir(parents=True, exist_ok=True)
    
    def _test_s3_connection(self) -> None:
        """Test S3 connection and create bucket if needed."""
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket '{self.bucket_name}' is accessible")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                # Bucket doesn't exist, try to create it
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created S3 bucket: {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create S3 bucket: {create_error}")
                    raise
            else:
                logger.error(f"S3 bucket access error: {e}")
                raise
    
    def upload_file(
        self,
        file_path: str,
        key: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        expires_hours: int = 48,
    ) -> str:
        """
        Upload file to S3 or local storage.
        
        Args:
            file_path: Path to local file to upload
            key: S3 key (path). If None, uses filename with timestamp
            content_type: MIME type of file
            metadata: Additional metadata to store
            expires_hours: Hours until automatic deletion
            
        Returns:
            URL to access the uploaded file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_path = Path(file_path)
        
        # Generate key if not provided
        if key is None:
            timestamp = int(time.time())
            key = f"audio/{timestamp}_{file_path.name}"
        
        # Determine content type
        if content_type is None:
            content_type = self._get_content_type(file_path.suffix)
        
        # Prepare metadata
        upload_metadata = {
            "uploaded_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat(),
            "original_filename": file_path.name,
        }
        if metadata:
            upload_metadata.update(metadata)
        
        if self.s3_available:
            return self._upload_to_s3(file_path, key, content_type, upload_metadata)
        elif self.use_local_fallback:
            return self._upload_to_local(file_path, key, upload_metadata)
        else:
            raise RuntimeError("No storage backend available")
    
    def _upload_to_s3(
        self, 
        file_path: Path, 
        key: str, 
        content_type: str, 
        metadata: Dict[str, str]
    ) -> str:
        """Upload file to S3."""
        try:
            extra_args = {
                "ContentType": content_type,
                "Metadata": metadata,
            }
            
            # Add lifecycle tags for automatic deletion
            extra_args["Tagging"] = f"AutoDelete=true&ExpiresAt={metadata['expires_at']}"
            
            # Upload file
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                key,
                ExtraArgs=extra_args
            )
            
            # Return S3 URL
            url = f"s3://{self.bucket_name}/{key}"
            logger.info(f"Uploaded to S3: {key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            if self.use_local_fallback:
                logger.info("Falling back to local storage")
                return self._upload_to_local(file_path, key, metadata)
            raise
    
    def _upload_to_local(
        self, 
        file_path: Path, 
        key: str, 
        metadata: Dict[str, str]
    ) -> str:
        """Upload file to local storage."""
        # Create target path
        local_key = key.replace("/", "_")  # Flatten path for local storage
        target_path = self.local_storage_path / local_key
        
        # Copy file
        import shutil
        shutil.copy2(file_path, target_path)
        
        # Save metadata
        metadata_path = target_path.with_suffix(target_path.suffix + ".meta")
        import json
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Uploaded to local storage: {target_path}")
        return f"file://{target_path}"
    
    def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 900,  # 15 minutes
        method: str = "GET",
    ) -> str:
        """
        Generate presigned URL for S3 object.
        
        Args:
            key: S3 object key
            expires_in: URL expiration time in seconds
            method: HTTP method (GET, PUT, etc.)
            
        Returns:
            Presigned URL string
        """
        if not self.s3_available:
            # For local files, return file path
            local_key = key.replace("/", "_")
            local_path = self.local_storage_path / local_key
            if local_path.exists():
                return f"file://{local_path}"
            else:
                raise FileNotFoundError(f"Local file not found: {local_path}")
        
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            logger.debug(f"Generated presigned URL for {key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    def delete_file(self, key: str) -> bool:
        """
        Delete file from storage.
        
        Args:
            key: File key/path
            
        Returns:
            True if successful
        """
        if self.s3_available:
            return self._delete_from_s3(key)
        else:
            return self._delete_from_local(key)
    
    def _delete_from_s3(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted from S3: {key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete from S3: {e}")
            return False
    
    def _delete_from_local(self, key: str) -> bool:
        """Delete file from local storage."""
        try:
            local_key = key.replace("/", "_")
            local_path = self.local_storage_path / local_key
            metadata_path = local_path.with_suffix(local_path.suffix + ".meta")
            
            # Delete main file
            if local_path.exists():
                local_path.unlink()
            
            # Delete metadata file
            if metadata_path.exists():
                metadata_path.unlink()
            
            logger.info(f"Deleted from local storage: {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from local storage: {e}")
            return False
    
    def cleanup_expired_files(self) -> Dict[str, int]:
        """
        Clean up expired files.
        
        Returns:
            Dict with cleanup statistics
        """
        if self.s3_available:
            return self._cleanup_s3_expired()
        else:
            return self._cleanup_local_expired()
    
    def _cleanup_s3_expired(self) -> Dict[str, int]:
        """Clean up expired S3 files."""
        deleted_count = 0
        total_count = 0
        
        try:
            # List objects with AutoDelete tag
            paginator = self.s3_client.get_paginator("list_objects_v2")
            
            for page in paginator.paginate(Bucket=self.bucket_name):
                if "Contents" not in page:
                    continue
                
                for obj in page["Contents"]:
                    total_count += 1
                    key = obj["Key"]
                    
                    try:
                        # Get object tagging
                        tagging = self.s3_client.get_object_tagging(
                            Bucket=self.bucket_name, Key=key
                        )
                        
                        # Check if expired
                        for tag in tagging.get("TagSet", []):
                            if tag["Key"] == "ExpiresAt":
                                expires_at = datetime.fromisoformat(tag["Value"])
                                if datetime.utcnow() > expires_at:
                                    self.delete_file(key)
                                    deleted_count += 1
                                break
                                
                    except ClientError:
                        # Skip if can't get tags
                        continue
            
            logger.info(f"S3 cleanup: deleted {deleted_count}/{total_count} expired files")
            
        except ClientError as e:
            logger.error(f"S3 cleanup failed: {e}")
        
        return {"deleted": deleted_count, "total": total_count}
    
    def _cleanup_local_expired(self) -> Dict[str, int]:
        """Clean up expired local files."""
        deleted_count = 0
        total_count = 0
        
        try:
            import json
            
            for meta_file in self.local_storage_path.glob("*.meta"):
                total_count += 1
                
                try:
                    with open(meta_file) as f:
                        metadata = json.load(f)
                    
                    expires_at_str = metadata.get("expires_at")
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)
                        if datetime.utcnow() > expires_at:
                            # Delete main file and metadata
                            main_file = meta_file.with_suffix("")
                            if main_file.exists():
                                main_file.unlink()
                            meta_file.unlink()
                            deleted_count += 1
                            
                except Exception as e:
                    logger.warning(f"Failed to process {meta_file}: {e}")
                    continue
            
            logger.info(f"Local cleanup: deleted {deleted_count}/{total_count} expired files")
            
        except Exception as e:
            logger.error(f"Local cleanup failed: {e}")
        
        return {"deleted": deleted_count, "total": total_count}
    
    def _get_content_type(self, file_extension: str) -> str:
        """Get MIME type for file extension."""
        content_types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".mp4": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".json": "application/json",
            ".txt": "text/plain",
            ".vtt": "text/vtt",
            ".srt": "text/plain",
        }
        return content_types.get(file_extension.lower(), "application/octet-stream")
    
    def get_file_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get file information.
        
        Args:
            key: File key
            
        Returns:
            Dict with file info or None if not found
        """
        if self.s3_available:
            return self._get_s3_file_info(key)
        else:
            return self._get_local_file_info(key)
    
    def _get_s3_file_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get S3 file information."""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return {
                "key": key,
                "size": response.get("ContentLength", 0),
                "content_type": response.get("ContentType", "unknown"),
                "last_modified": response.get("LastModified"),
                "metadata": response.get("Metadata", {}),
                "storage": "s3",
            }
        except ClientError:
            return None
    
    def _get_local_file_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get local file information."""
        try:
            local_key = key.replace("/", "_")
            local_path = self.local_storage_path / local_key
            metadata_path = local_path.with_suffix(local_path.suffix + ".meta")
            
            if not local_path.exists():
                return None
            
            # Get file stats
            stat = local_path.stat()
            
            # Load metadata if available
            metadata = {}
            if metadata_path.exists():
                import json
                with open(metadata_path) as f:
                    metadata = json.load(f)
            
            return {
                "key": key,
                "size": stat.st_size,
                "content_type": self._get_content_type(local_path.suffix),
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
                "metadata": metadata,
                "storage": "local",
            }
        except Exception:
            return None
    
    def health_check(self) -> Dict[str, Any]:
        """Check storage health."""
        status = {
            "s3_available": self.s3_available,
            "local_fallback_enabled": self.use_local_fallback,
            "bucket_name": self.bucket_name if self.s3_available else None,
            "local_storage_path": str(self.local_storage_path) if self.use_local_fallback else None,
        }
        
        # Test S3 if available
        if self.s3_available:
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                status["s3_healthy"] = True
            except Exception as e:
                status["s3_healthy"] = False
                status["s3_error"] = str(e)
        
        # Test local storage if enabled
        if self.use_local_fallback:
            try:
                test_file = self.local_storage_path / ".health_check"
                test_file.write_text("test")
                test_file.unlink()
                status["local_healthy"] = True
            except Exception as e:
                status["local_healthy"] = False
                status["local_error"] = str(e)
        
        return status


# Global storage manager instance
_storage_manager: Optional[S3StorageManager] = None


def get_storage_manager() -> S3StorageManager:
    """Get global storage manager instance."""
    global _storage_manager
    
    if _storage_manager is None:
        _storage_manager = S3StorageManager()
    
    return _storage_manager


def parse_storage_url(url: str) -> tuple[str, str]:
    """
    Parse storage URL to extract storage type and key.
    
    Args:
        url: Storage URL (s3://bucket/key or file://path)
        
    Returns:
        Tuple of (storage_type, key)
    """
    parsed = urlparse(url)
    
    if parsed.scheme == "s3":
        # S3 URL: s3://bucket/key
        return "s3", parsed.path.lstrip("/")
    elif parsed.scheme == "file":
        # Local file URL: file://path
        path = Path(parsed.path)
        return "local", path.name
    else:
        # Assume local path
        path = Path(url)
        return "local", path.name