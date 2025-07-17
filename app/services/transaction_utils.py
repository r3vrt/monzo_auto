from datetime import datetime, timedelta

def batch_fetch_transactions(monzo_service, account_id: str, since: str, before: str, batch_days: int = 10) -> list[dict]:
    """
    Fetch transactions in batches to avoid API/network timeouts.
    Args:
        monzo_service: An instance of MonzoService.
        account_id (str): The account ID to fetch transactions for.
        since (str): RFC3339 start timestamp (inclusive).
        before (str): RFC3339 end timestamp (exclusive).
        batch_days (int): Number of days per batch.
    Returns:
        List of transaction dicts for the account in the given range.
    """
    # Debug: print type and value of batch_days
    print(f"[DEBUG] batch_fetch_transactions called with batch_days={batch_days} (type={type(batch_days)})")
    # Ensure batch_days is always an integer
    batch_days = int(batch_days)
    all_txns = []
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
    current_start = since_dt
    while current_start < before_dt:
        current_end = min(current_start + timedelta(days=batch_days), before_dt)
        batch_since = current_start.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        batch_before = current_end.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[DEBUG] Calling get_all_transactions with account_id={account_id} (type={type(account_id)}), since={batch_since} (type={type(batch_since)}), before={batch_before} (type={type(batch_before)})")
        try:
            txns = monzo_service.get_all_transactions(account_id, since=batch_since, before=batch_before)
            print(f"[DEBUG] get_all_transactions returned {len(txns)} transactions")
            all_txns.extend(txns)
        except Exception as e:
            import traceback
            print(f"[ERROR] Exception in get_all_transactions: {e}")
            traceback.print_exc()
        current_start = current_end
    return all_txns 