"""Autosorter service for business logic related to the autosorter task."""

from typing import Any, Dict, Optional, Tuple

from flask import current_app

from app.services.monzo_service import MonzoService, get_selected_account_ids
from app.services.configuration_service import get_automation_config
from app.services.metrics_service import metrics_service
import time


def execute_autosorter() -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Execute the autosorter task and return result for rendering.

    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    monzo_service = MonzoService()
    automation_config = get_automation_config()
    autosorter_config = automation_config.get("autosorter", {})
    source_pot = autosorter_config.get("source_pot", "")
    destination_pots = autosorter_config.get("destination_pots", {})
    allocation_strategy = autosorter_config.get("allocation_strategy", "free_selection")
    priority_pots = autosorter_config.get("priority_pots", [])
    goal_allocation_method = autosorter_config.get("goal_allocation_method", "even")
    enable_bills_pot = autosorter_config.get("enable_bills_pot", False)
    bills_pot_name = autosorter_config.get("bills_pot_name", "")
    savings_pot_name = autosorter_config.get("savings_pot_name", "")
    pay_cycle = autosorter_config.get(
        "pay_cycle", {"payday": "15", "frequency": "monthly"}
    )
    if not source_pot:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter",
                "error": "Source pot not configured",
                "home_url": "/",
            },
            None,
        )
    if allocation_strategy == "free_selection" and not destination_pots:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter",
                "error": "No destination pots configured for free selection strategy",
                "home_url": "/",
            },
            None,
        )
    try:
        monzo_service.autosorter(
            source_pot=source_pot,
            destination_pots=destination_pots,
            allocation_strategy=allocation_strategy,
            priority_pots=priority_pots,
            goal_allocation_method=goal_allocation_method,
            bills_pot_name=bills_pot_name,
            savings_pot_name=savings_pot_name,
            pay_cycle=pay_cycle,
            enable_bills_pot=enable_bills_pot,
        )
        result = {
            "status": "success",
            "message": f"Autosorter executed successfully from {source_pot}",
            "source_pot": source_pot,
            "allocation_strategy": allocation_strategy,
            "destination_pots": (
                list(destination_pots.keys())
                if allocation_strategy == "free_selection"
                else None
            ),
            "priority_pots": (
                priority_pots if allocation_strategy == "priority_goals" else None
            ),
            "goal_allocation_method": goal_allocation_method,
            "enable_bills_pot": enable_bills_pot,
            "bills_pot_name": bills_pot_name if enable_bills_pot else None,
            "savings_pot_name": savings_pot_name if savings_pot_name else None,
        }
        strategy_description = {
            "free_selection": f"free selection to {len(destination_pots)} pots",
            "all_goals": "all pots with goals",
            "priority_goals": f"priority pots + remaining goals",
        }.get(allocation_strategy, allocation_strategy)
        return (
            True,
            {
                "success": True,
                "task_name": "Autosorter",
                "message": f"Autosorter executed successfully from '{source_pot}' using {strategy_description}",
                "home_url": "/",
            },
            result,
        )
    except Exception as e:
        result = {"status": "error", "message": str(e), "source_pot": source_pot}
        current_app.logger.exception("Autosorter failed", extra={"task_name": "Autosorter"})
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter",
                "error": f"Autosorter failed: {str(e)}",
                "home_url": "/",
            },
            result,
        )


