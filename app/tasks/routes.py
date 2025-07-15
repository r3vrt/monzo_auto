"""Routes for automation tasks."""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from flask import current_app, jsonify, render_template, request

from app.services.monzo_service import MonzoService, get_selected_account_ids
from app.services.auto_topup_service import execute_auto_topup, run_and_record_auto_topup
from app.services.sweep_pots_service import execute_sweep_pots, dry_run_sweep_pots, run_and_record_sweep_pots
from app.services.autosorter_service import execute_autosorter, dry_run_autosorter, run_and_record_autosorter
from app.services.combined_dry_run_service import dry_run_combined
from app.services.task_service import save_task_history, load_task_history, get_task_list
from app.services.transaction_service import get_transactions_for_selected_accounts
from app.tasks import bp


@bp.route("/", methods=["GET"])
def list_tasks():
    """List all available automation tasks."""
    tasks = get_task_list()
    return render_template("pages/tasks/list.html", tasks=tasks, home_url="/")


@bp.route("/<task_id>/execute", methods=["GET", "POST"])
def execute_task(task_id: str):
    """Execute a specific automation task."""
    if task_id == "auto_topup":
        success, context, error = run_and_record_auto_topup({"manual_execution": True})
        
        # Ensure balance is always a float for template rendering
        balance = context.get("balance")
        if balance is None:
            balance = 0.0
        try:
            balance = float(balance)
        except (TypeError, ValueError):
            balance = 0.0
        
        # Save task history for manual executions
        result = {
            "success": success,
            "message": context.get("message", ""),
            "error": context.get("error", error),
            "task_name": context.get("task_name", "Auto Topup"),
            "manual_execution": True,  # Mark this as a manual execution
            # Include the detailed result data for display in the UI
            "balance": balance,
            "threshold": context.get("threshold"),
            "target": context.get("target"),
            "pot_balance": context.get("pot_balance"),
            "amount_transferred": context.get("amount_transferred"),
            "status": context.get("status", "unknown"),
        }
        save_task_history("auto_topup", result, success)
        
        return render_template("pages/tasks/execute.html", **context), (200 if success else 400)
    elif task_id == "sweep_pots":
        success, context, error = run_and_record_sweep_pots({"manual_execution": True})
        
        # Save task history for manual executions
        result = {
            "success": success,
            "message": context.get("message", ""),
            "error": context.get("error", error),
            "task_name": context.get("task_name", "Sweep Pots"),
            "manual_execution": True,  # Mark this as a manual execution
        }
        save_task_history("sweep_pots", result, success)
        
        return render_template("pages/tasks/execute.html", **context), (200 if success else 400)
    elif task_id == "autosorter":
        success, context, error = run_and_record_autosorter({"manual_execution": True})
        return render_template("pages/tasks/execute.html", **context), (200 if success else 400)
    elif task_id == "transaction_sync":
        # For now, just show a not implemented message (implement if service exists)
        context = {
            "success": False,
            "task_name": "Transaction Sync",
            "error": "Transaction sync via service not yet implemented.",
            "home_url": "/",
        }
        return render_template("pages/tasks/execute.html", **context), 501
    else:
        context = {
            "success": False,
            "task_name": task_id,
            "error": "Unknown or removed task.",
            "home_url": "/",
        }
        return render_template("pages/tasks/execute.html", **context), 404


@bp.route("/autosorter/execute", methods=["GET", "POST"])
def execute_autosorter_route():
    """Execute the autosorter task."""
    success, context, error = execute_autosorter()
    
    # Save task history for manual executions
    result = {
        "success": success,
        "message": context.get("message", ""),
        "error": context.get("error", error),
        "task_name": context.get("task_name", "Autosorter"),
        "manual_execution": True,  # Mark this as a manual execution
    }
    save_task_history("autosorter", result, success)
    
    return render_template("pages/tasks/execute.html", **context), (200 if success else 400)


@bp.route("/autosorter/dry_run", methods=["GET", "POST"])
def dry_run_autosorter_route():
    """Execute a dry run of the autosorter task without making actual transfers."""
    success, context, _ = dry_run_autosorter()
    return render_template("pages/tasks/execute.html", **context), (200 if success else 400)


