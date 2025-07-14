"""Routes for application configuration."""

import json
from markupsafe import Markup
import re

from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, url_for)

from app.configuration import bp
from app.services.configuration_service import get_config_overview, get_account_names
from app.services.monzo_service import MonzoService
from app.services.database_service import db_service
from app.services.schedule_utils import (
    cron_to_human,
    schedule_to_human,
    schedule_form_to_struct,
    schedule_struct_to_trigger,
    migrate_legacy_cron_schedules,
)


def get_general_config_from_db():
    return {
        "debug_mode": db_service.get_setting("general.debug_mode", False),
        "auto_sync": db_service.get_setting("general.auto_sync", True),
        "sync_interval_minutes": db_service.get_setting("general.sync_interval_minutes", 30),
        "log_level": db_service.get_setting("general.log_level", "INFO"),
        "max_retries": db_service.get_setting("general.max_retries", 3),
        "timeout_seconds": db_service.get_setting("general.timeout_seconds", 30),
    }

@bp.route("/", methods=["GET"])
def config_overview():
    """Show configuration overview page.

    Returns:
        HTML page with current configuration
    """
    config = get_config_overview()
    account_names = get_account_names()
    
    # Add account names to the config for display
    config["account_names"] = account_names
    
    # Add human-readable task schedules
    automation_config = db_service.get_setting("general.automation_tasks", {})
    schedules = {
        "Auto Topup": automation_config.get("auto_topup", {}).get("schedule", {"type": "none"}),
        "Sweep Pots": automation_config.get("sweep_pots", {}).get("schedule", {"type": "none"}),
        "Autosorter": automation_config.get("autosorter", {}).get("schedule", {"type": "none"}),
        "Combined": automation_config.get("combined", {}).get("schedule", {"type": "none"}),
    }
    task_summaries = {task: schedule_to_human(sched) for task, sched in schedules.items()}
    
    # Add automation configs for unified tab
    sweep_config = automation_config.get("sweep_pots", {})
    autosorter_config = automation_config.get("autosorter", {})
    combined_config = automation_config.get("combined", {})
    sweep_schedule = sweep_config.get("schedule", {"type": "none"})
    autosorter_schedule = autosorter_config.get("schedule", {"type": "none"})
    combined_schedule = combined_config.get("schedule", {"type": "none"})
    
    return render_template(
        "pages/configuration/overview.html",
        config=config,
        home_url="/",
        task_summaries=task_summaries,
    )


@bp.route("/api", methods=["GET"])
def get_config():
    """Get current application configuration.

    Returns:
        JSON response with current configuration
    """
    config = get_config_overview()
    return jsonify(config)


@bp.route("/auth", methods=["GET"])
def edit_auth_config():
    """Show authentication configuration edit form.

    Returns:
        HTML form for editing auth configuration
    """
    auth_config = {
        "monzo_client_id": db_service.get_setting("auth.client_id", ""),
        "monzo_client_secret": db_service.get_setting("auth.client_secret", ""),
        "monzo_redirect_uri": db_service.get_setting("auth.redirect_uri", ""),
    }
    return render_template(
        "pages/configuration/auth_edit.html", config=auth_config, home_url="/"
    )


@bp.route("/auth", methods=["POST"])
def update_auth_config():
    """Update authentication configuration from form submission.

    Returns:
        Redirect to config overview with success/error message
    """
    monzo_client_id = request.form.get("monzo_client_id", "").strip()
    monzo_client_secret = request.form.get("monzo_client_secret", "").strip()
    monzo_redirect_uri = request.form.get("monzo_redirect_uri", "").strip()
    if not monzo_client_id or not monzo_client_secret or not monzo_redirect_uri:
        flash("Client ID, Secret, and Redirect URI are required", "error")
        return redirect(url_for("configuration.edit_auth_config"))
    ok1 = db_service.save_setting("auth.client_id", monzo_client_id, data_type="string")
    ok2 = db_service.save_setting("auth.client_secret", monzo_client_secret, data_type="string")
    ok3 = db_service.save_setting("auth.redirect_uri", monzo_redirect_uri, data_type="string")
    if ok1 and ok2 and ok3:
            flash("Authentication configuration updated successfully", "success")
    else:
        flash("Failed to save authentication configuration", "error")
    return redirect(url_for("configuration.config_overview"))


