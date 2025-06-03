#!/usr/bin/env python3
"""VoiceReel TLS certificate management CLI tool."""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from voicereel.tls_manager import TLSCertificateManager, get_tls_manager


def cmd_generate_self_signed(args):
    """Generate self-signed certificate for development."""
    manager = get_tls_manager(args.cert_dir)
    
    try:
        cert_path, key_path = manager.generate_self_signed_cert(
            domain=args.domain,
            days_valid=args.days,
            key_size=args.key_size
        )
        
        print(f"✅ Self-signed certificate generated successfully!")
        print(f"Certificate: {cert_path}")
        print(f"Private key: {key_path}")
        print(f"Domain: {args.domain}")
        print(f"Valid for: {args.days} days")
        
        # Show validation info
        cert_info = manager.validate_certificate()
        if cert_info.get("valid"):
            print(f"Expires: {cert_info.get('expires')}")
        
    except Exception as e:
        print(f"❌ Failed to generate certificate: {e}")
        sys.exit(1)


def cmd_setup_letsencrypt(args):
    """Setup Let's Encrypt certificate."""
    manager = get_tls_manager(args.cert_dir)
    
    try:
        cert_path, key_path = manager.setup_letsencrypt_cert(
            domain=args.domain,
            email=args.email,
            staging=args.staging
        )
        
        print(f"✅ Let's Encrypt certificate obtained successfully!")
        print(f"Certificate: {cert_path}")
        print(f"Private key: {key_path}")
        print(f"Domain: {args.domain}")
        print(f"Email: {args.email}")
        
        if args.staging:
            print("⚠️  This is a STAGING certificate - not trusted by browsers")
        
    except Exception as e:
        print(f"❌ Failed to obtain Let's Encrypt certificate: {e}")
        print("Make sure:")
        print("  1. certbot is installed (apt-get install certbot)")
        print("  2. Domain points to this server")
        print("  3. Port 80 is accessible for HTTP challenge")
        sys.exit(1)


def cmd_load_existing(args):
    """Load existing certificate files."""
    manager = get_tls_manager(args.cert_dir)
    
    try:
        cert_path, key_path = manager.load_existing_cert(
            args.cert_file,
            args.key_file
        )
        
        print(f"✅ Certificate files loaded successfully!")
        print(f"Certificate: {cert_path}")
        print(f"Private key: {key_path}")
        
        # Show validation info
        cert_info = manager.validate_certificate()
        if cert_info.get("valid"):
            print(f"Expires: {cert_info.get('expires')}")
            print(f"Common Name: {cert_info.get('common_name')}")
            if cert_info.get("san_domains"):
                print(f"SAN Domains: {', '.join(cert_info.get('san_domains'))}")
        else:
            print(f"⚠️  Certificate validation failed: {cert_info.get('error')}")
        
    except Exception as e:
        print(f"❌ Failed to load certificate: {e}")
        sys.exit(1)


def cmd_validate(args):
    """Validate existing certificate."""
    manager = get_tls_manager(args.cert_dir)
    
    cert_info = manager.validate_certificate()
    
    if cert_info.get("valid"):
        print("✅ Certificate is valid")
    else:
        print("❌ Certificate is invalid")
        print(f"Error: {cert_info.get('error', 'Unknown error')}")
        return
    
    # Print detailed information
    print(f"\nCertificate Information:")
    print(f"  Common Name: {cert_info.get('common_name')}")
    print(f"  Serial Number: {cert_info.get('serial_number')}")
    print(f"  Issuer: {cert_info.get('issuer')}")
    print(f"  Expires: {cert_info.get('expires')}")
    print(f"  Days until expiry: {cert_info.get('days_until_expiry')}")
    
    if cert_info.get("san_domains"):
        print(f"  SAN Domains: {', '.join(cert_info.get('san_domains'))}")
    
    # Status indicators
    if cert_info.get("expired"):
        print("🔴 Certificate has expired!")
    elif cert_info.get("expiring_soon"):
        print("🟡 Certificate expires soon (within 30 days)")
    else:
        print("🟢 Certificate is valid and not expiring soon")