@bp.route("/combined/dry_run", methods=["GET", "POST"])
def dry_run_combined_route():
    """Execute a dry run of both sweep pots and autosorter tasks in sequence without making actual transfers."""
    current_app.logger.info("[Route] Entered /tasks/combined/dry_run route")
    success, context, result = dry_run_combined()
    current_app.logger.info("[Route] dry_run_combined() returned. Preparing to render template.")
    # Pass detailed results for breakdown rendering
    sweep_results = result["sweep"] if result and "sweep" in result else None
    autosorter_results = result["autosorter"] if result and "autosorter" in result else None
    current_app.logger.info("[Route] About to return response for /tasks/combined/dry_run")
    return render_template(
        "pages/tasks/execute.html",
        **context,
        sweep_results=sweep_results,
        autosorter_results=autosorter_results,
    ), (200 if success else 400)


@bp.route("/accounts", methods=["GET"])
def get_accounts():
    """Get user accounts.

    Returns:
        HTML page with account information
    """
    try:
        monzo_service = MonzoService()
        accounts = monzo_service.get_accounts()
        return render_template(
            "pages/tasks/accounts.html", success=True, accounts=accounts, home_url="/"
        )
    except Exception as e:
        current_app.logger.exception("Failed to get accounts", extra={"route": "get_accounts"})
        return (
            render_template(
                "pages/tasks/accounts.html", success=False, error=str(e), home_url="/"
            ),
            500,
        )


@bp.route("/accounts/<account_id>/transactions", methods=["GET"])
def get_account_transactions(account_id: str):
    """Get transactions for a specific account and render them with pot names."""
    try:
        limit = request.args.get("limit", 100, type=int)
        monzo_service = MonzoService()
        transactions = monzo_service.get_transactions(account_id, limit=limit)
        
        # Get all pots for this account to create a mapping from pot_id to pot_name
        try:
            pots = monzo_service.get_pots(account_id)
            pot_map = {pot.get("id"): pot.get("name", "Unknown Pot") for pot in pots if pot.get("id")}
        except Exception as e:
            current_app.logger.error(f"Failed to get pots: {e}")
            pot_map = {}
        
        for txn in transactions:
            # Check for pot_id in different possible locations
            pot_id = txn.get("pot_id")
            
            # If no pot_id, check if description starts with 'pot_' (pot ID)
            if not pot_id and txn.get("description", "").startswith("pot_"):
                pot_id = txn.get("description")
            
            # Check metadata for pot information
            if not pot_id and txn.get("metadata"):
                metadata = txn.get("metadata", {})
                if isinstance(metadata, dict):
                    pot_id = metadata.get("pot_id") or metadata.get("pot")
            
            if pot_id and pot_id in pot_map:
                txn["pot_name"] = pot_map[pot_id]
                txn["pot_id_short"] = None
            elif pot_id:
                txn["pot_name"] = "Unknown Pot"
                txn["pot_id_short"] = pot_id[:8] if len(pot_id) > 8 else pot_id
            else:
                txn["pot_name"] = None
                txn["pot_id_short"] = None
        
        return render_template(
            "pages/tasks/transactions.html",
            transactions=transactions,
            account_id=account_id,
            task_name="Account Transactions",
            success=True,
            transaction_count=len(transactions),
            message=None,
            error=None,
        )
    except Exception as e:
        current_app.logger.exception("Failed to get transactions", extra={"route": "get_account_transactions"})
        return render_template(
            "pages/tasks/transactions.html",
            transactions=[],
            account_id=account_id,
            task_name="Account Transactions",
            success=False,
            transaction_count=0,
            message=None,
            error=str(e),
        ), 500


