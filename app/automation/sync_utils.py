"""
Sync utilities for automation modules.

This module provides sync functionality without creating circular imports.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Account, Pot, Transaction, User

logger = logging.getLogger(__name__)


def trigger_account_sync(db: Session, monzo_client: Any, user_id: str, module_name: str) -> None:
    """
    Trigger account sync to ensure database has latest balance information.
    
    This is a simplified sync that updates account and pot data without triggering
    the full automation integration to avoid circular imports.
    
    Args:
        db: Database session
        monzo_client: Authenticated Monzo client
        user_id: User ID to sync accounts for
        module_name: Name of the calling module for logging
    """
    try:
        logger.info(f"[{module_name.upper()}] Triggering account sync for user {user_id}")
        
        # Get all active accounts for the user
        accounts = db.query(Account).filter_by(user_id=user_id, closed=0, is_active=True).all()
        
        # Get all accounts from Monzo API
        api_accounts = monzo_client.get_accounts()
        api_accounts_dict = {acc.id: acc for acc in api_accounts}
        
        for account in accounts:
            try:
                logger.info(f"[{module_name.upper()}] Syncing account {account.id}")
                
                # Update account details from Monzo API
                api_account = api_accounts_dict.get(account.id)
                if api_account:
                    account.description = api_account.description
                    account.type = api_account.type
                    account.closed = int(api_account.closed)
                    account.updated_at = getattr(api_account, "updated_at", None)
                
                # Update pots for this account
                pots = monzo_client.get_pots(account.id)
                for pot in pots:
                    if getattr(pot, "deleted", False):
                        continue  # Skip deleted pots
                    
                    db_pot = db.query(Pot).filter_by(id=pot.id, user_id=user_id).first()
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
                            account_id=account.id,
                            user_id=user_id,
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
                
                logger.info(f"[{module_name.upper()}] Successfully synced account {account.id}")
                
            except Exception as e:
                logger.error(f"[{module_name.upper()}] Failed to sync account {account.id}: {e}")
        
        # Commit all changes
        db.commit()
        logger.info(f"[{module_name.upper()}] Account sync completed for user {user_id}")
        
    except Exception as e:
        logger.error(f"[{module_name.upper()}] Error during account sync: {e}")
        db.rollback()


def trigger_bills_pot_transactions_sync(
    db: Session,
    monzo_client: Any,
    user_id: str,
    bills_pot_id: str,
    module_name: str = "automation",
) -> bool:
    """
    Trigger a sync of bills pot transactions to ensure BillsPotTransaction table is up to date.
    Uses a lazy import to avoid circular dependencies.
    
    Args:
        db: Database session
        monzo_client: Authenticated Monzo client
        user_id: Monzo user ID
        bills_pot_id: Bills pot ID to sync
        module_name: For logging context
    
    Returns:
        bool: True if sync succeeded, False otherwise
    """
    try:
        logger.info(f"[{module_name.upper()}] Syncing bills pot transactions for pot {bills_pot_id}")
        from app.monzo.sync import sync_bills_pot_transactions  # Lazy import
        success = sync_bills_pot_transactions(db, user_id, bills_pot_id, monzo_client)
        if success:
            logger.info(f"[{module_name.upper()}] Bills pot transactions synced for pot {bills_pot_id}")
        else:
            logger.warning(f"[{module_name.upper()}] Bills pot transaction sync returned False for pot {bills_pot_id}")
        return success
    except Exception as e:
        logger.error(f"[{module_name.upper()}] Error syncing bills pot transactions for pot {bills_pot_id}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False 