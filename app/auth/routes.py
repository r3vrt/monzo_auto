"""Authentication routes for OAuth flow."""

from flask import (current_app, jsonify, redirect, render_template, request,
                   session, url_for)

from app.auth import bp
from app.services.auth_service import (clear_tokens, exchange_code_for_tokens,
                                       generate_oauth_state, get_user_info,
                                       load_auth_config, save_auth_config)


@bp.route("/setup", methods=["GET", "POST"])
def setup_form():
    """OAuth setup form.

    Returns:
        HTML form for OAuth configuration
    """
    if request.method == "POST":
        client_id = request.form.get("client_id")
        client_secret = request.form.get("client_secret")
        redirect_uri = request.form.get("redirect_uri")
        if not all([client_id, client_secret, redirect_uri]):
            return render_template(
                "pages/auth/setup.html",
                message="All fields are required",
                success=False,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        config = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        if save_auth_config(config):
            return render_template(
                "pages/auth/setup.html",
                message="OAuth credentials saved successfully! You can now start the OAuth flow.",
                success=True,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        else:
            return render_template(
                "pages/auth/setup.html",
                message="Failed to save credentials.",
                success=False,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
    config = load_auth_config()
    return render_template(
        "pages/auth/setup.html",
        client_id=config.get("client_id", ""),
        client_secret=config.get("client_secret", ""),
        redirect_uri=config.get("redirect_uri", "http://localhost:5000/auth/callback"),
    )


@bp.route("/login", methods=["GET"])
def login():
    """Start OAuth login flow.

    Returns:
        HTML page with authorization URL
    """
    config = load_auth_config()
    if not config.get("client_id") or not config.get("client_secret"):
        return render_template(
            "pages/auth/login.html",
            title="OAuth Not Configured",
            message="OAuth credentials not configured. Please set up your Monzo OAuth app first.",
            success=False,
            setup_url="/auth/setup",
            home_url="/",
        )
    try:
        state = generate_oauth_state()
        auth_url = (
            f"https://auth.monzo.com/?"
            f"client_id={config['client_id']}&"
            f"redirect_uri={config['redirect_uri']}&"
            f"response_type=code&"
            f"state={state}"
        )
        return render_template(
            "pages/auth/login.html",
            title="OAuth Login",
            message="Click the button below to authorize with Monzo:",
            success=True,
            auth_url=auth_url,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.error(f"Failed to generate auth URL: {e}")
        return render_template(
            "pages/auth/login.html",
            title="OAuth Error",
            message=f"Failed to generate authorization URL: {str(e)}",
            success=False,
            setup_url="/auth/setup",
            home_url="/",
        )


@bp.route("/callback", methods=["GET"])
def callback():
    """OAuth callback handler.

    Returns:
        HTML page with authentication result
    """
    error = request.args.get("error")
    code = request.args.get("code")
    state = request.args.get("state")
    if error:
        return render_template(
            "pages/auth/callback.html",
            title="OAuth Error",
            message=f"OAuth authorization failed: {error}",
            success=False,
            home_url="/",
        )
    if state != session.get("oauth_state"):
        return render_template(
            "pages/auth/callback.html",
            title="OAuth Error",
            message="Invalid state parameter. Please try again.",
            success=False,
            home_url="/",
        )
    if not code:
        return render_template(
            "pages/auth/callback.html",
            title="OAuth Error",
            message="No authorization code received from Monzo.",
            success=False,
            home_url="/",
        )
    try:
        tokens = exchange_code_for_tokens(
            code, load_auth_config().get("redirect_uri", "")
        )
        if not tokens:
            return render_template(
                "pages/auth/callback.html",
                title="OAuth Error",
                message="Failed to exchange authorization code for tokens.",
                success=False,
                home_url="/",
            )
        user = get_user_info()
        return render_template(
            "pages/auth/callback.html",
            title="OAuth Success",
            message="Successfully authenticated with Monzo!",
            success=True,
            user=user,
            home_url="/",
            show_manual_sync=True,
        )
    except Exception as e:
        current_app.logger.exception("OAuth callback failed", extra={"route": "auth_callback"})
        return render_template(
            "pages/auth/callback.html",
            title="OAuth Error",
            message=f"OAuth callback failed: {str(e)}",
            success=False,
            home_url="/",
        )


@bp.route("/status", methods=["GET"])
def auth_status():
    """Check authentication status.

    Returns:
        HTML page with authentication status
    """
    try:
        user = get_user_info()
        if not user:
            return render_template(
                "pages/auth/status.html",
                title="Not Authenticated",
                message="You are not authenticated with Monzo.",
                success=False,
                home_url="/",
            )
        return render_template(
            "pages/auth/status.html",
            title="Authenticated",
            message="You are successfully authenticated with Monzo.",
            success=True,
            user=user,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.error(f"Auth status check failed: {e}")
        return render_template(
            "pages/auth/status.html",
            title="Authentication Error",
            message=f"Failed to check authentication status: {str(e)}",
            success=False,
            home_url="/",
        )


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Logout and clear authentication.

    Returns:
        Redirect to home page
    """
    try:
        session.clear()
        clear_tokens()
        return redirect("/")
    except Exception as e:
        current_app.logger.error(f"Logout failed: {e}")
        return redirect("/")


@bp.route("/manual_sync", methods=["POST"])
def manual_sync():
    """Trigger a manual incremental sync after login."""
    from app.__init__ import incremental_sync
    incremental_sync()
    return redirect(url_for("dashboard.overview", sync="success"))
