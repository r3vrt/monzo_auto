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
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_

from app.automation.integration import AutomationIntegration
from app.models import Account, BillsPotTransaction, Pot, Transaction, User

logger = logging.getLogger(__name__)

# Timeout handling for API calls using threading (works in background threads)
class TimeoutException(Exception):
    pass

def safe_api_call(api_func, timeout_seconds=30, *args, **kwargs):
    """
    Execute an API call with a timeout to prevent hangs.
    Uses threading instead of signals to work in background threads.
    
    Args:
        api_func: The API function to call
        timeout_seconds: Timeout in seconds (default 30)
        *args, **kwargs: Arguments to pass to the API function
    
    Returns:
        The result of the API call
    
    Raises:
        TimeoutException: If the call times out
    """
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = api_func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout_seconds)
    
    if thread.is_alive():
        logger.error(f"API call timed out after {timeout_seconds} seconds")
        logger.debug(f"[API] Thread is still alive after {timeout_seconds}s timeout - this indicates a hang")
        raise TimeoutException(f"API call timed out after {timeout_seconds} seconds")
    
    if exception[0]:
        logger.debug(f"[API] API call failed with exception: {exception[0]}")
        raise exception[0]
    
    return result[0]


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
    # Ensure we start with a clean transaction state
    try:
        db.rollback()
    except Exception:
        # If rollback fails, it might mean we're already in a clean state
        pass
    
    # Get the monzo_user_id from the database user
    # user_id could be either the database user.id (int) or monzo_user_id (str)
    try:
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
    except Exception as e:
        logger.error(f"[SYNC] Error getting user info: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return

    # Fetch account details
    try:
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
            logger.info(f"[SYNC] Account {account_id} is closed or not found, skipping sync")
            return
    except Exception as e:
        logger.error(f"[SYNC] Error fetching account details: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return
    # Fetch pots
    try:
        pots = monzo.get_pots(account_id)
        logger.info(f"[SYNC] Found {len(pots)} pots for account {account_id}")
        
        for pot in pots:
            if getattr(pot, "deleted", False):
                logger.debug(f"[SYNC] Skipping deleted pot: {pot.id}")
                continue  # Skip deleted pots
                
            try:
                db_pot = db.query(Pot).filter_by(id=pot.id, user_id=user_id_str).first()
                if db_pot:
                    # Update existing pot
                    logger.debug(f"[SYNC] Updating existing pot: {pot.id} - {pot.name}")
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
                    # Create new pot
                    logger.debug(f"[SYNC] Creating new pot: {pot.id} - {pot.name}")
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
                    
            except Exception as pot_error:
                logger.error(f"[SYNC] Error processing pot {pot.id}: {pot_error}")
                # Continue with other pots instead of failing completely
                continue
                
    except Exception as e:
        logger.error(f"[SYNC] Error fetching pots: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return
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
        # For first-time sync, pull all 89 days in one go
        # Start from 89 days ago and pull everything up to now
        start_date = now - timedelta(days=89)
        
        try:
            logger.info(
                f"[SYNC] Pulling transactions for account {account_id} from {start_date.isoformat()} to {now.isoformat()}"
            )
            # Use the fixed library method for pagination
            transactions = safe_api_call(
                lambda: monzo.get_transactions(
                    account_id, 
                    since=start_date.isoformat()
                ),
                timeout_seconds=120
            )
            logger.info(
                f"[SYNC] Pulled {len(transactions)} transactions using fixed library pagination"
            )
            
            # If no transactions returned, we're done
            if not transactions:
                logger.info(f"[SYNC] No transactions found for account {account_id}")
                return
                
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
                
        except TimeoutException as e:
            logger.error(
                f"[SYNC] Error pulling transactions for account {account_id}: {e}"
            )
            # Rollback transaction
            try:
                db.rollback()
                logger.info("[SYNC] Database transaction rolled back after timeout")
            except Exception as rollback_error:
                logger.error(f"[SYNC] Error during rollback: {rollback_error}")
        except Exception as e:
            logger.error(
                f"[SYNC] Error pulling transactions for account {account_id}: {e}"
            )
            # Rollback transaction
            try:
                db.rollback()
                logger.info("[SYNC] Database transaction rolled back after error")
            except Exception as rollback_error:
                logger.error(f"[SYNC] Error during rollback: {rollback_error}")

        logger.info(f"First-time sync completed for account {account_id}.")

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

    else:
        # Incremental sync - use the latest transaction ID for more reliable syncing
        latest_txn_id = latest_txn.id
        logger.info(
            f"[SYNC] Using latest transaction ID for incremental sync: {latest_txn_id}"
        )
        
        # Add detailed diagnostics for debugging device-specific issues
        logger.info(f"[SYNC] Incremental sync: latest txn {latest_txn_id} from {latest_txn.created}")
        

        
        # Add a reasonable time limit to prevent pulling too much historical data
        # Use 3 days as a safety limit for incremental syncs to prevent hangs
        # The limit should be relative to the latest transaction, not today
        latest_txn_date = latest_txn.created
        time_limit = latest_txn_date - timedelta(days=3)
        time_limit_iso = time_limit.isoformat()
        
        # Prevent syncing if the latest transaction is too recent (within last 15 minutes)
        # This prevents rapid-fire API calls that could cause loops
        # Scheduler runs every 10 minutes, so we need at least 15 minutes cooldown
        if (now - latest_txn_date).total_seconds() < 900:  # 15 minutes
            logger.info(f"[SYNC] Latest transaction {latest_txn_id} is too recent (within 15 minutes), skipping sync to prevent loops")
            return
        
        try:
            logger.info(
                f"[SYNC] Pulling transactions for account {account_id} since transaction ID: {latest_txn_id} (with 3-day limit from latest txn: {time_limit_iso})"
            )
            
            # Add debug info about the latest transaction
            days_since_latest = (now - latest_txn_date).days
            logger.info(
                f"[SYNC] Latest transaction date: {latest_txn_date}, days since: {days_since_latest}"
            )
            
            # We don't need the 3-day limit check here since we're looking for NEWER transactions
            # The API call will only return transactions newer than the latest one
            
            # Use timestamp-based sync instead of transaction ID to avoid loops
            # The 'since' parameter with transaction IDs can cause issues if there are no new transactions
            since_timestamp = (latest_txn_date + timedelta(seconds=1)).isoformat()
            logger.info(f"[SYNC] Using timestamp-based sync to avoid loops: since={since_timestamp}")
            
            # Log API call for troubleshooting
            logger.info(f"[SYNC] Calling Monzo API: account {account_id}, since {since_timestamp}")
            
            transactions = safe_api_call(
                lambda: monzo.get_transactions(
                    account_id, since=since_timestamp
                ),
                timeout_seconds=30
            )
            
            # Log response summary for troubleshooting
            if transactions:
                logger.info(f"[SYNC] API response: {len(transactions)} transactions, first: {transactions[0].id}, last: {transactions[-1].id}")
            else:
                logger.info(f"[SYNC] API response: no transactions")
            
            logger.debug(f"[SYNC] Monzo API call completed, received {len(transactions) if transactions else 0} transactions")
            
            # If no transactions returned, log and exit early to prevent hangs
            if not transactions:
                logger.info(f"[SYNC] No new transactions found since {since_timestamp}, sync complete")
                return
            
            # Check if we're getting the same transactions as the latest one (potential loop)
            if transactions and len(transactions) > 0:
                first_txn_id = transactions[0].id
                first_txn_date = transactions[0].created
                
                # Check for ID match (direct loop)
                if first_txn_id == latest_txn_id:
                    logger.warning(f"[SYNC] Potential loop detected - first transaction ID matches latest: {first_txn_id}")
                    logger.info(f"[SYNC] Skipping sync to prevent loop")
                    return
                
                # Check for timestamp issues (transactions older than our since timestamp)
                since_datetime = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
                if first_txn_date <= since_datetime:
                    logger.warning(f"[SYNC] Potential loop detected - first transaction date {first_txn_date} is not after since timestamp {since_datetime}")
                    logger.info(f"[SYNC] Skipping sync to prevent loop")
                    return
                
                # Check if any of these transactions already exist in the database
                existing_count = 0
                for txn in transactions:
                    existing_txn = db.query(Transaction).filter_by(id=txn.id, user_id=user_id_str).first()
                    if existing_txn:
                        existing_count += 1
                
                if existing_count > 0:
                    logger.warning(f"[SYNC] Potential loop detected - {existing_count} out of {len(transactions)} transactions already exist in database")
                    logger.info(f"[SYNC] Skipping sync to prevent loop")
                    return
            
            logger.info(
                f"[SYNC] Raw API response: {len(transactions)} transactions received"
            )
            
            # Filter transactions to only include those newer than the latest transaction
            # and within a reasonable time range (not too old)
            filtered_transactions = [
                txn for txn in transactions 
                if txn.created > latest_txn_date  # Must be newer than latest
            ]
            
            # Additional safety: limit to max 100 transactions to prevent hangs
            max_transactions = 100
            if len(filtered_transactions) > max_transactions:
                logger.warning(
                    f"[SYNC] Limiting transactions from {len(filtered_transactions)} to {max_transactions} to prevent hangs"
                )
                filtered_transactions = filtered_transactions[:max_transactions]
            
            logger.info(
                f"[SYNC] Pulled {len(transactions)} transactions, filtered to {len(filtered_transactions)} within 3-day limit"
            )
            
            if filtered_transactions:
                logger.info(
                    f"[SYNC] First txn: {filtered_transactions[0].id} {filtered_transactions[0].created}, Last txn: {filtered_transactions[-1].id} {filtered_transactions[-1].created}"
                )

                # Check how many of these transactions already exist in the database
                existing_count = 0
                new_transactions = []
                for txn in filtered_transactions:
                    if (
                        db.query(Transaction)
                        .filter_by(id=txn.id, user_id=user_id_str)
                        .first()
                    ):
                        existing_count += 1
                    else:
                        new_transactions.append(txn)

                logger.info(
                    f"[SYNC] {existing_count} out of {len(filtered_transactions)} transactions already exist in database"
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
            # Rollback the transaction to handle PostgreSQL aborted transaction state
            try:
                db.rollback()
                logger.info("[SYNC] Database transaction rolled back after error")
            except Exception as rollback_error:
                logger.error(f"[SYNC] Error during rollback: {rollback_error}")
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
                f"[SYNC] No existing bills pot transactions for pot {bills_pot_id}, performing first-time sync with 10-day chunks"
            )
            # For first-time sync, use 10-day chunks to avoid timeouts
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=90)
            chunk_size = 10  # days per chunk
            
            current_start = start_date
            all_transactions = []
            
            while current_start < now:
                current_end = min(current_start + timedelta(days=chunk_size), now)
                
                try:
                    logger.info(
                        f"[SYNC] Pulling bills pot transactions from {current_start.isoformat()} to {current_end.isoformat()}"
                    )
                    chunk_transactions = safe_api_call(
                        lambda: monzo.get_transactions(
                            account_id=pot_account_id, 
                            since=current_start.isoformat(), 
                            before=current_end.isoformat()
                        ),
                        timeout_seconds=15
                    )
                    logger.info(
                        f"[SYNC] Pulled {len(chunk_transactions)} bills pot transactions in this chunk"
                    )
                    
                    all_transactions.extend(chunk_transactions)
                    
                    # Move to next chunk
                    current_start = current_end
                    
                except Exception as e:
                    logger.error(
                        f"[SYNC] Error pulling bills pot transactions for chunk {current_start.isoformat()} to {current_end.isoformat()}: {e}"
                    )
                    # Continue with next chunk instead of failing completely
                    current_start = current_end
                    continue
            
            transactions = all_transactions
            logger.info(f"[SYNC] First-time bills pot sync completed, total transactions: {len(transactions)}")
        else:
            logger.info(
                f"[SYNC] Found existing bills pot transactions, latest transaction ID: {latest_bills_txn.id}"
            )
            # Incremental sync - use the latest transaction ID with time limit
            latest_txn_id = latest_bills_txn.id
            
            # Add a reasonable time limit to prevent pulling too much historical data
            now = datetime.now(timezone.utc)
            time_limit = now - timedelta(days=3)
            
            logger.info(
                f"[SYNC] Pulling bills pot transactions since transaction ID: {latest_txn_id} (with 3-day time limit: {time_limit.isoformat()})"
            )
            
            all_transactions = safe_api_call(
                lambda: monzo.get_transactions(
                    account_id=pot_account_id, since=latest_txn_id
                ),
                timeout_seconds=15
            )
            
            # Filter transactions to only include those within the time limit
            transactions = [
                txn for txn in all_transactions 
                if txn.created >= time_limit
            ]
            
            # Additional safety: limit to max 50 transactions to prevent hangs
            max_transactions = 50
            if len(transactions) > max_transactions:
                logger.warning(
                    f"[SYNC] Limiting bills pot transactions from {len(transactions)} to {max_transactions} to prevent hangs"
                )
                transactions = transactions[:max_transactions]
            
            logger.info(
                f"[SYNC] Pulled {len(all_transactions)} bills pot transactions, filtered to {len(transactions)} within 3-day limit"
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
