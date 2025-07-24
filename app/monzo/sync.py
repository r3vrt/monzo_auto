"""
Monzo sync module for account data synchronization.

This module handles syncing of accounts, pots, and transactions from Monzo.
It uses transaction IDs for incremental syncs, which is more reliable than timestamps.

Key Features:
- First-time sync: Uses date-based windows to fetch historical data
- Incremental sync: Uses transaction ID as "since" parameter for reliable syncing
- Automatic token refresh and error handling
- Integration with automation system
"""

import ast
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_

from app.automation.integration import AutomationIntegration
from app.models import Account, BillsPotTransaction, Pot, Transaction, User

logger = logging.getLogger(__name__)

# Placeholder for process-level timeout (for future use)
# import signal
# class TimeoutException(Exception): pass
# def handler(signum, frame): raise TimeoutException()
# signal.signal(signal.SIGALRM, handler)


def sync_account_data(db, user_id: int, account_id: str, monzo: Any) -> None:
    """
    Sync Monzo account data (account, pots, transactions) for a user.
    Handles first-time and incremental sync with window reduction and timeout.
    Args:
        db: SQLAlchemy session
        user_id (int): User ID
        account_id (str): Monzo account ID
        monzo (MonzoClient): Authenticated MonzoClient instance
    """
    # Get the monzo_user_id from the database user
    # user_id could be either the database user.id (int) or monzo_user_id (str)
    if isinstance(user_id, int):
        # user_id is the database user.id
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            logger.error(f"[SYNC] User with id {user_id} not found")
            return
        user_id_str = user.monzo_user_id
    else:
        # user_id is already the monzo_user_id
        user_id_str = user_id

    # Fetch account details
    accounts = monzo.get_accounts()
    acc = next(
        (a for a in accounts if a.id == account_id and not getattr(a, "closed", False)),
        None,
    )
    if acc:
        db_acc = db.query(Account).filter_by(id=account_id, user_id=user_id_str).first()
        if db_acc:
            db_acc.description = acc.description
            db_acc.type = acc.type
            db_acc.closed = int(acc.closed)
            db_acc.updated_at = datetime.now(timezone.utc)
        else:
            db_acc = Account(
                id=acc.id,
                user_id=user_id_str,
                description=acc.description,
                type=acc.type,
                created=acc.created,
                closed=int(acc.closed),
                updated_at=datetime.now(timezone.utc),
                is_active=True,
            )
            db.add(db_acc)
    else:
        # If the account is closed, skip syncing
        return
    # Fetch pots
    pots = monzo.get_pots(account_id)
    for pot in pots:
        if getattr(pot, "deleted", False):
            continue  # Skip deleted pots
        db_pot = db.query(Pot).filter_by(id=pot.id, user_id=user_id_str).first()
        if db_pot:
            db_pot.name = pot.name
            db_pot.style = getattr(pot, "style", None)
            db_pot.balance = pot.balance
            db_pot.currency = pot.currency
            db_pot.created = pot.created
            db_pot.updated = pot.updated
            db_pot.deleted = 0
            db_pot.pot_current_id = getattr(pot, "pot_current_id", None)
            # Sync goal_amount from API to goal field in database
            goal_amount = getattr(pot, "goal_amount", None)
            if goal_amount is not None:
                db_pot.goal = goal_amount
        else:
            # Get goal_amount from API
            goal_amount = getattr(pot, "goal_amount", None)
            db_pot = Pot(
                id=pot.id,
                account_id=account_id,
                user_id=user_id_str,
                name=pot.name,
                style=getattr(pot, "style", None),
                balance=pot.balance,
                currency=pot.currency,
                created=pot.created,
                updated=pot.updated,
                deleted=0,
                pot_current_id=getattr(pot, "pot_current_id", None),
                goal=goal_amount if goal_amount is not None else 0,
            )
            db.add(db_pot)
    # Fetch transactions
    now = datetime.now(timezone.utc)

    # Check if we have any existing transactions to determine if this is first-time sync
    latest_txn = (
        db.query(Transaction)
        .filter_by(account_id=account_id, user_id=user_id_str)
        .order_by(Transaction.id.desc())
        .first()
    )
    first_time = latest_txn is None

    if first_time:
        logger.info(
            f"[SYNC] No existing transactions for account {account_id}, performing first-time sync"
        )
    else:
        logger.info(
            f"[SYNC] Found existing transactions for account {account_id}, latest transaction ID: {latest_txn.id}"
        )

    if first_time:
        # For first-time sync, we need to use a date-based approach since we don't have a transaction ID
        window_sizes = [89, 50, 30, 10]
        for days in window_sizes:
            since = now - timedelta(days=days)
            try:
                # signal.alarm(10)  # Uncomment for process-level timeout (10s)
                now_iso = now.isoformat()
                logger.info(
                    f"[SYNC] Pulling transactions for account {account_id} since {since.isoformat()} before {now_iso}"
                )
                transactions = monzo.client._get_all_transactions(
                    account_id, since=since.isoformat(), before=now_iso
                )
                logger.info(
                    f"[SYNC] Pulled {len(transactions)} transactions for account {account_id}"
                )
                if transactions:
                    logger.info(
                        f"[SYNC] First txn: {transactions[0].id} {transactions[0].created}, Last txn: {transactions[-1].id} {transactions[-1].created}"
                    )

                    # Check how many of these transactions already exist in the database
                    existing_count = 0
                    new_transactions = []
                    for txn in transactions:
                        if (
                            db.query(Transaction)
                            .filter_by(id=txn.id, user_id=user_id_str)
                            .first()
                        ):
                            existing_count += 1
                        else:
                            new_transactions.append(txn)

                    logger.info(
                        f"[SYNC] {existing_count} out of {len(transactions)} transactions already exist in database"
                    )

                    # Only process new transactions
                    if new_transactions:
                        for txn in new_transactions:
                            # Extract pot_account_id from metadata if available
                            pot_current_id = None
                            if hasattr(txn, "metadata") and txn.metadata:
                                try:
                                    if isinstance(txn.metadata, str):
                                        metadata = ast.literal_eval(txn.metadata)
                                    else:
                                        metadata = txn.metadata
                                    pot_current_id = metadata.get("pot_account_id")
                                except (ValueError, SyntaxError, AttributeError):
                                    pass

                            # Create new transaction
                            db_txn = Transaction(
                                id=txn.id,
                                account_id=account_id,
                                user_id=user_id_str,
                                created=txn.created,
                                amount=txn.amount,
                                currency=txn.currency,
                                description=txn.description,
                                category=getattr(txn, "category", None),
                                merchant=getattr(txn, "merchant", None),
                                notes=getattr(txn, "notes", None),
                                is_load=int(getattr(txn, "is_load", False)),
                                settled=getattr(txn, "settled", None),
                                txn_metadata=str(getattr(txn, "metadata", "")),
                                pot_current_id=pot_current_id,
                            )
                            db.add(db_txn)
                            logger.debug(f"[SYNC] Added new transaction: {txn.id}")

                        # Commit only new transactions
                        db.commit()
                        logger.info(
                            f"[SYNC] Committed {len(new_transactions)} new transactions to database"
                        )
                    else:
                        logger.info("[SYNC] No new transactions to commit")

                # If we found transactions, we're done with first-time sync
                if transactions:
                    logger.info(f"First-time sync succeeded for {days} days window.")

                    # Trigger automation after successful first-time sync
                    try:
                        automation = AutomationIntegration(db, monzo)
                        automation_results = automation.execute_post_sync_automation(
                            user_id_str, account_id
                        )
                        logger.info(
                            f"[SYNC] Automation results for first-time sync account {account_id}: {automation_results}"
                        )
                    except Exception as automation_error:
                        logger.error(
                            f"[SYNC] Automation failed for first-time sync account {account_id}: {automation_error}"
                        )
                        # Don't fail the sync if automation fails

                    break
                else:
                    logger.info(
                        f"First-time sync completed for {days} days window but no transactions found. Trying next window."
                    )
            except Exception as e:
                # signal.alarm(0)
                logger.warning(f"Sync failed for {days} days window: {e}")
                continue
        else:
            logger.error("Failed to sync after all retries.")
    else:
        # Incremental sync - use the latest transaction ID for more reliable syncing
        latest_txn_id = latest_txn.id
        logger.info(
            f"[SYNC] Using latest transaction ID for incremental sync: {latest_txn_id}"
        )
        try:
            # signal.alarm(10)  # Uncomment for process-level timeout (10s)
            logger.info(
                f"[SYNC] Pulling transactions for account {account_id} since transaction ID: {latest_txn_id}"
            )
            transactions = monzo.client._get_all_transactions(
                account_id, since=latest_txn_id
            )
            logger.info(
                f"[SYNC] Pulled {len(transactions)} transactions for account {account_id}"
            )
            if transactions:
                logger.info(
                    f"[SYNC] First txn: {transactions[0].id} {transactions[0].created}, Last txn: {transactions[-1].id} {transactions[-1].created}"
                )

                # Check how many of these transactions already exist in the database
                existing_count = 0
                new_transactions = []
                for txn in transactions:
                    if (
                        db.query(Transaction)
                        .filter_by(id=txn.id, user_id=user_id_str)
                        .first()
                    ):
                        existing_count += 1
                    else:
                        new_transactions.append(txn)

                logger.info(
                    f"[SYNC] {existing_count} out of {len(transactions)} transactions already exist in database"
                )

                # Only process new transactions
                if new_transactions:
                    for txn in new_transactions:
                        # Extract pot_account_id from metadata if available
                        pot_current_id = None
                        if hasattr(txn, "metadata") and txn.metadata:
                            try:
                                if isinstance(txn.metadata, str):
                                    metadata = ast.literal_eval(txn.metadata)
                                else:
                                    metadata = txn.metadata
                                pot_current_id = metadata.get("pot_account_id")
                            except (ValueError, SyntaxError, AttributeError):
                                pass

                        # Create new transaction
                        db_txn = Transaction(
                            id=txn.id,
                            account_id=account_id,
                            user_id=user_id_str,
                            created=txn.created,
                            amount=txn.amount,
                            currency=txn.currency,
                            description=txn.description,
                            category=getattr(txn, "category", None),
                            merchant=getattr(txn, "merchant", None),
                            notes=getattr(txn, "notes", None),
                            is_load=int(getattr(txn, "is_load", False)),
                            settled=getattr(txn, "settled", None),
                            txn_metadata=str(getattr(txn, "metadata", "")),
                            pot_current_id=pot_current_id,
                        )
                        db.add(db_txn)
                        logger.debug(f"[SYNC] Added new transaction: {txn.id}")

                    # Commit only new transactions
                    db.commit()
                    logger.info(
                        f"[SYNC] Committed {len(new_transactions)} new transactions to database"
                    )
                else:
                    logger.info("[SYNC] No new transactions to commit")

            logger.info(f"Incremental sync completed for account {account_id}.")

            # Trigger automation after successful sync
            try:
                automation = AutomationIntegration(db, monzo)
                automation_results = automation.execute_post_sync_automation(
                    user_id_str, account_id
                )
                logger.info(
                    f"[SYNC] Automation results for account {account_id}: {automation_results}"
                )
            except Exception as automation_error:
                logger.error(
                    f"[SYNC] Automation failed for account {account_id}: {automation_error}"
                )
                # Don't fail the sync if automation fails

        except Exception as e:
            # signal.alarm(0)
            logger.error(f"Incremental sync failed: {e}")
            # Don't update sync metadata on failure to avoid losing sync state


