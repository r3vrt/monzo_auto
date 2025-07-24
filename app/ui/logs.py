"""
Logs UI Routes

Handles log viewing and debugging pages.
"""

import os

from flask import render_template

from app.ui import ui_bp


@ui_bp.route("/logs")
def view_logs():
    """Display application logs for debugging."""
    log_path = os.path.join(os.path.dirname(__file__), "../../monzo_app.log")
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()[-200:]
    except Exception as e:
        lines = [f"Error reading log file: {e}"]

    return render_template("logs/view.html", log_content="".join(lines))
