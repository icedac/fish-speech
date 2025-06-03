# VoiceReel TLS 1.3 Deployment Guide

This guide covers deploying VoiceReel with TLS 1.3 support for production security requirements.

## Overview

VoiceReel implements comprehensive TLS 1.3 support including:
- **Automatic certificate management** (self-signed and Let's Encrypt)
- **TLS 1.3 preferred with TLS 1.2 minimum** for compatibility
- **Modern cipher suites** with forward secrecy
- **Docker deployment** with NGINX reverse proxy
- **Certificate lifecycle management** with auto-renewal

## Quick Start

### Development (Self-Signed Certificates)

```bash
# Generate self-signed certificate
python tools/voicereel_cert.py generate --domain localhost

# Start HTTPS server
export VOICEREEL_ENABLE_HTTPS=true
python -m voicereel.https_server
```

### Production (Let's Encrypt)

```bash
# Set domain and email
export VOICEREEL_DOMAIN=api.yourdomain.com
export LETSENCRYPT_EMAIL=admin@yourdomain.com

# Deploy with Docker Compose
docker-compose -f docker-compose.https.yml up -d
```

## Certificate Management

### Using the Certificate CLI Tool

The `voicereel_cert.py` tool provides comprehensive certificate management:

```bash
# Generate self-signed certificate for development
python tools/voicereel_cert.py generate --domain localhost --days 365

# Setup Let's Encrypt certificate for production  
python tools/voicereel_cert.py letsencrypt \
  --domain api.example.com \
  --email admin@example.com

# Load existing certificate files
python tools/voicereel_cert.py load \
  --cert-file /path/to/cert.pem \
  --key-file /path/to/key.pem

# Validate current certificate
python tools/voicereel_cert.py validate

# Show certificate information
python tools/voicereel_cert.py info

# Test SSL connection
python tools/voicereel_cert.py test --host localhost --port 8443
```

### Programmatic Certificate Management

```python
from voicereel.tls_manager import TLSCertificateManager

# Initialize manager
cert_manager = TLSCertificateManager("/etc/voicereel/certs")

# Generate self-signed certificate
cert_path, key_path = cert_manager.generate_self_signed_cert(
    domain="api.example.com",
    days_valid=365
)

# Validate certificate
cert_info = cert_manager.validate_certificate()
if cert_info["valid"]:
    print(f"Certificate expires: {cert_info['expires']}")
    print(f"Days until expiry: {cert_info['days_until_expiry']}")

# Create SSL context for server
ssl_context = cert_manager.create_ssl_context()
```

## HTTPS Server Configuration

### Basic HTTPS Server

```python
from voicereel.https_server import VoiceReelHTTPSServer

# Create HTTPS server
server = VoiceReelHTTPSServer(
    host="0.0.0.0",
    port=8443,
    auto_generate_cert=True,  # Generate self-signed for development
    domain="localhost",
    tls_version="TLSv1.3"
)

# Start server
server.start()
print(f"HTTPS server running on {server.get_server_info()['url']}")
```

### Production Server with Custom Certificates

```python
server = VoiceReelHTTPSServer(
    host="0.0.0.0", 
    port=8443,
    cert_path="/etc/ssl/certs/voicereel.crt",
    key_path="/etc/ssl/private/voicereel.key",
    auto_generate_cert=False,
    tls_version="TLSv1.3"
)
```

### Environment Variable Configuration

```bash
# HTTPS Configuration
export VOICEREEL_ENABLE_HTTPS=true
export VOICEREEL_HTTPS_PORT=8443
export VOICEREEL_HTTP_PORT=8080  # For redirects
export VOICEREEL_DOMAIN=api.example.com
export VOICEREEL_TLS_VERSION=TLSv1.3

# Certificate Management
export VOICEREEL_CERT_PATH=/path/to/cert.pem
export VOICEREEL_KEY_PATH=/path/to/key.pem
export VOICEREEL_AUTO_GENERATE_CERT=false
export VOICEREEL_CERT_DIR=/etc/voicereel/certs

# Let's Encrypt
export LETSENCRYPT_EMAIL=admin@example.com
```

## Docker Deployment

### Production Stack with NGINX + Let's Encrypt

The `docker-compose.https.yml` provides a complete production stack:

```yaml
# Key components:
# - VoiceReel HTTPS server (port 8443)
# - NGINX reverse proxy with TLS termination
# - Let's Encrypt certificate automation
# - PostgreSQL database
# - Redis for task queue
```

#### Deployment Steps

1. **Configure environment**:
   ```bash
   # Set your domain and email
   export VOICEREEL_DOMAIN=api.yourdomain.com
   export LETSENCRYPT_EMAIL=admin@yourdomain.com
   
   # Set API credentials
   export VR_API_KEY=your-secret-api-key
   export VR_HMAC_SECRET=your-hmac-secret
   ```

2. **Deploy the stack**:
   ```bash
   docker-compose -f docker-compose.https.yml up -d
   ```

3. **Verify deployment**:
   ```bash
   # Check certificate
   curl -v https://api.yourdomain.com/health
   
   # Test API endpoint
   curl -k -H "X-VR-APIKEY: your-api-key" \
        https://api.yourdomain.com/v1/speakers
   ```

### Development with Self-Signed Certificates

```bash
# Use localhost domain for development
export VOICEREEL_DOMAIN=localhost
docker-compose -f docker-compose.https.yml up -d

# Test with self-signed certificate
curl -k https://localhost:8443/health
```

## TLS Security Configuration

### TLS Version Support

VoiceReel implements the following TLS policy:
- **Preferred**: TLS 1.3 (latest security standard)
- **Minimum**: TLS 1.2 (for compatibility)
- **Disabled**: SSLv2, SSLv3, TLS 1.0, TLS 1.1 (insecure)

### Cipher Suite Configuration

Modern cipher suites with forward secrecy:
- **TLS 1.3**: AES-GCM, ChaCha20-Poly1305 (automatic)
- **TLS 1.2**: ECDHE+AESGCM, ECDHE+CHACHA20, DHE+AESGCM
- **Disabled**: RC4, DES, MD5, aNULL (weak ciphers)

### Security Headers

NGINX configuration includes security headers:
```nginx
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Referrer-Policy "strict-origin-when-cross-origin";
add_header Content-Security-Policy "default-src 'self'";
# add_header Strict-Transport-Security "max-age=31536000"; # Uncomment for HSTS
```

## Certificate Lifecycle Management

### Automatic Renewal

The HTTPS server manager supports automatic certificate renewal:

```python
from voicereel.https_server import VoiceReelHTTPSServerManager

# Enable automatic renewal monitoring
manager = VoiceReelHTTPSServerManager(auto_renew_certs=True)
server = manager.start_server()

# Manager will check certificate expiry daily
# and log warnings when certificates expire within 30 days
```

### Manual Renewal (Let's Encrypt)

```bash
# Renew certificates manually
certbot renew

# Copy renewed certificates to VoiceReel
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /etc/voicereel/certs/voicereel.crt
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /etc/voicereel/certs/voicereel.key

# Restart VoiceReel to load new certificates
docker-compose -f docker-compose.https.yml restart fish-speech-https
```

### Certificate Monitoring

```bash
# Check certificate status
python tools/voicereel_cert.py validate

# Get detailed certificate information
python tools/voicereel_cert.py info --json
```

## Load Balancing and High Availability

### Multiple HTTPS Servers

```bash
# Deploy multiple instances
docker-compose -f docker-compose.https.yml up --scale fish-speech-https=3
```

### Health Checks

```bash
# HTTP health check (allows HTTP for load balancer health checks)
curl http://api.yourdomain.com/health

# HTTPS health check
curl -k https://api.yourdomain.com/health
```

## Troubleshooting

### Common Issues

1. **Certificate not found**:
   ```bash
   # Check certificate files exist
   ls -la /etc/voicereel/certs/
   
   # Generate new certificate
   python tools/voicereel_cert.py generate --domain localhost
   ```

2. **Permission errors**:
   ```bash
   # Fix certificate permissions
   chmod 644 /etc/voicereel/certs/voicereel.crt
   chmod 600 /etc/voicereel/certs/voicereel.key
   ```

3. **Let's Encrypt failures**:
   ```bash
   # Check domain DNS
   nslookup api.yourdomain.com
   
   # Verify port 80 is accessible
   curl http://api.yourdomain.com/.well-known/acme-challenge/test
   
   # Use staging environment for testing
   python tools/voicereel_cert.py letsencrypt \
     --domain api.yourdomain.com \
     --email admin@yourdomain.com \
     --staging
   ```

4. **TLS connection errors**:
   ```bash
   # Test SSL connection
   python tools/voicereel_cert.py test --host api.yourdomain.com --port 443
   
   # Check with openssl
   openssl s_client -connect api.yourdomain.com:443 -servername api.yourdomain.com
   ```

### Debug Logging

Enable verbose logging for troubleshooting:

```bash
export VOICEREEL_LOG_LEVEL=DEBUG
python -m voicereel.https_server
```

### Certificate Validation

```python
from voicereel.tls_manager import get_tls_manager

manager = get_tls_manager()
cert_info = manager.validate_certificate()

if not cert_info["valid"]:
    print(f"Certificate error: {cert_info['error']}")
elif cert_info["expiring_soon"]:
    print(f"Certificate expires in {cert_info['days_until_expiry']} days")
else:
    print("Certificate is valid")
```

## Security Best Practices

1. **Use strong passwords** for certificate private keys in production
2. **Enable HSTS** headers for production domains
3. **Monitor certificate expiry** and set up alerts
4. **Use secure cipher suites** (automatically configured)
5. **Keep certificates secure** with proper file permissions
6. **Regular security updates** of OpenSSL and dependencies
7. **Use Let's Encrypt** for production domains when possible
8. **Implement certificate pinning** for critical deployments

## Production Checklist

- [ ] Domain DNS configured to point to server
- [ ] Firewall allows ports 80 (HTTP) and 443 (HTTPS)
- [ ] Let's Encrypt certificates obtained and validated
- [ ] NGINX reverse proxy configured with security headers
- [ ] Certificate auto-renewal configured
- [ ] Monitoring and alerting for certificate expiry
- [ ] Load balancer health checks configured
- [ ] Backup and restore procedures for certificates
- [ ] Security scan performed (SSL Labs, etc.)
- [ ] Documentation updated with domain-specific details

## Integration with Existing Infrastructure

### AWS Application Load Balancer

```yaml
# Use ALB for TLS termination and forward HTTP to VoiceReel
Target:
  Protocol: HTTP
  Port: 8080
  HealthCheck: /health
```

### Kubernetes Deployment

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: voicereel-tls
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-cert>
  tls.key: <base64-encoded-key>
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: voicereel-https
spec:
  template:
    spec:
      containers:
      - name: voicereel
        image: voicereel:latest
        ports:
        - containerPort: 8443
        volumeMounts:
        - name: tls-certs
          mountPath: /etc/voicereel/certs
      volumes:
      - name: tls-certs
        secret:
          secretName: voicereel-tls
```

This comprehensive TLS implementation ensures VoiceReel meets enterprise security requirements with modern TLS 1.3 support, automatic certificate management, and production-ready deployment options.