@bp.route("/status", methods=["GET"])
def task_status():
    """Display task execution history.

    Returns:
        HTML page with task execution history
    """
    try:
        # Load history for all tasks
        auto_topup_history = load_task_history("auto_topup")
        transaction_sync_history = load_task_history("transaction_sync")
        sweep_pots_history = load_task_history("sweep_pots")

        # Format timestamps for display
        def format_history(history):
            for record in history:
                if "timestamp" in record:
                    try:
                        dt = datetime.fromisoformat(record["timestamp"])
                        record["formatted_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        record["formatted_time"] = record["timestamp"]
            return history

        auto_topup_history = sorted(
            format_history(auto_topup_history),
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )
        transaction_sync_history = sorted(
            format_history(transaction_sync_history),
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )
        sweep_pots_history = sorted(
            format_history(sweep_pots_history),
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )

        return render_template(
            "pages/tasks/status.html",
            auto_topup_history=auto_topup_history,
            transaction_sync_history=transaction_sync_history,
            sweep_pots_history=sweep_pots_history,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to load task status", extra={"route": "task_status"})
        return (
            render_template(
                "pages/tasks/status.html",
                error=str(e),
                auto_topup_history=[],
                transaction_sync_history=[],
                sweep_pots_history=[],
                home_url="/",
            ),
            500,
        )


@bp.route("/auto_topup/status", methods=["GET"])
def auto_topup_status():
    """Display auto-topup task execution history.

    Returns:
        HTML page with auto-topup execution history
    """
    try:
        auto_topup_history = load_task_history("auto_topup")

        # Format timestamps for display
        for record in auto_topup_history:
            if "timestamp" in record:
                try:
                    dt = datetime.fromisoformat(record["timestamp"])
                    record["formatted_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    record["formatted_time"] = record["timestamp"]

        auto_topup_history = sorted(
            auto_topup_history, key=lambda r: r.get("timestamp", ""), reverse=True
        )

        return render_template(
            "pages/tasks/status.html",
            auto_topup_history=auto_topup_history,
            transaction_sync_history=[],
            highlighted_task="auto_topup",
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to load auto-topup status", extra={"route": "auto_topup_status"})
        return (
            render_template(
                "pages/tasks/status.html",
                error=str(e),
                auto_topup_history=[],
                transaction_sync_history=[],
                highlighted_task="auto_topup",
                home_url="/",
            ),
            500,
        )


@bp.route("/transaction_sync/status", methods=["GET"])
def transaction_sync_status():
    """Display transaction sync task execution history.

    Returns:
        HTML page with transaction sync execution history
    """
    try:
        transaction_sync_history = load_task_history("transaction_sync")

        # Format timestamps for display
        for record in transaction_sync_history:
            if "timestamp" in record:
                try:
                    dt = datetime.fromisoformat(record["timestamp"])
                    record["formatted_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    record["formatted_time"] = record["timestamp"]

        transaction_sync_history = sorted(
            transaction_sync_history, key=lambda r: r.get("timestamp", ""), reverse=True
        )

        return render_template(
            "pages/tasks/status.html",
            auto_topup_history=[],
            transaction_sync_history=transaction_sync_history,
            highlighted_task="transaction_sync",
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to load transaction sync status", extra={"route": "transaction_sync_status"})
        return (
            render_template(
                "pages/tasks/status.html",
                error=str(e),
                auto_topup_history=[],
                transaction_sync_history=[],
                highlighted_task="transaction_sync",
                home_url="/",
            ),
            500,
        )


@bp.route("/sweep_pots/status", methods=["GET"])
def sweep_pots_status():
    """Display sweep pots task execution history.

    Returns:
        HTML page with sweep pots execution history
    """
    try:
        sweep_pots_history = load_task_history("sweep_pots")

        # Format timestamps for display
        for record in sweep_pots_history:
            if "timestamp" in record:
                try:
                    dt = datetime.fromisoformat(record["timestamp"])
                    record["formatted_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    record["formatted_time"] = record["timestamp"]

        sweep_pots_history = sorted(
            sweep_pots_history, key=lambda r: r.get("timestamp", ""), reverse=True
        )

        return render_template(
            "pages/tasks/status.html",
            auto_topup_history=[],
            transaction_sync_history=[],
            sweep_pots_history=sweep_pots_history,
            highlighted_task="sweep_pots",
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to load sweep pots status", extra={"route": "sweep_pots_status"})
        return (
            render_template(
                "pages/tasks/status.html",
                error=str(e),
                auto_topup_history=[],
                transaction_sync_history=[],
                sweep_pots_history=[],
                highlighted_task="sweep_pots",
                home_url="/",
            ),
            500,
        )


@bp.route("/combined_automation/status", methods=["GET"])
def combined_automation_status():
    """Display combined sweep & sort task execution history.

    Returns:
        HTML page with combined automation execution history
    """
    try:
        combined_history = load_task_history("combined_automation")

        # Format timestamps for display
        for record in combined_history:
            if "timestamp" in record:
                try:
                    dt = datetime.fromisoformat(record["timestamp"])
                    record["formatted_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    record["formatted_time"] = record["timestamp"]

        combined_history = sorted(
            combined_history, key=lambda r: r.get("timestamp", ""), reverse=True
        )

        return render_template(
            "pages/tasks/status.html",
            auto_topup_history=[],
            transaction_sync_history=[],
            sweep_pots_history=[],
            autosorter_history=[],
            combined_automation_history=combined_history,
            highlighted_task="combined_automation",
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to load combined automation status", extra={"route": "combined_automation_status"})
        return (
            render_template(
                "pages/tasks/status.html",
                error=str(e),
                auto_topup_history=[],
                transaction_sync_history=[],
                sweep_pots_history=[],
                autosorter_history=[],
                combined_automation_history=[],
                highlighted_task="combined_automation",
                home_url="/",
            ),
            500,
        )
