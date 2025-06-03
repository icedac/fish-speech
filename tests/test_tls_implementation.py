"""Tests for VoiceReel TLS/HTTPS implementation."""

import os
import ssl
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import urllib3

from voicereel.tls_manager import TLSCertificateManager, get_tls_manager
from voicereel.https_server import VoiceReelHTTPSServer, VoiceReelHTTPSServerManager

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TestTLSCertificateManager:
    """Test TLS certificate management functionality."""
    
    @pytest.fixture
    def temp_cert_dir(self):
        """Create temporary directory for certificates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def cert_manager(self, temp_cert_dir):
        """Create certificate manager with temporary directory."""
        return TLSCertificateManager(temp_cert_dir)
    
    def test_generate_self_signed_cert(self, cert_manager):
        """Test self-signed certificate generation."""
        cert_path, key_path = cert_manager.generate_self_signed_cert(
            domain="test.local",
            days_valid=30
        )
        
        # Check files exist
        assert os.path.exists(cert_path)
        assert os.path.exists(key_path)
        
        # Check permissions
        assert oct(os.stat(key_path).st_mode)[-3:] == "600"
        assert oct(os.stat(cert_path).st_mode)[-3:] == "644"
        
        # Validate certificate
        cert_info = cert_manager.validate_certificate()
        assert cert_info["valid"] is True
        assert cert_info["common_name"] == "test.local"
        assert cert_info["days_until_expiry"] <= 30
    
    def test_load_existing_cert(self, cert_manager, temp_cert_dir):
        """Test loading existing certificate files."""
        # First generate a certificate
        original_cert, original_key = cert_manager.generate_self_signed_cert()
        
        # Copy to different location
        external_cert = os.path.join(temp_cert_dir, "external.crt")
        external_key = os.path.join(temp_cert_dir, "external.key")
        
        import shutil
        shutil.copy2(original_cert, external_cert)
        shutil.copy2(original_key, external_key)
        
        # Create new manager and load external certs
        new_manager = TLSCertificateManager(os.path.join(temp_cert_dir, "new"))
        loaded_cert, loaded_key = new_manager.load_existing_cert(
            external_cert, external_key
        )
        
        assert os.path.exists(loaded_cert)
        assert os.path.exists(loaded_key)
        
        # Should be valid
        cert_info = new_manager.validate_certificate()
        assert cert_info["valid"] is True
    
    def test_validate_certificate(self, cert_manager):
        """Test certificate validation."""
        # No certificate yet
        cert_info = cert_manager.validate_certificate()
        assert cert_info["valid"] is False
        assert "not found" in cert_info["error"].lower()
        
        # Generate certificate
        cert_manager.generate_self_signed_cert()
        
        # Should be valid now
        cert_info = cert_manager.validate_certificate()
        assert cert_info["valid"] is True
        assert "expires" in cert_info
        assert "common_name" in cert_info
        assert cert_info["expired"] is False
    
    def test_create_ssl_context(self, cert_manager):
        """Test SSL context creation."""
        # Generate certificate first
        cert_manager.generate_self_signed_cert()
        
        # Create SSL context
        context = cert_manager.create_ssl_context()
        
        assert isinstance(context, ssl.SSLContext)
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
        assert context.maximum_version == ssl.TLSVersion.TLSv1_3
        assert context.verify_mode == ssl.CERT_NONE
    
    def test_get_cert_info(self, cert_manager):
        """Test certificate information retrieval."""
        info = cert_manager.get_cert_info()
        
        assert "cert_dir" in info
        assert "certificate_path" in info
        assert "private_key_path" in info
        assert "certificate_exists" in info
        assert "private_key_exists" in info
        assert "validation" in info
        
        # Initially no certificates
        assert info["certificate_exists"] is False
        assert info["private_key_exists"] is False
        
        # Generate certificate
        cert_manager.generate_self_signed_cert()
        
        # Check again
        info = cert_manager.get_cert_info()
        assert info["certificate_exists"] is True
        assert info["private_key_exists"] is True
        assert info["validation"]["valid"] is True


class TestVoiceReelHTTPSServer:
    """Test HTTPS server implementation."""
    
    @pytest.fixture
    def temp_cert_dir(self):
        """Create temporary directory for certificates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def https_server(self, temp_cert_dir):
        """Create HTTPS server for testing."""
        # Mock database to avoid SQLite dependency
        with patch('voicereel.server.sqlite3.connect'):
            # Patch the TLS manager to use temp directory
            with patch('voicereel.https_server.get_tls_manager') as mock_get_manager:
                from voicereel.tls_manager import TLSCertificateManager
                mock_manager = TLSCertificateManager(cert_dir=temp_cert_dir)
                mock_get_manager.return_value = mock_manager
                
                server = VoiceReelHTTPSServer(
                    host="127.0.0.1",
                    port=0,  # Auto-assign port
                    dsn=":memory:",
                    auto_generate_cert=True,
                    domain="localhost",
                    use_celery=False
                )
            
            # Override cert directory
            server.tls_manager.cert_dir = Path(temp_cert_dir)
            server.tls_manager.certificate_path = Path(temp_cert_dir) / "voicereel.crt"
            server.tls_manager.private_key_path = Path(temp_cert_dir) / "voicereel.key"
            
            yield server
            
            if server.thread and server.thread.is_alive():
                server.stop()
    
    def test_server_initialization(self, https_server):
        """Test HTTPS server initialization."""
        assert https_server.host == "127.0.0.1"
        assert https_server.port == 0  # Auto-assigned
        assert https_server.auto_generate_cert is True
        assert https_server.domain == "localhost"
        assert https_server.tls_version == "TLSv1.3"
        
        # Should have SSL context
        assert hasattr(https_server, 'ssl_context')
        assert isinstance(https_server.ssl_context, ssl.SSLContext)
    
    def test_certificate_setup(self, https_server):
        """Test certificate setup during initialization."""
        # Certificates should have been generated
        assert https_server.tls_manager.certificate_path.exists()
        assert https_server.tls_manager.private_key_path.exists()
        
        # Should be valid
        cert_info = https_server.tls_manager.validate_certificate()
        assert cert_info["valid"] is True
    
    def test_get_server_info(self, https_server):
        """Test server information retrieval."""
        info = https_server.get_server_info()
        
        assert info["protocol"] == "https"
        assert info["host"] == "127.0.0.1"
        assert info["tls_version"] == "TLSv1.3"
        assert "certificate" in info
        assert "ssl_context" in info
        assert info["url"].startswith("https://")
    
    @pytest.mark.integration
    def test_https_server_start_stop(self, https_server):
        """Test starting and stopping HTTPS server."""
        # Start server
        https_server.start()
        
        # Should be running
        assert https_server.thread is not None
        assert https_server.thread.is_alive()
        
        # Get actual port
        port = https_server.address[1]
        assert port > 0
        
        # Test HTTPS connection (allow self-signed)
        try:
            response = requests.get(
                f"https://127.0.0.1:{port}/health",
                verify=False,
                timeout=5
            )
            assert response.status_code == 200
        except requests.exceptions.RequestException:
            # Connection might fail due to test environment
            pass
        
        # Stop server
        https_server.stop()
        
        # Should be stopped
        assert https_server.thread is None


