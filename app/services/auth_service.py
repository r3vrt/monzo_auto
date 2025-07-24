"""
Auth service for handling Monzo OAuth token persistence.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models import User
from app.monzo.client import MonzoClient


def save_monzo_tokens_to_user(
    db, tokens: Dict[str, Any], client_secret: Optional[str]
) -> User:
    """
    Create or update a User with Monzo OAuth tokens and metadata.
    Args:
        db: SQLAlchemy session
        tokens: Dict from Monzo token exchange
        client_secret: The Monzo client secret used
    Returns:
        The User object (created or updated)
    """
    user_id = tokens.get("user_id")
    user = db.query(User).filter_by(monzo_user_id=user_id).first()
    if not user:
        user = User(monzo_user_id=user_id)
        db.add(user)
    user.monzo_access_token = str(tokens.get("access_token") or "INVALID")
    refresh_token = tokens.get("refresh_token")
    if refresh_token is not None:
        user.monzo_refresh_token = str(refresh_token)
    token_type = tokens.get("token_type")
    if token_type is not None:
        user.monzo_token_type = str(token_type)
    expires_in = tokens.get("expires_in")
    if expires_in is not None:
        user.monzo_token_expires_in = int(expires_in)
    client_id = tokens.get("client_id")
    if client_id is not None:
        user.monzo_client_id = str(client_id)
    if client_secret is not None:
        user.monzo_client_secret = str(client_secret)
    user.monzo_token_obtained_at = datetime.now(timezone.utc)
    db.commit()
    return user


def get_authenticated_monzo_client(
    db, user_id: Optional[str] = None
) -> Optional[MonzoClient]:
    """
    Get an authenticated MonzoClient instance for a user.

    Args:
        db: SQLAlchemy session
        user_id: Optional user ID (monzo_user_id). If None, gets the most recent user.

    Returns:
        Authenticated MonzoClient instance or None if user not found/invalid
    """
    if user_id:
        user = db.query(User).filter_by(monzo_user_id=user_id).first()
    else:
        # Get the most recent user if no specific user_id provided
        user = db.query(User).order_by(User.id.desc()).first()

    if not user:
        return None

    # Validate that we have the required credentials
    if not (
        user.monzo_client_id and user.monzo_client_secret and user.monzo_access_token
    ):
        return None

    return MonzoClient(
        client_id=str(user.monzo_client_id),
        client_secret=str(user.monzo_client_secret),
        redirect_uri=str(user.monzo_redirect_uri) if user.monzo_redirect_uri else "",
        tokens={
            "access_token": str(user.monzo_access_token),
            "refresh_token": (
                str(user.monzo_refresh_token) if user.monzo_refresh_token else ""
            ),
            "user_id": str(user.monzo_user_id),
        },
    )


def get_user_from_session_or_db(
    db, session_user_id: Optional[str] = None
) -> Optional[User]:
    """
    Get a user from session user_id or fall back to the most recent user in database.

    Args:
        db: SQLAlchemy session
        session_user_id: Optional user ID from session

    Returns:
        User object or None if not found
    """
    if session_user_id:
        # Try to find user by monzo_user_id first
        user = db.query(User).filter_by(monzo_user_id=session_user_id).first()
        if user:
            return user

        # If not found by monzo_user_id, try by database id
        try:
            user_id_int = int(session_user_id)
            user = db.query(User).filter_by(id=user_id_int).first()
            if user:
                return user
        except (ValueError, TypeError):
            pass

    # Fall back to most recent user
    return db.query(User).order_by(User.id.desc()).first()
