"""
UI Blueprint Package

This package contains all UI-related blueprints for the Monzo application.
Each blueprint handles a specific area of functionality.
"""

from flask import Blueprint

# Create the main UI blueprint
ui_bp = Blueprint("ui", __name__)

# Import all route modules to register them
from . import auth, automation, dashboard, logs, pots, sync