def dry_run_autosorter(
    simulated_source_balance: Optional[float] = None,
    simulated_pot_balances: Optional[Dict[str, float]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Simulate a dry run of the autosorter task without making actual transfers.

    Args:
        simulated_source_balance (Optional[float]): If provided, use this as the source pot's starting balance instead of the real balance.
        simulated_pot_balances (Optional[Dict[str, float]]): If provided, use these balances for all pots (by name) instead of the real ones.

    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    from datetime import date, timedelta

    monzo_service = MonzoService()
    automation_config = get_automation_config()
    autosorter_config = automation_config.get("autosorter", {})
    source_pot = autosorter_config.get("source_pot", "")
    destination_pots = autosorter_config.get("destination_pots", {})
    allocation_strategy = autosorter_config.get("allocation_strategy", "free_selection")
    priority_pots = autosorter_config.get("priority_pots", [])
    goal_allocation_method = autosorter_config.get("goal_allocation_method", "even")
    enable_bills_pot = autosorter_config.get("enable_bills_pot", False)
    bills_pot_name = autosorter_config.get("bills_pot_name", "")
    savings_pot_name = autosorter_config.get("savings_pot_name", "")
    pay_cycle = autosorter_config.get(
        "pay_cycle", {"payday": "15", "frequency": "monthly"}
    )
    if not source_pot:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter (Dry Run)",
                "error": "Source pot not configured",
                "home_url": "/",
            },
            None,
        )
    if allocation_strategy == "free_selection" and not destination_pots:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter (Dry Run)",
                "error": "No destination pots configured for free selection strategy",
                "home_url": "/",
            },
            None,
        )
    selected_accounts = get_selected_account_ids()
    if not selected_accounts:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter (Dry Run)",
                "error": "No selected account for autosorter.",
                "home_url": "/",
            },
            None,
        )
    account_id = selected_accounts[0]
    pots = monzo_service.get_pots(account_id)
    active_pots = [pot for pot in pots if not pot.get("deleted", False)]
    pot_map = {pot["name"]: pot for pot in active_pots}
    # Override balances with simulated_pot_balances if provided
    def get_pot_balance(pot_name: str) -> float:
        if simulated_pot_balances and pot_name in simulated_pot_balances:
            return simulated_pot_balances[pot_name]
        pot = pot_map.get(pot_name)
        return pot.get("balance", 0) / 100.0 if pot else 0.0
    src_pot = pot_map.get(source_pot)
    if not src_pot:
        return (
            False,
            {
                "success": False,
                "task_name": "Autosorter (Dry Run)",
                "error": f"Source pot '{source_pot}' not found.",
                "home_url": "/",
            },
            None,
        )
    # Use simulated_source_balance for original_balance if provided
    if simulated_source_balance is not None:
        original_balance = simulated_source_balance
        real_balance = get_pot_balance(source_pot)
        simulated_addition = original_balance - real_balance
    else:
        original_balance = get_pot_balance(source_pot)
        simulated_addition = 3200.0
    # The key fix: use the simulated pot balance for all downstream calculations
    if simulated_pot_balances and source_pot in simulated_pot_balances:
        simulated_balance = simulated_pot_balances[source_pot]
    else:
        simulated_balance = original_balance + 3200.0
    bills_topup = 0.0
    bills_calculation = None
    bills_transactions = []
    running_total = 0.0
    if (
        enable_bills_pot
        and bills_pot_name
        and bills_pot_name in pot_map
        and pay_cycle
        and pay_cycle.get("payday")
    ):
        bills_pot = pot_map.get(bills_pot_name)
        if bills_pot:
            bills_balance = get_pot_balance(bills_pot_name)
            payday_day = int(pay_cycle["payday"])
            today = date.today()
            if pay_cycle.get("frequency") == "biweekly":
                days_since_last_payday = (today.day - payday_day) % 14
                if days_since_last_payday < 0:
                    days_since_last_payday += 14
                last_payday = today - timedelta(days=days_since_last_payday)
                cycle_start = last_payday - timedelta(days=14)
                cycle_end = last_payday
            elif pay_cycle.get("frequency") == "monthly":
                if today.day >= payday_day:
                    last_payday = today.replace(day=payday_day)
                else:
                    if today.month == 1:
                        prev_month = 12
                        prev_year = today.year - 1
                    else:
                        prev_month = today.month - 1
                        prev_year = today.year
                    try:
                        last_payday = today.replace(
                            year=prev_year, month=prev_month, day=payday_day
                        )
                    except ValueError:
                        last_day = (
                            date(prev_year, prev_month + 1, 1) - timedelta(days=1)
                        ).day
                        last_payday = today.replace(
                            year=prev_year,
                            month=prev_month,
                            day=min(payday_day, last_day),
                        )
                if last_payday.month == 1:
                    prev_cycle_month = 12
                    prev_cycle_year = last_payday.year - 1
                else:
                    prev_cycle_month = last_payday.month - 1
                    prev_cycle_year = last_payday.year
                try:
                    cycle_start = last_payday.replace(
                        year=prev_cycle_year, month=prev_cycle_month, day=payday_day
                    )
                except ValueError:
                    last_day = (
                        date(prev_cycle_year, prev_cycle_month + 1, 1)
                        - timedelta(days=1)
                    ).day
                    cycle_start = last_payday.replace(
                        year=prev_cycle_year,
                        month=prev_cycle_month,
                        day=min(payday_day, last_day),
                    )
                cycle_end = last_payday
            else:
                cycle_start = today - timedelta(days=60)
                cycle_end = today - timedelta(days=30)
            since = cycle_start.isoformat() + "T00:00:00Z"
            before = cycle_end.isoformat() + "T00:00:00Z"
            txns = monzo_service.get_all_transactions(
                account_id, since=since, before=before
            )
            bills_pot_account_id = None
            for txn in txns:
                metadata = txn.get("metadata", {})
                if (
                    "pot_account_id" in metadata
                    and metadata.get("pot_id") == bills_pot["id"]
                ):
                    bills_pot_account_id = metadata["pot_account_id"]
                    break
            outgoings = 0.0
            if bills_pot_account_id:
                try:
                    pot_txns = monzo_service.get_all_transactions(
                        bills_pot_account_id, since=since, before=before
                    )
                    for txn in pot_txns:
                        if txn.get("amount", 0) < 0:
                            outgoings += abs(txn["amount"]) / 100.0
                            running_total += abs(txn["amount"]) / 100.0
                            bills_transactions.append({
                                "date": txn.get("created"),
                                "description": txn.get("description", txn.get("name", "")),
                                "amount": txn.get("amount", 0) / 100.0,
                                "running_total": running_total
                            })
                except Exception as e:
                    for txn in txns:
                        if (
                            txn.get("pot_id") == bills_pot["id"]
                            and txn.get("amount", 0) < 0
                        ):
                            outgoings += abs(txn["amount"]) / 100.0
                            running_total += abs(txn["amount"]) / 100.0
                            bills_transactions.append({
                                "date": txn.get("created"),
                                "description": txn.get("description", txn.get("name", "")),
                                "amount": txn.get("amount", 0) / 100.0,
                                "running_total": running_total
                            })
            else:
                for txn in txns:
                    if (
                        txn.get("pot_id") == bills_pot["id"]
                        and txn.get("amount", 0) < 0
                    ):
                        outgoings += abs(txn["amount"]) / 100.0
                        running_total += abs(txn["amount"]) / 100.0
                        bills_transactions.append({
                            "date": txn.get("created"),
                            "description": txn.get("description", txn.get("name", "")),
                            "amount": txn.get("amount", 0) / 100.0,
                            "running_total": running_total
                        })
            bills_topup = max(0, outgoings - bills_balance)
            bills_calculation = {
                "pot_name": bills_pot_name,
                "current_balance": bills_balance,
                "outgoings": outgoings,
                "topup_needed": bills_topup,
                "new_balance": bills_balance + bills_topup,
                "cycle_start": cycle_start.isoformat(),
                "cycle_end": cycle_end.isoformat(),
                "bills_transactions": bills_transactions,
            }
            # Cap bills_topup at available simulated_balance
            if bills_topup > simulated_balance:
                bills_topup = simulated_balance
                simulated_balance = 0.0
            else:
                simulated_balance -= bills_topup
            # Update simulated_pot_balances for bills pot after topup
            if simulated_pot_balances is not None and bills_pot_name:
                simulated_pot_balances[bills_pot_name] = get_pot_balance(bills_pot_name) + bills_topup
    allocations = {}
    allocation_details = {}
    if allocation_strategy == "free_selection":
        if destination_pots:
            total_percent = sum(
                info["amount"]
                for name, info in destination_pots.items()
                if info["is_percent"] and name in pot_map
            )
            total_fixed = sum(
                info["amount"]
                for name, info in destination_pots.items()
                if not info["is_percent"] and name in pot_map
            )
            for pot_name, info in destination_pots.items():
                if (
                    pot_name == source_pot
                    or pot_name == bills_pot_name
                    or pot_name not in pot_map
                ):
                    continue
                if info["is_percent"]:
                    amt = (info["amount"] / 100.0) * simulated_balance
                else:
                    amt = info["amount"]
                allocations[pot_name] = amt
                allocation_details[pot_name] = {
                    "amount": amt,
                    "type": "percentage" if info["is_percent"] else "fixed",
                    "original_value": info["amount"],
                }
                # Update simulated_pot_balances for each destination pot
                if simulated_pot_balances is not None:
                    simulated_pot_balances[pot_name] = get_pot_balance(pot_name) + amt
            total_alloc = sum(allocations.values())
            if total_alloc > simulated_balance:
                scale = simulated_balance / total_alloc
                for pot_name in allocations:
                    allocations[pot_name] *= scale
                    allocation_details[pot_name]["amount"] = allocations[pot_name]
                    allocation_details[pot_name]["scaled"] = True
                    # Update simulated_pot_balances for scaled allocations
                    if simulated_pot_balances is not None:
                        simulated_pot_balances[pot_name] = get_pot_balance(pot_name) + allocations[pot_name]
    elif allocation_strategy in ["all_goals", "priority_goals"]:
        pots_with_goals = [
            pot
            for pot in active_pots
            if pot.get("goal_amount")
            and pot["name"] != source_pot
            and pot["name"] != bills_pot_name
        ]
        if allocation_strategy == "priority_goals" and priority_pots:
            for pot_name in priority_pots:
                if pot_name in [p["name"] for p in pots_with_goals]:
                    pot = pot_map.get(pot_name)
                    if pot and pot.get("goal_amount"):
                        current_balance = get_pot_balance(pot_name)
                        needed = (pot["goal_amount"] - current_balance * 100) / 100.0
                        amt = min(needed, simulated_balance)
                        if amt > 0:
                            allocations[pot_name] = amt
                            simulated_balance -= amt
                            allocation_details[pot_name] = {
                                "amount": amt,
                                "type": "priority_goal",
                                "goal_amount": pot["goal_amount"] / 100.0,
                                "current_balance": current_balance,
                                "needed": needed,
                            }
                            # Update simulated_pot_balances for this pot
                            if simulated_pot_balances is not None:
                                simulated_pot_balances[pot_name] = get_pot_balance(pot_name) + amt
        remaining_pots = [p for p in pots_with_goals if p["name"] not in allocations]
        if remaining_pots:
            if goal_allocation_method == "even":
                per_pot = simulated_balance / len(remaining_pots)
                for pot in remaining_pots:
                    current_balance = get_pot_balance(pot["name"])
                    needed = (pot["goal_amount"] - current_balance * 100) / 100.0
                    amt = min(per_pot, needed)
                    allocations[pot["name"]] = max(0, amt)
                    allocation_details[pot["name"]] = {
                        "amount": amt,
                        "type": "goal_even",
                        "goal_amount": pot["goal_amount"] / 100.0,
                        "current_balance": current_balance,
                        "needed": needed,
                    }
                    # Update simulated_pot_balances for this pot
                    if simulated_pot_balances is not None:
                        simulated_pot_balances[pot["name"]] = get_pot_balance(pot["name"]) + amt
            elif goal_allocation_method == "relative":
                needs = {}
                for pot in remaining_pots:
                    current_balance = get_pot_balance(pot["name"])
                    needs[pot["name"]] = max(
                        0, (pot["goal_amount"] - current_balance * 100) / 100.0
                    )
                total_needed = sum(needs.values())
                if total_needed > 0:
                    # First, top up pots that are within £20 of their goal
                    pots_to_remove = []
                    for pot in remaining_pots:
                        pot_name = pot["name"]
                        current_balance = get_pot_balance(pot_name)
                        goal_amount = pot["goal_amount"] / 100.0
                        remaining_needed = goal_amount - current_balance
                        # If remaining amount is under £20 and we have enough simulated balance
                        if 0 < remaining_needed <= 20.0 and remaining_needed <= simulated_balance:
                            allocations[pot_name] = remaining_needed
                            simulated_balance -= remaining_needed
                            pots_to_remove.append(pot_name)
                            allocation_details[pot_name] = {
                                "amount": remaining_needed,
                                "type": "goal_relative_topped_up",
                                "goal_amount": goal_amount,
                                "current_balance": current_balance,
                                "needed": remaining_needed,
                                "topup_amount": remaining_needed,
                            }
                            # Update simulated_pot_balances for this pot
                            if simulated_pot_balances is not None:
                                simulated_pot_balances[pot_name] = get_pot_balance(pot_name) + remaining_needed
                    # Remove topped up pots from remaining pots for relative distribution
                    remaining_pots = [
                        pot for pot in remaining_pots 
                        if pot["name"] not in pots_to_remove
                    ]
                    # Now do relative distribution with remaining pots and balance
                    if remaining_pots:
                        needs = {}
                        for pot in remaining_pots:
                            current_balance = get_pot_balance(pot["name"])
                            needs[pot["name"]] = max(
                                0, (pot["goal_amount"] - current_balance * 100) / 100.0
                            )
                        total_needed = sum(needs.values())
                        if total_needed > 0:
                            max_per_pot = simulated_balance * 0.20  # 20% maximum per pot
                            for pot in remaining_pots:
                                pot_name = pot["name"]
                                share = needs[pot_name] / total_needed
                                amt = share * simulated_balance
                                amt = min(amt, needs[pot_name], max_per_pot)  # Cap at 20% of simulated balance
                                allocations[pot_name] = max(0, amt)
                                current_balance = get_pot_balance(pot_name)
                                allocation_details[pot_name] = {
                                    "amount": amt,
                                    "type": "goal_relative",
                                    "goal_amount": pot["goal_amount"] / 100.0,
                                    "current_balance": current_balance,
                                    "needed": needs[pot_name],
                                    "share_percentage": share * 100,
                                    "max_cap": max_per_pot,
                                    "capped": amt == max_per_pot,
                                }
                                # Update simulated_pot_balances for this pot
                                if simulated_pot_balances is not None:
                                    simulated_pot_balances[pot_name] = get_pot_balance(pot_name) + amt
    total_allocated = sum(allocations.values())
    # Check flex account balance and adjust remaining balance for savings pot
    accounts = monzo_service.get_accounts()
    flex_account = None
    for account in accounts:
        if account.get("type") == "uk_monzo_flex":
            flex_account = account
            break
    
    flex_account_balance = 0.0
    if flex_account:
        try:
            flex_account_balance = monzo_service.get_balance(flex_account["id"]).get("balance", 0) / 100.0
        except:
            pass
    
    if flex_account_balance < 0:
        # If flex account is negative, leave 20% of remaining balance in source pot
        buffer_amount = simulated_balance * 0.20
        simulated_balance -= buffer_amount
        # Add buffer to allocation details for display
        allocation_details["source_pot_buffer"] = {
            "amount": buffer_amount,
            "type": "flex_account_buffer",
            "reason": f"Flex account balance negative (£{flex_account_balance:.2f})",
        }
    # Calculate remaining balance for savings pot
    remaining_balance = simulated_balance
    if savings_pot_name and remaining_balance > 0:
        allocations[savings_pot_name] = remaining_balance
        allocation_details[savings_pot_name] = {
            "amount": remaining_balance,
            "type": "savings_pot",
            "remaining_balance": remaining_balance,
        }
        total_allocated += remaining_balance
        # Update simulated_pot_balances for savings pot
        if simulated_pot_balances is not None:
            simulated_pot_balances[savings_pot_name] = get_pot_balance(savings_pot_name) + remaining_balance
    # Store the original simulated balance before deductions for display
    original_simulated_balance = simulated_balance + bills_topup + total_allocated
    # Calculate final source balance correctly
    final_source_balance = original_simulated_balance - bills_topup - total_allocated
    result = {
        "status": "dry_run_success",
        "enabled": True,
        "message": f"DRY RUN: Would distribute £{total_allocated:.2f} from {source_pot}",
        "source_pot": {
            "name": source_pot,
            "original_balance": original_balance,
            "sweep_adjustment": 0.0,  # Set by combined dry run if sweep occurred
            "simulated_addition": simulated_addition,
            "simulated_balance": original_simulated_balance,
            "bills_topup": bills_topup,
            "total_allocated": total_allocated,
            "final_balance": final_source_balance,
        },
        "bills_calculation": bills_calculation,
        "allocations": allocation_details,
        "allocation_strategy": allocation_strategy,
        "enable_bills_pot": enable_bills_pot,
        "savings_pot_name": savings_pot_name if savings_pot_name else None,
    }
    # Create message for display
    message_parts = [
        f"DRY RUN: Would distribute £{total_allocated:.2f} from '{source_pot}'"
    ]
    message_parts.append(
        f"Source pot: £{original_balance:.2f} +£{simulated_addition:.2f} → £{original_simulated_balance:.2f} (after -£{bills_topup:.2f}, -£{total_allocated:.2f})"
    )
    if bills_calculation:
        message_parts.append(f"Bills pot '{bills_pot_name}': +£{bills_topup:.2f}")
    if allocations:
        allocation_list = [
            f"{name} (£{amt:.2f})" for name, amt in allocations.items() if amt > 0.01
        ]
        message_parts.append(f"Allocations: {', '.join(allocation_list)}")
    if "source_pot_buffer" in allocation_details:
        buffer_info = allocation_details["source_pot_buffer"]
        message_parts.append(f"Source pot buffer: +£{buffer_info['amount']:.2f} ({buffer_info['reason']})")
    if savings_pot_name and remaining_balance > 0:
        message_parts.append(f"Savings pot '{savings_pot_name}': +£{remaining_balance:.2f}")
    return (
        True,
        {
            "success": True,
            "task_name": "Autosorter (Dry Run)",
            "message": " | ".join(message_parts),
            "home_url": "/",
        },
        result,
    )


def run_and_record_autosorter(context_flags=None):
    """Run autosorter, normalize result, save history, and return result.
    Args:
        context_flags: Optional dict of extra flags (e.g., manual_execution, startup_run)
    Returns:
        Tuple: (success, context, error)
    """
    start = time.time()
    success, context, error = execute_autosorter()
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
        "task_name": context.get("task_name", "Autosorter"),
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
    save_task_history("autosorter", result, success)
    metrics_service.record("autosorter", success, duration, error)
    return success, context, error
