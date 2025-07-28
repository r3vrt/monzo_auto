"""
Enhanced Pot Sweeps automation - Move money between pots and accounts based on advanced rules.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

from app.models import Account, Pot, Transaction, User
from app.monzo.client import MonzoClient
from .sync_utils import trigger_account_sync

logger = logging.getLogger(__name__)


class SweepStrategy(Enum):
    """Different strategies for determining how much to sweep from a pot."""

    FIXED_AMOUNT = "fixed_amount"  # Move a specific amount
    PERCENTAGE = "percentage"  # Move a percentage of balance
    REMAINING_BALANCE = "remaining_balance"  # Move everything except minimum
    ALL_AVAILABLE = "all_available"  # Move entire balance


class SweepTrigger(Enum):
    """Different trigger types for pot sweeps."""

    MANUAL = "manual"  # Manual execution only
    MONTHLY = "monthly"  # Monthly on specific day
    WEEKLY = "weekly"  # Weekly on specific day
    PAYDAY_DETECTION = "payday_detection"  # Based on salary deposits
    BALANCE_THRESHOLD = "balance_threshold"  # When source exceeds amount


@dataclass
class SweepSource:
    """Configuration for a single source in a pot sweep."""

    pot_name: str  # User-friendly pot name or "main_account" for main account balance
    strategy: SweepStrategy
    amount: Optional[int] = None  # For FIXED_AMOUNT strategy
    percentage: Optional[float] = None  # For PERCENTAGE strategy (0.0-1.0)
    min_balance: Optional[int] = None  # For REMAINING_BALANCE strategy
    priority: int = 0  # Execution order (lower = higher priority)
    
    @property
    def is_main_account(self) -> bool:
        """Check if this source is the main account balance."""
        return self.pot_name.lower() in ["main_account", "main account", "account", "main"]


@dataclass
class PotSweepRule:
    """Enhanced configuration for a pot sweep rule."""

    rule_id: Optional[str] = None
    name: Optional[str] = None
    user_id: Optional[str] = None
    trigger_type: SweepTrigger = SweepTrigger.MANUAL
    trigger_day: Optional[int] = None  # Day of month/week for triggers
    trigger_threshold: Optional[int] = None  # For BALANCE_THRESHOLD
    payday_threshold: Optional[int] = (
        50000  # Minimum amount for payday detection (£500 default)
    )
    payday_description_pattern: Optional[str] = None  # Description pattern for payday detection
    sources: List[SweepSource] = None
    target_pot_name: Optional[str] = None  # User-friendly pot name
    enabled: bool = True

    def __post_init__(self):
        if self.sources is None:
            self.sources = []


class PotSweeps:
    """Enhanced pot sweep operations with multiple sources and strategies."""

    def __init__(self, db: Session, monzo_client: MonzoClient):
        self.db = db
        self.monzo_client = monzo_client

    def _resolve_pot_name_to_id(self, user_id: str, pot_name: str) -> Optional[str]:
        """Resolve a pot name to its ID."""
        try:
            pot = (
                self.db.query(Pot)
                .filter_by(user_id=user_id, name=pot_name, deleted=0)
                .first()
            )

            if pot:
                return pot.id
            else:
                logger.error(f"Pot not found: {pot_name} for user {user_id}")
                return None

        except Exception as e:
            logger.error(f"Error resolving pot name {pot_name}: {e}")
            return None

    def _get_pot_name_from_id(self, user_id: str, pot_id: str) -> Optional[str]:
        """Get pot name from ID."""
        try:
            pot = (
                self.db.query(Pot)
                .filter_by(user_id=user_id, id=pot_id, deleted=0)
                .first()
            )

            if pot:
                return pot.name
            else:
                logger.error(f"Pot not found: {pot_id} for user {user_id}")
                return None

        except Exception as e:
            logger.error(f"Error getting pot name for {pot_id}: {e}")
            return None

    def get_available_pots(self, user_id: str) -> List[Dict[str, str]]:
        """Get list of available pots with names and IDs."""
        try:
            pots = self.db.query(Pot).filter_by(user_id=user_id, deleted=0).all()
            return [{"id": pot.id, "name": pot.name} for pot in pots]
        except Exception as e:
            logger.error(f"Error getting available pots: {e}")
            return []

    def execute_sweep_rule(self, user_id: str, rule: PotSweepRule) -> Dict[str, any]:
        """
        Execute a single sweep rule with multiple sources.

        Args:
            user_id: Monzo user ID
            rule: The sweep rule to execute

        Returns:
            Dict: Results of the sweep operation
        """
        try:
            logger.info(f"[SWEEP] Starting execution of sweep rule: {rule.name}")
            
            # Trigger account sync to ensure we have latest balance information
            self._sync_account_data(user_id)
            
            # Check if rule should be triggered
            if not self._should_trigger_sweep(rule, user_id):
                logger.info(f"[SWEEP] Sweep rule {rule.name} not triggered")
                return {"success": False, "reason": "not_triggered"}
            
            # Debug: Log the rule configuration
            logger.info(f"[SWEEP] Rule configuration: trigger_type={rule.trigger_type.value}, target_pot_name={rule.target_pot_name}")
            logger.info(f"[SWEEP] Sources: {[(s.pot_name, s.strategy.value, s.min_balance if s.strategy == SweepStrategy.REMAINING_BALANCE else None) for s in rule.sources]}")
            
            logger.info(f"[SWEEP] Sweep rule {rule.name} triggered, proceeding with execution")

            # Resolve target pot name to ID
            logger.info(f"[SWEEP] Resolving target pot: {rule.target_pot_name}")
            target_pot_id = self._resolve_pot_name_to_id(user_id, rule.target_pot_name)
            if not target_pot_id:
                logger.error(f"[SWEEP] Target pot not found: {rule.target_pot_name}")
                return {
                    "success": False,
                    "error": f"Target pot not found: {rule.target_pot_name}",
                }
            
            logger.info(f"[SWEEP] Target pot resolved: {rule.target_pot_name} -> {target_pot_id}")

            # Sort sources by priority
            sorted_sources = sorted(rule.sources, key=lambda s: s.priority)

            total_moved = 0
            results = {
                "success": True,
                "total_moved": 0,
                "sources_processed": [],
                "errors": [],
            }

            # Process each source
            logger.info(f"[SWEEP] Processing {len(sorted_sources)} sources")
            for source in sorted_sources:
                try:
                    logger.info(f"[SWEEP] Processing source: {source.pot_name} (strategy: {source.strategy.value})")
                    
                    # Handle main account balance differently
                    if source.is_main_account:
                        source_pot_id = None  # Not needed for main account
                        source_name = "Main Account"
                        logger.info(f"[SWEEP] Source is main account")
                    else:
                        # Resolve source pot name to ID
                        source_pot_id = self._resolve_pot_name_to_id(
                            user_id, source.pot_name
                        )
                        if not source_pot_id:
                            logger.error(f"[SWEEP] Source pot not found: {source.pot_name}")
                            results["errors"].append(
                                f"Source pot not found: {source.pot_name}"
                            )
                            continue
                        source_name = source.pot_name
                        logger.info(f"[SWEEP] Source pot resolved: {source.pot_name} -> {source_pot_id}")

                    source_result = self._process_sweep_source(
                        source, source_pot_id, target_pot_id, user_id
                    )
                    if source_result["success"]:
                        total_moved += source_result["amount"]
                        results["sources_processed"].append(
                            {
                                "pot_name": source_name,
                                "amount": source_result["amount"],
                                "strategy": source.strategy.value,
                            }
                        )
                        logger.info(
                            f"Successfully moved {source_result['amount']} from {source_name}"
                        )
                    else:
                        results["errors"].append(
                            f"Failed to process source {source_name}: {source_result['error']}"
                        )

                except Exception as e:
                    logger.error(f"Error processing source {source.pot_name}: {e}")
                    results["errors"].append(f"Error processing source {source.pot_name}: {e}")

            results["total_moved"] = total_moved
            logger.info(f"[SWEEP] Sweep rule {rule.name} completed. Total moved: {total_moved} ({total_moved/100:.2f}£)")
            return results

        except Exception as e:
            logger.error(f"Error executing sweep rule: {e}")
            return {"success": False, "error": str(e)}

    def _sync_account_data(self, user_id: str) -> None:
        """Trigger account sync to ensure database has latest balance information."""
        trigger_account_sync(self.db, self.monzo_client, user_id, "sweep")

    def _process_sweep_source(
        self, source: SweepSource, source_pot_id: str, target_pot_id: str, user_id: str
    ) -> Dict[str, any]:
        """Process a single sweep source according to its strategy."""
        try:
            # Handle main account balance differently
            if source.is_main_account:
                logger.info(f"[SWEEP] Processing main account source with strategy: {source.strategy.value}")
                
                # Get current main account balance
                account_balance = self._get_main_account_balance(user_id)
                if account_balance is None:
                    logger.error(f"[SWEEP] Could not get main account balance for user {user_id}")
                    return {"success": False, "error": "Could not get main account balance"}

                logger.info(f"[SWEEP] Main account balance: {account_balance} ({account_balance/100:.2f}£)")

                # Calculate amount to move based on strategy
                amount_to_move = self._calculate_sweep_amount(source, account_balance)
                logger.info(f"[SWEEP] Calculated amount to move: {amount_to_move} ({amount_to_move/100:.2f}£)")

                if amount_to_move <= 0:
                    logger.info(f"[SWEEP] No amount to move (amount_to_move: {amount_to_move})")
                    return {"success": False, "error": "No amount to move", "amount": 0}

                # Execute the transfer from main account
                success = self._transfer_from_main_account(
                    user_id=user_id,
                    target_pot_id=target_pot_id,
                    amount=amount_to_move,
                    description=f"Auto sweep: {source.strategy.value}",
                )

                if success:
                    logger.info(f"[SWEEP] Main account transfer successful: {amount_to_move} ({amount_to_move/100:.2f}£)")
                    return {"success": True, "amount": amount_to_move}
                else:
                    logger.error(f"[SWEEP] Main account transfer failed")
                    return {"success": False, "error": "Transfer from main account failed"}
            else:
                # Handle pot transfers (existing logic)
                # Get current pot balance
                pot_balance = self._get_pot_balance(source_pot_id)
                if pot_balance is None:
                    return {"success": False, "error": "Could not get pot balance"}

                # Calculate amount to move based on strategy
                amount_to_move = self._calculate_sweep_amount(source, pot_balance)

                if amount_to_move <= 0:
                    return {"success": False, "error": "No amount to move", "amount": 0}

                # Execute the transfer
                success = self._transfer_between_pots(
                    source_pot_id=source_pot_id,
                    target_pot_id=target_pot_id,
                    amount=amount_to_move,
                    description=f"Auto sweep: {source.strategy.value}",
                )

                if success:
                    return {"success": True, "amount": amount_to_move}
                else:
                    return {"success": False, "error": "Transfer failed"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calculate_sweep_amount(self, source: SweepSource, current_balance: int) -> int:
        """Calculate how much to sweep based on the strategy."""
        logger.info(f"[SWEEP] Calculating sweep amount for strategy: {source.strategy.value}")
        logger.info(f"[SWEEP] Current balance: {current_balance} ({current_balance/100:.2f}£)")
        
        if source.strategy == SweepStrategy.FIXED_AMOUNT:
            if source.amount is None:
                logger.info(f"[SWEEP] Fixed amount strategy: amount is None, returning 0")
                return 0
            amount_to_move = min(source.amount, current_balance)
            logger.info(f"[SWEEP] Fixed amount strategy: configured={source.amount} ({source.amount/100:.2f}£), current_balance={current_balance} ({current_balance/100:.2f}£), amount_to_move={amount_to_move} ({amount_to_move/100:.2f}£)")
            return amount_to_move

        elif source.strategy == SweepStrategy.PERCENTAGE:
            if source.percentage is None:
                logger.info(f"[SWEEP] Percentage strategy: percentage is None, returning 0")
                return 0
            amount_to_move = int(current_balance * source.percentage)
            logger.info(f"[SWEEP] Percentage strategy: percentage={source.percentage} ({source.percentage*100:.1f}%), current_balance={current_balance} ({current_balance/100:.2f}£), amount_to_move={amount_to_move} ({amount_to_move/100:.2f}£)")
            return amount_to_move

        elif source.strategy == SweepStrategy.REMAINING_BALANCE:
            if source.min_balance is None:
                logger.info(f"[SWEEP] Remaining balance strategy: min_balance is None, moving entire balance")
                return current_balance
            amount_to_move = max(0, current_balance - source.min_balance)
            logger.info(f"[SWEEP] Remaining balance strategy: min_balance={source.min_balance} ({source.min_balance/100:.2f}£), current_balance={current_balance} ({current_balance/100:.2f}£), amount_to_move={amount_to_move} ({amount_to_move/100:.2f}£)")
            return amount_to_move

        elif source.strategy == SweepStrategy.ALL_AVAILABLE:
            logger.info(f"[SWEEP] All available strategy: moving entire balance {current_balance} ({current_balance/100:.2f}£)")
            return current_balance

        logger.info(f"[SWEEP] Unknown strategy: {source.strategy}, returning 0")
        return 0

    def _should_trigger_sweep(self, rule: PotSweepRule, user_id: str) -> bool:
        """Determine if a sweep rule should be triggered."""
        logger.info(f"[SWEEP] Checking if rule '{rule.name}' should trigger (type: {rule.trigger_type.value})")
        
        if not rule.enabled:
            logger.info(f"[SWEEP] Rule '{rule.name}' is disabled")
            return False

        if rule.trigger_type == SweepTrigger.MANUAL:
            logger.info(f"[SWEEP] Rule '{rule.name}' is manual trigger (handled separately)")
            return False  # Manual triggers are handled separately

        elif rule.trigger_type == SweepTrigger.MONTHLY:
            today = datetime.now()
            should_trigger = today.day == rule.trigger_day
            logger.info(f"[SWEEP] Monthly trigger check: today.day={today.day}, trigger_day={rule.trigger_day}, should_trigger={should_trigger}")
            return should_trigger

        elif rule.trigger_type == SweepTrigger.WEEKLY:
            today = datetime.now()
            should_trigger = today.isoweekday() == rule.trigger_day  # 1=Monday, 7=Sunday
            logger.info(f"[SWEEP] Weekly trigger check: today.isoweekday()={today.isoweekday()}, trigger_day={rule.trigger_day}, should_trigger={should_trigger}")
            return should_trigger

        elif rule.trigger_type == SweepTrigger.PAYDAY_DETECTION:
            should_trigger = self._detect_payday(user_id, rule)
            logger.info(f"[SWEEP] Payday detection trigger check: should_trigger={should_trigger}")
            return should_trigger

        elif rule.trigger_type == SweepTrigger.BALANCE_THRESHOLD:
            if rule.trigger_threshold is None:
                logger.info(f"[SWEEP] Balance threshold trigger has no threshold configured")
                return False
            
            logger.info(f"[SWEEP] Checking balance threshold trigger: threshold={rule.trigger_threshold} ({rule.trigger_threshold/100:.2f}£)")
            
            # Check if any source exceeds the threshold
            for source in rule.sources:
                if source.is_main_account:
                    # Check main account balance
                    account_balance = self._get_main_account_balance(user_id)
                    if account_balance and account_balance >= rule.trigger_threshold:
                        logger.info(f"[SWEEP] Balance threshold triggered by main account: {account_balance} ({account_balance/100:.2f}£) >= {rule.trigger_threshold} ({rule.trigger_threshold/100:.2f}£)")
                        return True
                    else:
                        logger.info(f"[SWEEP] Main account balance {account_balance} ({account_balance/100:.2f}£ if not None) < threshold {rule.trigger_threshold} ({rule.trigger_threshold/100:.2f}£)")
                else:
                    # Check pot balance
                    source_pot_id = self._resolve_pot_name_to_id(user_id, source.pot_name)
                    if source_pot_id:
                        pot_balance = self._get_pot_balance(source_pot_id)
                        if pot_balance and pot_balance >= rule.trigger_threshold:
                            logger.info(f"[SWEEP] Balance threshold triggered by pot {source.pot_name}: {pot_balance} ({pot_balance/100:.2f}£) >= {rule.trigger_threshold} ({rule.trigger_threshold/100:.2f}£)")
                            return True
                        else:
                            logger.info(f"[SWEEP] Pot {source.pot_name} balance {pot_balance} ({pot_balance/100:.2f}£ if not None) < threshold {rule.trigger_threshold} ({rule.trigger_threshold/100:.2f}£)")
            
            logger.info(f"[SWEEP] No sources exceeded balance threshold")
            return False

        logger.info(f"[SWEEP] Unknown trigger type: {rule.trigger_type}")
        return False

    def _detect_payday(self, user_id: str, rule: PotSweepRule) -> bool:
        """Detect if today is payday based on recent salary deposits."""
        try:
            # Check if this sweep rule has already been executed recently
            # Get the rule from the database to check last_executed time
            from app.automation.rules import RulesManager
            rules_manager = RulesManager(self.db)
            db_rule = rules_manager.get_rule_by_id(rule.rule_id)
            
            if db_rule and db_rule.last_executed:
                # Check if the sweep was executed in the last 7 days
                # This prevents the sweep from running multiple times for the same payday
                seven_days_ago = datetime.now() - timedelta(days=7)
                
                # Ensure both datetimes are timezone-aware for comparison
                last_executed = db_rule.last_executed
                if last_executed.tzinfo is None:
                    last_executed = last_executed.replace(tzinfo=timezone.utc)
                
                if last_executed >= seven_days_ago:
                    logger.info(f"[SWEEP] Payday sweep rule '{rule.name}' already executed recently ({last_executed.strftime('%Y-%m-%d %H:%M:%S')}), skipping to prevent duplicate execution")
                    return False
            
            # Look for large positive transactions in the last 3 days
            three_days_ago = datetime.now() - timedelta(days=3)

            # Use the rule's configured threshold, or default to £500
            threshold = rule.payday_threshold or 50000

            # Build the query
            query = (
                self.db.query(Transaction)
                .filter(
                    Transaction.user_id == user_id,
                    Transaction.created >= three_days_ago,
                    Transaction.amount > 0,  # Positive transactions (income)
                    Transaction.amount > threshold,  # Use the configured threshold
                )
            )

            # Add description pattern filter if configured
            if rule.payday_description_pattern:
                pattern = rule.payday_description_pattern.strip()
                if pattern:
                    # Case-insensitive pattern matching
                    query = query.filter(
                        Transaction.description.ilike(f"%{pattern}%")
                    )

            recent_transactions = query.all()

            if recent_transactions:
                pattern_info = f" (pattern: '{rule.payday_description_pattern}')" if rule.payday_description_pattern else ""
                logger.info(
                    f"[SWEEP] Payday detected: {len(recent_transactions)} salary transactions found (threshold: £{threshold/100}){pattern_info}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error detecting payday: {e}")
            return False

    def _get_pot_balance(self, pot_id: str) -> Optional[int]:
        """Get current balance for a pot from live Monzo API with database fallback."""
        try:
            logger.info(f"[SWEEP] Getting live pot balance for {pot_id}")
            # Get live pot balance from Monzo API instead of stale database data
            try:
                # Get all pots for the user's accounts
                accounts = self.monzo_client.get_accounts()
                for account in accounts:
                    pots = self.monzo_client.get_pots(account.id)
                    for pot in pots:
                        if pot.id == pot_id:
                            balance = pot.balance
                            logger.info(f"[SWEEP] Live pot balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                            return balance
                
                # If pot not found in live data, fall back to database
                logger.warning(f"[SWEEP] Pot {pot_id} not found in live data, falling back to database")
                pot = self.db.query(Pot).filter_by(id=pot_id, deleted=0).first()
                if pot:
                    balance = pot.balance
                    logger.warning(f"[SWEEP] Using stale database balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error(f"[SWEEP] Pot not found in database: {pot_id}")
                    return None
            except Exception as e:
                logger.error(f"[SWEEP] Error getting live pot balance for {pot_id}: {e}")
                # Fall back to database
                pot = self.db.query(Pot).filter_by(id=pot_id, deleted=0).first()
                if pot:
                    balance = pot.balance
                    logger.warning(f"[SWEEP] Using stale database balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error(f"[SWEEP] Pot not found in database: {pot_id}")
                    return None
        except Exception as e:
            logger.error(f"[SWEEP] Error getting pot balance for {pot_id}: {e}")
            return None

    def _get_main_account_balance(self, user_id: str) -> Optional[int]:
        """Get current balance for the main account."""
        try:
            logger.info(f"[SWEEP] Getting live main account balance for user {user_id}")
            
            # Get all accounts from Monzo API to ensure we have live data
            accounts = self.monzo_client.get_accounts()
            if not accounts:
                logger.error(f"[SWEEP] No accounts found for user {user_id}")
                return None
            
            # Use the first account as the main account
            main_account = accounts[0]
            logger.info(f"[SWEEP] Using main account: {main_account.id}")
            
            # Get the live balance using the dedicated balance API
            balance_obj = self.monzo_client.get_balance(main_account.id)
            if balance_obj and hasattr(balance_obj, 'balance'):
                balance = balance_obj.balance
                logger.info(f"[SWEEP] Live main account balance for user {user_id}: {balance} ({balance/100:.2f}£)")
                return balance
            else:
                logger.error(f"[SWEEP] Invalid balance object returned for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"[SWEEP] Error getting main account balance for user {user_id}: {e}")
            return None

    def _transfer_from_main_account(
        self, user_id: str, target_pot_id: str, amount: int, description: str
    ) -> bool:
        """Transfer money from main account to a pot."""
        try:
            # Get the main account from Monzo API to ensure we have live data
            accounts = self.monzo_client.get_accounts()
            if not accounts:
                logger.error(f"[SWEEP] No accounts found for user {user_id}")
                return False
            
            # Use the first account as the main account
            main_account = accounts[0]
            logger.info(f"[SWEEP] Using main account for transfer: {main_account.id}")
            
            logger.info(f"[SWEEP] Attempting transfer from main account: {amount} ({amount/100:.2f}£) to pot {target_pot_id}")
            
            # Use Monzo API to deposit into pot from account
            result = self.monzo_client.deposit_to_pot(
                pot_id=target_pot_id,
                account_id=main_account.id,
                amount=amount,
                dedupe_id=f"sweep_main_{datetime.now().isoformat()}",
            )
            
            if result:
                logger.info(
                    f"[SWEEP] Transfer from main account successful: {amount} ({amount/100:.2f}£) to pot {target_pot_id}"
                )
                return True
            else:
                logger.error(f"[SWEEP] Transfer from main account failed: API returned None for pot {target_pot_id}")
                return False
            
        except Exception as e:
            logger.error(f"[SWEEP] Transfer from main account failed: {e}")
            return False

    def _transfer_between_pots(
        self, source_pot_id: str, target_pot_id: str, amount: int, description: str
    ) -> bool:
        """Transfer money between pots using Monzo API."""
        try:
            # Get the account ID for the transfer
            # We need to get the account ID from one of the pots
            source_pot = self.db.query(Pot).filter_by(id=source_pot_id).first()
            if not source_pot:
                logger.error(f"Source pot {source_pot_id} not found")
                return False

            account_id = source_pot.account_id

            # Use Monzo API to transfer between pots via account
            # First withdraw from source pot to account
            result = self.monzo_client.withdraw_from_pot(
                pot_id=source_pot_id,
                account_id=account_id,
                amount=amount,
                dedupe_id=f"sweep_{datetime.now().isoformat()}",
            )

            # Then deposit from account to target pot
            result2 = self.monzo_client.deposit_to_pot(
                pot_id=target_pot_id,
                account_id=account_id,
                amount=amount,
                dedupe_id=f"sweep_{datetime.now().isoformat()}",
            )

            logger.info(
                f"Transfer successful: {amount} from pot {source_pot_id} to pot {target_pot_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return False

    def create_sweep_rule_from_config(self, config: Dict, user_id: str) -> PotSweepRule:
        """Create a PotSweepRule from a configuration dictionary."""
        try:
            logger.info(f"[SWEEP] Creating sweep rule from config: {config}")
            
            # Parse sources
            sources = []
            for source_config in config.get("sources", []):
                logger.info(f"[SWEEP] Parsing source config: {source_config}")
                source = SweepSource(
                    pot_name=source_config[
                        "pot_name"
                    ],  # Use pot_name instead of pot_id
                    strategy=SweepStrategy(source_config["strategy"]),
                    amount=source_config.get("amount"),
                    percentage=source_config.get("percentage"),
                    min_balance=source_config.get("min_balance"),
                    priority=source_config.get("priority", 0),
                )
                logger.info(f"[SWEEP] Created source: pot_name={source.pot_name}, strategy={source.strategy.value}, amount={source.amount}, percentage={source.percentage}, min_balance={source.min_balance}")
                logger.info(f"[SWEEP] Source config details: {source_config}")
                logger.info(f"[SWEEP] Parsed source object: {source}")
                sources.append(source)

            # Create rule
            rule = PotSweepRule(
                trigger_type=SweepTrigger(config.get("trigger_type", "manual")),
                trigger_day=config.get("trigger_day"),
                trigger_threshold=config.get("trigger_threshold"),
                payday_threshold=config.get("payday_threshold"),
                payday_description_pattern=config.get("payday_description_pattern"),
                sources=sources,
                target_pot_name=config.get(
                    "target_pot_name"
                ),  # Use pot_name instead of pot_id
            )

            logger.info(f"[SWEEP] Created sweep rule: {rule}")
            logger.info(f"[SWEEP] Rule sources: {[f'{s.pot_name}:{s.strategy.value}:amount={s.amount}:min_balance={s.min_balance}' for s in rule.sources]}")

            return rule

        except Exception as e:
            logger.error(f"Error creating sweep rule from config: {e}")
            raise
