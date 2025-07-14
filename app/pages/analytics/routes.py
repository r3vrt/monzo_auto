"""Analytics routes for analytics-related pages."""

from flask import current_app, render_template

from app.pages.analytics import bp
from app.services.analytics_service import get_analytics_overview


@bp.route("/", methods=["GET"])
def analytics_overview():
    """Show analytics overview page."""
    try:
        analytics_data = get_analytics_overview()
        return render_template(
            "pages/analytics/overview.html", analytics_data=analytics_data, home_url="/"
        )
    except Exception as e:
        current_app.logger.exception("Failed to load analytics", extra={"route": "analytics_overview"})
        return render_template(
            "pages/analytics/overview.html",
            analytics_data=None,
            error=str(e),
            home_url="/",
        )