@bp.route("/auth/api", methods=["GET"])
def get_auth_config():
    """Get authentication configuration (API endpoint).

    Returns:
        JSON response with auth configuration
    """
    auth_config = {
        "monzo_client_id": current_app.config.get("MONZO_CLIENT_ID", ""),
        "monzo_client_secret": current_app.config.get("MONZO_CLIENT_SECRET", ""),
        "monzo_redirect_uri": current_app.config.get("MONZO_REDIRECT_URI", ""),
    }
    return jsonify(auth_config)


@bp.route("/auth/api", methods=["PUT"])
def update_auth_config_api():
    """Update authentication configuration (API endpoint)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Map API field names to database field names
    mapped_data = {}
    if "client_id" in data:
        mapped_data["client_id"] = data["client_id"]
    if "client_secret" in data:
        mapped_data["client_secret"] = data["client_secret"]
    if "redirect_uri" in data:
        mapped_data["redirect_uri"] = data["redirect_uri"]

    # Save to database
    for key, value in mapped_data.items():
        db_service.save_setting(f"auth.{key}", value, data_type="string")

    return jsonify({
        "status": "updated",
        "message": "Authentication configuration updated successfully",
    })


@bp.route("/general", methods=["GET"])
def edit_general_config():
    """Show general configuration edit form.

    Returns:
        HTML form for editing general configuration
    """
    general_config = get_general_config_from_db()
    auto_topup_config = db_service.get_setting("general.auto_topup", {})
    general_config.update({
        "auto_topup_enabled": auto_topup_config.get("enabled", False),
        "auto_topup_source_pot_name": auto_topup_config.get("source_pot_name", ""),
        "auto_topup_threshold_amount": auto_topup_config.get("threshold_amount", 30.0),
        "auto_topup_target_amount": auto_topup_config.get("target_amount", 50.0),
        "auto_topup_check_interval": auto_topup_config.get("check_interval_minutes", 60),
    })
    return render_template(
        "pages/configuration/general_edit.html", config=general_config, home_url="/"
    )


@bp.route("/general", methods=["POST"])
def update_general_config():
    """Update general configuration from form submission.

    Returns:
        Redirect to config overview with success/error message
    """
    debug_mode = request.form.get("debug_mode") == "on"
    auto_sync = request.form.get("auto_sync") == "on"
    sync_interval_minutes = int(request.form.get("sync_interval_minutes", 30))
    log_level = request.form.get("log_level", "INFO")
    max_retries = int(request.form.get("max_retries", 3))
    timeout_seconds = int(request.form.get("timeout_seconds", 30))
    auto_topup_enabled = request.form.get("auto_topup_enabled") == "on"
    auto_topup_source_pot_name = request.form.get("auto_topup_source_pot_name", "").strip()
    auto_topup_threshold_amount = float(request.form.get("auto_topup_threshold_amount", 30.0))
    auto_topup_target_amount = float(request.form.get("auto_topup_target_amount", 50.0))
    auto_topup_check_interval = int(request.form.get("auto_topup_check_interval", 60))
    # Save general config
    db_service.save_setting("general.debug_mode", debug_mode, data_type="bool")
    db_service.save_setting("general.auto_sync", auto_sync, data_type="bool")
    db_service.save_setting("general.sync_interval_minutes", sync_interval_minutes, data_type="int")
    db_service.save_setting("general.log_level", log_level, data_type="string")
    db_service.save_setting("general.max_retries", max_retries, data_type="int")
    db_service.save_setting("general.timeout_seconds", timeout_seconds, data_type="int")
    # Save auto_topup config as JSON
    auto_topup_data = {
        "enabled": auto_topup_enabled,
        "source_pot_name": auto_topup_source_pot_name,
        "threshold_amount": auto_topup_threshold_amount,
        "target_amount": auto_topup_target_amount,
        "check_interval_minutes": auto_topup_check_interval,
    }
    db_service.save_setting("general.auto_topup", auto_topup_data, data_type="json")
    flash("General configuration updated successfully", "success")
    return redirect(url_for("configuration.config_overview"))


@bp.route("/general/api", methods=["GET"])
def get_general_config():
    """Get general configuration (API endpoint).

    Returns:
        JSON response with general configuration
    """
    return jsonify(get_general_config_from_db())


@bp.route("/general/api", methods=["PUT"])
def update_general_config_api():
    """Update general configuration (API endpoint)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Save each setting to database
    for key, value in data.items():
        if key == "debug_mode":
            db_service.save_setting("general.debug_mode", value, data_type="bool")
        elif key == "auto_sync":
            db_service.save_setting("general.auto_sync", value, data_type="bool")
        elif key == "sync_interval_minutes":
            db_service.save_setting("general.sync_interval_minutes", value, data_type="int")
        elif key == "log_level":
            db_service.save_setting("general.log_level", value, data_type="string")
        elif key == "max_retries":
            db_service.save_setting("general.max_retries", value, data_type="int")
        elif key == "timeout_seconds":
            db_service.save_setting("general.timeout_seconds", value, data_type="int")

    return jsonify({
                    "status": "updated",
                    "message": "General configuration updated successfully",
    })


