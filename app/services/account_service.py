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
from app.database import get_db_session, Transaction


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
    """Get transactions for an account, formatted for display, using the database as the source of truth."""
    current_app.logger.warning('DEBUG: Entered get_account_transactions_for_display for account_id=%s', account_id)
    selected_ids = get_selected_account_ids()
    if selected_ids and account_id not in selected_ids:
        raise Exception("Account not selected for display.")
    session = get_db_session()
    try:
        txns = (
            session.query(Transaction)
            .filter(Transaction.account_id == account_id)
            .order_by(Transaction.created.desc())
            .all()
        )
        transactions = []
        for txn in txns:
            txn_dict = {
                "id": txn.id,
                "account_id": txn.account_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "description": txn.description,
                "category": txn.category,
                "created": txn.created.isoformat(),
                "settled": txn.settled.isoformat() if txn.settled else None,
                "notes": txn.notes,
                "metadata": txn.metadata_json,
                "last_sync": txn.last_sync.isoformat() if txn.last_sync else None,
            }
            # Add display fields as before
            try:
                dt = txn.created
                txn_dict["created_display"] = dt.strftime("%Y-%m-%d %H:%M")
                txn_dict["_created_dt"] = dt
            except Exception:
                txn_dict["created_display"] = txn.created
                txn_dict["_created_dt"] = txn.created
            transactions.append(txn_dict)
        # Sort transactions by _created_dt descending (newest first)
        transactions.sort(key=lambda x: x.get("_created_dt", ""), reverse=True)
        return transactions
    finally:
        session.close()