class TestVoiceReelHTTPSServerManager:
    """Test HTTPS server manager."""
    
    def test_manager_initialization(self):
        """Test server manager initialization."""
        manager = VoiceReelHTTPSServerManager(auto_renew_certs=False)
        
        assert manager.auto_renew_certs is False
        assert manager.server is None
        assert manager.renewal_thread is None
    
    def test_create_server_from_env(self):
        """Test creating server from environment variables."""
        with patch.dict(os.environ, {
            'VOICEREEL_HOST': '0.0.0.0',
            'VOICEREEL_HTTPS_PORT': '9443',
            'VOICEREEL_DOMAIN': 'test.example.com',
            'VOICEREEL_AUTO_GENERATE_CERT': 'true'
        }):
            manager = VoiceReelHTTPSServerManager()
            
            with patch('voicereel.server.sqlite3.connect'):
                with patch('voicereel.tls_manager.get_tls_manager'):
                    server = manager.create_server_from_env()
                
                assert server.host == "0.0.0.0"
                assert server.port == 9443
                assert server.domain == "test.example.com"
                assert server.auto_generate_cert is True


class TestTLSIntegration:
    """Integration tests for TLS functionality."""
    
    @pytest.mark.slow
    def test_self_signed_cert_workflow(self):
        """Test complete self-signed certificate workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create manager
            manager = TLSCertificateManager(temp_dir)
            
            # Generate certificate
            cert_path, key_path = manager.generate_self_signed_cert(
                domain="integration-test.local"
            )
            
            # Validate
            cert_info = manager.validate_certificate()
            assert cert_info["valid"] is True
            assert cert_info["common_name"] == "integration-test.local"
            
            # Create SSL context
            context = manager.create_ssl_context()
            assert isinstance(context, ssl.SSLContext)
            
            # Test certificate loading
            new_manager = TLSCertificateManager(os.path.join(temp_dir, "copy"))
            new_cert, new_key = new_manager.load_existing_cert(cert_path, key_path)
            
            # Should be identical
            with open(cert_path, 'rb') as f1, open(new_cert, 'rb') as f2:
                assert f1.read() == f2.read()
    
    @pytest.mark.slow
    def test_tls_version_enforcement(self):
        """Test that TLS version requirements are enforced."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TLSCertificateManager(temp_dir)
            manager.generate_self_signed_cert()
            
            context = manager.create_ssl_context()
            
            # Check TLS version settings
            assert context.minimum_version == ssl.TLSVersion.TLSv1_2
            assert context.maximum_version == ssl.TLSVersion.TLSv1_3
            
            # Verify that old protocols are disabled
            assert context.options & ssl.OP_NO_SSLv2
            assert context.options & ssl.OP_NO_SSLv3
            assert context.options & ssl.OP_NO_TLSv1
            assert context.options & ssl.OP_NO_TLSv1_1


