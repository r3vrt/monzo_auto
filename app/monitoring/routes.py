"""Routes for system monitoring."""

from flask import current_app, jsonify, render_template, redirect, url_for

from app.monitoring import bp
from app.services.monitoring_service import (get_health_status,
                                             get_monzo_status,
                                             get_system_status,
                                             get_metrics_prometheus)


@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint.

    Returns:
        HTML page with system health status
    """
    health = get_health_status()
    return render_template(
        "pages/monitoring/health.html",
        status=health["status"],
        service=health["service"],
        version=health["version"],
        home_url="/",
    )


@bp.route("/status", methods=["GET"])
def system_status():
    """Get system status and metrics.

    Returns:
        HTML page with system status
    """
    status = get_system_status()
    return render_template(
        "pages/monitoring/status.html",
        api_status=status["api_status"],
        account_count=status["account_count"],
        active_tasks=status["active_tasks"],
        errors=status["errors"],
        last_sync=status["last_sync"],
        task_metrics=status["task_metrics"],
        home_url="/",
    )


@bp.route("/monzo", methods=["GET"])
def monzo_status():
    """Get detailed Monzo API status.

    Returns:
        HTML page with Monzo API status
    """
    status = get_monzo_status()
    return render_template(
        "pages/monitoring/monzo.html",
        status=status["status"],
        accounts_found=status.get("accounts_found", 0),
        client_configured=status.get("client_configured", False),
        message=status.get("message", ""),
        home_url="/",
    )


@bp.route("/api/health", methods=["GET"])
def api_health():
    """API health check endpoint.

    Returns:
        JSON response with health status
    """
    return jsonify(get_health_status())


@bp.route("/api/status", methods=["GET"])
def api_status():
    """API status endpoint.

    Returns:
        JSON response with system status
    """
    status = get_system_status()
    return jsonify(
        {
            "monzo_api": status["api_status"],
            "account_count": status["account_count"],
            "active_tasks": status["active_tasks"],
            "errors": status["errors"],
            "last_sync": status["last_sync"],
        }
    )


@bp.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus metrics endpoint."""
    metrics_text = get_metrics_prometheus()
    return metrics_text, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


@bp.route("/", methods=["GET"])
def monitoring_overview():
    """Redirect /monitoring/ to /monitoring/status."""
    return redirect(url_for("monitoring.system_status"))