@bp.route("/auto-topup", methods=["GET"])
def edit_auto_topup_config():
    """Show auto-topup configuration edit form."""
    auto_topup_config = db_service.get_setting("general.auto_topup", {})
    config = {
        "auto_topup_enabled": auto_topup_config.get("enabled", False),
        "auto_topup_source_pot_name": auto_topup_config.get("source_pot_name", ""),
        "auto_topup_threshold_amount": auto_topup_config.get("threshold_amount", 30.0),
        "auto_topup_target_amount": auto_topup_config.get("target_amount", 50.0),
        "auto_topup_check_interval": auto_topup_config.get("check_interval_minutes", 60),
    }
    return render_template(
        "pages/configuration/auto_topup_edit.html", config=config, home_url="/"
    )


@bp.route("/auto-topup", methods=["POST"])
def update_auto_topup_config():
    """Update auto-topup configuration from form submission."""
    auto_topup_enabled = request.form.get("auto_topup_enabled") == "on"
    auto_topup_source_pot_name = request.form.get("auto_topup_source_pot_name", "").strip()
    auto_topup_threshold_amount = float(request.form.get("auto_topup_threshold_amount", 30.0))
    auto_topup_target_amount = float(request.form.get("auto_topup_target_amount", 50.0))
    auto_topup_check_interval = int(request.form.get("auto_topup_check_interval", 60))
    auto_topup_data = {
        "enabled": auto_topup_enabled,
        "source_pot_name": auto_topup_source_pot_name,
        "threshold_amount": auto_topup_threshold_amount,
        "target_amount": auto_topup_target_amount,
        "check_interval_minutes": auto_topup_check_interval,
    }
    db_service.save_setting("general.auto_topup", auto_topup_data, data_type="json")
    flash("Auto-topup configuration updated successfully", "success")
    return redirect(url_for("configuration.config_overview"))


@bp.route("/accounts", methods=["GET"])
def edit_accounts_config():
    """Show account display configuration form."""
    try:
        monzo_service = MonzoService()
        accounts = monzo_service.get_accounts()
        # Load selected account IDs and custom names from database
        selected_ids = db_service.get_setting("selected_account_ids", [])
        account_names = db_service.get_setting("account_names", {})
        return render_template(
            "pages/configuration/accounts_edit.html",
            accounts=accounts,
            selected_ids=selected_ids,
            account_names=account_names,
            home_url="/",
        )
    except Exception as e:
        return render_template(
            "pages/configuration/accounts_edit.html",
            accounts=[],
            selected_ids=[],
            account_names={},
            error=str(e),
            home_url="/",
        )


