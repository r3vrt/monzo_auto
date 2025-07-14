"""Dashboard blueprint for overview and summary pages."""

from flask import Blueprint

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

from app.pages.dashboard import routes
