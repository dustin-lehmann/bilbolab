"""
Authentication module - JWT tokens + bcrypt password hashing.
"""

import os
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

import bcrypt
import jwt
from flask import request, jsonify

_secret_key = None
_content_dir = None


def init_auth(content_dir):
    """Load or generate JWT secret key."""
    global _secret_key, _content_dir
    _content_dir = Path(content_dir)
    key_file = _content_dir / '_secret.key'

    if key_file.exists():
        _secret_key = key_file.read_text().strip()
    else:
        _secret_key = secrets.token_hex(32)
        _content_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_text(_secret_key)


def hash_password(plain):
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain, hashed):
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


def create_token():
    """Create a JWT with 7-day expiry."""
    payload = {
        'exp': datetime.now(timezone.utc) + timedelta(days=7),
        'iat': datetime.now(timezone.utc),
        'sub': 'admin'
    }
    return jwt.encode(payload, _secret_key, algorithm='HS256')


def _verify_token(token):
    """Verify a JWT token. Returns True if valid."""
    try:
        jwt.decode(token, _secret_key, algorithms=['HS256'])
        return True
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False


def require_admin(f):
    """Decorator that validates Bearer token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing authorization'}), 401
        token = auth_header[7:]
        if not _verify_token(token):
            return jsonify({'error': 'Invalid or expired token'}), 401
        return f(*args, **kwargs)
    return decorated