@bp.route("/accounts", methods=["POST"])
def update_accounts_config():
    """Save selected account IDs and custom names to database."""
    selected_ids = request.form.getlist("account_ids")
    
    # Parse custom account names from form data
    account_names = {}
    for key, value in request.form.items():
        if key.startswith("account_name_") and value.strip():
            # Extract account ID from the form field name (e.g., "account_name_acc123" -> "acc123")
            account_id = key.replace("account_name_", "")
            if account_id:
                account_names[account_id] = value.strip()
    
    # Save to database
    db_service.save_setting("selected_account_ids", selected_ids, data_type="json")
    db_service.save_setting("account_names", account_names, data_type="json")
    
    flash(f"Account configuration updated successfully. {len(selected_ids)} accounts selected, {len(account_names)} custom names saved.", "success")
    return redirect(url_for("configuration.edit_accounts_config"))


@bp.route("/schedules", methods=["GET", "POST"])
def edit_task_schedules():
    from app import scheduler
    automation_config = db_service.get_setting("general.automation_tasks", {})
    schedules = {
        "auto_topup": automation_config.get("auto_topup", {}).get("schedule", {"type": "none"}),
        "sweep_pots": automation_config.get("sweep_pots", {}).get("schedule", {"type": "none"}),
        "autosorter": automation_config.get("autosorter", {}).get("schedule", {"type": "none"}),
        "combined": automation_config.get("combined", {}).get("schedule", {"type": "none"}),
    }
    human_summaries = {task: schedule_to_human(sched) for task, sched in schedules.items()}
    error = None
    success = None
    x_minutes_selected = {}
    patterns = {}
    if request.method == "POST":
        for task in schedules:
            pattern = request.form.get(f"{task}_pattern", "custom")
            patterns[task] = pattern
            hour = request.form.get(f"{task}_hour", "0")
            minute = request.form.get(f"{task}_minute", "0")
            weekday = request.form.get(f"{task}_weekday", "0")
            dom = request.form.get(f"{task}_dom", "1")
            x_minutes = request.form.get(f"{task}_x_minutes", None)
            custom_cron = request.form.get(f"{task}_custom_cron", "")
            struct = schedule_form_to_struct(pattern, hour, minute, weekday, dom, x_minutes, custom_cron)
            schedules[task] = struct
        try:
            for struct in schedules.values():
                if struct["type"] == "custom" and struct.get("cron"):
                    pass  # Optionally validate cron string if needed
            for task, struct in schedules.items():
                if task not in automation_config:
                    automation_config[task] = {}
                automation_config[task]["schedule"] = struct
            db_service.save_setting("general.automation_tasks", automation_config, data_type="json")
            success = "Schedules updated successfully. Restart the app to apply new schedules."
            human_summaries = {task: schedule_to_human(sched) for task, sched in schedules.items()}
            for task, struct in schedules.items():
                if struct["type"] == "interval":
                    x_minutes_selected[task] = struct["minutes"]
                else:
                    x_minutes_selected[task] = None
        except Exception as e:
            error = f"Invalid schedule: {e}"
    else:
        for task, struct in schedules.items():
            if isinstance(struct, str):
                t = "custom"
            else:
                t = struct.get("type", "none")
            if t == "none":
                patterns[task] = "none"
            elif t == "interval":
                patterns[task] = "every_x_minutes"
                x_minutes_selected[task] = struct.get("minutes") if not isinstance(struct, str) else None
            elif t == "daily":
                patterns[task] = "daily"
            elif t == "weekly":
                patterns[task] = "weekly"
            elif t == "monthly":
                patterns[task] = "monthly"
            elif t == "custom":
                patterns[task] = "custom"
            else:
                patterns[task] = "custom"
            if t != "interval":
                x_minutes_selected[task] = None
    return render_template(
        "pages/configuration/schedules_edit.html",
        schedules=schedules,
        human_summaries=human_summaries,
        x_minutes_selected=x_minutes_selected,
        patterns=patterns,
        error=error,
        success=success,
        home_url="/",
    )


