"""Configuration blueprint for app settings."""

from flask import Blueprint

bp = Blueprint("configuration", __name__)

from app.configuration import routes
