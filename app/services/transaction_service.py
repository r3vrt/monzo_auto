"""Transaction service for business logic related to transactions sync and formatting."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from app.services.account_utils import get_selected_account_ids
from app.services.monzo_service import MonzoService


def get_transactions_for_selected_accounts(
    since: str, before: str
) -> Tuple[Dict[str, List[dict]], Dict[str, dict], List[str]]:
    """Fetch and format transactions for all selected accounts within a date range.

    Args:
        since (str): ISO8601 string for the earliest transaction to fetch.
        before (str): ISO8601 string for the latest transaction to fetch.
    Returns:
        Tuple containing:
            - account_transactions: Dict[account_id, List[transaction dicts]]
            - all_accounts: Dict[account_id, account dict]
            - selected_ids: List[str]
    Raises:
        Exception: If authentication or fetching fails.
    """
    monzo_service = MonzoService()
    # Test authentication
    test_accounts = monzo_service.get_accounts()
    selected_ids = get_selected_account_ids()
    if not selected_ids:
        raise Exception("No accounts selected.")
    all_accounts = {
        a["id"]: a for a in monzo_service.get_accounts() if a["id"] in selected_ids
    }
    account_transactions = {}
    for account_id in selected_ids:
        try:
            transactions = monzo_service.get_all_transactions(
                account_id, since=since, before=before
            )
        except Exception:
            transactions = []
        # Get all pots for this account to create a mapping from pot_id to pot_name
        try:
            pots = monzo_service.get_pots(account_id)
            pot_map = {pot.get("id"): pot.get("name", "Unknown Pot") for pot in pots if pot.get("id")}
        except Exception:
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
            
            created = txn.get("created")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    txn["created_display"] = dt.strftime("%Y-%m-%d %H:%M")
                    txn["_created_dt"] = dt
                except Exception:
                    txn["created_display"] = created
                    txn["_created_dt"] = created
            else:
                txn["created_display"] = ""
                txn["_created_dt"] = ""
            txn["account_id"] = account_id
        # Sort transactions by _created_dt descending (newest first)
        transactions.sort(key=lambda x: x.get("_created_dt", ""), reverse=True)
        account_transactions[account_id] = transactions
    return account_transactions, all_accounts, selected_ids
