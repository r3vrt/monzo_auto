"""Transaction service for business logic related to transactions sync and formatting."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from app.services.account_utils import get_selected_account_ids
from app.services.monzo_service import MonzoService
from app.database import get_db_session, Transaction

def get_transactions_for_selected_accounts(
    since: str, before: str
) -> Tuple[Dict[str, List[dict]], Dict[str, dict], List[str]]:
    """Fetch and format transactions for all selected accounts within a date range, using the database as the source of truth."""
    session = get_db_session()
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        raise Exception("No accounts selected.")
    # all_accounts is still fetched from MonzoService for account metadata
    monzo_service = MonzoService()
    all_accounts = {
        a["id"]: a for a in monzo_service.get_accounts() if a["id"] in selected_ids
    }
    account_transactions = {}
    for account_id in selected_ids:
        try:
            txns = (
                session.query(Transaction)
                .filter(
                    Transaction.account_id == account_id,
                    Transaction.created >= since,
                    Transaction.created < before,
                )
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
            account_transactions[account_id] = transactions
        except Exception:
            account_transactions[account_id] = []
    session.close()
    return account_transactions, all_accounts, selected_ids
