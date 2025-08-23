"""
Autosorter automation - Intelligent money distribution system.
Distributes funds from holding pot based on spending analysis and goals.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Account, BillsPotTransaction, Pot, Transaction, User
from app.monzo.client import MonzoClient
from .sync_utils import trigger_account_sync, trigger_bills_pot_transactions_sync

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Different trigger types for autosorter."""
    
    PAYDAY_DATE = "payday_date"  # Legacy: specific day of month
    TIME_OF_DAY = "time_of_day"  # Specific day and time
    TRANSACTION_BASED = "transaction_based"  # Based on specific transactions
    DATE_RANGE = "date_range"  # Range of days in month
    MANUAL_ONLY = "manual_only"  # Manual execution only


@dataclass
class TimeOfDayTrigger:
    """Configuration for time of day trigger."""
    
    day_of_month: int  # Day of month (1-31)
    hour: int = 9  # Hour (0-23)
    minute: int = 0  # Minute (0-59)


@dataclass
class TransactionTrigger:
    """Configuration for transaction-based trigger."""
    
    description_pattern: str  # Pattern to match in transaction description
    amount_min: Optional[int] = None  # Minimum amount in pence
    amount_max: Optional[int] = None  # Maximum amount in pence
    category: Optional[str] = None  # Transaction category
    merchant: Optional[str] = None  # Merchant name
    days_to_look_back: int = 3  # How many days back to look for matching transactions


@dataclass
class DateRangeTrigger:
    """Configuration for date range trigger."""
    
    start_day: int  # Start day of month (1-31)
    end_day: int  # End day of month (1-31)
    preferred_time: Optional[time] = None  # Preferred time within the range


@dataclass
class PotAllocation:
    """Configuration for pot allocation in autosorter."""

    pot_id: str
    pot_name: str
    allocation_type: str  # "bills_replenish", "priority", "goal", "investment"
    amount: Optional[int] = None  # Fixed amount for priority pots
    percentage: Optional[float] = None  # Percentage of available funds
    goal_amount: Optional[int] = None  # Target goal amount
    max_allocation: Optional[int] = None  # Maximum allocation limit
    priority: int = 0  # Priority order for allocation
    use_all_remaining: bool = False  # For "All remaining pots" option


@dataclass
class AutosorterConfig:
    """Configuration for autosorter execution."""

    holding_pot_id: str
    bills_pot_id: str
    priority_pots: List[PotAllocation]
    goal_pots: List[PotAllocation]
    investment_pots: List[PotAllocation]
    holding_reserve_amount: Optional[int] = None
    holding_reserve_percentage: Optional[float] = None
    min_holding_balance: int = 10000  # Minimum to keep in holding (£100)
    include_goal_pots: bool = True  # Toggle to include/exclude goal pots
    
    # Enhanced trigger configuration
    trigger_type: TriggerType = TriggerType.PAYDAY_DATE
    payday_date: int = 25  # Legacy: Day of month when payday occurs
    time_of_day_trigger: Optional[TimeOfDayTrigger] = None
    transaction_trigger: Optional[TransactionTrigger] = None
    date_range_trigger: Optional[DateRangeTrigger] = None


