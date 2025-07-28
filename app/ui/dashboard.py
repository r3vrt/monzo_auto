"""
Dashboard UI Routes

Handles the main dashboard and account management pages.
"""

import requests
from flask import flash, redirect, render_template, request, url_for

from app.ui import ui_bp


@ui_bp.route("/")
def landing_page():
    """
    Basic landing page listing links to all available UI pages.
    """
    pages = [
        {
            "name": "Import Accounts",
            "url": "/accounts/select-ui",
            "icon": "📥",
            "description": "Import and configure your Monzo accounts",
        },
        {
            "name": "Pot Management",
            "url": "/pots/manage",
            "icon": "💰",
            "description": "Organize pots into categories for automation",
        },
        {
            "name": "Automation Rules",
            "url": "/automation/manage",
            "icon": "🤖",
            "description": "Create and manage automated money management rules",
        },
        {
            "name": "Sync Status",
            "url": "/sync/status",
            "icon": "🔄",
            "description": "View sync status and manually trigger syncs",
        },
        {
            "name": "View Logs",
            "url": "/logs",
            "icon": "📋",
            "description": "View application logs for debugging",
        },
    ]
    return render_template("dashboard.html", pages=pages)


@ui_bp.route("/accounts/select-ui", methods=["GET", "POST"])
def accounts_select_ui():
    """
    Basic UI for selecting Monzo accounts to import and naming them.
    """
    if request.method == "POST":
        # If this is the name entry step
        if "name_entry" in request.form:
            selected = request.form.getlist("account_id")
            names = {aid: request.form.get(f"name_{aid}") for aid in selected}
            # Submit to API endpoint
            api_url = url_for("api.accounts_select_post", _external=True)
            resp = requests.post(
                api_url,
                json={"account_ids": selected, "account_names": names},
                cookies=request.cookies,
            )
            if resp.ok:
                return render_template("accounts/success.html", accounts=selected)
            else:
                flash("Error importing accounts", "error")
                return redirect(url_for("ui.accounts_select_ui"))

        # First step: account selection
        selected = request.form.getlist("account_id")
        # Fetch available accounts for names
        api_url = url_for("api.accounts_available", _external=True)
        resp = requests.get(api_url, cookies=request.cookies)
        accounts = resp.json().get("accounts", []) if resp.ok else []
        selected_accounts = [acc for acc in accounts if acc["id"] in selected]
        return render_template(
            "accounts/name.html", selected_accounts=selected_accounts
        )

    # GET: fetch available accounts
    api_url = url_for("api.accounts_available", _external=True)
    resp = requests.get(api_url, cookies=request.cookies)
    accounts = resp.json().get("accounts", []) if resp.ok else []
    return render_template("accounts/select.html", accounts=accounts)
