"""Sweep Pots service for business logic related to the sweep pots task."""

from typing import Any, Dict, Optional, Tuple
import logging
import time

from flask import current_app

from app.services.monzo_service import MonzoService, get_selected_account_ids
from app.services.configuration_service import get_automation_config
from app.services.task_service import save_task_history
from app.services.metrics_service import metrics_service


def execute_sweep_pots() -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Execute the sweep pots task and return result for rendering.

    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    monzo_service = MonzoService()
    automation_config = get_automation_config()
    sweep_config = automation_config.get("sweep_pots", {})
    sweep_enabled = sweep_config.get("enabled", False)
    source_pot_names = sweep_config.get("source_pot_names", [])
    target_pot_name = sweep_config.get("target_pot_name", "")
    minimum_amount = sweep_config.get("minimum_amount", 0.0)
    current_app.logger.info(
        f"Sweep config: enabled={sweep_enabled}, source_pots={source_pot_names}, target_pot='{target_pot_name}', min_amount=£{minimum_amount}"
    )
    if not sweep_enabled:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots",
                "error": "Sweep pots is not enabled in configuration",
                "home_url": "/",
            },
            None,
        )
    if not source_pot_names:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots",
                "error": "No source pots configured for sweep",
                "home_url": "/",
            },
            None,
        )
    if not target_pot_name:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots",
                "error": "Target pot not configured for sweep",
                "home_url": "/",
            },
            None,
        )
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots",
                "error": "No accounts selected for sweep.",
                "home_url": "/",
            },
            None,
        )
    account_id = selected_ids[0]
    current_app.logger.info(f"Using account: {account_id}")
    target_pot = monzo_service.get_pot_by_name(account_id, target_pot_name)
    if not target_pot:
        result = {
            "status": "error",
            "message": f'Target pot "{target_pot_name}" not found',
            "source_pots": source_pot_names,
            "target_pot": target_pot_name,
        }
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots",
                "error": f"Target pot '{target_pot_name}' not found",
                "home_url": "/",
            },
            result,
        )
    total_swept = 0
    swept_pots = []
    failed_pots = []
    for source_pot_name in source_pot_names:
        try:
            source_pot = monzo_service.get_pot_by_name(account_id, source_pot_name)
            if not source_pot:
                current_app.logger.warning(
                    f"[SweepPots] Source pot '{source_pot_name}' not found"
                )
                continue
            if source_pot.get("deleted", False):
                current_app.logger.info(
                    f"[SweepPots] Skipping deleted pot '{source_pot_name}'"
                )
                continue
            pot_balance_data = monzo_service.get_pot_balance(source_pot["id"])
            pot_balance = pot_balance_data.get("balance", 0) / 100.0
            current_app.logger.info(
                f"Pot '{source_pot_name}' balance: £{pot_balance:.2f}"
            )
            if pot_balance <= minimum_amount:
                current_app.logger.info(
                    f"Pot '{source_pot_name}' balance £{pot_balance:.2f} is below minimum £{minimum_amount:.2f}"
                )
                continue
            amount_pence = int(pot_balance * 100)
            withdrawal_result = monzo_service.withdraw_from_pot(
                source_pot["id"], amount_pence, account_id
            )
            # Annotate withdrawal transaction
            dedupe_id = (
                withdrawal_result.get("dedupe_id")
                if isinstance(withdrawal_result, dict)
                else None
            )
            if dedupe_id:
                monzo_service.find_and_annotate_transaction(account_id, dedupe_id, "Sweep Pots")
            deposit_result = monzo_service.deposit_to_pot(
                target_pot["id"], amount_pence, account_id
            )
            # Annotate deposit transaction
            dedupe_id = (
                deposit_result.get("dedupe_id")
                if isinstance(deposit_result, dict)
                else None
            )
            if dedupe_id:
                monzo_service.find_and_annotate_transaction(account_id, dedupe_id, "Sweep Pots")
            current_app.logger.info(
                f"Withdrew £{pot_balance:.2f} from '{source_pot_name}'"
            )
            current_app.logger.info(
                f"Deposited £{pot_balance:.2f} to '{target_pot_name}'"
            )
            total_swept += pot_balance
            swept_pots.append({"name": source_pot_name, "amount": pot_balance})
        except Exception as e:
            current_app.logger.exception(f"Failed to sweep pot '{source_pot_name}'", extra={"task_name": "Sweep Pots"})
            failed_pots.append({"name": source_pot_name, "error": str(e)})
    result = {
        "status": "partial_success" if failed_pots else "success",
        "message": f"Swept £{total_swept:.2f} from {len(swept_pots)} pots",
        "total_swept": total_swept,
        "swept_pots": swept_pots,
        "failed_pots": failed_pots,
        "target_pot": target_pot_name,
        "minimum_amount": minimum_amount,
    }
    return (
        True,
        {
            "success": True,
            "task_name": "Sweep Pots",
            "message": f"Swept £{total_swept:.2f} from {len(swept_pots)} pots to '{target_pot_name}'",
            "home_url": "/",
        },
        result,
    )


