"""
Pot Manager - Structured pot management without fuzzy name matching.
"""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Pot, User, UserPotCategory
from app.monzo.client import MonzoClient

logger = logging.getLogger(__name__)


class PotCategory:
    """Categories for pots to avoid fuzzy name matching."""

    BILLS = "bills"
    SAVINGS = "savings"
    HOLDING = "holding"
    SPENDING = "spending"
    EMERGENCY = "emergency"
    INVESTMENT = "investment"
    CUSTOM = "custom"


class PotManager:
    """
    Manages pots using explicit categories and IDs rather than fuzzy name matching.

    This provides a more structured approach where users explicitly configure
    which pots belong to which categories.
    """

    def __init__(self, db: Session, monzo_client: MonzoClient):
        self.db = db
        self.monzo_client = monzo_client

    def get_pots_by_category(self, user_id: str, category: str) -> List[Pot]:
        """
        Get pots for a specific category.

        Args:
            user_id: Monzo user ID
            category: Pot category (e.g., 'bills', 'savings', 'holding')

        Returns:
            List[Pot]: List of pots in the category
        """
        try:
            pot_ids = self._get_pot_ids_for_category(user_id, category)

            if not pot_ids:
                logger.info(
                    f"No pots configured for category '{category}' for user {user_id}"
                )
                return []

            pots = (
                self.db.query(Pot)
                .filter(
                    and_(
                        Pot.user_id == user_id,
                        Pot.deleted == 0,  # Active pots only
                        Pot.id.in_(pot_ids),
                    )
                )
                .all()
            )

            logger.info(
                f"Found {len(pots)} pots in category '{category}' for user {user_id}"
            )
            return pots

        except Exception as e:
            logger.error(
                f"Error getting pots for category '{category}' for user {user_id}: {e}"
            )
            return []

    def get_all_user_pots(self, user_id: str) -> List[Pot]:
        """
        Get all active pots for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            List[Pot]: List of all active pots
        """
        try:
            pots = (
                self.db.query(Pot)
                .filter(and_(Pot.user_id == user_id, Pot.deleted == 0))
                .all()
            )

            logger.info(f"Found {len(pots)} total pots for user {user_id}")
            return pots

        except Exception as e:
            logger.error(f"Error getting all pots for user {user_id}: {e}")
            return []

    def get_pot_categories(self, user_id: str) -> Dict[str, List[str]]:
        """
        Get all pot categories and their associated pot IDs for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            Dict[str, List[str]]: Dictionary mapping categories to pot IDs
        """
        try:
            # Get all category assignments for the user
            category_assignments = (
                self.db.query(UserPotCategory).filter_by(user_id=user_id).all()
            )

            # Group by category
            categories = {}
            for assignment in category_assignments:
                if assignment.category not in categories:
                    categories[assignment.category] = []
                categories[assignment.category].append(assignment.pot_id)

            logger.info(
                f"Found {len(categories)} configured categories for user {user_id}"
            )
            return categories

        except Exception as e:
            logger.error(f"Error getting pot categories for user {user_id}: {e}")
            return {}

    def set_pot_category(self, user_id: str, pot_id: str, category: str) -> bool:
        """
        Assign a pot to a specific category.

        Args:
            user_id: Monzo user ID
            pot_id: Pot ID to categorize
            category: Category to assign

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if pot exists
            pot = self.db.query(Pot).filter_by(id=pot_id, user_id=user_id).first()
            if not pot:
                logger.error(f"Pot {pot_id} not found for user {user_id}")
                return False

            # Check if category assignment already exists
            existing = (
                self.db.query(UserPotCategory)
                .filter_by(user_id=user_id, pot_id=pot_id, category=category)
                .first()
            )

            if existing:
                logger.info(
                    f"Pot {pot_id} already assigned to category '{category}' for user {user_id}"
                )
                return True

            # Create new category assignment
            pot_category = UserPotCategory(
                user_id=user_id, pot_id=pot_id, category=category
            )

            self.db.add(pot_category)
            self.db.commit()

            logger.info(
                f"Assigned pot {pot_id} to category '{category}' for user {user_id}"
            )
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error setting pot category: {e}")
            return False

    def remove_pot_from_category(
        self, user_id: str, pot_id: str, category: str
    ) -> bool:
        """
        Remove a pot from a specific category.

        Args:
            user_id: Monzo user ID
            pot_id: Pot ID to remove
            category: Category to remove from

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Find the category assignment
            category_assignment = (
                self.db.query(UserPotCategory)
                .filter_by(user_id=user_id, pot_id=pot_id, category=category)
                .first()
            )

            if not category_assignment:
                logger.warning(
                    f"Pot {pot_id} not found in category '{category}' for user {user_id}"
                )
                return False

            # Remove the assignment
            self.db.delete(category_assignment)
            self.db.commit()

            logger.info(
                f"Removed pot {pot_id} from category '{category}' for user {user_id}"
            )
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error removing pot from category: {e}")
            return False

    def get_pot_balance(self, pot_id: str) -> Optional[int]:
        """
        Get current balance of a pot.

        Args:
            pot_id: Pot ID

        Returns:
            Optional[int]: Current balance in minor units, or None if error
        """
        try:
            pot_data = self.monzo_client.get_pot(pot_id)
            return pot_data.balance

        except Exception as e:
            logger.error(f"Error getting balance for pot {pot_id}: {e}")
            return None

    def get_pots_with_balances(
        self, user_id: str, category: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Get pots with their current balances.

        Args:
            user_id: Monzo user ID
            category: Optional category filter

        Returns:
            Dict[str, int]: Dictionary mapping pot IDs to balances
        """
        try:
            if category:
                pots = self.get_pots_by_category(user_id, category)
            else:
                pots = self.get_all_user_pots(user_id)

            balances = {}
            for pot in pots:
                balance = self.get_pot_balance(pot.id)
                if balance is not None:
                    balances[pot.id] = balance

            return balances

        except Exception as e:
            logger.error(f"Error getting pot balances for user {user_id}: {e}")
            return {}

    def _get_pot_ids_for_category(self, user_id: str, category: str) -> List[str]:
        """
        Get pot IDs for a specific category from the database.

        Args:
            user_id: Monzo user ID
            category: Pot category

        Returns:
            List[str]: List of pot IDs in the category
        """
        try:
            categories = (
                self.db.query(UserPotCategory)
                .filter_by(user_id=user_id, category=category)
                .all()
            )

            return [cat.pot_id for cat in categories]

        except Exception as e:
            logger.error(f"Error getting pot IDs for category {category}: {e}")
            return []

    def get_available_categories(self) -> List[str]:
        """
        Get list of available pot categories.

        Returns:
            List[str]: List of available categories
        """
        return [
            PotCategory.BILLS,
            PotCategory.SAVINGS,
            PotCategory.HOLDING,
            PotCategory.SPENDING,
            PotCategory.EMERGENCY,
            PotCategory.INVESTMENT,
            PotCategory.CUSTOM,
        ]

    def get_pot_category(self, user_id: str, pot_id: str) -> Optional[str]:
        """
        Get the category for a specific pot.

        Args:
            user_id: Monzo user ID
            pot_id: Pot ID

        Returns:
            Optional[str]: Category name or None if not categorized
        """
        try:
            category_assignment = (
                self.db.query(UserPotCategory)
                .filter_by(user_id=user_id, pot_id=pot_id)
                .first()
            )

            return category_assignment.category if category_assignment else None

        except Exception as e:
            logger.error(f"Error getting category for pot {pot_id}: {e}")
            return None
