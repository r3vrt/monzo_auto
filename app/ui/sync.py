"""
Sync UI Routes

Handles sync status and manual sync operations.
"""

from flask import (flash, get_flashed_messages, redirect, render_template,
                   request, url_for)

from app.db import get_db_session
from app.models import Account, Pot, Transaction
from app.monzo.sync import sync_account_data
from app.services.auth_service import get_authenticated_monzo_client
from app.ui import ui_bp


@ui_bp.route("/sync/manual/<account_id>", methods=["POST"])
def manual_sync(account_id):
    """Handle manual sync request for a specific account."""
    with next(get_db_session()) as db:
        acc = db.query(Account).filter_by(id=account_id, is_active=True).first()
        if not acc:
            flash(f"Account {account_id} not found or not active.", "error")
            return redirect(url_for("ui.sync_status"))

        # Get authenticated Monzo client
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            flash("No authenticated user found. Please authenticate.", "error")
            return redirect(url_for("ui.sync_status"))

        try:
            sync_account_data(db, str(acc.user_id), str(acc.id), monzo)
            flash(
                f"Sync successful for account {acc.description or acc.id}.", "success"
            )
        except Exception as e:
            flash(f"Sync failed for account {acc.description or acc.id}: {e}", "error")

    return redirect(url_for("ui.sync_status"))


@ui_bp.route("/sync/status")
def sync_status():
    """
    Display sync status for all active accounts.
    """
    with next(get_db_session()) as db:
        accounts = db.query(Account).filter_by(is_active=True).all()
        sync_info = []
        for acc in accounts:
            # Get latest transaction timestamp as last sync time
            latest_txn = (
                db.query(Transaction)
                .filter_by(account_id=acc.id, user_id=acc.user_id)
                .order_by(Transaction.id.desc())
                .first()
            )
            last_synced_at = latest_txn.created if latest_txn else None

            # Get last 5 transactions
            txns = (
                db.query(Transaction)
                .filter_by(account_id=acc.id, user_id=acc.user_id)
                .order_by(Transaction.created.desc())
                .limit(5)
                .all()
            )
            # Get all pots for this account
            pots = db.query(Pot).filter_by(account_id=acc.id, user_id=acc.user_id).all()
            sync_info.append(
                {
                    "id": acc.id,
                    "name": acc.description,
                    "type": acc.type,
                    "last_synced_at": last_synced_at,
                    "transactions": txns,
                    "pots": pots,
                }
            )

    messages = get_flashed_messages(with_categories=True)
    return render_template("sync/status.html", sync_info=sync_info, messages=messages)
