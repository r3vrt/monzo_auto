"""Combined Dry Run service for simulating sweep pots and autosorter dry runs in sequence."""

from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from flask import current_app

from app.services.monzo_service import MonzoService, get_selected_account_ids
from app.services.configuration_service import get_config_overview, get_automation_config


def dry_run_combined() -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Simulate a dry run of both sweep pots and autosorter tasks in sequence without making actual transfers.

    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    current_app.logger.info("[Debug] Entered dry_run_combined")
    monzo_service = MonzoService()
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        current_app.logger.warning("[Debug] No accounts selected in dry_run_combined, returning early.")
        return (
            False,
            {
                "success": False,
                "task_name": "Combined Dry Run (Sweep + Autosorter)",
                "error": "No accounts selected.",
                "home_url": "/",
            },
            None,
        )
    account_id = selected_ids[0]
    results = {"sweep": None, "autosorter": None, "combined_effect": {}}
    # Step 1: Dry run sweep pots (reuse dry_run_sweep_pots logic)
    from app.services.sweep_pots_service import dry_run_sweep_pots
    current_app.logger.info("[Debug] Calling dry_run_sweep_pots in dry_run_combined")
    sweep_success, sweep_context, sweep_result = dry_run_sweep_pots()
    current_app.logger.info(f"[Debug] dry_run_sweep_pots returned: success={sweep_success}")
    results["sweep"] = sweep_result
    # Step 2: Dry run autosorter (reuse dry_run_autosorter logic, but simulate pot balances after sweep)
    from app.services.autosorter_service import dry_run_autosorter
    current_app.logger.info("[Debug] Building simulated_pot_balances in dry_run_combined")
    simulated_pot_balances = {}
    sweep_adjustment = 0.0
    total_swept = 0.0
    sweep_source_pot_names = []
    sweep_target_pot_name = None
    if sweep_result:
        for swept in sweep_result.get("swept_pots", []):
            simulated_pot_balances[swept["name"]] = 0.0
            total_swept += swept["amount"]
            sweep_source_pot_names.append(swept["name"])
        if sweep_result.get("target_pot"):
            sweep_target_pot_name = sweep_result["target_pot"]["name"]
            sweep_adjustment = sweep_result["target_pot"]["amount_to_add"]
    current_app.logger.info(f"[Debug] Simulated pot balances after sweep: {simulated_pot_balances}")
    pots = _get_all_pots()
    automation_config = get_automation_config()
    autosorter_config = automation_config.get("autosorter", {})
    source_pot_name = autosorter_config.get("source_pot") if autosorter_config else None
    true_original_balance = None
    if source_pot_name:
        for pot in pots:
            if pot["name"] == source_pot_name:
                true_original_balance = pot["balance"] / 100.0
                break
        simulated_pot_balances[source_pot_name] = (true_original_balance or 0.0) + total_swept + 3200.0
        current_app.logger.info(f"[Debug] Source pot: {source_pot_name}, true_original_balance: {true_original_balance}, total_swept: {total_swept}, simulated_source_balance: {simulated_pot_balances[source_pot_name]}")
    current_app.logger.info("[Debug] Calling dry_run_autosorter in dry_run_combined")
    autosorter_success, autosorter_context, autosorter_result = dry_run_autosorter(
        simulated_source_balance=true_original_balance,
        simulated_pot_balances=simulated_pot_balances
    )
    current_app.logger.info(f"[Debug] dry_run_autosorter returned: success={autosorter_success}")
    if autosorter_result and "source_pot" in autosorter_result:
        autosorter_result["source_pot"]["sweep_adjustment"] = total_swept
    results["autosorter"] = autosorter_result
    combined_message = []
    if sweep_result:
        combined_message.append(sweep_result.get("message", ""))
    if autosorter_result:
        combined_message.append(autosorter_result.get("message", ""))
    result = {
        "status": (
            "dry_run_success"
            if sweep_success and autosorter_success
            else "dry_run_partial"
        ),
        "message": " | ".join(combined_message),
        "sweep": sweep_result,
        "autosorter": autosorter_result,
    }
    current_app.logger.info("[Debug] Returning from dry_run_combined")
    return (
        sweep_success and autosorter_success,
        {
            "success": sweep_success and autosorter_success,
            "task_name": "Combined Dry Run (Sweep + Autosorter)",
            "message": " | ".join(combined_message),
            "home_url": "/",
        },
        result,
    )


def _get_all_pots():
    """Helper function to get all pots for all selected accounts."""
    monzo_service = MonzoService()
    account_ids = get_selected_account_ids()
    pots = []
    for account_id in account_ids:
        pots.extend(monzo_service.get_pots(account_id))
    return pots
