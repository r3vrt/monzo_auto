"""Auto Topup service for business logic related to the auto topup task."""

from typing import Any, Dict, Optional, Tuple
import logging
import os
import datetime
import time

from flask import current_app

from app.services.monzo_service import MonzoService, get_selected_account_ids
from app.services.task_service import save_task_history, load_task_history
from app.services.database_service import db_service
from app.services.metrics_service import metrics_service


def execute_auto_topup() -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Execute the auto topup task and return result for rendering.

    Returns:
        Tuple of (success, context dict for template, error message if any)
    """
    logging.warning("[AutoTopup] execute_auto_topup called")
    monzo_service = MonzoService()
    
    # Load auto topup configuration from database
    auto_topup_config = db_service.get_setting("general.auto_topup", {})
    if not auto_topup_config.get("enabled", False):
        return (
            False,
            {
                "success": False,
                "task_name": "Auto Topup",
                "error": "Auto-topup is not enabled in configuration",
                "home_url": "/",
            },
            None,
        )
    source_pot_name = auto_topup_config.get("source_pot_name", "")
    threshold_amount = auto_topup_config.get("threshold_amount", 30.0)
    target_amount = auto_topup_config.get("target_amount", 50.0)
    current_app.logger.info(
        f"Auto-topup config: pot='{source_pot_name}', threshold=£{threshold_amount}, target=£{target_amount}"
    )
    if not source_pot_name:
        return (
            False,
            {
                "success": False,
                "task_name": "Auto Topup",
                "error": "Source pot name not configured",
                "home_url": "/",
            },
            "Source pot name not configured",
        )
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        return (
            False,
            {
                "success": False,
                "task_name": "Auto Topup",
                "error": "No accounts selected for auto-topup.",
                "home_url": "/",
            },
            "No accounts selected for auto-topup.",
        )
    account_id = selected_ids[0]
    current_app.logger.info(f"Using account: {account_id}")
    balance_data = monzo_service.get_balance(account_id)
    current_app.logger.debug(f"Balance data: {balance_data}")
    if isinstance(balance_data, dict):
        current_balance = balance_data.get("balance", 0) / 100.0
    else:
        current_balance = float(balance_data)
    current_app.logger.info(f"Current balance: £{current_balance:.2f}")
    if current_balance >= threshold_amount:
        result = {
            "status": "no_action_needed",
            "message": f"Balance £{current_balance:.2f} is above threshold £{threshold_amount:.2f}",
            "balance": current_balance,
            "threshold": threshold_amount,
            "target": target_amount,
        }
        logging.warning(f"[AutoTopup] execute_auto_topup result: success={{}} context={{}} error={{}}".format(True, result, None))
        return (
            True,
            {
                "success": True,
                "task_name": "Auto Topup",
                "message": f"Topup not needed. Current balance: £{current_balance:.2f}, Threshold: £{threshold_amount:.2f}",
                "home_url": "/",
            },
            None,
        )
    amount_needed = target_amount - current_balance
    current_app.logger.info(f"Amount needed: £{amount_needed:.2f}")
    current_app.logger.info(f"Looking for pot: '{source_pot_name}'")
    source_pot = monzo_service.get_pot_by_name(account_id, source_pot_name)
    if not source_pot:
        try:
            all_pots = monzo_service.get_pots(account_id)
            pot_names = [pot.get("name", "Unknown") for pot in all_pots]
            current_app.logger.warning(f"Available pots: {pot_names}")
            return (
                False,
                {
                    "success": False,
                    "task_name": "Auto Topup",
                    "error": f"Source pot '{source_pot_name}' not found. Available pots: {', '.join(pot_names)}",
                    "home_url": "/",
                },
                f"Source pot '{source_pot_name}' not found. Available pots: {', '.join(pot_names)}",
            )
        except Exception as e:
            current_app.logger.exception(f"Failed to get available pots", extra={"task_name": "Auto Topup"})
            return (
                False,
                {
                    "success": False,
                    "task_name": "Auto Topup",
                    "error": f"Source pot '{source_pot_name}' not found. Error getting available pots: {str(e)}",
                    "home_url": "/",
                },
                f"Source pot '{source_pot_name}' not found. Error getting available pots: {str(e)}",
            )
    current_app.logger.info(f"Found source pot: {source_pot}")
    pot_balance_data = monzo_service.get_pot_balance(source_pot["id"])
    current_app.logger.debug(f"Pot balance data: {pot_balance_data}")
    if isinstance(pot_balance_data, dict):
        pot_balance = pot_balance_data.get("balance", 0) / 100.0
    else:
        pot_balance = float(pot_balance_data)
    current_app.logger.info(f"Pot balance: £{pot_balance:.2f}")
    if pot_balance < amount_needed:
        amount_to_transfer = pot_balance
        current_app.logger.warning(
            f"Pot does not have enough. Will transfer remaining £{amount_to_transfer:.2f} instead of £{amount_needed:.2f}"
        )
    else:
        amount_to_transfer = amount_needed
    amount_pence = int(amount_to_transfer * 100)
    current_app.logger.info(
        f"Performing topup: {amount_pence} pence from pot {source_pot['id']} to account {account_id}"
    )
    if amount_pence < 1:
        return (
            False,
            {
                "success": False,
                "task_name": "Auto Topup",
                "error": "Amount to transfer is less than 1p. No transfer will be made.",
                "home_url": "/",
            },
            "Amount to transfer is less than 1p. No transfer will be made.",
        )
    try:
        transfer_result = monzo_service.withdraw_from_pot(
            source_pot["id"], amount_pence, account_id
        )
        # Annotate the transaction with the task name as note
        dedupe_id = (
            transfer_result.get("dedupe_id")
            if isinstance(transfer_result, dict)
            else None
        )
        if dedupe_id:
            monzo_service.find_and_annotate_transaction(account_id, dedupe_id, "Auto Topup")
        result = {
            "status": "success",
            "message": f'Transferred £{amount_to_transfer:.2f} from pot "{source_pot_name}" to account.',
            "balance": current_balance,
            "threshold": threshold_amount,
            "target": target_amount,
            "pot_balance": pot_balance,
            "amount_transferred": amount_to_transfer,
            "transfer_result": transfer_result,
        }
        logging.warning(f"[AutoTopup] execute_auto_topup result: success={{}} context={{}} error={{}}".format(True, result, None))
        return (
            True,
            {
                "success": True,
                "task_name": "Auto Topup",
                "message": f"Transferred £{amount_to_transfer:.2f} from pot '{source_pot_name}' to account.",
                "home_url": "/",
            },
            None,
        )
    except Exception as e:
        result = {
            "status": "error",
            "message": f"Failed to transfer funds: {str(e)}",
            "balance": current_balance,
            "threshold": threshold_amount,
            "target": target_amount,
            "pot_balance": pot_balance,
            "amount_to_transfer": amount_to_transfer,
        }
        current_app.logger.exception(f"[AutoTopup] execute_auto_topup failed", extra={"task_name": "Auto Topup"})
        return (
            False,
            {
                "success": False,
                "task_name": "Auto Topup",
                "error": f"Failed to transfer funds: {str(e)}",
                "home_url": "/",
            },
            str(e),
        )

def run_and_record_auto_topup(context_flags=None):
    """Run auto topup, normalize result, save history, and return result.
    Args:
        context_flags: Optional dict of extra flags (e.g., manual_execution, startup_run)
    Returns:
        Tuple: (success, context, error)
    """
    start = time.time()
    success, context, error = execute_auto_topup()
    duration = time.time() - start
    # Normalize balance
    balance = context.get("balance")
    if balance is None:
        balance = 0.0
    try:
        balance = float(balance)
    except (TypeError, ValueError):
        balance = 0.0
    result = {
        "success": success,
        "message": context.get("message", ""),
        "error": context.get("error", error),
        "task_name": context.get("task_name", "Auto Topup"),
        "balance": balance,
        "threshold": context.get("threshold"),
        "target": context.get("target"),
        "pot_balance": context.get("pot_balance"),
        "amount_transferred": context.get("amount_transferred"),
        "status": context.get("status", "unknown"),
    }
    if context_flags:
        result.update(context_flags)
    save_task_history("auto_topup", result, success)
    metrics_service.record("auto_topup", success, duration, error)
    return success, context, error


def scheduled_auto_topup():
    """Scheduled job for auto topup, to be used with APScheduler."""
    import logging
    from app import app  # Import inside the function to avoid circular import
    pid = os.getpid()
    now = datetime.datetime.now().isoformat()
    logging.warning(f"[AutoTopup] Running in PID {pid} at {now}")
    with app.app_context():
        run_and_record_auto_topup()
        logging.warning(f"[AutoTopup] Task history saved for auto_topup")


def should_run_auto_topup_on_startup() -> bool:
    """Check if auto topup should run on app startup.
    
    Returns True if:
    - Auto topup is enabled
    - More than 30 minutes have passed since the last successful run
    - Or if there's no previous run history
    
    Returns:
        bool: True if auto topup should run on startup
    """
    try:
        # Check if auto topup is enabled (read from database)
        auto_topup_config = db_service.get_setting("general.auto_topup", {})
        if not auto_topup_config.get("enabled", False):
            current_app.logger.info("Auto topup: Not enabled in configuration")
            return False
        
        # Load the last auto topup execution
        history = load_task_history("auto_topup")
        if not history:
            # No previous runs, so run on startup
            current_app.logger.info("Auto topup: No previous runs found, will run on startup")
            return True
        
        # Get the most recent successful run
        last_successful_run = None
        for record in history:
            if record.get("success", False):
                last_successful_run = record
                break
        
        if not last_successful_run:
            # No successful runs, so run on startup
            current_app.logger.info("Auto topup: No previous successful runs found, will run on startup")
            return True
        
        # Check if more than 30 minutes have passed
        last_run_time = datetime.datetime.fromisoformat(last_successful_run["timestamp"])
        now = datetime.datetime.now()
        time_diff = now - last_run_time
        
        # 30 minutes = 30 * 60 = 1800 seconds
        if time_diff.total_seconds() > 1800:
            current_app.logger.info(f"Auto topup: Last run was {time_diff.total_seconds()/60:.1f} minutes ago, will run on startup")
            return True
        else:
            current_app.logger.info(f"Auto topup: Last run was {time_diff.total_seconds()/60:.1f} minutes ago, skipping startup run")
            return False
            
    except Exception as e:
        current_app.logger.error(f"Error checking auto topup startup condition: {e}")
        # If there's an error, err on the side of caution and don't run
        return False


def run_auto_topup_on_startup():
    """Run auto topup on app startup if conditions are met."""
    try:
        if should_run_auto_topup_on_startup():
            current_app.logger.info("Auto topup: Running on startup")
            run_and_record_auto_topup({"startup_run": True})
            current_app.logger.info(f"Auto topup startup run completed")
        else:
            current_app.logger.info("Auto topup: Skipping startup run")
    except Exception as e:
        current_app.logger.error(f"Error running auto topup on startup: {e}")
