"""
Automation UI Routes

Handles automation rule management and configuration.
"""

from flask import render_template

from app.ui import ui_bp


@ui_bp.route("/automation/manage")
def automation_management():
    """Automation rule management interface."""

    # This is a simplified version - the full implementation is quite large
    # and would be better served by proper templates
    return render_template("automation/manage.html")