def cmd_info(args):
    """Show certificate and TLS configuration info."""
    manager = get_tls_manager(args.cert_dir)
    
    info = manager.get_cert_info()
    
    print("VoiceReel TLS Configuration")
    print("=" * 40)
    print(f"Certificate directory: {info['cert_dir']}")
    print(f"Certificate file: {info['certificate_path']}")
    print(f"Private key file: {info['private_key_path']}")
    print(f"Certificate exists: {'✅' if info['certificate_exists'] else '❌'}")
    print(f"Private key exists: {'✅' if info['private_key_exists'] else '❌'}")
    
    if args.json:
        print(json.dumps(info, indent=2, default=str))
    else:
        validation = info.get("validation", {})
        if validation.get("valid"):
            print(f"\nCertificate Status: ✅ Valid")
            print(f"Expires: {validation.get('expires')}")
            print(f"Days until expiry: {validation.get('days_until_expiry')}")
        elif validation.get("error"):
            print(f"\nCertificate Status: ❌ {validation.get('error')}")
        else:
            print(f"\nCertificate Status: ❌ Invalid")


def cmd_test_ssl(args):
    """Test SSL configuration."""
    import ssl
    import socket
    
    print(f"Testing SSL connection to {args.host}:{args.port}")
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        
        if args.insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        # Connect
        with socket.create_connection((args.host, args.port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=args.host) as ssock:
                print(f"✅ SSL connection successful!")
                print(f"Protocol: {ssock.version()}")
                print(f"Cipher: {ssock.cipher()[0]}")
                
                # Get certificate info
                cert = ssock.getpeercert()
                if cert:
                    print(f"Subject: {dict(x[0] for x in cert['subject'])}")
                    print(f"Issuer: {dict(x[0] for x in cert['issuer'])}")
                    print(f"Valid until: {cert['notAfter']}")
                
    except Exception as e:
        print(f"❌ SSL connection failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="VoiceReel TLS certificate management tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate self-signed certificate for development
  python voicereel_cert.py generate --domain localhost

  # Setup Let's Encrypt certificate for production
  python voicereel_cert.py letsencrypt --domain api.example.com --email admin@example.com

  # Load existing certificate files
  python voicereel_cert.py load --cert-file /path/to/cert.pem --key-file /path/to/key.pem

  # Validate current certificate
  python voicereel_cert.py validate

  # Show certificate information
  python voicereel_cert.py info

  # Test SSL connection
  python voicereel_cert.py test --host localhost --port 8443
        """
    )
    
    parser.add_argument("--cert-dir", default=None,
                       help="Certificate directory (default: VOICEREEL_CERT_DIR or /etc/voicereel/certs)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Generate self-signed certificate
    gen_parser = subparsers.add_parser("generate", help="Generate self-signed certificate")
    gen_parser.add_argument("--domain", default="localhost",
                           help="Domain name for certificate (default: localhost)")
    gen_parser.add_argument("--days", type=int, default=365,
                           help="Certificate validity in days (default: 365)")
    gen_parser.add_argument("--key-size", type=int, default=2048,
                           help="RSA key size (default: 2048)")
    gen_parser.set_defaults(func=cmd_generate_self_signed)
    
    # Setup Let's Encrypt certificate
    le_parser = subparsers.add_parser("letsencrypt", help="Setup Let's Encrypt certificate")
    le_parser.add_argument("--domain", required=True,
                          help="Domain name for certificate")
    le_parser.add_argument("--email", required=True,
                          help="Email address for Let's Encrypt registration")
    le_parser.add_argument("--staging", action="store_true",
                          help="Use Let's Encrypt staging environment")
    le_parser.set_defaults(func=cmd_setup_letsencrypt)
    
    # Load existing certificate
    load_parser = subparsers.add_parser("load", help="Load existing certificate files")
    load_parser.add_argument("--cert-file", required=True,
                            help="Path to certificate file")
    load_parser.add_argument("--key-file", required=True,
                            help="Path to private key file")
    load_parser.set_defaults(func=cmd_load_existing)
    
    # Validate certificate
    val_parser = subparsers.add_parser("validate", help="Validate certificate")
    val_parser.set_defaults(func=cmd_validate)
    
    # Show info
    info_parser = subparsers.add_parser("info", help="Show certificate information")
    info_parser.add_argument("--json", action="store_true",
                            help="Output in JSON format")
    info_parser.set_defaults(func=cmd_info)
    
    # Test SSL
    test_parser = subparsers.add_parser("test", help="Test SSL connection")
    test_parser.add_argument("--host", default="localhost",
                            help="Host to connect to (default: localhost)")
    test_parser.add_argument("--port", type=int, default=8443,
                            help="Port to connect to (default: 8443)")
    test_parser.add_argument("--insecure", action="store_true",
                            help="Skip certificate verification")
    test_parser.set_defaults(func=cmd_test_ssl)
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    
    # Show help if no command specified
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Run command
    args.func(args)


if __name__ == "__main__":
    main()