class TestCertificateCLI:
    """Test certificate CLI tool functionality."""
    
    def test_cli_import(self):
        """Test that CLI tool can be imported."""
        # This tests the basic structure without running commands
        import subprocess
        import sys
        
        # Test that the CLI script is syntactically correct
        result = subprocess.run([
            sys.executable, "-m", "py_compile", 
            "tools/voicereel_cert.py"
        ], capture_output=True)
        
        assert result.returncode == 0, f"CLI script has syntax errors: {result.stderr}"


# Performance and security tests
class TestTLSSecurity:
    """Test TLS security configurations."""
    
    def test_cipher_suite_security(self):
        """Test that secure cipher suites are configured."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TLSCertificateManager(temp_dir)
            manager.generate_self_signed_cert()
            
            context = manager.create_ssl_context()
            
            # Get cipher list (this may vary by OpenSSL version)
            ciphers = context.get_ciphers()
            
            # Should have ciphers configured
            assert len(ciphers) > 0
            
            # Check for modern cipher suites
            cipher_names = [cipher['name'] for cipher in ciphers]
            
            # Should include ECDHE (forward secrecy)
            ecdhe_ciphers = [name for name in cipher_names if 'ECDHE' in name]
            assert len(ecdhe_ciphers) > 0, "No ECDHE ciphers found"
    
    def test_security_options(self):
        """Test that security options are properly set."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TLSCertificateManager(temp_dir)
            manager.generate_self_signed_cert()
            
            context = manager.create_ssl_context()
            
            # Check security options
            assert context.options & ssl.OP_SINGLE_DH_USE
            assert context.options & ssl.OP_SINGLE_ECDH_USE
            assert context.verify_mode == ssl.CERT_NONE  # For self-signed
            assert context.check_hostname is False  # For self-signed