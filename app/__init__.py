from flask import Flask

from app.api.routes import api_bp
from app.ui import ui_bp
from app.logging_config import configure_logging


def create_app():
    app = Flask(__name__)
    
    # Configure logging
    configure_logging()
    
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)

    return app
