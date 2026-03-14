"""
Flask app factory.
"""

import os
from flask import Flask
from flask_cors import CORS

from .content_store import ContentStore
from .auth import init_auth
from .visitor_log import VisitorLog
from .routes_public import public_bp, init_public_routes
from .routes_admin import admin_bp, init_admin_routes


def create_app(content_dir=None):
    """Create and configure the Flask application."""
    if content_dir is None:
        content_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'content')
    content_dir = os.path.abspath(content_dir)

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = None
    CORS(app)

    # Initialize content store and visitor log
    store = ContentStore(content_dir)
    vlog = VisitorLog(content_dir)

    # Initialize auth
    init_auth(content_dir)

    # Register blueprints
    init_public_routes(store, vlog)
    init_admin_routes(store, vlog)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    return app
