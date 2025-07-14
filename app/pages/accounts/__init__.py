"""Accounts blueprint for account-related pages."""

from flask import Blueprint

bp = Blueprint("accounts", __name__, url_prefix="/accounts")

from app.pages.accounts import routes
