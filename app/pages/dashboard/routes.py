"""Dashboard routes for overview and summary pages."""

from flask import current_app, render_template

from app.pages.dashboard import bp
from app.services.dashboard_service import get_dashboard_overview
from app.services.schedule_utils import schedule_to_human
from app.services.database_service import db_service


@bp.route("/", methods=["GET"])
def overview():
    """Main application overview page.

    Returns:
        HTML response with account overview and quick actions
    """
    try:
        account_summaries, user_info, total_balance, account_count = (
            get_dashboard_overview()
        )
        # Add active task schedules (only those with a real schedule)
        automation_config = db_service.get_setting("general.automation_tasks", {})
        schedules = {
            "Auto Topup": automation_config.get("auto_topup", {}).get("schedule", {"type": "none"}),
            "Sweep Pots": automation_config.get("sweep_pots", {}).get("schedule", {"type": "none"}),
            "Autosorter": automation_config.get("autosorter", {}).get("schedule", {"type": "none"}),
            "Sweep & Sort": automation_config.get("combined", {}).get("schedule", {"type": "none"}),
        }
        # Only include tasks with a real schedule
        task_summaries = {task: schedule_to_human(sched) for task, sched in schedules.items() if sched.get("type") != "none"}
        # Determine if login button should be shown
        access_token = db_service.get_setting("auth.access_token", "")
        show_login_button = not access_token
        return render_template(
            "pages/dashboard/overview.html",
            authenticated=True,
            user=user_info,
            accounts=account_summaries,
            total_balance=total_balance,
            account_count=account_count,
            home_url="/",
            task_summaries=task_summaries,
            show_login_button=show_login_button,
        )
    except Exception as e:
        current_app.logger.exception("Failed to load overview", extra={"route": "dashboard_overview"})
        return render_template(
            "pages/dashboard/overview.html",
            authenticated=False,
            error=str(e),
            home_url="/",
        )
