#!/usr/bin/env python3
"""
HTTPS server for the ArUco Marker Detector web app.

Serves the web app over HTTPS (required for camera access on iOS Safari).
Auto-generates a self-signed certificate with SAN for the local IP.

Usage:
    python aruco_server.py [--port PORT]
"""

import http.server
import ssl
import os
import subprocess
import socket
import argparse
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(SCRIPT_DIR, 'web')
CERT_DIR = os.path.join(SCRIPT_DIR, '.certs')
CERT_FILE = os.path.join(CERT_DIR, 'server.pem')
KEY_FILE = os.path.join(CERT_DIR, 'server-key.pem')


def get_local_ip():
    """Get the local IP address of the machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def generate_cert(ip):
    """Generate a self-signed certificate with SAN for the given IP."""
    os.makedirs(CERT_DIR, exist_ok=True)

    # Check if cert already exists and has the right IP
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        try:
            result = subprocess.run(
                ['openssl', 'x509', '-in', CERT_FILE, '-noout', '-ext', 'subjectAltName'],
                capture_output=True, text=True
            )
            if f'IP Address:{ip}' in result.stdout:
                print(f'Using existing certificate for {ip}')
                return
        except Exception:
            pass

    print(f'Generating self-signed certificate for {ip}...')

    san_config = f"""[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = ArUco Detector

[v3_req]
subjectAltName = @alt_names

[alt_names]
IP.1 = {ip}
IP.2 = 127.0.0.1
DNS.1 = localhost
"""

    config_path = os.path.join(CERT_DIR, 'openssl.cnf')
    with open(config_path, 'w') as f:
        f.write(san_config)

    subprocess.run([
        'openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048',
        '-keyout', KEY_FILE, '-out', CERT_FILE,
        '-days', '365', '-config', config_path
    ], check=True, capture_output=True)

    os.remove(config_path)
    print('Certificate generated.')


def run_server(port):
    """Start the HTTPS server."""
    ip = get_local_ip()
    generate_cert(ip)

    os.chdir(WEB_DIR)

    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.HTTPServer(('0.0.0.0', port), handler)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print()
    print(f'  ArUco Detector running at:')
    print(f'  https://{ip}:{port}')
    print()
    print(f'  Open this URL on your iPhone/iPad in Safari.')
    print(f'  Accept the certificate warning (one-time).')
    print()
    print(f'  Press Ctrl+C to stop.')
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ArUco Marker Detector HTTPS Server')
    parser.add_argument('--port', type=int, default=8443, help='Port number (default: 8443)')
    args = parser.parse_args()
    run_server(args.port)