def sync_bills_pot_transactions(
    db, user_id: str, bills_pot_id: str, monzo: Any
) -> bool:
    """
    Sync transactions specifically for the bills pot using pot_account_id.
    This ensures we have complete and accurate bills pot transaction data.
    """
    try:
        logger.info(f"[SYNC] Starting bills pot transaction sync for user {user_id}")

        # Get the bills pot
        bills_pot = db.query(Pot).filter_by(id=bills_pot_id, user_id=user_id).first()
        if not bills_pot:
            logger.error(
                f"[SYNC] Bills pot {bills_pot_id} not found for user {user_id}"
            )
            return False

        # Get the pot_account_id for the bills pot
        pot_account_id = None
        if bills_pot.pot_current_id:
            pot_account_id = bills_pot.pot_current_id
            logger.info(f"[SYNC] Using pot_account_id from pot: {pot_account_id}")
        else:
            # Fallback: try to find pot_account_id from existing transactions for this pot
            pot_transaction = (
                db.query(Transaction)
                .filter(
                    and_(
                        Transaction.description == bills_pot_id,
                        Transaction.pot_current_id.isnot(None),
                    )
                )
                .first()
            )
            if pot_transaction:
                pot_account_id = pot_transaction.pot_current_id
                logger.info(
                    f"[SYNC] Found pot_account_id from transaction: {pot_account_id}"
                )
            else:
                logger.error(
                    f"[SYNC] No pot_account_id found for bills pot {bills_pot_id}"
                )
                return False

        # Get transactions directly from Monzo using pot_account_id
        logger.info(
            f"[SYNC] Fetching transactions from Monzo for pot_account_id: {pot_account_id}"
        )

        # Check if we have any existing bills pot transactions to determine if this is first-time sync
        latest_bills_txn = (
            db.query(BillsPotTransaction)
            .filter_by(bills_pot_id=bills_pot_id)
            .order_by(BillsPotTransaction.id.desc())
            .first()
        )
        first_time = latest_bills_txn is None

        if first_time:
            logger.info(
                f"[SYNC] No existing bills pot transactions for pot {bills_pot_id}, performing first-time sync"
            )
            # Get all transactions for the bills pot (no date limit for first-time sync)
            transactions = monzo.client._get_all_transactions(account_id=pot_account_id)
        else:
            logger.info(
                f"[SYNC] Found existing bills pot transactions, latest transaction ID: {latest_bills_txn.id}"
            )
            # Incremental sync - use the latest transaction ID
            latest_txn_id = latest_bills_txn.id
            transactions = monzo.client._get_all_transactions(
                account_id=pot_account_id, since=latest_txn_id
            )

        logger.info(
            f"[SYNC] Found {len(transactions)} transactions from Monzo for bills pot"
        )

        # Process each transaction
        new_transactions = 0
        updated_transactions = 0

        for txn in transactions:
            # Check if transaction already exists in bills pot table
            existing_txn = db.query(BillsPotTransaction).filter_by(id=txn.id).first()

            # Determine transaction type and if it's a pot withdrawal
            transaction_type = "other"
            is_pot_withdrawal = False

            # Check if it's a subscription
            if any(
                keyword in txn.description.upper()
                for keyword in [
                    "NETFLIX",
                    "DISNEY",
                    "CRUNCHYROLL",
                    "CURSOR",
                    "WODIFY",
                    "ARISTOS",
                ]
            ):
                transaction_type = "subscription"

            # Check if it's a pot transfer
            elif "pot_" in txn.description:
                transaction_type = "pot_transfer"

            # Check if it's an actual pot withdrawal (has pot_withdrawal_id in metadata)
            try:
                if hasattr(txn, "metadata") and txn.metadata:
                    if isinstance(txn.metadata, str):
                        metadata = ast.literal_eval(txn.metadata)
                    else:
                        metadata = txn.metadata
                    if metadata.get("pot_withdrawal_id"):
                        is_pot_withdrawal = True
            except (ValueError, SyntaxError, AttributeError):
                pass

            if existing_txn:
                # Update existing transaction if needed
                if (
                    existing_txn.amount != txn.amount
                    or existing_txn.description != txn.description
                    or existing_txn.transaction_type != transaction_type
                    or existing_txn.is_pot_withdrawal != is_pot_withdrawal
                ):

                    existing_txn.amount = txn.amount
                    existing_txn.description = txn.description
                    existing_txn.category = getattr(txn, "category", None)
                    existing_txn.merchant = getattr(txn, "merchant", None)
                    existing_txn.notes = getattr(txn, "notes", None)
                    existing_txn.is_load = int(getattr(txn, "is_load", False))
                    existing_txn.settled = getattr(txn, "settled", None)
                    existing_txn.txn_metadata = str(getattr(txn, "metadata", ""))
                    existing_txn.transaction_type = transaction_type
                    existing_txn.is_pot_withdrawal = is_pot_withdrawal

                    updated_transactions += 1
            else:
                # Create new bills pot transaction
                db_txn = BillsPotTransaction(
                    id=txn.id,
                    bills_pot_id=bills_pot_id,
                    user_id=user_id,
                    created=txn.created,
                    amount=txn.amount,
                    currency=txn.currency,
                    description=txn.description,
                    category=getattr(txn, "category", None),
                    merchant=getattr(txn, "merchant", None),
                    notes=getattr(txn, "notes", None),
                    is_load=int(getattr(txn, "is_load", False)),
                    settled=getattr(txn, "settled", None),
                    txn_metadata=str(getattr(txn, "metadata", "")),
                    pot_account_id=pot_account_id,
                    transaction_type=transaction_type,
                    is_pot_withdrawal=is_pot_withdrawal,
                )
                db.add(db_txn)
                new_transactions += 1

        # Commit changes
        db.commit()

        logger.info(
            f"[SYNC] Bills pot sync completed: {new_transactions} new, {updated_transactions} updated transactions"
        )
        return True

    except Exception as e:
        logger.error(f"[SYNC] Error syncing bills pot transactions: {e}")
        db.rollback()
        return False
