"""
Pots UI Routes

Handles pot management and categorization.
"""

from flask import render_template

from app.ui import ui_bp


@ui_bp.route("/pots/manage")
def pot_management():
    """
    Modern pot category management interface.
    """
    return render_template("pots/manage.html")
