"""
Rules management - Database models and operations for automation rules.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.db import Base

logger = logging.getLogger(__name__)


class AutomationRule(Base):
    """Database model for storing automation rules."""

    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    rule_type = Column(String, nullable=False)  # "sweep", "sort", "topup"
    name = Column(String, nullable=False)
    config = Column(JSON, nullable=False)  # Rule configuration as JSON
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_executed = Column(DateTime(timezone=True), nullable=True)
    execution_metadata = Column(JSON, nullable=True)  # Store execution results and metadata

    def __repr__(self) -> str:
        return f"<AutomationRule rule_id={self.rule_id} type={self.rule_type} name={self.name}>"


class RulesManager:
    """Manages automation rules in the database."""

    def __init__(self, db: Session):
        self.db = db

    def create_rule(self, rule_data: Dict[str, Any]) -> Optional[AutomationRule]:
        """
        Create a new automation rule.

        Args:
            rule_data: Dictionary containing rule configuration

        Returns:
            Optional[AutomationRule]: Created rule or None if failed
        """
        try:
            rule = AutomationRule(
                rule_id=rule_data["rule_id"],
                user_id=rule_data["user_id"],
                rule_type=rule_data["rule_type"],
                name=rule_data["name"],
                config=rule_data["config"],
                enabled=rule_data.get("enabled", True),
            )

            self.db.add(rule)
            self.db.commit()
            self.db.refresh(rule)

            logger.info(f"Created automation rule: {rule.rule_id}")
            return rule

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating automation rule: {e}")
            return None

    def get_rules_by_user(
        self, user_id: str, rule_type: Optional[str] = None
    ) -> List[AutomationRule]:
        """
        Get all rules for a user, optionally filtered by type.

        Args:
            user_id: Monzo user ID
            rule_type: Optional rule type filter

        Returns:
            List[AutomationRule]: List of rules
        """
        try:
            query = self.db.query(AutomationRule).filter_by(user_id=user_id)
            if rule_type:
                query = query.filter_by(rule_type=rule_type)

            return query.all()

        except Exception as e:
            logger.error(f"Error getting rules for user {user_id}: {e}")
            return []

    def get_rule_by_id(self, rule_id: str) -> Optional[AutomationRule]:
        """
        Get a specific rule by ID.

        Args:
            rule_id: Rule ID

        Returns:
            Optional[AutomationRule]: Rule or None if not found
        """
        try:
            return self.db.query(AutomationRule).filter_by(rule_id=rule_id).first()
        except Exception as e:
            logger.error(f"Error getting rule {rule_id}: {e}")
            return None

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing rule.

        Args:
            rule_id: Rule ID to update
            updates: Dictionary of fields to update

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            rule = self.get_rule_by_id(rule_id)
            if not rule:
                return False

            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

            self.db.commit()
            logger.info(f"Updated automation rule: {rule_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating rule {rule_id}: {e}")
            return False

    def delete_rule(self, rule_id: str) -> bool:
        """
        Delete a rule.

        Args:
            rule_id: Rule ID to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            rule = self.get_rule_by_id(rule_id)
            if not rule:
                return False

            self.db.delete(rule)
            self.db.commit()

            logger.info(f"Deleted automation rule: {rule_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting rule {rule_id}: {e}")
            return False

    def update_execution_time(
        self, rule_id: str, execution_time: Optional[datetime] = None
    ) -> bool:
        """
        Update the last execution time for a rule.

        Args:
            rule_id: Rule ID
            execution_time: Execution time (defaults to now)

        Returns:
            bool: True if successful, False otherwise
        """
        if execution_time is None:
            execution_time = datetime.now()

        return self.update_rule(rule_id, {"last_executed": execution_time})

    def get_enabled_rules(
        self, user_id: str, rule_type: Optional[str] = None
    ) -> List[AutomationRule]:
        """
        Get all enabled rules for a user.

        Args:
            user_id: Monzo user ID
            rule_type: Optional rule type filter

        Returns:
            List[AutomationRule]: List of enabled rules
        """
        try:
            query = self.db.query(AutomationRule).filter_by(
                user_id=user_id, enabled=True
            )
            if rule_type:
                query = query.filter_by(rule_type=rule_type)

            return query.all()

        except Exception as e:
            logger.error(f"Error getting enabled rules for user {user_id}: {e}")
            return []

    def toggle_rule(self, rule_id: str) -> bool:
        """
        Toggle the enabled state of a rule.

        Args:
            rule_id: Rule ID to toggle

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            rule = self.get_rule_by_id(rule_id)
            if not rule:
                return False

            rule.enabled = not rule.enabled
            self.db.commit()

            logger.info(f"Toggled rule {rule_id} to enabled={rule.enabled}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error toggling rule {rule_id}: {e}")
            return False
