"""Accounts routes for account-related pages."""

from flask import current_app, render_template

from app.pages.accounts import bp
from app.services.account_service import get_account_transactions_for_display, get_display_accounts
from app.tasks.routes import \
    save_task_history  # Import the save_task_history function


@bp.route("/", methods=["GET"])
def accounts_list():
    """List user accounts."""
    try:
        accounts = get_display_accounts()
        return render_template(
            "pages/accounts/list.html", accounts=accounts, home_url="/"
        )
    except Exception as e:
        current_app.logger.exception("Failed to get accounts", extra={"route": "accounts_list"})
        return render_template(
            "pages/accounts/list.html", accounts=[], error=str(e), home_url="/"
        )


@bp.route("/<account_id>/transactions", methods=["GET"])
def account_transactions(account_id: str):
    """Show transactions for a specific account."""
    try:
        transactions = get_account_transactions_for_display(account_id)
        # Save to task history
        result = {
            "status": "success",
            "message": f"Successfully viewed {len(transactions)} transactions for account {account_id} via transactions page",
            "account_id": account_id,
            "transaction_count": len(transactions),
        }
        save_task_history("transaction_sync", result, True)
        return render_template(
            "pages/accounts/transactions.html",
            account_id=account_id,
            transactions=transactions,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.error(f"Failed to get transactions: {e}")
        return render_template(
            "pages/accounts/transactions.html",
            account_id=account_id,
            transactions=[],
            error=str(e),
            home_url="/",
        )
