"""Tasks blueprint for automation functionality."""

from flask import Blueprint

bp = Blueprint("tasks", __name__)

from app.tasks import routes
