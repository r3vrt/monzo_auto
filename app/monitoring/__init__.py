"""Monitoring blueprint for system monitoring."""

from flask import Blueprint

bp = Blueprint("monitoring", __name__)

from app.monitoring import routes
