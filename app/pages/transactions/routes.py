"""Transactions routes for transaction-related pages."""

from datetime import datetime, timedelta

from flask import current_app, render_template, request

from app.pages.transactions import bp
from app.services.transaction_service import \
    get_transactions_for_selected_accounts


@bp.route("/sync", methods=["GET", "POST"])
def sync_transactions():
    """Sync transactions for selected accounts, up to 90 days, split by account."""
    try:
        # Calculate 90 days ago and now
        since = (datetime.utcnow() - timedelta(days=89)).replace(
            microsecond=0
        ).isoformat() + "Z"
        before = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        account_transactions, all_accounts, selected_ids = (
            get_transactions_for_selected_accounts(since, before)
        )
        return render_template(
            "pages/transactions/sync.html",
            account_transactions=account_transactions,
            accounts=all_accounts,
            account_ids=selected_ids,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.exception("Failed to sync transactions", extra={"route": "sync_transactions"})
        return render_template(
            "pages/transactions/sync.html",
            account_transactions={},
            accounts={},
            account_ids=[],
            error=str(e),
            home_url="/",
        )
