"""Account service for business logic related to accounts and transactions."""

from datetime import datetime
from typing import Any, Dict, List
from flask import current_app

from app.services.monzo_service import MonzoService
from app.services.database_service import db_service
from app.services.account_utils import (
    get_selected_account_ids,
    get_account_names,
    save_selected_account_ids,
    save_account_names,
)


def get_display_accounts() -> List[Dict[str, Any]]:
    """Get accounts for display, filtered by selected IDs and with balances.

    Returns:
        List[Dict[str, Any]]: List of account dicts with balance info.
    Raises:
        Exception: If MonzoService fails or accounts cannot be fetched.
    """
    monzo_service = MonzoService()
    accounts = monzo_service.get_accounts()
    selected_ids = get_selected_account_ids()
    account_names = get_account_names()
    
    if selected_ids:
        accounts = [a for a in accounts if a["id"] in selected_ids]
    
    for account in accounts:
        try:
            balance_data = monzo_service.get_balance(account["id"])
            if isinstance(balance_data, dict):
                account["balance"] = balance_data.get("balance", 0)
            else:
                account["balance"] = balance_data
        except Exception:
            account["balance"] = 0
        # Set display name
        account["name"] = account_names.get(account["id"], account.get("name", "Unknown"))
    
    return accounts


def get_account_transactions_for_display(account_id: str) -> List[Dict[str, Any]]:
    """Get transactions for an account, formatted for display.

    Args:
        account_id (str): The account ID.
    Returns:
        List[Dict[str, Any]]: List of transaction dicts with display fields.
    Raises:
        Exception: If MonzoService fails or transactions cannot be fetched.
    """
    current_app.logger.warning('DEBUG: Entered get_account_transactions_for_display for account_id=%s', account_id)
    selected_ids = get_selected_account_ids()
    if selected_ids and account_id not in selected_ids:
        raise Exception("Account not selected for display.")
    monzo_service = MonzoService()
    transactions = monzo_service.get_transactions(account_id, limit=100)
    
    if transactions:
        current_app.logger.info('DEBUG: First transaction keys: %s', list(transactions[0].keys()))
        current_app.logger.info('DEBUG: First transaction: %r', transactions[0])
        raise Exception('DEBUG: This code path is hit - check logs for transaction structure')
    
    # Get all pots for this account to create a mapping from pot_id to pot_name
    try:
        pots = monzo_service.get_pots(account_id)
        pot_map = {pot.get("id"): pot.get("name", "Unknown Pot") for pot in pots if pot.get("id")}
    except Exception:
        pot_map = {}
    
    for txn in transactions:
        created = txn.get("created")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                txn["created_display"] = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                txn["created_display"] = created
        else:
            txn["created_display"] = ""
        txn["account_id"] = account_id
        
        # Add pot name if transaction has a pot_id
        pot_id = txn.get("pot_id")
        if pot_id and pot_id in pot_map:
            txn["pot_name"] = pot_map[pot_id]
            txn["pot_id_short"] = None
        elif pot_id:
            txn["pot_name"] = "Unknown Pot"
            txn["pot_id_short"] = pot_id[:8]
        else:
            txn["pot_name"] = None
            txn["pot_id_short"] = None
    
    return transactions