@bp.route("/automation", methods=["GET", "POST"])
def edit_automation_config():
    """Unified configuration page for Sweep Pots, Autosorter, and Combined Sweep and Sort."""
    automation_config = db_service.get_setting("general.automation_tasks", {})
    sweep_config = automation_config.get("sweep_pots", {})
    autosorter_config = automation_config.get("autosorter", {})
    combined_config = automation_config.get("combined", {})
    sweep_schedule = sweep_config.get("schedule", {"type": "none"})
    autosorter_schedule = autosorter_config.get("schedule", {"type": "none"})
    combined_schedule = combined_config.get("schedule", {"type": "none"})
    message = None
    error = None
    if request.method == "POST":
        # Sweep Pots
        sweep_enabled = request.form.get("sweep_enabled") == "on"
        sweep_source_pot_names = [n.strip() for n in request.form.get("sweep_source_pot_names", "").split(",") if n.strip()]
        sweep_target_pot_name = request.form.get("sweep_target_pot_name", "").strip()
        sweep_minimum_amount = float(request.form.get("sweep_minimum_amount", 0.0))
        sweep_config = {
            "enabled": sweep_enabled,
            "source_pot_names": sweep_source_pot_names,
            "target_pot_name": sweep_target_pot_name,
            "minimum_amount": sweep_minimum_amount,
            "schedule": sweep_config.get("schedule", {"type": "none"}),
        }
        # Autosorter
        autosorter_source_pot = request.form.get("autosorter_source_pot", "").strip()
        autosorter_allocation_strategy = request.form.get("autosorter_allocation_strategy", "free_selection")
        autosorter_destination_pots = [n.strip() for n in request.form.get("autosorter_destination_pots", "").split(",") if n.strip()]
        autosorter_priority_pots = [n.strip() for n in request.form.get("autosorter_priority_pots", "").split(",") if n.strip()]
        autosorter_goal_allocation_method = request.form.get("autosorter_goal_allocation_method", "even")
        autosorter_enable_bills_pot = request.form.get("autosorter_enable_bills_pot") == "on"
        autosorter_bills_pot_name = request.form.get("autosorter_bills_pot_name", "").strip()
        autosorter_savings_pot_name = request.form.get("autosorter_savings_pot_name", "").strip()
        autosorter_payday = request.form.get("autosorter_payday", "15").strip()
        autosorter_frequency = request.form.get("autosorter_frequency", "monthly").strip()
        autosorter_pay_cycle = {"payday": autosorter_payday, "frequency": autosorter_frequency}
        autosorter_config = {
            "source_pot": autosorter_source_pot,
            "allocation_strategy": autosorter_allocation_strategy,
            "destination_pots": {n: {} for n in autosorter_destination_pots},
            "priority_pots": autosorter_priority_pots,
            "goal_allocation_method": autosorter_goal_allocation_method,
            "enable_bills_pot": autosorter_enable_bills_pot,
            "bills_pot_name": autosorter_bills_pot_name,
            "savings_pot_name": autosorter_savings_pot_name,
            "pay_cycle": autosorter_pay_cycle,
            "schedule": autosorter_config.get("schedule", {"type": "none"}),
        }
        # Combined
        combined_enabled = request.form.get("combined_enabled") == "on"
        combined_config = {
            "enabled": combined_enabled,
            "schedule": combined_config.get("schedule", {"type": "none"}),
        }
        # Save all
        automation_config["sweep_pots"] = sweep_config
        automation_config["autosorter"] = autosorter_config
        automation_config["combined"] = combined_config
        db_service.save_setting("general.automation_tasks", automation_config, data_type="json")
        message = "Automation configuration updated successfully."
    return render_template(
        "pages/configuration/automation_unified_edit.html",
        sweep_config=sweep_config,
        autosorter_config=autosorter_config,
        combined_config=combined_config,
        sweep_schedule=sweep_schedule,
        autosorter_schedule=autosorter_schedule,
        combined_schedule=combined_schedule,
        message=message,
        error=error,
        schedule_to_human=schedule_to_human,
        home_url="/",
    )
