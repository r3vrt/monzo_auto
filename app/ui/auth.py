"""
Authentication UI Routes

Handles authentication-related UI pages and forms.
"""

import os

from flask import (current_app, jsonify, redirect, render_template, request,
                   session, url_for)

from app.db import get_db_session
from app.models import User
from app.monzo.client import MonzoClient
from app.services.auth_service import save_monzo_tokens_to_user
from app.ui import ui_bp


@ui_bp.route("/monzo_auth")
def monzo_auth():
    """Display Monzo authentication form."""
    return render_template("monzo_auth.html")


@ui_bp.route("/auth/start", methods=["GET"])
def auth_start():
    """
    Initiate Monzo OAuth flow. Redirects user to Monzo's authorization URL.
    If credentials are missing from session, look them up from the most recent User in the DB.
    """
    client_id = session.get("monzo_client_id")
    client_secret = session.get("monzo_client_secret")
    redirect_uri = session.get("monzo_redirect_uri")

    if not client_id or not client_secret or not redirect_uri:
        with next(get_db_session()) as db:
            user = db.query(User).order_by(User.id.desc()).first()
            if (
                user
                and getattr(user, "monzo_client_id", None)
                and getattr(user, "monzo_client_secret", None)
                and getattr(user, "monzo_redirect_uri", None)
            ):
                session["monzo_client_id"] = str(user.monzo_client_id)
                session["monzo_client_secret"] = str(user.monzo_client_secret)
                session["monzo_redirect_uri"] = str(user.monzo_redirect_uri)
                client_id = str(user.monzo_client_id)
                client_secret = str(user.monzo_client_secret)
                redirect_uri = str(user.monzo_redirect_uri)
            else:
                return (
                    "<h2>Missing Monzo client credentials.</h2>"
                    '<p><a href="/monzo_auth">Enter credentials here</a></p>',
                    400,
                )

    monzo = MonzoClient(
        client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
    )
    state = os.urandom(16).hex()  # Should be stored in session/csrf for real app
    auth_url = monzo.get_authorization_url(state=state)
    return redirect(auth_url)


@ui_bp.route("/auth/callback", methods=["GET"])
def auth_callback():
    """
    Handle Monzo OAuth callback. Exchanges code for tokens and saves to DB.
    Redirects to home page on success.
    """
    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return jsonify({"error": "Missing code"}), 400

    client_id = session.get("monzo_client_id")
    client_secret = session.get("monzo_client_secret")
    redirect_uri = session.get("monzo_redirect_uri")

    if not client_id or not client_secret or not redirect_uri:
        return jsonify({"error": "Missing Monzo client credentials in session"}), 400

    monzo = MonzoClient(
        client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
    )

    try:
        tokens = monzo.exchange_code_for_token(code)
    except Exception as e:
        current_app.logger.error(f"OAuth token exchange failed: {e}")
        return jsonify({"error": "Token exchange failed", "details": str(e)}), 500

    # Use service layer to save tokens and metadata
    with next(get_db_session()) as db:
        user = save_monzo_tokens_to_user(db, tokens, monzo.client_secret)
        user_id = str(user.monzo_user_id)  # Access while session is open
        session["user_id"] = user_id

    # Redirect to home page after successful authentication
    return redirect(url_for("ui.landing_page"))


@ui_bp.route("/auth/client_info", methods=["POST"])
def auth_client_info():
    """
    Accept Monzo client credentials from the user and store in session.
    Expects JSON: {"client_id": ..., "client_secret": ..., "redirect_uri": ...}
    """
    data = request.get_json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    redirect_uri = data.get("redirect_uri")

    session["monzo_client_id"] = client_id
    session["monzo_client_secret"] = client_secret
    session["monzo_redirect_uri"] = redirect_uri

    return jsonify({"success": True})
