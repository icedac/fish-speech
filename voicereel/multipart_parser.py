"""Simple multipart form parser for VoiceReel."""

import io
import os
import tempfile
from typing import Dict, Optional, Tuple, BinaryIO
from urllib.parse import unquote


class MultipartParser:
    """Simple multipart/form-data parser."""
    
    def __init__(self, data: bytes, boundary: str):
        self.data = data
        self.boundary = boundary.encode()
        self.parts: Dict[str, any] = {}
        self.files: Dict[str, str] = {}  # field_name -> temp_file_path
        
    def parse(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Parse multipart data.
        
        Returns:
            Tuple of (form_fields, file_paths)
        """
        # Split by boundary
        parts = self.data.split(b'--' + self.boundary)
        
        form_fields = {}
        file_paths = {}
        
        for part in parts[1:-1]:  # Skip first empty and last closing parts
            if not part.strip():
                continue
                
            # Find headers/body separator
            if b'\r\n\r\n' in part:
                headers_data, body = part.split(b'\r\n\r\n', 1)
            else:
                continue
                
            headers = self._parse_headers(headers_data)
            content_disposition = headers.get('content-disposition', '')
            
            if 'name=' in content_disposition:
                field_name = self._extract_name(content_disposition)
                
                if 'filename=' in content_disposition:
                    # File upload
                    filename = self._extract_filename(content_disposition)
                    temp_path = self._save_temp_file(body, filename)
                    file_paths[field_name] = temp_path
                else:
                    # Regular form field
                    value = body.decode('utf-8').strip()
                    form_fields[field_name] = value
        
        return form_fields, file_paths
    
    def _parse_headers(self, headers_data: bytes) -> Dict[str, str]:
        """Parse HTTP headers."""
        headers = {}
        lines = headers_data.decode().strip().split('\r\n')
        
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
        
        return headers
    
    def _extract_name(self, disposition: str) -> str:
        """Extract field name from Content-Disposition header."""
        for part in disposition.split(';'):
            part = part.strip()
            if part.startswith('name='):
                name = part[5:].strip('"\'')
                return unquote(name)
        return ""
    
    def _extract_filename(self, disposition: str) -> str:
        """Extract filename from Content-Disposition header."""
        for part in disposition.split(';'):
            part = part.strip()
            if part.startswith('filename='):
                filename = part[9:].strip('"\'')
                return unquote(filename)
        return "upload"
    
    def _save_temp_file(self, data: bytes, filename: str) -> str:
        """Save uploaded data to temporary file."""
        # Get file extension
        _, ext = os.path.splitext(filename)
        if not ext:
            ext = '.bin'
        
        # Create temporary file
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='voicereel_upload_')
        
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            return temp_path
        except Exception:
            os.close(fd)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def cleanup(self):
        """Clean up temporary files."""
        for temp_path in self.files.values():
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


def parse_multipart_form(data: bytes, content_type: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Parse multipart/form-data.
    
    Args:
        data: Raw form data
        content_type: Content-Type header value
        
    Returns:
        Tuple of (form_fields, file_paths)
    """
    if not content_type.startswith('multipart/form-data'):
        raise ValueError("Not multipart/form-data")
    
    # Extract boundary
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[9:].strip('"\'')
            break
    
    if not boundary:
        raise ValueError("No boundary found in Content-Type")
    
    parser = MultipartParser(data, boundary)
    return parser.parse()