from datetime import datetime, timedelta
from app.services.monzo_service import MonzoService

def batch_fetch_transactions(account_id: str, since: str, before: str, batch_days: int = 10) -> list[dict]:
    """Fetch transactions in batches to avoid API/network timeouts.
    Args:
        account_id (str): The account ID to fetch transactions for.
        since (str): RFC3339 start timestamp (inclusive).
        before (str): RFC3339 end timestamp (exclusive).
        batch_days (int): Number of days per batch.
    Returns:
        List of transaction dicts for the account in the given range.
    """
    all_txns = []
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
    current_start = since_dt
    monzo_service = MonzoService()
    while current_start < before_dt:
        current_end = min(current_start + timedelta(days=batch_days), before_dt)
        # Format as RFC3339 (no microseconds)
        batch_since = current_start.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        batch_before = current_end.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            txns = monzo_service.get_all_transactions(account_id, since=batch_since, before=batch_before)
            all_txns.extend(txns)
        except Exception:
            pass
        current_start = current_end
    return all_txns 