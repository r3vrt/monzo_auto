"""Dashboard service for business logic related to the overview page."""

from typing import Any, Dict, List, Tuple

from app.services.monzo_service import MonzoService
from app.services.database_service import db_service


def get_dashboard_overview() -> Tuple[List[Dict[str, Any]], Dict[str, Any], float, int]:
    """Prepare dashboard overview data: account summaries, user info, total balance, and account count.

    Returns:
        Tuple containing:
            - account_summaries: List of account summary dicts
            - user_info: Dict with user info
            - total_balance: float
            - account_count: int
    Raises:
        Exception: If MonzoService fails or accounts cannot be fetched.
    """
    monzo_service = MonzoService()
    accounts = monzo_service.get_accounts()
    user_info = monzo_service.whoami()
    
    # Load selected account IDs and custom names from database
    selected_ids = db_service.get_setting("selected_account_ids", [])
    account_names = db_service.get_setting("account_names", {})
    
    # Filter accounts if selection is not empty
    if selected_ids:
        accounts = [a for a in accounts if a["id"] in selected_ids]
    
    # Calculate total balance and prepare summaries
    total_balance = 0.0
    account_summaries = []
    
    for account in accounts:
        try:
            balance_info = monzo_service.get_balance(account["id"])
            balance = balance_info.get("balance", 0) / 100.0  # Convert from pence to pounds
            spend_today = balance_info.get("spend_today", 0) / 100.0
            total_balance += balance
            
            # Use custom name if available, otherwise use Monzo name
            display_name = account_names.get(account["id"], account.get("name", "Unknown"))
            
            account_summary = {
                "id": account["id"],
                "name": display_name,
                "type": account.get("type", "Unknown"),
                "currency": account.get("currency", "GBP"),
                "balance": balance,
                "balance_formatted": f"£{balance:.2f}",
                "spend_today": spend_today,
            }
            account_summaries.append(account_summary)
        except Exception as e:
            # Skip accounts that can't be loaded
            continue
    
    return account_summaries, user_info, total_balance, len(account_summaries)
