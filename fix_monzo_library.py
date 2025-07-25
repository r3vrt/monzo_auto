# Fix for monzo_apy library's _get_all_transactions method
# File: /path/to/monzo/client.py (line ~475)

def _get_all_transactions(self, account_id: str, since: Optional[str] = None, before: Optional[str] = None) -> List[Transaction]:
    """Get all transactions using pagination.

    Args:
        account_id: The account ID
        since: ISO 8601 timestamp to get transactions since
        before: ISO 8601 timestamp to get transactions before

    Returns:
        List of all transactions
    """
    all_transactions = []
    current_since = since
    
    while True:
        params = {"account_id": account_id, "limit": "100"}
        if current_since:
            params["since"] = current_since
        if before:
            params["before"] = before

        response = self._make_request("GET", "/transactions", params=params)
        transactions = [Transaction.from_dict(tx) for tx in response["transactions"]]
        
        if not transactions:
            break
            
        all_transactions.extend(transactions)
        
        # Check if we have more transactions to fetch
        if len(transactions) < 100:
            break
            
        # FIXED: Use the last transaction's timestamp + 1 second for next request
        # This ensures we don't get the same transaction again
        last_transaction = transactions[-1]
        from datetime import datetime, timedelta, timezone
        
        # Add 1 second to avoid getting the same transaction
        next_since = last_transaction.created + timedelta(seconds=1)
        current_since = next_since.isoformat()
    
    return all_transactions 