"""Transactions blueprint for transaction-related pages."""

from flask import Blueprint

bp = Blueprint("transactions", __name__, url_prefix="/transactions")

from app.pages.transactions import routes
