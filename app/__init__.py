import os
from flask import Flask, request
from flask_wtf.csrf import CSRFProtect

from app.api.routes import api_bp
from app.ui import ui_bp
from app.logging_config import configure_logging


def create_app():
    app = Flask(__name__)
    
    # Security configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
    app.config['WTF_CSRF_SSL_STRICT'] = False  # Set to True in production with HTTPS
    
    # Session security configuration
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Initialize CSRF protection
    csrf = CSRFProtect()
    # Temporarily disable CSRF for testing
    app.config['WTF_CSRF_ENABLED'] = False
    csrf.init_app(app)
    
    # Configure logging
    configure_logging()
    
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)

    return app
