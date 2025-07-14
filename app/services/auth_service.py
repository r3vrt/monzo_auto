"""Auth service for business logic related to authentication and OAuth flow."""

import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from flask import current_app, session

from app.services.monzo_service import MonzoService
from app.services.database_service import db_service


def load_auth_config() -> Dict[str, Any]:
    """Load authentication configuration from the database."""
    return {
        "client_id": db_service.get_setting("auth.client_id", ""),
        "client_secret": db_service.get_setting("auth.client_secret", ""),
        "redirect_uri": db_service.get_setting("auth.redirect_uri", "http://localhost:5000/auth/callback"),
    }


def save_auth_config(config: Dict[str, Any]) -> bool:
    """Save authentication configuration to the database."""
    ok1 = db_service.save_setting("auth.client_id", config.get("client_id", ""), data_type="string")
    ok2 = db_service.save_setting("auth.client_secret", config.get("client_secret", ""), data_type="string")
    ok3 = db_service.save_setting("auth.redirect_uri", config.get("redirect_uri", ""), data_type="string")
    return ok1 and ok2 and ok3


def generate_oauth_state() -> str:
    """Generate a secure state parameter for OAuth flow and store in session."""
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    return state


def get_monzo_service() -> MonzoService:
    """Get a MonzoService instance."""
    return MonzoService()


def exchange_code_for_tokens(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for tokens using MonzoService."""
    config = load_auth_config()
    monzo_service = MonzoService()
    return monzo_service.exchange_code_for_tokens(code, redirect_uri)


def get_user_info() -> Optional[Dict[str, Any]]:
    """Get user info from MonzoService."""
    monzo_service = MonzoService()
    return monzo_service.get_user_info()


def clear_tokens() -> None:
    """Clear stored authentication tokens using MonzoService."""
    monzo_service = MonzoService()
    monzo_service.clear_tokens()
