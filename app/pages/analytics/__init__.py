"""Analytics blueprint for analytics-related pages."""

from flask import Blueprint

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

from app.pages.analytics import routes