class Autosorter:
    """Intelligent money distribution system."""

    def __init__(self, db: Session, monzo_client: MonzoClient):
        self.db = db
        self.monzo_client = monzo_client

    def should_trigger_autosorter(self, user_id: str, config: AutosorterConfig) -> bool:
        """
        Check if the autosorter should be triggered based on the configuration.
        
        Args:
            user_id: Monzo user ID
            config: Autosorter configuration
            
        Returns:
            True if autosorter should be triggered, False otherwise
        """
        try:
            if config.trigger_type == TriggerType.PAYDAY_DATE:
                return self._check_payday_date_trigger(config)
            elif config.trigger_type == TriggerType.TIME_OF_DAY:
                return self._check_time_of_day_trigger(config)
            elif config.trigger_type == TriggerType.TRANSACTION_BASED:
                return self._check_transaction_trigger(user_id, config)
            elif config.trigger_type == TriggerType.DATE_RANGE:
                return self._check_date_range_trigger(config)
            else:
                logger.warning(f"[AUTOSORTER] Unknown trigger type: {config.trigger_type}")
                return False
        except Exception as e:
            logger.error(f"[AUTOSORTER] Error checking trigger: {e}")
            return False

    def _check_payday_date_trigger(self, config: AutosorterConfig) -> bool:
        """Check if today is the payday date."""
        today = datetime.now()
        return today.day == config.payday_date

    def _check_time_of_day_trigger(self, config: AutosorterConfig) -> bool:
        """Check if current time matches the time of day trigger."""
        if not config.time_of_day_trigger:
            return False
            
        now = datetime.now()
        trigger = config.time_of_day_trigger
        
        # Check if today is the trigger day
        if now.day != trigger.day_of_month:
            return False
            
        # Check if current time is within 1 hour of the trigger time
        trigger_time = time(trigger.hour, trigger.minute)
        current_time = now.time()
        
        # Calculate time difference in minutes
        current_minutes = current_time.hour * 60 + current_time.minute
        trigger_minutes = trigger_time.hour * 60 + trigger_time.minute
        
        time_diff = abs(current_minutes - trigger_minutes)
        
        # Allow 1 hour window for execution
        return time_diff <= 60

    def _check_transaction_trigger(self, user_id: str, config: AutosorterConfig) -> bool:
        """Check if a matching transaction has occurred recently."""
        if not config.transaction_trigger:
            return False
            
        trigger = config.transaction_trigger
        cutoff_date = datetime.now() - timedelta(days=trigger.days_to_look_back)
        
        # Build query for matching transactions
        query = self.db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.created >= cutoff_date,
            Transaction.amount > 0  # Only positive transactions (income)
        )
        
        # Add description pattern filter
        if trigger.description_pattern:
            query = query.filter(
                Transaction.description.ilike(f"%{trigger.description_pattern}%")
            )
            
        # Add amount range filters
        if trigger.amount_min is not None:
            query = query.filter(Transaction.amount >= trigger.amount_min)
        if trigger.amount_max is not None:
            query = query.filter(Transaction.amount <= trigger.amount_max)
            
        # Add category filter
        if trigger.category:
            query = query.filter(Transaction.category == trigger.category)
            
        # Add merchant filter
        if trigger.merchant:
            query = query.filter(Transaction.merchant.ilike(f"%{trigger.merchant}%"))
            
        # Check if any matching transactions exist
        matching_transactions = query.limit(1).all()
        return len(matching_transactions) > 0

    def _check_date_range_trigger(self, config: AutosorterConfig) -> bool:
        """Check if current date is within the specified range."""
        if not config.date_range_trigger:
            return False
            
        trigger = config.date_range_trigger
        today = datetime.now()
        
        # Handle month boundary cases
        if trigger.start_day <= trigger.end_day:
            # Normal case: 25-27
            return trigger.start_day <= today.day <= trigger.end_day
        else:
            # Month boundary case: 28-2 (28th to 2nd of next month)
            return today.day >= trigger.start_day or today.day <= trigger.end_day

    def validate_config(self, config: AutosorterConfig) -> Dict[str, Any]:
        """
        Validate autosorter configuration.
        
        Args:
            config: Autosorter configuration to validate
            
        Returns:
            Dict with validation results
        """
        errors = []
        warnings = []
        
        # Validate trigger configuration
        if config.trigger_type == TriggerType.TIME_OF_DAY:
            if not config.time_of_day_trigger:
                errors.append("time_of_day_trigger is required for TIME_OF_DAY trigger type")
            else:
                trigger = config.time_of_day_trigger
                if not (1 <= trigger.day_of_month <= 31):
                    errors.append("day_of_month must be between 1 and 31")
                if not (0 <= trigger.hour <= 23):
                    errors.append("hour must be between 0 and 23")
                if not (0 <= trigger.minute <= 59):
                    errors.append("minute must be between 0 and 59")
                    
        elif config.trigger_type == TriggerType.TRANSACTION_BASED:
            if not config.transaction_trigger:
                errors.append("transaction_trigger is required for TRANSACTION_BASED trigger type")
            else:
                trigger = config.transaction_trigger
                if not trigger.description_pattern and not trigger.merchant:
                    warnings.append("No description_pattern or merchant specified - may match too many transactions")
                if trigger.days_to_look_back < 1:
                    errors.append("days_to_look_back must be at least 1")
                if trigger.days_to_look_back > 30:
                    warnings.append("days_to_look_back is very high - may impact performance")
                    
        elif config.trigger_type == TriggerType.DATE_RANGE:
            if not config.date_range_trigger:
                errors.append("date_range_trigger is required for DATE_RANGE trigger type")
            else:
                trigger = config.date_range_trigger
                if not (1 <= trigger.start_day <= 31):
                    errors.append("start_day must be between 1 and 31")
                if not (1 <= trigger.end_day <= 31):
                    errors.append("end_day must be between 1 and 31")
                    
        # Validate pot configurations
        if not config.holding_pot_id:
            errors.append("holding_pot_id is required")
        if not config.bills_pot_id:
            errors.append("bills_pot_id is required")
            
        # Validate reserve configuration
        if config.holding_reserve_amount and config.holding_reserve_percentage:
            warnings.append("Both holding_reserve_amount and holding_reserve_percentage specified - amount takes precedence")
            
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def execute_distribution(
        self, user_id: str, config: AutosorterConfig
    ) -> Dict[str, Any]:
        """
        Execute the distribution of funds from holding pot to other pots.

        Args:
            user_id: Monzo user ID
            config: Autosorter configuration

        Returns:
            Dict: Results of the distribution
        """
        try:
            logger.info(f"[AUTOSORTER] Starting distribution for user {user_id}")

            # Trigger account sync to ensure we have latest balance information
            self._sync_account_data(user_id)

            # Ensure bills pot transactions are synced before calculating spending
            if config.bills_pot_id:
                try:
                    synced = trigger_bills_pot_transactions_sync(
                        self.db, self.monzo_client, user_id, config.bills_pot_id, module_name="autosorter"
                    )
                    if not synced:
                        logger.warning("[AUTOSORTER] Bills pot transaction sync did not complete successfully; proceeding with existing data")
                except Exception as e:
                    logger.error(f"[AUTOSORTER] Error syncing bills pot transactions: {e}")

            # Get current holding pot balance
            holding_balance = self._get_pot_balance(config.holding_pot_id)
            if holding_balance is None:
                return {"success": False, "error": "Could not get holding pot balance"}

            logger.info(f"[AUTOSORTER] Holding pot balance: £{holding_balance/100:.2f}")

            # Calculate bills spending from previous payday cycle
            bills_spending = self._calculate_bills_spending(
                user_id, config.bills_pot_id, config.payday_date
            )
            logger.info(
                f"[AUTOSORTER] Bills spending (since last payday): £{bills_spending/100:.2f}"
            )

            # Calculate total available for distribution
            available_amount = self._calculate_available_amount(holding_balance, config)
            logger.info(
                f"[AUTOSORTER] Available for distribution: £{available_amount/100:.2f}"
            )

            if available_amount <= 0:
                return {
                    "success": False,
                    "error": "No funds available for distribution",
                }

            # Execute distribution in priority order
            distribution_results = {
                "bills_replenish": 0,
                "priority_pots": {},
                "goal_pots": {},
                "investment_pots": {},
                "remaining_balance": holding_balance,
            }

            remaining_amount = available_amount

            # 1. Replenish bills pot
            if bills_spending > 0:
                bills_transfer = min(bills_spending, remaining_amount)
                success = self._transfer_to_pot(
                    config.holding_pot_id, config.bills_pot_id, bills_transfer
                )
                if success:
                    distribution_results["bills_replenish"] = bills_transfer
                    remaining_amount -= bills_transfer
                    distribution_results["remaining_balance"] -= bills_transfer
                    logger.info(
                        f"[AUTOSORTER] Replenished bills pot: £{bills_transfer/100:.2f}"
                    )

            # 2. Priority pots (fixed amounts, but respect existing goals)
            for priority_pot in config.priority_pots:
                if remaining_amount <= 0:
                    break

                # Get current pot balance
                current_balance = self._get_pot_balance(priority_pot.pot_id) or 0

                # Get pot goal (use existing pot goal if not specified)
                pot_goal = priority_pot.goal_amount
                if not pot_goal:
                    pot = self.db.query(Pot).filter_by(id=priority_pot.pot_id).first()
                    pot_goal = pot.goal if pot else None

                # Calculate how much can be transferred (convert to pence if needed)
                requested_amount = self._convert_to_pence(priority_pot.amount)

                # If pot has a goal, don't exceed it
                if pot_goal:
                    space_available = max(0, pot_goal - current_balance)
                    transfer_amount = min(
                        requested_amount, space_available, remaining_amount
                    )
                else:
                    transfer_amount = min(requested_amount, remaining_amount)

                if transfer_amount > 0:
                    success = self._transfer_to_pot(
                        config.holding_pot_id, priority_pot.pot_id, transfer_amount
                    )
                    if success:
                        distribution_results["priority_pots"][
                            priority_pot.pot_name
                        ] = transfer_amount
                        remaining_amount -= transfer_amount
                        distribution_results["remaining_balance"] -= transfer_amount
                        logger.info(
                            f"[AUTOSORTER] Priority pot {priority_pot.pot_name}: £{transfer_amount/100:.2f}"
                        )

                        # Log if goal was reached
                        if pot_goal and (current_balance + transfer_amount) >= pot_goal:
                            logger.info(
                                f"[AUTOSORTER] Priority pot {priority_pot.pot_name} reached its goal of £{pot_goal/100:.2f}"
                            )
                else:
                    logger.info(
                        f"[AUTOSORTER] Priority pot {priority_pot.pot_name}: No transfer (goal reached or no space)"
                    )

            # 3. Goal-based pots (split remaining funds, no single pot gets more than 20% of remaining)
            if config.include_goal_pots:
                goal_pots_allocated = self._allocate_goal_pots(
                    config.goal_pots, remaining_amount, config.holding_pot_id,
                    config.priority_pots, config.investment_pots
                )
                for pot_name, amount in goal_pots_allocated.items():
                    distribution_results["goal_pots"][pot_name] = amount
                    remaining_amount -= amount
                    distribution_results["remaining_balance"] -= amount
                logger.info(f"[AUTOSORTER] Goal pots allocation: {'enabled' if config.include_goal_pots else 'disabled'}")
            else:
                logger.info(f"[AUTOSORTER] Skipping goal pots allocation (disabled)")

            # 4. Investment pots (split remaining funds)
            investment_pots_allocated = self._allocate_investment_pots(
                config.investment_pots, remaining_amount, config.holding_pot_id
            )
            for pot_name, amount in investment_pots_allocated.items():
                distribution_results["investment_pots"][pot_name] = amount
                remaining_amount -= amount
                distribution_results["remaining_balance"] -= amount

            # Update remaining balance in results
            distribution_results["remaining_balance"] = remaining_amount

            total_distributed = available_amount - remaining_amount
            logger.info(
                f"[AUTOSORTER] Distribution completed: £{total_distributed/100:.2f} distributed, £{remaining_amount/100:.2f} remaining"
            )

            return {
                "success": True,
                "distribution": distribution_results,
                "total_distributed": total_distributed,
            }

        except Exception as e:
            logger.error(f"[AUTOSORTER] Error during distribution: {e}")
            return {"success": False, "error": str(e)}

    def _sync_account_data(self, user_id: str) -> None:
        """Trigger account sync to ensure database has latest balance information."""
        trigger_account_sync(self.db, self.monzo_client, user_id, "autosorter")

    def _calculate_bills_spending(
        self, user_id: str, bills_pot_id: str, payday_date: int
    ) -> int:
        """Calculate total spending from bills pot since last payday using dedicated BillsPotTransaction table."""
        try:
            # Calculate the last payday date
            today = datetime.now()
            if today.day >= payday_date:
                # Payday has already occurred this month
                last_payday = today.replace(day=payday_date)
            else:
                # Payday hasn't occurred yet, go back to previous month
                if today.month == 1:
                    last_payday = today.replace(
                        year=today.year - 1, month=12, day=payday_date
                    )
                else:
                    last_payday = today.replace(month=today.month - 1, day=payday_date)

            # Get all outgoing transactions from the bills pot since last payday
            # Using the new dedicated BillsPotTransaction table for accurate calculations
            outgoing_transactions = (
                self.db.query(BillsPotTransaction)
                .filter(
                    and_(
                        BillsPotTransaction.bills_pot_id == bills_pot_id,
                        BillsPotTransaction.user_id == user_id,
                        BillsPotTransaction.created >= last_payday,
                        BillsPotTransaction.amount < 0,  # Outgoing transactions
                    )
                )
                .all()
            )

            logger.info(
                f"[AUTOSORTER] Found {len(outgoing_transactions)} outgoing transactions for bills pot since {last_payday.strftime('%Y-%m-%d')}"
            )

            # Calculate total spending from bills pot
            bills_spending = sum(abs(t.amount) for t in outgoing_transactions)

            # Log breakdown by transaction type for debugging
            subscription_count = sum(
                1 for t in outgoing_transactions if t.transaction_type == "subscription"
            )
            pot_transfer_count = sum(
                1 for t in outgoing_transactions if t.transaction_type == "pot_transfer"
            )
            actual_withdrawal_count = sum(
                1 for t in outgoing_transactions if t.is_pot_withdrawal
            )

            subscription_total = sum(
                abs(t.amount)
                for t in outgoing_transactions
                if t.transaction_type == "subscription"
            )
            pot_transfer_total = sum(
                abs(t.amount)
                for t in outgoing_transactions
                if t.transaction_type == "pot_transfer"
            )
            actual_withdrawal_total = sum(
                abs(t.amount) for t in outgoing_transactions if t.is_pot_withdrawal
            )

            logger.info(
                f"[AUTOSORTER] Bills spending breakdown since {last_payday.strftime('%Y-%m-%d')}:"
            )
            logger.info(f"  - Total: £{bills_spending/100:.2f}")
            logger.info(
                f"  - Subscriptions: £{subscription_total/100:.2f} ({subscription_count} transactions)"
            )
            logger.info(
                f"  - Pot transfers: £{pot_transfer_total/100:.2f} ({pot_transfer_count} transactions)"
            )
            logger.info(
                f"  - Actual withdrawals: £{actual_withdrawal_total/100:.2f} ({actual_withdrawal_count} transactions)"
            )

            return bills_spending

        except Exception as e:
            logger.error(f"[AUTOSORTER] Error calculating bills spending: {e}")
            return 0

    def _convert_to_pence(self, amount) -> int:
        """Convert amount to pence, handling both pence and pounds formats."""
        if amount is None:
            return 0
        
        # Check for NaN values
        if isinstance(amount, float) and (amount != amount):  # NaN check
            logger.warning(f"[AUTOSORTER] NaN value detected in amount conversion, returning 0")
            return 0
        
        # If amount is a float or has decimal places, assume it's in pounds
        if isinstance(amount, float) or (isinstance(amount, int) and amount < 1000):
            # Assume it's in pounds, convert to pence
            try:
                return int(amount * 100)
            except (ValueError, OverflowError) as e:
                logger.error(f"[AUTOSORTER] Error converting amount {amount} to pence: {e}")
                return 0
        else:
            # Assume it's already in pence
            try:
                return int(amount)
            except (ValueError, OverflowError) as e:
                logger.error(f"[AUTOSORTER] Error converting amount {amount} to pence: {e}")
                return 0

    def _calculate_available_amount(
        self, holding_balance: int, config: AutosorterConfig
    ) -> int:
        """Calculate how much is available for distribution."""
        # Calculate holding reserve
        reserve_amount = 0
        if config.holding_reserve_amount:
            reserve_amount = self._convert_to_pence(config.holding_reserve_amount)
        elif config.holding_reserve_percentage and not (isinstance(config.holding_reserve_percentage, float) and (config.holding_reserve_percentage != config.holding_reserve_percentage)):
            # Check for NaN values in percentage
            try:
                # Percentage is now stored as decimal (0.01-1.0), so no need to divide by 100
                reserve_amount = int(
                    holding_balance * config.holding_reserve_percentage
                )
            except (ValueError, OverflowError) as e:
                logger.error(f"[AUTOSORTER] Error calculating holding reserve percentage: {e}")
                reserve_amount = 0

        # Use the higher of calculated reserve or minimum balance
        min_balance = self._convert_to_pence(config.min_holding_balance)
        reserve_amount = max(reserve_amount, min_balance)

        return max(0, holding_balance - reserve_amount)

    def _allocate_goal_pots(
        self, goal_pots: List[PotAllocation], available_amount: int, source_pot_id: str, 
        priority_pots: List[PotAllocation], investment_pots: List[PotAllocation]
    ) -> Dict[str, int]:
        """Allocate funds to goal-based pots automatically cycling through unselected pots."""
        allocated = {}
        remaining = available_amount

        # Get all pots that are already allocated in priority and investment sections
        allocated_pot_ids = set()
        for pot in priority_pots:
            allocated_pot_ids.add(pot.pot_id)
        for pot in investment_pots:
            allocated_pot_ids.add(pot.pot_id)

        # Get all pots with goals that aren't already allocated elsewhere
        pots_with_goals = (
            self.db.query(Pot)
            .filter(
                and_(
                    Pot.goal > 0, 
                    Pot.deleted == 0,
                    ~Pot.id.in_(allocated_pot_ids)  # Exclude already allocated pots
                )
            )
            .all()
        )

        if not pots_with_goals:
            logger.info("[AUTOSORTER] No unallocated pots with goals found")
            return allocated

        # Calculate allocation per pot (equal distribution with 20% max per pot)
        max_per_pot = int(available_amount * 0.20)  # 20% limit per pot
        total_allocated = 0

        for pot in pots_with_goals:
            if total_allocated >= available_amount:
                break

            # Calculate how much more is needed to reach goal
            needed_amount = max(0, pot.goal - pot.balance)

            if needed_amount > 0:
                # Allocate up to the needed amount, respecting the 20% per pot limit
                allocation = min(
                    needed_amount, 
                    max_per_pot, 
                    available_amount - total_allocated
                )

                success = self._transfer_to_pot(source_pot_id, pot.id, allocation)
                if success:
                    allocated[pot.name] = allocation
                    total_allocated += allocation
                    logger.info(
                        f"[AUTOSORTER] Goal pot {pot.name}: £{allocation/100:.2f}"
                    )

        return allocated



    def _allocate_investment_pots(
        self,
        investment_pots: List[PotAllocation],
        available_amount: int,
        source_pot_id: str,
    ) -> Dict[str, int]:
        """Allocate remaining funds to investment pots."""
        allocated = {}
        remaining = available_amount

        logger.info(f"[AUTOSORTER] Starting investment pot allocation with £{available_amount/100:.2f} available")
        logger.info(f"[AUTOSORTER] Investment pots configuration: {len(investment_pots)} pots")
        for pot in investment_pots:
            logger.info(f"[AUTOSORTER] Investment pot config: {pot.pot_name} - percentage: {pot.percentage}, amount: {pot.amount}, goal_amount: {pot.goal_amount}")

        # Sort by priority
        sorted_pots = sorted(investment_pots, key=lambda p: p.priority, reverse=True)

        # First pass: calculate initial allocations
        initial_allocations = {}
        for investment_pot in sorted_pots:
            # Get current pot balance
            current_balance = self._get_pot_balance(investment_pot.pot_id) or 0
            logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: current balance £{current_balance/100:.2f}")

            # Calculate initial allocation
            if investment_pot.percentage and not (isinstance(investment_pot.percentage, float) and (investment_pot.percentage != investment_pot.percentage)):
                # Check for NaN values in percentage
                try:
                    # Percentage is now stored as decimal (0.01-1.0), so no need to divide by 100
                    allocation = int(available_amount * investment_pot.percentage)
                    logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: percentage allocation £{allocation/100:.2f} (percentage: {investment_pot.percentage})")
                except (ValueError, OverflowError, ZeroDivisionError) as e:
                    logger.error(f"[AUTOSORTER] Error calculating percentage allocation: {e}")
                    allocation = 0
            elif investment_pot.amount:
                try:
                    allocation = min(investment_pot.amount, available_amount)
                    logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: amount allocation £{allocation/100:.2f} (amount: £{investment_pot.amount/100:.2f})")
                except (ValueError, TypeError) as e:
                    logger.error(f"[AUTOSORTER] Error calculating amount allocation: {e}")
                    allocation = 0
            else:
                # Equal distribution among remaining investment pots
                try:
                    allocation = available_amount // len(sorted_pots) if sorted_pots else 0
                    logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: equal distribution £{allocation/100:.2f}")
                except (ValueError, ZeroDivisionError) as e:
                    logger.error(f"[AUTOSORTER] Error calculating equal distribution: {e}")
                    allocation = 0

            # Apply maximum allocation limit
            if investment_pot.max_allocation:
                allocation = min(allocation, investment_pot.max_allocation)
                logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: limited by max_allocation to £{allocation/100:.2f}")

            # Don't exceed goal amount (use existing pot goal if not specified)
            pot_goal = investment_pot.goal_amount
            if not pot_goal:
                pot = self.db.query(Pot).filter_by(id=investment_pot.pot_id).first()
                pot_goal = pot.goal if pot else None

            if pot_goal:
                original_allocation = allocation
                allocation = min(allocation, max(0, pot_goal - current_balance))
                if allocation != original_allocation:
                    logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: limited by goal from £{original_allocation/100:.2f} to £{allocation/100:.2f} (goal: £{pot_goal/100:.2f}, current: £{current_balance/100:.2f})")
            else:
                logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: no goal set")

            initial_allocations[investment_pot.pot_id] = allocation
            logger.info(f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: final initial allocation £{allocation/100:.2f}")

        # Second pass: redistribute unused funds
        total_allocated = sum(initial_allocations.values())
        unused_funds = available_amount - total_allocated

        if unused_funds > 0:
            # Find pots that haven't reached their goals
            eligible_pots = []
            for investment_pot in sorted_pots:
                current_balance = self._get_pot_balance(investment_pot.pot_id) or 0

                # Get pot goal from allocation configuration
                pot_goal = investment_pot.goal_amount
                if not pot_goal:
                    pot = self.db.query(Pot).filter_by(id=investment_pot.pot_id).first()
                    pot_goal = pot.goal if pot else None

                pot_goal_display = f"£{pot_goal/100:.2f}" if pot_goal else "None"
                logger.info(f"[AUTOSORTER] Redistribution check for {investment_pot.pot_name}: current_balance=£{current_balance/100:.2f}, pot_goal={pot_goal_display}, initial_allocation=£{initial_allocations[investment_pot.pot_id]/100:.2f}")

                if pot_goal:
                    space_remaining = max(
                        0,
                        pot_goal
                        - current_balance
                        - initial_allocations[investment_pot.pot_id],
                    )
                    logger.info(f"[AUTOSORTER] {investment_pot.pot_name}: space_remaining=£{space_remaining/100:.2f}")
                else:
                    space_remaining = float("inf")  # No goal limit
                    logger.info(f"[AUTOSORTER] {investment_pot.pot_name}: no goal limit (space_remaining=inf)")

                if space_remaining > 0:
                    eligible_pots.append((investment_pot, space_remaining))
                    logger.info(f"[AUTOSORTER] {investment_pot.pot_name}: added to eligible pots")
                else:
                    logger.info(f"[AUTOSORTER] {investment_pot.pot_name}: NOT eligible (no space remaining)")

            # Distribute unused funds among eligible pots
            if eligible_pots:
                # Sort by priority and remaining space
                eligible_pots.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)

                # Separate pots with goals from pots without goals
                pots_with_goals = [(pot, space) for pot, space in eligible_pots if space != float("inf")]
                pots_without_goals = [(pot, space) for pot, space in eligible_pots if space == float("inf")]
                
                # Phase 1: Try to fill pots with goals first
                if pots_with_goals:
                    total_finite_space = sum(space for _, space in pots_with_goals)
                    
                    for investment_pot, space_remaining in pots_with_goals:
                        if unused_funds <= 0:
                            break

                        # Distribute proportionally among pots with goals
                        if total_finite_space > 0:
                            try:
                                additional_allocation = min(
                                    int(unused_funds * space_remaining / total_finite_space),
                                    space_remaining,
                                    unused_funds,
                                )
                                initial_allocations[
                                    investment_pot.pot_id
                                ] += additional_allocation
                                unused_funds -= additional_allocation
                                logger.info(f"[AUTOSORTER] Added £{additional_allocation/100:.2f} to pot with goal: {investment_pot.pot_name}")
                            except (ValueError, OverflowError, ZeroDivisionError) as e:
                                logger.error(f"[AUTOSORTER] Error calculating additional allocation: {e}")
                                # Skip this allocation if there's an error
                                pass
                
                # Phase 2: Give any remaining funds to pots without goals
                if pots_without_goals and unused_funds > 0:
                    # Give all remaining funds to the highest priority pot without a goal
                    for investment_pot, space_remaining in pots_without_goals:
                        if unused_funds > 0:
                            initial_allocations[investment_pot.pot_id] += unused_funds
                            logger.info(f"[AUTOSORTER] Giving remaining £{unused_funds/100:.2f} to pot without goal: {investment_pot.pot_name}")
                            unused_funds = 0
                            break

        # Third pass: execute transfers
        for investment_pot in sorted_pots:
            allocation = initial_allocations[investment_pot.pot_id]
            if allocation > 0:
                success = self._transfer_to_pot(
                    source_pot_id, investment_pot.pot_id, allocation
                )
                if success:
                    allocated[investment_pot.pot_name] = allocation
                    logger.info(
                        f"[AUTOSORTER] Investment pot {investment_pot.pot_name}: £{allocation/100:.2f}"
                    )

        return allocated

    def _get_pot_balance(self, pot_id: str) -> Optional[int]:
        """Get current balance of a pot from live Monzo API with database fallback."""
        try:
            logger.info(f"[AUTOSORTER] Getting live pot balance for {pot_id}")
            # Get live pot balance from Monzo API instead of stale database data
            try:
                # Get all pots for the user's accounts
                accounts = self.monzo_client.get_accounts()
                for account in accounts:
                    pots = self.monzo_client.get_pots(account.id)
                    for pot in pots:
                        if pot.id == pot_id:
                            balance = pot.balance
                            logger.info(f"[AUTOSORTER] Live pot balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                            return balance
                
                # If pot not found in live data, fall back to database
                logger.warning(f"[AUTOSORTER] Pot {pot_id} not found in live data, falling back to database")
                pot = self.db.query(Pot).filter_by(id=pot_id).first()
                if pot:
                    balance = pot.balance
                    logger.warning(f"[AUTOSORTER] Using stale database balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error(f"[AUTOSORTER] Pot not found in database: {pot_id}")
                    return None
            except Exception as e:
                logger.error(f"[AUTOSORTER] Error getting live pot balance for {pot_id}: {e}")
                # Fall back to database
                pot = self.db.query(Pot).filter_by(id=pot_id).first()
                if pot:
                    balance = pot.balance
                    logger.warning(f"[AUTOSORTER] Using stale database balance for {pot_id}: {balance} ({balance/100:.2f}£)")
                    return balance
                else:
                    logger.error(f"[AUTOSORTER] Pot not found in database: {pot_id}")
                    return None
        except Exception as e:
            logger.error(f"[AUTOSORTER] Error getting pot balance: {e}")
            return None

    def _transfer_to_pot(self, from_pot_id: str, to_pot_id: str, amount: int) -> bool:
        """Transfer money between pots using Monzo API."""
        try:
            # Get the account ID for the transfer
            # We need to get the account ID from one of the pots
            from_pot = self.db.query(Pot).filter_by(id=from_pot_id).first()
            if not from_pot:
                logger.error(f"[AUTOSORTER] Source pot {from_pot_id} not found")
                return False

            account_id = from_pot.account_id

            # Generate unique dedupe_id for this transfer
            dedupe_id = f"autosorter_{datetime.now(timezone.utc).isoformat()}_{from_pot_id}_{to_pot_id}"

            # Use Monzo API to transfer between pots via account
            # First withdraw from source pot to account
            result1 = self.monzo_client.withdraw_from_pot(
                from_pot_id, 
                account_id, 
                amount, 
                dedupe_id=f"{dedupe_id}_withdraw"
            )
            
            if not result1:
                logger.error(f"[AUTOSORTER] Failed to withdraw from pot {from_pot_id}")
                return False

            # Then deposit from account to destination pot
            result2 = self.monzo_client.deposit_to_pot(
                to_pot_id, 
                account_id, 
                amount, 
                dedupe_id=f"{dedupe_id}_deposit"
            )
            
            if not result2:
                logger.error(f"[AUTOSORTER] Failed to deposit to pot {to_pot_id}")
                return False

            # Update local database
            self._update_pot_balances(from_pot_id, to_pot_id, amount)

            logger.info(
                f"[AUTOSORTER] Successfully transferred £{amount/100:.2f} from {from_pot_id} to {to_pot_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[AUTOSORTER] Transfer error: {e}")
            return False

    def _update_pot_balances(
        self, from_pot_id: str, to_pot_id: str, amount: int
    ) -> None:
        """Update pot balances in local database."""
        try:
            # Update source pot
            from_pot = self.db.query(Pot).filter_by(id=from_pot_id).first()
            if from_pot:
                from_pot.balance -= amount

            # Update destination pot
            to_pot = self.db.query(Pot).filter_by(id=to_pot_id).first()
            if to_pot:
                to_pot.balance += amount

            self.db.commit()

        except Exception as e:
            logger.error(f"[AUTOSORTER] Error updating pot balances: {e}")
            self.db.rollback()