def dry_run_sweep_pots() -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Simulate a dry run of the sweep pots task without making actual transfers.

    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    from app.services.monzo_service import get_selected_account_ids
    monzo_service = MonzoService()
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots (Dry Run)",
                "error": "No accounts selected for sweep pots.",
                "home_url": "/",
            },
            None,
        )
    account_id = selected_ids[0]
    automation_config = get_automation_config()
    sweep_config = automation_config.get("sweep_pots", {})
    sweep_enabled = sweep_config.get("enabled", False)
    if not sweep_enabled:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots (Dry Run)",
                "error": "Sweep pots is not enabled in configuration.",
                "home_url": "/",
            },
            None,
        )
    source_pot_names = sweep_config.get("source_pot_names", [])
    target_pot_name = sweep_config.get("target_pot_name", "")
    minimum_amount = sweep_config.get("minimum_amount", 0.0)
    if not source_pot_names or not target_pot_name:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots (Dry Run)",
                "error": "Source pots or target pot not configured.",
                "home_url": "/",
            },
            None,
        )
    target_pot = monzo_service.get_pot_by_name(account_id, target_pot_name)
    if not target_pot:
        return (
            False,
            {
                "success": False,
                "task_name": "Sweep Pots (Dry Run)",
                "error": f"Target pot '{target_pot_name}' not found",
                "home_url": "/",
            },
            None,
        )
    total_swept = 0
    swept_pots = []
    skipped_pots = []
    failed_pots = []
    for source_pot_name in source_pot_names:
        try:
            source_pot = monzo_service.get_pot_by_name(account_id, source_pot_name)
            if not source_pot:
                failed_pots.append({"name": source_pot_name, "error": "Pot not found"})
                continue
            if source_pot.get("deleted", False):
                skipped_pots.append(
                    {
                        "name": source_pot_name,
                        "balance": 0.0,
                        "reason": "Pot is deleted",
                    }
                )
                continue
            pot_balance_data = monzo_service.get_pot_balance(source_pot["id"])
            pot_balance = pot_balance_data.get("balance", 0) / 100.0
            if pot_balance <= minimum_amount:
                skipped_pots.append(
                    {
                        "name": source_pot_name,
                        "balance": pot_balance,
                        "reason": f"Balance £{pot_balance:.2f} is below minimum £{minimum_amount:.2f}",
                    }
                )
                continue
            swept_pots.append(
                {
                    "name": source_pot_name,
                    "amount": pot_balance,
                    "previous_balance": pot_balance,
                    "new_balance": 0.0,
                }
            )
            total_swept += pot_balance
        except Exception as e:
            failed_pots.append({"name": source_pot_name, "error": str(e)})
    target_balance_data = monzo_service.get_pot_balance(target_pot["id"])
    target_current_balance = target_balance_data.get("balance", 0) / 100.0
    target_new_balance = target_current_balance + total_swept
    result = {
        "status": "dry_run_success",
        "enabled": True,
        "message": f"DRY RUN: Would sweep £{total_swept:.2f} from {len(swept_pots)} pots to {target_pot_name}",
        "total_swept": total_swept,
        "swept_pots": swept_pots,
        "skipped_pots": skipped_pots,
        "failed_pots": failed_pots,
        "target_pot": {
            "name": target_pot_name,
            "current_balance": target_current_balance,
            "new_balance": target_new_balance,
            "amount_to_add": total_swept,
        },
        "minimum_amount": minimum_amount,
    }
    # Create detailed message for display
    message_parts = [
        f"DRY RUN: Would sweep £{total_swept:.2f} from {len(swept_pots)} pots"
    ]
    if swept_pots:
        pot_list = [f"{p['name']} (£{p['amount']:.2f})" for p in swept_pots]
        message_parts.append(f"Pots to sweep: {', '.join(pot_list)}")
    if skipped_pots:
        skipped_list = [f"{p['name']} ({p['reason']})" for p in skipped_pots]
        message_parts.append(f"Skipped: {', '.join(skipped_list)}")
    if failed_pots:
        failed_list = [f"{p['name']} ({p['error']})" for p in failed_pots]
        message_parts.append(f"Failed: {', '.join(failed_list)}")
    message_parts.append(
        f"Target '{target_pot_name}' would go from £{target_current_balance:.2f} to £{target_new_balance:.2f}"
    )
    return (
        True,
        {
            "success": True,
            "task_name": "Sweep Pots (Dry Run)",
            "message": " | ".join(message_parts),
            "home_url": "/",
        },
        result,
    )


def run_and_record_sweep_pots(context_flags=None):
    """Run sweep pots, normalize result, save history, and return result.
    Args:
        context_flags: Optional dict of extra flags (e.g., manual_execution, startup_run)
    Returns:
        Tuple: (success, context, error)
    """
    start = time.time()
    success, context, error = execute_sweep_pots()
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
        "task_name": context.get("task_name", "Sweep Pots"),
        "balance": balance,
        "threshold": context.get("threshold"),
        "target": context.get("target"),
        "pot_balance": context.get("pot_balance"),
        "amount_transferred": context.get("amount_transferred"),
        "status": context.get("status", "unknown"),
    }
    if context_flags:
        result.update(context_flags)
    from app.services.task_service import save_task_history
    save_task_history("sweep_pots", result, success)
    metrics_service.record("sweep_pots", success, duration, error)
    return success, context, error
