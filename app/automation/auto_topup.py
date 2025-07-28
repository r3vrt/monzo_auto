"""
Auto Topup automation - Automatically add money to pots based on rules.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Account, Pot, Transaction, User
from app.monzo.client import MonzoClient
from .sync_utils import trigger_account_sync

logger = logging.getLogger(__name__)


class TopupRule:
    """Configuration for an auto topup rule."""

    def __init__(
        self,
        source_account_id: str,
        target_pot_id: str,
        amount: int,  # Amount in minor units (pennies)
        trigger_type: str = "monthly",  # "monthly", "weekly", "daily", "hourly", "minute", "balance_threshold"
        trigger_day: Optional[int] = None,  # Day of month/week for triggers
        trigger_hour: Optional[int] = None,  # Hour for daily/hourly triggers
        trigger_minute: Optional[int] = None,  # Minute for hourly/minute triggers
        trigger_interval: Optional[int] = None,  # Interval in minutes for minute triggers
        min_balance: Optional[int] = None,  # Minimum balance to maintain
        target_balance: Optional[int] = None,  # Target balance to top up to
        rule_id: Optional[str] = None,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        last_executed: Optional[datetime] = None,
        enabled: bool = True,
    ):
        self.rule_id = rule_id
        self.name = name
        self.user_id = user_id
        self.source_account_id = source_account_id
        self.target_pot_id = target_pot_id
        self.trigger_type = trigger_type
        self.amount = amount
        self.trigger_day = trigger_day
        self.trigger_hour = trigger_hour
        self.trigger_minute = trigger_minute
        self.trigger_interval = trigger_interval
        self.min_balance = min_balance
        self.target_balance = target_balance
        self.last_executed = last_executed
        self.enabled = enabled


class AutoTopup:
    """Handles automated pot topup operations."""

    def __init__(self, db: Session, monzo_client):
        self.db = db
        self.monzo_client = monzo_client

    def execute_topup_rule(self, user_id: str, rule: TopupRule) -> Dict[str, Any]:
        """
        Execute a single topup rule.

        Args:
            user_id: Monzo user ID
            rule: The topup rule to execute

        Returns:
            Dict[str, Any]: Detailed execution results
        """
        try:
            # Check if rule was recently executed to prevent duplicate transfers
            # This can happen when multiple automation flows trigger the same rule simultaneously
            if self._is_rule_recently_executed(rule):
                logger.warning(f"🚫 Topup rule '{rule.name}' was recently executed, skipping to prevent duplicate transfer (this suggests multiple automation flows are triggering the same rule)")
                return {"success": False, "reason": "Rule recently executed - preventing duplicate transfer"}
            
            # Trigger account sync to ensure we have latest balance information
            self._sync_account_data(user_id)
            
            # Check if rule should be triggered
            if not self._should_trigger_topup(rule):
                logger.info(f"Topup rule '{rule.name}' not triggered")
                return {"success": False, "reason": "Rule not triggered"}

            logger.info(f"🎯 Executing topup rule '{rule.name}'")

            # Calculate transfer amount
            transfer_amount = rule.amount
            
            # If target_balance is specified, calculate the amount needed
            if rule.target_balance is not None:
                logger.info(f"🎯 Target balance mode: calculating amount needed to reach {rule.target_balance} ({rule.target_balance/100:.2f}£)")
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is None:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return {"success": False, "error": f"Could not get balance for target {rule.target_pot_id}"}
                
                logger.info(f"💰 Target balance check: current={current_balance} (£{current_balance/100:.2f}), target={rule.target_balance} (£{rule.target_balance/100:.2f})")
                
                # Calculate how much we need to add to reach target balance
                needed_amount = rule.target_balance - current_balance
                if needed_amount <= 0:
                    logger.info(f"✅ Target {rule.target_pot_id} already at or above target balance {rule.target_balance} (£{rule.target_balance/100:.2f})")
                    return {"success": True, "amount": 0, "reason": "Target already at or above target balance"}
                
                transfer_amount = min(needed_amount, rule.amount)  # Don't exceed the rule's max amount
                logger.info(f"🧮 Calculated transfer amount: {transfer_amount} (£{transfer_amount/100:.2f}) (needed: {needed_amount} (£{needed_amount/100:.2f}), max: {rule.amount} (£{rule.amount/100:.2f}))")
            else:
                logger.info(f"💸 Fixed amount mode: using rule amount {transfer_amount} (£{transfer_amount/100:.2f})")

            # Get current source balance
            logger.info(f"🔍 Checking source balance for {rule.source_account_id}")
            source_balance = self._get_account_balance(rule.source_account_id)
            if source_balance is None:
                logger.error(f"❌ Could not get balance for source {rule.source_account_id}")
                return {"success": False, "error": f"Could not get balance for source {rule.source_account_id}"}

            logger.info(f"💰 Source balance: {source_balance} (£{source_balance/100:.2f}), transfer amount: {transfer_amount} (£{transfer_amount/100:.2f})")

            # Check if we have enough funds
            if source_balance < transfer_amount:
                logger.warning(
                    f"❌ Insufficient funds for topup '{rule.name}': {source_balance} (£{source_balance/100:.2f}) < {transfer_amount} (£{transfer_amount/100:.2f})"
                )
                return {"success": False, "error": f"Insufficient funds: {source_balance} (£{source_balance/100:.2f}) < {transfer_amount} (£{transfer_amount/100:.2f})"}

            logger.info(f"✅ Sufficient funds available, executing transfer")

            # Execute the topup
            logger.info(f"🔄 Executing transfer: {transfer_amount} (£{transfer_amount/100:.2f}) from {rule.source_account_id} to {rule.target_pot_id}")
            success = self._topup_pot(
                rule.source_account_id,
                rule.target_pot_id,
                transfer_amount,
                f"Auto topup: {rule.name}",
            )

            if success:
                # Update the rule's last execution time
                rule.last_executed = datetime.now(timezone.utc)
                self._update_rule_execution_time(rule)
                logger.info(
                    f"🎉 Successfully executed topup rule '{rule.name}': {transfer_amount} (£{transfer_amount/100:.2f}) from {rule.source_account_id} to {rule.target_pot_id}"
                )
                return {"success": True, "amount": transfer_amount, "reason": f"Successfully topped up £{transfer_amount/100:.2f}"}
            else:
                logger.error(f"❌ Failed to execute topup rule '{rule.name}'")
                return {"success": False, "error": "Transfer failed"}

        except Exception as e:
            logger.error(f"Error executing topup rule {rule.name}: {e}")
            return {"success": False, "error": str(e)}

    def execute_all_topup_rules(self, user_id: str) -> Dict[str, int]:
        """
        Execute all topup rules for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            Dict[str, int]: Summary of topup results
        """
        try:
            rules = self.get_topup_rules(user_id)

            successful_count = 0
            failed_count = 0

            for rule in rules:
                result = self.execute_topup_rule(user_id, rule)
                if result.get("success"):
                    successful_count += 1
                else:
                    failed_count += 1

            logger.info(
                f"Executed {successful_count} topup rules successfully, {failed_count} failed for user {user_id}"
            )
            return {
                "successful": successful_count,
                "failed": failed_count,
                "total": len(rules),
            }

        except Exception as e:
            logger.error(f"Error executing topup rules for user {user_id}: {e}")
            return {"successful": 0, "failed": 0, "total": 0}

    def _should_trigger_topup(self, rule: TopupRule) -> bool:
        """Determine if a topup rule should be triggered."""
        logger.info(f"🔍 Evaluating trigger for rule '{rule.name}' (type: {rule.trigger_type})")
        
        if not rule.enabled:
            logger.info(f"❌ Rule '{rule.name}' is disabled, skipping")
            return False

        if rule.trigger_type == "monthly":
            today = datetime.now(timezone.utc)
            time_trigger = today.day == (rule.trigger_day or 1)
            logger.info(f"📅 Monthly trigger for rule '{rule.name}': current day {today.day}, trigger day {rule.trigger_day or 1}, time trigger: {time_trigger}")
            
            # If min_balance (topup threshold) is set, also check balance threshold
            if rule.min_balance is not None and time_trigger:
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is not None:
                    balance_trigger = current_balance < rule.min_balance
                    logger.info(f"💰 Balance threshold check for rule '{rule.name}': current={current_balance} ({current_balance/100:.2f}£), threshold={rule.min_balance} ({rule.min_balance/100:.2f}£), balance trigger: {balance_trigger}")
                    return time_trigger and balance_trigger
                else:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return False
            
            return time_trigger

        elif rule.trigger_type == "weekly":
            today = datetime.now(timezone.utc)
            time_trigger = today.weekday() == (rule.trigger_day or 0)  # Monday = 0
            logger.info(f"📅 Weekly trigger for rule '{rule.name}': current weekday {today.weekday()}, trigger day {rule.trigger_day or 0}, time trigger: {time_trigger}")
            
            # If min_balance (topup threshold) is set, also check balance threshold
            if rule.min_balance is not None and time_trigger:
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is not None:
                    balance_trigger = current_balance < rule.min_balance
                    logger.info(f"💰 Balance threshold check for rule '{rule.name}': current={current_balance} ({current_balance/100:.2f}£), threshold={rule.min_balance} ({rule.min_balance/100:.2f}£), balance trigger: {balance_trigger}")
                    return time_trigger and balance_trigger
                else:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return False
            
            return time_trigger

        elif rule.trigger_type == "daily":
            today = datetime.now(timezone.utc)
            time_trigger = today.hour == (rule.trigger_hour or 0) and today.minute == (rule.trigger_minute or 0)
            logger.info(f"📅 Daily trigger for rule '{rule.name}': current time {today.hour:02d}:{today.minute:02d}, trigger time {rule.trigger_hour or 0:02d}:{rule.trigger_minute or 0:02d}, time trigger: {time_trigger}")
            
            # If min_balance (topup threshold) is set, also check balance threshold
            if rule.min_balance is not None and time_trigger:
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is not None:
                    balance_trigger = current_balance < rule.min_balance
                    logger.info(f"💰 Balance threshold check for rule '{rule.name}': current={current_balance} ({current_balance/100:.2f}£), threshold={rule.min_balance} ({rule.min_balance/100:.2f}£), balance trigger: {balance_trigger}")
                    return time_trigger and balance_trigger
                else:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return False
            
            return time_trigger

        elif rule.trigger_type == "hourly":
            today = datetime.now(timezone.utc)
            time_trigger = today.minute == (rule.trigger_minute or 0)
            logger.info(f"📅 Hourly trigger for rule '{rule.name}': current minute {today.minute}, trigger minute {rule.trigger_minute or 0}, time trigger: {time_trigger}")
            
            # If min_balance (topup threshold) is set, also check balance threshold
            if rule.min_balance is not None and time_trigger:
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is not None:
                    balance_trigger = current_balance < rule.min_balance
                    logger.info(f"💰 Balance threshold check for rule '{rule.name}': current={current_balance} ({current_balance/100:.2f}£), threshold={rule.min_balance} ({rule.min_balance/100:.2f}£), balance trigger: {balance_trigger}")
                    return time_trigger and balance_trigger
                else:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return False
            
            return time_trigger

        elif rule.trigger_type == "minute":
            if rule.trigger_interval is None:
                logger.warning(f"⚠️ Minute trigger for rule '{rule.name}' has no interval set")
                return False
            today = datetime.now(timezone.utc)
            
            # Check if enough time has passed since last execution
            time_trigger = False
            if rule.last_executed is None:
                logger.info(f"⏰ Minute trigger for rule '{rule.name}': No previous execution, time trigger: True")
                time_trigger = True
            else:
                # Ensure both datetimes are timezone-aware
                last_executed = rule.last_executed
                if last_executed.tzinfo is None:
                    last_executed = last_executed.replace(tzinfo=timezone.utc)
                time_diff = (today - last_executed).total_seconds() / 60
                time_trigger = time_diff >= rule.trigger_interval
                logger.info(f"⏰ Minute trigger for rule '{rule.name}': {time_diff:.1f} minutes since last execution, interval: {rule.trigger_interval}, time trigger: {time_trigger}")
            
            # If min_balance (topup threshold) is set, also check balance threshold
            if rule.min_balance is not None and time_trigger:
                current_balance = self._get_account_balance(rule.target_pot_id)
                if current_balance is not None:
                    balance_trigger = current_balance < rule.min_balance
                    logger.info(f"💰 Balance threshold check for rule '{rule.name}': current={current_balance} ({current_balance/100:.2f}£), threshold={rule.min_balance} ({rule.min_balance/100:.2f}£), balance trigger: {balance_trigger}")
                    return time_trigger and balance_trigger
                else:
                    logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                    return False
            
            return time_trigger

        elif rule.trigger_type == "balance_threshold":
            if rule.min_balance is None:
                logger.warning(f"⚠️ Balance threshold trigger for rule '{rule.name}' has no min_balance set")
                return False
            # For balance threshold triggers, check the target balance (the account/pot we want to top up)
            target_balance = self._get_account_balance(rule.target_pot_id)
            if target_balance is None:
                logger.error(f"❌ Could not get balance for target {rule.target_pot_id}")
                return False
            
            should_trigger = target_balance <= rule.min_balance
            logger.info(f"💰 Balance threshold trigger for rule '{rule.name}': target balance {target_balance} ({target_balance/100:.2f}£), min threshold {rule.min_balance} ({rule.min_balance/100:.2f}£), should trigger: {should_trigger}")
            return should_trigger

        elif rule.trigger_type == "transaction_based":
            # Check if we've had recent transactions that should trigger topup
            # This could be based on spending patterns, income received, etc.
            logger.info(f"💳 Transaction-based trigger for rule '{rule.name}': checking recent transactions")
            return self._check_transaction_based_trigger(rule)

        logger.warning(f"⚠️ Unknown trigger type '{rule.trigger_type}' for rule '{rule.name}'")
        return False

    def _check_transaction_based_trigger(self, rule: TopupRule) -> bool:
        """Check if transaction-based trigger conditions are met."""
        try:
            # Example: Topup after receiving salary (large positive transaction)
            # This is a simplified example - you'd implement your own logic
            recent_transactions = (
                self.db.query(Transaction)
                .filter(
                    Transaction.account_id == rule.source_account_id,
                    Transaction.created >= datetime.now(timezone.utc) - timedelta(days=7),
                    Transaction.amount > 0,  # Positive transactions (income)
                )
                .all()
            )

            # Check if we've had significant income recently
            total_income = sum(txn.amount for txn in recent_transactions)
            return total_income > 10000  # £100 threshold

        except Exception as e:
            logger.error(f"Error checking transaction-based trigger: {e}")
            return False

    def _get_account_balance(self, account_or_pot_id: str) -> Optional[int]:
        """Get current balance for an account or pot."""
        try:
            logger.info(f"🔍 Getting balance for: {account_or_pot_id}")
            
            # Check if this is a main account (starts with 'acc_')
            if account_or_pot_id.startswith('acc_'):
                logger.info(f"💳 Getting account balance for {account_or_pot_id}")
                # Get all accounts and find the specific one
                accounts = self.monzo_client.get_accounts()
                account = next((acc for acc in accounts if acc.id == account_or_pot_id), None)
                if account:
                    balance = account.balance
                    logger.info(f"💰 Account balance for {account_or_pot_id}: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error(f"❌ Account not found: {account_or_pot_id}")
                    return None
                
            # Check if this is a pot (starts with 'pot_')
            elif account_or_pot_id.startswith('pot_'):
                logger.info(f"🏦 Getting live pot balance for {account_or_pot_id}")
                # Get live pot balance from Monzo API instead of stale database data
                try:
                    # Get all pots for the user's accounts
                    accounts = self.monzo_client.get_accounts()
                    for account in accounts:
                        pots = self.monzo_client.get_pots(account.id)
                        for pot in pots:
                            if pot.id == account_or_pot_id:
                                balance = pot.balance
                                logger.info(f"💰 Live pot balance for {account_or_pot_id}: {balance} ({balance/100:.2f}£)")
                                return balance
                    
                    # If pot not found in live data, fall back to database
                    logger.warning(f"⚠️ Pot {account_or_pot_id} not found in live data, falling back to database")
                    pot = self.db.query(Pot).filter_by(id=account_or_pot_id, deleted=0).first()
                    if pot:
                        balance = pot.balance
                        logger.warning(f"⚠️ Using stale database balance for {account_or_pot_id}: {balance} ({balance/100:.2f}£)")
                        return balance
                    else:
                        logger.error(f"❌ Pot not found in database: {account_or_pot_id}")
                        return None
                except Exception as e:
                    logger.error(f"❌ Error getting live pot balance for {account_or_pot_id}: {e}")
                    # Fall back to database
                    pot = self.db.query(Pot).filter_by(id=account_or_pot_id, deleted=0).first()
                    if pot:
                        balance = pot.balance
                        logger.warning(f"⚠️ Using stale database balance for {account_or_pot_id}: {balance} ({balance/100:.2f}£)")
                        return balance
                    else:
                        logger.error(f"❌ Pot not found in database: {account_or_pot_id}")
                        return None
                        
            # Check if this is the main account (special identifier)
            elif account_or_pot_id == "main_account":
                logger.info(f"💳 Getting main account balance using dedicated API")
                # Get the user's main account balance using the dedicated balance API
                accounts = self.monzo_client.get_accounts()
                if accounts:
                    # Use the dedicated get_balance method for accurate balance
                    main_account = accounts[0]
                    balance_obj = self.monzo_client.get_balance(main_account.id)
                    balance = balance_obj.balance
                    logger.info(f"💰 Live main account balance: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error("❌ No accounts found for main account balance")
                    return None
            else:
                logger.error(f"❌ Unknown account/pot ID format: {account_or_pot_id}")
                return None
        except Exception as e:
            logger.error(f"❌ Error getting balance for {account_or_pot_id}: {e}")
            return None

    def _topup_pot(
        self, source_id: str, target_id: str, amount: int, description: str
    ) -> bool:
        """Transfer money between accounts and/or pots."""
        try:
            # Determine the type of transfer based on source and target IDs
            source_is_account = source_id.startswith('acc_') or source_id == "main_account"
            target_is_pot = target_id.startswith('pot_')
            
            if source_is_account and target_is_pot:
                # Account to pot transfer
                if source_id == "main_account":
                    # Get the main account ID
                    accounts = self.monzo_client.get_accounts()
                    if not accounts:
                        logger.error("No accounts found for main account transfer")
                        return False
                    source_account_id = accounts[0].id
                else:
                    source_account_id = source_id
                
                # Use Monzo API to deposit into pot
                result = self.monzo_client.deposit_to_pot(
                    pot_id=target_id,
                    amount=amount,
                    account_id=source_account_id,
                    dedupe_id=f"topup_{datetime.now(timezone.utc).isoformat()}",
                )
                
                if not result:
                    logger.error(f"Failed to deposit {amount} to pot {target_id}")
                    return False
                
            elif source_id.startswith('pot_') and target_is_pot:
                # Pot to pot transfer - need to get an account ID for the transfer
                accounts = self.monzo_client.get_accounts()
                if not accounts:
                    logger.error("No accounts found for pot-to-pot transfer")
                    return False
                account_id = accounts[0].id
                
                # Withdraw from source pot to account
                result = self.monzo_client.withdraw_from_pot(
                    pot_id=source_id,
                    account_id=account_id,
                    amount=amount,
                    dedupe_id=f"withdraw_{datetime.now(timezone.utc).isoformat()}",
                )
                
                if not result:
                    logger.error(f"Failed to withdraw {amount} from pot {source_id}")
                    return False
                
                # Then deposit from account to target pot
                result2 = self.monzo_client.deposit_to_pot(
                    pot_id=target_id,
                    account_id=account_id,
                    amount=amount,
                    dedupe_id=f"deposit_{datetime.now(timezone.utc).isoformat()}",
                )
                
                if not result2:
                    logger.error(f"Failed to deposit {amount} to pot {target_id}")
                    return False
                
            elif source_id.startswith('pot_') and target_id.startswith('acc_'):
                # Pot to account transfer (withdraw from pot)
                result = self.monzo_client.withdraw_from_pot(
                    pot_id=source_id,
                    account_id=target_id,
                    amount=amount,
                    dedupe_id=f"withdraw_{datetime.now(timezone.utc).isoformat()}",
                )
                
                if not result:
                    logger.error(f"Failed to withdraw {amount} from pot {source_id}")
                    return False
                
            elif source_id.startswith('pot_') and target_id == "main_account":
                # Pot to main account transfer (withdraw from pot)
                # Get the main account ID
                accounts = self.monzo_client.get_accounts()
                if not accounts:
                    logger.error("No accounts found for main account transfer")
                    return False
                main_account_id = accounts[0].id
                
                result = self.monzo_client.withdraw_from_pot(
                    pot_id=source_id,
                    account_id=main_account_id,
                    amount=amount,
                    dedupe_id=f"withdraw_{datetime.now(timezone.utc).isoformat()}",
                )
                
                if not result:
                    logger.error(f"Failed to withdraw {amount} from pot {source_id} to main account")
                    return False
                
            else:
                logger.error(f"Unsupported transfer: {source_id} to {target_id}")
                return False

            # Log the transfer
            logger.info(f"Transfer successful: {amount} from {source_id} to {target_id}")
            return True

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return False

    def _is_rule_recently_executed(self, rule: TopupRule) -> bool:
        """Check if a rule was executed recently to prevent duplicate transfers."""
        try:
            if rule.last_executed is None:
                return False
            
            # Ensure last_executed is timezone-aware
            last_executed = rule.last_executed
            if last_executed.tzinfo is None:
                last_executed = last_executed.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            time_diff = (now - last_executed).total_seconds() / 60  # Convert to minutes
            
            # Consider rule recently executed if it was run within the last 5 minutes
            # This prevents multiple concurrent executions
            recently_executed = time_diff < 5
            
            if recently_executed:
                logger.info(f"Rule '{rule.name}' was executed {time_diff:.1f} minutes ago, considered recent")
            
            return recently_executed
        except Exception as e:
            logger.error(f"Error checking if rule {rule.rule_id} was recently executed: {e}")
            return False

    def _update_rule_execution_time(self, rule: TopupRule) -> bool:
        """Update the last execution time for a rule."""
        try:
            from app.automation.rules import RulesManager
            
            rules_manager = RulesManager(self.db)
            success = rules_manager.update_execution_time(rule.rule_id)
            
            if success:
                logger.info(f"Updated execution time for rule {rule.rule_id}")
            else:
                logger.warning(f"Failed to update execution time for rule {rule.rule_id}")
                
            return success
        except Exception as e:
            logger.error(f"Error updating execution time for rule {rule.rule_id}: {e}")
            return False

    def get_topup_rules(self, user_id: str) -> List[TopupRule]:
        """Get all topup rules for a user from the database."""
        try:
            from app.automation.rules import RulesManager
            
            rules_manager = RulesManager(self.db)
            automation_rules = rules_manager.get_rules_by_user(user_id, "auto_topup")
            
            topup_rules = []
            for rule in automation_rules:
                config = rule.config
                topup_rule = TopupRule(
                    rule_id=rule.rule_id,
                    name=rule.name,
                    user_id=user_id,
                    source_account_id=config.get("source_account_id"),
                    target_pot_id=config.get("target_pot_id"),
                    amount=config.get("amount"),
                    trigger_type=config.get("trigger_type", "monthly"),
                    trigger_day=config.get("trigger_day"),
                    trigger_hour=config.get("trigger_hour"),
                    trigger_minute=config.get("trigger_minute"),
                    trigger_interval=config.get("trigger_interval"),
                    min_balance=config.get("min_balance"),
                    target_balance=config.get("target_balance"),
                    last_executed=rule.last_executed,
                    enabled=rule.enabled,
                )
                topup_rules.append(topup_rule)
            
            return topup_rules
            
        except Exception as e:
            logger.error(f"Error getting topup rules for user {user_id}: {e}")
            return []

    def create_topup_rule(self, rule: TopupRule) -> bool:
        """Create a new topup rule in the database."""
        try:
            from app.automation.rules import RulesManager
            
            rules_manager = RulesManager(self.db)
            
            rule_data = {
                "rule_id": rule.rule_id,
                "user_id": rule.user_id,
                "rule_type": "auto_topup",
                "name": rule.name,
                "config": {
                    "source_account_id": rule.source_account_id,
                    "target_pot_id": rule.target_pot_id,
                    "amount": rule.amount,
                    "trigger_type": rule.trigger_type,
                    "trigger_day": rule.trigger_day,
                    "trigger_hour": rule.trigger_hour,
                    "trigger_minute": rule.trigger_minute,
                    "trigger_interval": rule.trigger_interval,
                    "min_balance": rule.min_balance,
                    "target_balance": rule.target_balance,
                },
                "enabled": rule.enabled,
            }
            
            created_rule = rules_manager.create_rule(rule_data)
            if created_rule:
                logger.info(f"Created topup rule: {rule.name}")
                return True
            else:
                logger.error(f"Failed to create topup rule: {rule.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating topup rule {rule.name}: {e}")
            return False

    def delete_topup_rule(self, rule_id: str, user_id: str) -> bool:
        """Delete a topup rule from the database."""
        try:
            from app.automation.rules import RulesManager
            
            rules_manager = RulesManager(self.db)
            success = rules_manager.delete_rule(rule_id)
            
            if success:
                logger.info(f"Deleted topup rule: {rule_id}")
            else:
                logger.warning(f"Failed to delete topup rule: {rule_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error deleting topup rule {rule_id}: {e}")
            return False

    def _sync_account_data(self, user_id: str) -> None:
        """Trigger account sync to ensure database has latest balance information."""
        trigger_account_sync(self.db, self.monzo_client, user_id, "topup")

    def create_topup_rule_from_config(self, config: Dict, user_id: str) -> TopupRule:
        """Create a TopupRule from configuration dictionary."""
        try:
            return TopupRule(
                rule_id=config.get("rule_id"),
                name=config.get("name"),
                user_id=user_id,
                source_account_id=config.get("source_account_id"),
                target_pot_id=config.get("target_pot_id"),
                amount=config.get("amount"),
                trigger_type=config.get("trigger_type", "monthly"),
                trigger_day=config.get("trigger_day"),
                trigger_hour=config.get("trigger_hour"),
                trigger_minute=config.get("trigger_minute"),
                trigger_interval=config.get("trigger_interval"),
                min_balance=config.get("min_balance"),
                target_balance=config.get("target_balance"),
                last_executed=config.get("last_executed"),
                enabled=config.get("enabled", True),
            )
        except Exception as e:
            logger.error(f"Error creating topup rule from config: {e}")
            raise


