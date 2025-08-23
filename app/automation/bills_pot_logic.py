"""
Bills Pot Logic - Special handling for bills pots using pot_current_id for accurate transaction queries.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Account, Pot, Transaction, User
from app.monzo.client import MonzoClient

from .pot_manager import PotCategory, PotManager

logger = logging.getLogger(__name__)


class BillsPotLogic:
    """
    Handles bills pot logic for accurate transaction queries.

    When bills pots are in use, using pot_current_id instead of account_id
    provides more accurate transaction data by showing outflows rather than inflows.
    """

    def __init__(self, db: Session, monzo_client: MonzoClient):
        self.db = db
        self.monzo_client = monzo_client
        self.pot_manager = PotManager(db, monzo_client)

    def get_bills_pots(self, user_id: str) -> List[Pot]:
        """
        Get all bills pots for a user using structured pot management.

        Args:
            user_id: Monzo user ID

        Returns:
            List[Pot]: List of bills pots
        """
        return self.pot_manager.get_pots_by_category(user_id, PotCategory.BILLS)

    def get_transactions_for_bills_pot(
        self,
        pot: Pot,
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> List[Transaction]:
        """
        Get transactions for a bills pot using pot_current_id for accuracy.

        Args:
            pot: The bills pot
            since: Optional start date
            before: Optional end date

        Returns:
            List[Transaction]: List of transactions
        """
        try:
            if not pot.pot_current_id:
                logger.warning(f"Pot {pot.id} has no pot_current_id, using account_id")
                return self._get_transactions_by_account_id(
                    pot.account_id, since, before
                )

            # Use pot_current_id for more accurate transaction queries
            query = self.db.query(Transaction).filter(
                Transaction.pot_current_id == pot.pot_current_id
            )

            if since:
                query = query.filter(Transaction.created >= since)
            if before:
                query = query.filter(Transaction.created < before)

            transactions = query.order_by(Transaction.created.desc()).all()

            logger.info(
                f"Found {len(transactions)} transactions for bills pot {pot.id} using pot_current_id"
            )
            return transactions

        except Exception as e:
            logger.error(f"Error getting transactions for bills pot {pot.id}: {e}")
            return []

    def get_bills_spending(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """
        Get total bills spending across all bills pots.

        Args:
            user_id: Monzo user ID
            since: Optional start date
            before: Optional end date

        Returns:
            Dict[str, int]: Dictionary with pot_id as key and total spending as value
        """
        try:
            bills_pots = self.get_bills_pots(user_id)

            spending_by_pot = {}
            total_spending = 0

            for pot in bills_pots:
                transactions = self.get_transactions_for_bills_pot(pot, since, before)
                pot_spending = sum(
                    abs(txn.amount) for txn in transactions if txn.amount < 0
                )  # Only outflows
                spending_by_pot[pot.id] = pot_spending
                total_spending += pot_spending

            spending_by_pot["total"] = total_spending
            return spending_by_pot

        except Exception as e:
            logger.error(f"Error calculating bills spending for user {user_id}: {e}")
            return {"total": 0}

    def calculate_bills_spending(self, user_id: str) -> int:
        """
        Calculate total bills spending for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            int: Total bills spending in pence
        """
        try:
            bills_pots = self.get_bills_pots(user_id)

            total_spending = 0
            for pot in bills_pots:
                transactions = self.get_transactions_for_bills_pot(pot)
                pot_spending = sum(
                    abs(txn.amount) for txn in transactions if txn.amount < 0
                )  # Only outflows
                total_spending += pot_spending

            logger.info(
                f"Calculated bills spending for user {user_id}: {total_spending} pence"
            )
            return total_spending

        except Exception as e:
            logger.error(f"Error calculating bills spending for user {user_id}: {e}")
            return 0

    def calculate_shortfall(self, user_id: str) -> int:
        """
        Calculate bills shortfall for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            int: Shortfall amount in pence
        """
        try:
            bills_pots = self.get_bills_pots(user_id)

            total_shortfall = 0
            for pot in bills_pots:
                pot_balance = self.get_bills_pot_balance(pot)
                if pot_balance is not None and pot_balance < 0:
                    total_shortfall += abs(pot_balance)

            logger.info(
                f"Calculated bills shortfall for user {user_id}: {total_shortfall} pence"
            )
            return total_shortfall

        except Exception as e:
            logger.error(f"Error calculating bills shortfall for user {user_id}: {e}")
            return 0

    def get_pay_cycle_bills_spending(
        self,
        user_id: str,
        pay_day: int = 25,  # Day of month for pay day
        days_before_pay: int = 30,  # Days to look back from pay day
    ) -> Dict[str, int]:
        """
        Get bills spending for the current pay cycle.

        This computes the period as: from the most recent payday (pay_day) up to now.
        For example, if today is Aug 10 and pay_day is 25, the window is Jul 25 → Aug 10.
        If today is Aug 28 and pay_day is 25, the window is Aug 25 → Aug 28.

        Args:
            user_id: Monzo user ID
            pay_day: Day of month for pay day (default 25th)
            days_before_pay: (Unused) kept for backward compatibility

        Returns:
            Dict[str, int]: Dictionary with pot_id as key and pay cycle spending as value
        """
        try:
            today = datetime.now()

            # Determine the most recent payday date
            if today.day >= pay_day:
                # Most recent payday is this month
                cycle_start = today.replace(day=pay_day)
            else:
                # Most recent payday was last month
                if today.month == 1:
                    cycle_start = today.replace(year=today.year - 1, month=12, day=pay_day)
                else:
                    cycle_start = today.replace(month=today.month - 1, day=pay_day)

            cycle_end = today  # Up to "now"

            logger.info(f"Pay cycle (most recent payday to now): {cycle_start} → {cycle_end}")

            return self.get_bills_spending(user_id, cycle_start, cycle_end)

        except Exception as e:
            logger.error(
                f"Error calculating pay cycle bills spending for user {user_id}: {e}"
            )
            return {}

    def get_bills_pot_balance(self, pot: Pot) -> Optional[int]:
        """
        Get current balance of a bills pot from the database.

        Args:
            pot: The bills pot

        Returns:
            Optional[int]: Current balance in minor units, or None if error
        """
        try:
            # Get balance from database
            return pot.balance

        except Exception as e:
            logger.error(f"Error getting balance for bills pot {pot.id}: {e}")
            return None

    def calculate_bills_shortfall(
        self, user_id: str, target_amount: int, pay_day: int = 25
    ) -> Dict[str, int]:
        """
        Calculate how much more needs to be added to bills pots to reach target.

        Args:
            user_id: Monzo user ID
            target_amount: Target amount per pay cycle in minor units
            pay_day: Day of month for pay day

        Returns:
            Dict[str, int]: Dictionary with pot_id as key and shortfall amount as value
        """
        try:
            bills_pots = self.get_bills_pots(user_id)
            pay_cycle_spending = self.get_pay_cycle_bills_spending(user_id, pay_day)
            shortfalls = {}

            for pot in bills_pots:
                current_balance = self.get_bills_pot_balance(pot)
                if current_balance is None:
                    continue

                # Calculate shortfall: target - (balance + spending)
                spending = pay_cycle_spending.get(pot.id, 0)
                shortfall = max(0, target_amount - (current_balance + spending))

                shortfalls[pot.id] = shortfall
                logger.info(f"Bills pot {pot.name} shortfall: £{shortfall/100:.2f}")

            return shortfalls

        except Exception as e:
            logger.error(f"Error calculating bills shortfall for user {user_id}: {e}")
            return {}

    def _get_transactions_by_account_id(
        self,
        account_id: str,
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> List[Transaction]:
        """Fallback method to get transactions by account_id."""
        try:
            query = self.db.query(Transaction).filter(
                Transaction.account_id == account_id
            )

            if since:
                query = query.filter(Transaction.created >= since)
            if before:
                query = query.filter(Transaction.created < before)

            return query.order_by(Transaction.created.desc()).all()

        except Exception as e:
            logger.error(f"Error getting transactions by account_id {account_id}: {e}")
            return []
