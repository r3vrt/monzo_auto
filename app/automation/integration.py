"""
Automation Integration - Handles automation execution after sync operations.
"""

import logging
from datetime import datetime, timezone, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Account, Pot, Transaction, User
from app.monzo.client import MonzoClient

from .auto_topup import AutoTopup, TopupRule
from .autosorter import Autosorter, AutosorterConfig, PotAllocation
from .pot_manager import PotManager
from .pot_sweeps import PotSweepRule, PotSweeps
from .rules import AutomationRule, RulesManager
from .autosorter import TriggerType, TimeOfDayTrigger, TransactionTrigger, DateRangeTrigger
from .queue_manager import get_queue_manager, determine_rule_priority, determine_dependencies, ExecutionPriority

# Import monitoring/alerting functions
try:
    from app.ui.monitoring import send_failure_alert
except ImportError:
    # Fallback if monitoring module isn't available
    def send_failure_alert(rule_name: str, rule_type: str, error_message: str, user_id: str) -> bool:
        return False

logger = logging.getLogger(__name__)


class AutomationIntegration:
    """
    Integrates automation features with the sync process.

    This class handles triggering automation rules after successful data syncs,
    ensuring that automation logic runs on fresh data.
    """

    def __init__(self, db: Session, monzo_client: MonzoClient):
        self.db = db
        self.monzo_client = monzo_client
        self.rules_manager = RulesManager(db)
        self.pot_manager = PotManager(db, monzo_client)

        # Initialize automation components
        self.pot_sweeps = PotSweeps(db, monzo_client)
        self.autosorter = Autosorter(db, monzo_client)
        self.auto_topup = AutoTopup(db, monzo_client)

    def execute_post_sync_automation(
        self, user_id: str, account_id: str = None, force_manual: bool = False
    ) -> Dict[str, Any]:
        """
        Execute automation rules after a successful sync using the queue system.

        Args:
            user_id: Monzo user ID
            account_id: Monzo account ID
            force_manual: Force manual execution of rules

        Returns:
            Dict containing execution results for each automation type
        """
        logger.info(
            f"[AUTOMATION] Starting post-sync automation for user {user_id}" + (f", account {account_id}" if account_id else "")
        )

        results = {
            "pot_sweeps": {"executed": 0, "success": 0, "errors": []},
            "autosorter": {"executed": 0, "success": 0, "errors": []},
            "auto_topup": {"executed": 0, "success": 0, "errors": []},
            "queued": 0,
            "queue_status": {}
        }

        try:
            # Get enabled automation rules for this user
            try:
                enabled_rules = self.rules_manager.get_enabled_rules(user_id)
            except Exception as e:
                logger.error(f"[AUTOMATION] Error getting enabled rules: {e}")
                try:
                    self.db.rollback()
                except Exception:
                    pass
                return results

            if not enabled_rules:
                logger.info(
                    f"[AUTOMATION] No enabled automation rules found for user {user_id}"
                )
                return results

            logger.info(
                f"[AUTOMATION] Found {len(enabled_rules)} enabled rules for user {user_id}"
            )

            # Get queue manager
            queue_manager = get_queue_manager()
            
            # Queue rules for execution based on their type and priority
            queued_rules = []
            
            for rule in enabled_rules:
                try:
                    # Determine if rule should be executed
                    should_queue = self._should_queue_rule(rule, force_manual)
                    
                    if should_queue:
                        # Determine priority and dependencies
                        trigger_type = rule.config.get('trigger_type', 'manual')
                        priority = determine_rule_priority(rule.rule_type, trigger_type, rule.config)
                        dependencies = determine_dependencies(rule.rule_type, trigger_type, rule.config)
                        
                        # Determine trigger reason
                        trigger_reason = self._determine_trigger_reason(rule, force_manual)
                        
                        # Determine the appropriate account for this rule based on pots involved
                        rule_account_id = self._determine_rule_account(rule, user_id, account_id)
                        
                        # Add to queue
                        success = queue_manager.add_rule_execution(
                            rule_id=rule.rule_id,
                            user_id=user_id,
                            account_id=rule_account_id,
                            rule_type=rule.rule_type,
                            priority=priority,
                            depends_on=dependencies,
                            metadata={
                                "trigger_type": trigger_type,
                                "force_manual": force_manual,
                                "rule_name": rule.name
                            },
                            trigger_reason=trigger_reason
                        )
                        
                        if success:
                            queued_rules.append(rule)
                            results["queued"] += 1
                            logger.info(f"[AUTOMATION] Queued rule {rule.rule_id} ({rule.rule_type}) with priority {priority.name} - trigger_type: {trigger_type}")
                        else:
                            logger.warning(f"[AUTOMATION] Failed to queue rule {rule.rule_id}")
                    
                except Exception as e:
                    logger.error(f"[AUTOMATION] Error queuing rule {rule.rule_id}: {e}")
                    results["errors"] = results.get("errors", [])
                    results["errors"].append(f"Error queuing rule {rule.rule_id}: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"[AUTOMATION] Error queuing rule {rule.rule_id}: {e}")
                    results["errors"] = results.get("errors", [])
                    results["errors"].append(f"Error queuing rule {rule.rule_id}: {str(e)}")

            # Get queue status
            results["queue_status"] = queue_manager.get_queue_status()
            
            # Handle automation_trigger rules after other rules are queued
            # Skip automation_trigger rules during manual execution to prevent double execution
            if not force_manual:
                self._queue_automation_trigger_rules(user_id, enabled_rules, force_manual)
            else:
                logger.info(f"[AUTOMATION] Skipping automation_trigger rules during manual execution to prevent double execution")
            
            logger.info(
                f"[AUTOMATION] Queued {results['queued']} rules for execution. Queue status: {results['queue_status']}"
            )

        except Exception as e:
            logger.error(
                f"[AUTOMATION] Error during post-sync automation for user {user_id}: {e}"
            )
            results["error"] = str(e)

        return results

    def _determine_rule_account(self, rule: AutomationRule, user_id: str, default_account_id: str = None) -> str:
        """
        Determine the appropriate account for a rule based on the pots involved.
        
        Args:
            rule: The automation rule
            user_id: Monzo user ID
            default_account_id: Default account ID to use if no pots are involved
            
        Returns:
            str: Account ID to use for this rule
        """
        try:
            if rule.rule_type == "pot_sweep":
                # For sweep rules, check source and target pots
                config = rule.config if hasattr(rule, "config") else {}
                
                # Get target pot account
                target_pot_name = config.get("target_pot_name")
                if target_pot_name:
                    target_pot = self.db.query(Pot).filter_by(
                        user_id=user_id, 
                        name=target_pot_name, 
                        deleted=0
                    ).first()
                    if target_pot:
                        logger.info(f"[AUTOMATION] Using account {target_pot.account_id} for sweep rule {rule.rule_id} (target pot: {target_pot_name})")
                        return target_pot.account_id
                
                # Check source pots
                sources = config.get("sources", [])
                for source in sources:
                    if not source.get("pot_name", "").lower() in ["main_account", "main account", "account", "main"]:
                        source_pot = self.db.query(Pot).filter_by(
                            user_id=user_id, 
                            name=source["pot_name"], 
                            deleted=0
                        ).first()
                        if source_pot:
                            logger.info(f"[AUTOMATION] Using account {source_pot.account_id} for sweep rule {rule.rule_id} (source pot: {source['pot_name']})")
                            return source_pot.account_id
            
            elif rule.rule_type == "autosorter":
                # For autosorter rules, check pot allocations
                config = rule.config if hasattr(rule, "config") else {}
                pot_allocations = config.get("pot_allocations", [])
                
                for allocation in pot_allocations:
                    pot_name = allocation.get("pot_name")
                    if pot_name:
                        pot = self.db.query(Pot).filter_by(
                            user_id=user_id, 
                            name=pot_name, 
                            deleted=0
                        ).first()
                        if pot:
                            logger.info(f"[AUTOMATION] Using account {pot.account_id} for autosorter rule {rule.rule_id} (target pot: {pot_name})")
                            return pot.account_id
            
            elif rule.rule_type == "auto_topup":
                # For auto topup rules, check target pot
                config = rule.config if hasattr(rule, "config") else {}
                target_pot_name = config.get("target_pot_name")
                if target_pot_name:
                    pot = self.db.query(Pot).filter_by(
                        user_id=user_id, 
                        name=target_pot_name, 
                        deleted=0
                    ).first()
                    if pot:
                        logger.info(f"[AUTOMATION] Using account {pot.account_id} for auto topup rule {rule.rule_id} (target pot: {target_pot_name})")
                        return pot.account_id
            
            # Fall back to default account or first available account
            if default_account_id:
                logger.info(f"[AUTOMATION] Using default account {default_account_id} for rule {rule.rule_id}")
                return default_account_id
            
            # Get first available account
            first_account = self.db.query(Account).filter_by(user_id=user_id, is_active=True).first()
            if first_account:
                logger.info(f"[AUTOMATION] Using first available account {first_account.id} for rule {rule.rule_id}")
                return str(first_account.id)
            
            logger.warning(f"[AUTOMATION] No account found for rule {rule.rule_id}")
            return ""
            
        except Exception as e:
            logger.error(f"[AUTOMATION] Error determining account for rule {rule.rule_id}: {e}")
            return default_account_id or ""

    def _determine_trigger_reason(self, rule: AutomationRule, force_manual: bool = False) -> str:
        """
        Determine the reason why a rule is being triggered.
        
        Args:
            rule: The automation rule
            force_manual: Whether this is a forced manual execution
            
        Returns:
            str: Human-readable trigger reason
        """
        try:
            if force_manual:
                return "Manual trigger"
            
            trigger_type = rule.config.get('trigger_type', 'manual')
            
            if trigger_type == "payday_detection":
                if rule.rule_type == "pot_sweep":
                    # Check if payday was actually detected
                    config = rule.config if hasattr(rule, "config") else {}
                    sweep_rule = self.pot_sweeps.create_sweep_rule_from_config(config, rule.user_id)
                    if self.pot_sweeps._should_trigger_sweep(sweep_rule, rule.user_id):
                        return "Payday detected - salary transaction found"
                    else:
                        return "Payday detection check - no salary found"
            
            elif trigger_type == "balance_threshold":
                threshold = rule.config.get('trigger_threshold', 0)
                return f"Balance threshold trigger (£{threshold/100:.2f})"
            
            elif trigger_type == "time_of_day":
                time_config = rule.config.get('time_of_day', {})
                hour = time_config.get('hour', 0)
                minute = time_config.get('minute', 0)
                return f"Time-based trigger ({hour:02d}:{minute:02d})"
            
            elif trigger_type == "minute":
                interval = rule.config.get('trigger_interval', 5)
                return f"Minute-based trigger (every {interval} minutes)"
            
            elif trigger_type == "monthly":
                day = rule.config.get('trigger_day', 1)
                return f"Monthly trigger (day {day})"
            
            elif trigger_type == "weekly":
                day = rule.config.get('trigger_day', 1)
                day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                day_name = day_names[day-1] if 1 <= day <= 7 else f"day {day}"
                return f"Weekly trigger ({day_name})"
            
            elif trigger_type == "automation_trigger":
                return "Automation trigger - depends on other rules"
            
            elif trigger_type == "manual_only":
                return "Manual execution only"
            
            else:
                return f"Unknown trigger type: {trigger_type}"
                
        except Exception as e:
            logger.error(f"[AUTOMATION] Error determining trigger reason for rule {rule.rule_id}: {e}")
            return f"Error determining trigger reason: {str(e)}"

    def _should_queue_rule(self, rule: AutomationRule, force_manual: bool = False) -> bool:
        """
        Determine if a rule should be queued for execution.
        
        Args:
            rule: The automation rule to check
            force_manual: Whether this is a forced manual execution
            
        Returns:
            bool: True if the rule should be queued
        """
        try:
            trigger_type = rule.config.get('trigger_type', 'manual')
            
            # If force_manual is True, queue all rules
            if force_manual:
                logger.info(f"[AUTOMATION] Force manual execution - queuing rule {rule.rule_id}")
                return True
            
            # Check specific trigger conditions
            if trigger_type == "payday_detection":
                # Check if payday sweep should trigger
                if rule.rule_type == "pot_sweep":
                    # Check if this rule was already executed recently (7-day cooldown)
                    if rule.last_executed:
                        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
                        last_executed = rule.last_executed
                        if last_executed.tzinfo is None:
                            last_executed = last_executed.replace(tzinfo=timezone.utc)
                        
                        if last_executed >= seven_days_ago:
                            logger.info(f"[AUTOMATION] Payday sweep rule '{rule.name}' already executed recently ({last_executed.strftime('%Y-%m-%d %H:%M:%S')}), skipping to prevent duplicate execution")
                            return False
                    
                    # Only check payday detection if not in cooldown
                    config = rule.config if hasattr(rule, "config") else {}
                    sweep_rule = self.pot_sweeps.create_sweep_rule_from_config(config, rule.user_id)
                    return self.pot_sweeps._should_trigger_sweep(sweep_rule, rule.user_id)
            
            elif trigger_type == "balance_threshold":
                # Always queue balance threshold rules
                return True
            
            elif trigger_type == "time_of_day":
                # Check time-based trigger
                if rule.rule_type == "autosorter":
                    autosorter_config = self._create_autosorter_config(rule.config, rule)
                    return self.autosorter.should_trigger_autosorter(rule.user_id, autosorter_config)
            
            elif trigger_type == "minute":
                # Check minute-based trigger
                if rule.rule_type == "auto_topup":
                    config = rule.config if hasattr(rule, "config") else {}
                    topup_rule = self.auto_topup.create_topup_rule_from_config(config, rule.user_id)
                    return self.auto_topup._should_trigger_topup(topup_rule)
            
            elif trigger_type == "automation_trigger":
                # These are handled separately after other rules complete
                return False
            
            elif trigger_type == "manual_only":
                # Manual-only rules are not queued automatically
                return False
            
            else:
                # For other trigger types, check if they should trigger
                if rule.rule_type == "autosorter":
                    autosorter_config = self._create_autosorter_config(rule.config, rule)
                    return self.autosorter.should_trigger_autosorter(rule.user_id, autosorter_config)
                elif rule.rule_type == "auto_topup":
                    config = rule.config if hasattr(rule, "config") else {}
                    topup_rule = self.auto_topup.create_topup_rule_from_config(config, rule.user_id)
                    return self.auto_topup._should_trigger_topup(topup_rule)
            
            return False
            
        except Exception as e:
            logger.error(f"[AUTOMATION] Error checking if rule {rule.rule_id} should be queued: {e}")
            return False

    def _queue_automation_trigger_rules(self, user_id: str, enabled_rules: List[AutomationRule], force_manual: bool = False) -> None:
        """
        Queue automation_trigger rules that depend on other automation results.
        
        Args:
            user_id: Monzo user ID
            enabled_rules: List of enabled rules
            force_manual: Whether this is a forced manual execution
        """
        try:
            # Get automation_trigger rules
            automation_trigger_rules = [
                rule for rule in enabled_rules 
                if rule.rule_type == "autosorter" and rule.config.get("trigger_type") == "automation_trigger"
            ]

            if not automation_trigger_rules:
                return

            logger.info(f"[AUTOMATION] Found {len(automation_trigger_rules)} automation_trigger rules to queue")

            queue_manager = get_queue_manager()
            
            for rule in automation_trigger_rules:
                try:
                    # For automation_trigger rules, we need to wait for other rules to complete
                    # They will be triggered by the queue manager when dependencies are satisfied
                    
                    # Get accounts for this user
                    accounts = self.db.query(Account).filter_by(user_id=user_id, is_active=True).all()
                    if not accounts:
                        continue
                    
                    account_id = str(accounts[0].id)
                    
                    # Determine dependencies based on trigger conditions
                    dependencies = []
                    trigger_conditions = rule.config.get("automation_trigger", {})
                    
                    if trigger_conditions.get("trigger_on_sweep", True):
                        # This rule depends on pot sweep rules
                        sweep_rules = [r for r in enabled_rules if r.rule_type == "pot_sweep"]
                        dependencies.extend([r.rule_id for r in sweep_rules])
                    
                    if trigger_conditions.get("trigger_on_topup", True):
                        # This rule depends on auto topup rules
                        topup_rules = [r for r in enabled_rules if r.rule_type == "auto_topup"]
                        dependencies.extend([r.rule_id for r in topup_rules])
                    
                    # Determine trigger reason for automation_trigger rules
                    trigger_reason = "Automation trigger - depends on other rules completing"
                    
                    # Queue the automation_trigger rule with dependencies
                    success = queue_manager.add_rule_execution(
                        rule_id=rule.rule_id,
                        user_id=user_id,
                        account_id=account_id,
                        rule_type=rule.rule_type,
                        priority=ExecutionPriority.NORMAL,  # Normal priority for automation_trigger
                        depends_on=dependencies,
                        metadata={
                            "trigger_type": "automation_trigger",
                            "force_manual": force_manual,
                            "rule_name": rule.name,
                            "trigger_conditions": trigger_conditions
                        },
                        trigger_reason=trigger_reason
                    )
                    
                    if success:
                        logger.info(f"[AUTOMATION] Queued automation_trigger rule {rule.rule_id} with dependencies: {dependencies}")
                    else:
                        logger.warning(f"[AUTOMATION] Failed to queue automation_trigger rule {rule.rule_id}")

                except Exception as e:
                    logger.error(f"[AUTOMATION] Error queuing automation_trigger rule {rule.rule_id}: {e}")

        except Exception as e:
            logger.error(f"[AUTOMATION] Error in _queue_automation_trigger_rules: {e}")

    def execute_single_rule(self, rule: AutomationRule, user_id: str, account_id: str) -> Dict[str, Any]:
        """
        Execute a single automation rule.
        
        Args:
            rule: The automation rule to execute
            user_id: Monzo user ID
            account_id: Monzo account ID
            
        Returns:
            Dict containing execution results
        """
        logger.info(f"[AUTOMATION] Executing single rule: {rule.rule_id} ({rule.rule_type})")
        
        try:
            if rule.rule_type == "pot_sweep":
                return self._execute_single_pot_sweep(rule, user_id)
            elif rule.rule_type == "autosorter":
                return self._execute_single_autosorter(rule, user_id)
            elif rule.rule_type == "auto_topup":
                return self._execute_single_auto_topup(rule, user_id)
            else:
                logger.error(f"[AUTOMATION] Unknown rule type: {rule.rule_type}")
                return {"success": False, "error": f"Unknown rule type: {rule.rule_type}"}
                
        except Exception as e:
            logger.error(f"[AUTOMATION] Error executing single rule {rule.rule_id}: {e}")
            return {"success": False, "error": str(e)}

    def _execute_single_pot_sweep(self, rule: AutomationRule, user_id: str) -> Dict[str, Any]:
        """Execute a single pot sweep rule."""
        try:
            # Parse rule configuration
            config = rule.config if hasattr(rule, "config") else {}
            
            # Create sweep rule object from config
            sweep_rule = self.pot_sweeps.create_sweep_rule_from_config(config, user_id)
            
            # Execute the sweep
            sweep_result = self.pot_sweeps.execute_sweep_rule(user_id, sweep_rule)
            
            if sweep_result["success"]:
                # Store execution results in the rule config for display
                if "execution_history" not in rule.config:
                    rule.config["execution_history"] = []

                execution_record = {
                    "timestamp": datetime.now().isoformat(),
                    "total_moved": sweep_result.get("total_moved", 0),
                    "sources_processed": sweep_result.get("sources_processed", []),
                    "success": True,
                }

                # Keep only last 5 executions
                rule.config["execution_history"] = [execution_record] + rule.config["execution_history"][:4]

                # Update the rule in database with config and execution time
                self.rules_manager.update_rule(rule.rule_id, {
                    "config": rule.config,
                    "last_executed": datetime.now(timezone.utc)
                })
                
                logger.info(f"[AUTOMATION] Single pot sweep rule {rule.rule_id} executed successfully")
            
            return sweep_result
            
        except Exception as e:
            logger.error(f"[AUTOMATION] Error executing single pot sweep rule {rule.rule_id}: {e}")
            return {"success": False, "error": str(e)}

    def _execute_single_autosorter(self, rule: AutomationRule, user_id: str) -> Dict[str, Any]:
        """Execute a single autosorter rule."""
        try:
            # Parse rule configuration
            config = rule.config if hasattr(rule, "config") else {}
            
            # Create autosorter configuration
            autosorter_config = self._create_autosorter_config(config, rule)
            
            # Validate configuration
            validation = self.autosorter.validate_config(autosorter_config)
            if not validation["valid"]:
                logger.error(f"[AUTOMATION] Invalid autosorter config for rule {rule.rule_id}: {validation['errors']}")
                return {"success": False, "error": f"Invalid config: {validation['errors']}"}
            
            # Execute the distribution
            distribution_result = self.autosorter.execute_distribution(user_id, autosorter_config)
            
            # Always update the rule with execution metadata
            execution_metadata = {
                "last_result": distribution_result,
                "last_trigger_reason": "Manual trigger",
                "execution_count": (rule.execution_metadata.get("execution_count", 0) if rule.execution_metadata else 0) + 1
            }
            
            self.rules_manager.update_rule(rule.rule_id, {
                "last_executed": datetime.now(timezone.utc),
                "execution_metadata": execution_metadata
            })
            
            if distribution_result.get("success"):
                logger.info(f"[AUTOMATION] Single autosorter rule {rule.rule_id} executed successfully")
            else:
                logger.error(f"[AUTOMATION] Single autosorter rule {rule.rule_id} failed: {distribution_result.get('error', 'Unknown error')}")
            
            return distribution_result
            
        except Exception as e:
            logger.error(f"[AUTOMATION] Error executing single autosorter rule {rule.rule_id}: {e}")
            return {"success": False, "error": str(e)}

    def _execute_single_auto_topup(self, rule: AutomationRule, user_id: str) -> Dict[str, Any]:
        """Execute a single auto topup rule."""
        try:
            # Parse rule configuration
            config = rule.config if hasattr(rule, "config") else {}
            
            # Create topup rule object from config
            topup_rule = self.auto_topup.create_topup_rule_from_config(config, user_id)
            
            # Execute the topup
            topup_result = self.auto_topup.execute_topup_rule(user_id, topup_rule)
            
            if topup_result["success"]:
                # Update the rule in database with execution metadata and execution time
                execution_metadata = {
                    "last_result": topup_result,
                    "last_trigger_reason": "Manual trigger",
                    "execution_count": (rule.execution_metadata.get("execution_count", 0) if rule.execution_metadata else 0) + 1
                }
                
                self.rules_manager.update_rule(rule.rule_id, {
                    "last_executed": datetime.now(timezone.utc),
                    "execution_metadata": execution_metadata
                })
                
                logger.info(f"[AUTOMATION] Single auto topup rule {rule.rule_id} executed successfully")
            
            # Always update the rule with execution metadata, even on failure
            if not topup_result.get("success"):
                execution_metadata = {
                    "last_result": topup_result,
                    "last_trigger_reason": "Manual trigger",
                    "execution_count": (rule.execution_metadata.get("execution_count", 0) if rule.execution_metadata else 0) + 1
                }
                
                self.rules_manager.update_rule(rule.rule_id, {
                    "last_executed": datetime.now(timezone.utc),
                    "execution_metadata": execution_metadata
                })
            
            return topup_result
            
        except Exception as e:
            logger.error(f"[AUTOMATION] Error executing single auto topup rule {rule.rule_id}: {e}")
            error_result = {"success": False, "error": str(e)}
            
            # Update the rule with error metadata
            execution_metadata = {
                "last_result": error_result,
                "last_trigger_reason": "Manual trigger",
                "execution_count": (rule.execution_metadata.get("execution_count", 0) if rule.execution_metadata else 0) + 1
            }
            
            self.rules_manager.update_rule(rule.rule_id, {
                "last_executed": datetime.now(timezone.utc),
                "execution_metadata": execution_metadata
            })
            
            return error_result

    def _execute_pot_sweeps(
        self, user_id: str, enabled_rules: List[AutomationRule]
    ) -> Dict[str, Any]:
        """Execute pot sweep automation rules."""
        results = {"executed": 0, "success": 0, "errors": [], "total_moved": 0}

        try:
            # Get pot sweep rules
            sweep_rules = [
                rule for rule in enabled_rules if rule.rule_type == "pot_sweep"
            ]

            if not sweep_rules:
                return results

            logger.info(
                f"[AUTOMATION] Executing {len(sweep_rules)} pot sweep rules for user {user_id}"
            )

            for rule in sweep_rules:
                try:
                    results["executed"] += 1

                    # Parse rule configuration
                    config = rule.config if hasattr(rule, "config") else {}

                    # Create sweep rule object from config
                    sweep_rule = self.pot_sweeps.create_sweep_rule_from_config(
                        config, user_id
                    )

                    # Execute the sweep
                    sweep_result = self.pot_sweeps.execute_sweep_rule(
                        user_id, sweep_rule
                    )

                    if sweep_result["success"]:
                        results["success"] += 1
                        total_moved = sweep_result.get("total_moved", 0)
                        results["total_moved"] += total_moved
                        logger.info(
                            f"[AUTOMATION] Pot sweep rule {rule.rule_id} executed successfully: {total_moved} moved"
                        )

                        # Store execution results in the rule config for display
                        if "execution_history" not in rule.config:
                            rule.config["execution_history"] = []

                        execution_record = {
                            "timestamp": datetime.now().isoformat(),
                            "total_moved": total_moved,
                            "sources_processed": sweep_result.get(
                                "sources_processed", []
                            ),
                            "success": True,
                        }

                        # Keep only last 5 executions
                        rule.config["execution_history"] = [
                            execution_record
                        ] + rule.config["execution_history"][:4]

                        # Update the rule in database with config and execution time
                        self.rules_manager.update_rule(
                            rule.rule_id, {
                                "config": rule.config,
                                "last_executed": datetime.now(timezone.utc)
                            }
                        )

                        # Trigger autosorter rules if this sweep moved enough money
                        if total_moved > 100000: # Example threshold
                            logger.info(
                                f"[AUTOMATION] Pot sweep rule {rule.rule_id} triggered autosorter rules due to large sweep."
                            )
                            self._trigger_autosorter_rules(user_id, enabled_rules)

                    else:
                        results["errors"].append(
                            f"Pot sweep rule {rule.rule_id} failed: {sweep_result.get('reason', 'unknown error')}"
                        )

                except Exception as e:
                    error_msg = f"Pot sweep rule {rule.rule_id}: {str(e)}"
                    results["errors"].append(error_msg)
                    logger.error(f"[AUTOMATION] {error_msg}")

        except Exception as e:
            results["errors"].append(f"Pot sweeps execution error: {str(e)}")
            logger.error(f"[AUTOMATION] Pot sweeps execution error: {e}")

        return results

    def _execute_autosorter(
        self, user_id: str, enabled_rules: List[AutomationRule]
    ) -> Dict[str, Any]:
        """Execute autosorter automation rules based on enhanced trigger system."""
        results = {"executed": 0, "success": 0, "errors": []}

        try:
            # Get autosorter rules
            autosorter_rules = [
                rule for rule in enabled_rules if rule.rule_type == "autosorter"
            ]

            if not autosorter_rules:
                return results

            # Check triggers for each autosorter rule
            triggered_rules = []
            executed_rules = []  # Track which rules were actually executed

            for rule in autosorter_rules:
                try:
                    # Parse rule configuration
                    config = rule.config if hasattr(rule, "config") else {}
                    
                    # Create autosorter configuration with enhanced triggers
                    autosorter_config = self._create_autosorter_config(config, rule)
                    
                    # Validate configuration
                    validation = self.autosorter.validate_config(autosorter_config)
                    if not validation["valid"]:
                        logger.error(
                            f"[AUTOMATION] Invalid autosorter config for rule {rule.rule_id}: {validation['errors']}"
                        )
                        results["errors"].append(
                            f"Invalid config for rule {rule.rule_id}: {validation['errors']}"
                        )
                        continue
                    
                    # Check if rule should be triggered
                    # For automation_trigger rules, we'll handle them separately in _trigger_automation_trigger_rules
                    # For manual_only rules, they should always be available for manual execution
                    should_execute = False
                    
                    if autosorter_config.trigger_type == TriggerType.MANUAL_ONLY:
                        # Manual-only rules should always be available for execution
                        should_execute = True
                        logger.info(f"[AUTOMATION] Manual-only autosorter rule {rule.rule_id} available for execution")
                    elif autosorter_config.trigger_type == TriggerType.PAYDAY_DATE:
                        # Check if today is the payday date
                        should_execute = self.autosorter.should_trigger_autosorter(user_id, autosorter_config)
                    elif autosorter_config.trigger_type == TriggerType.TIME_OF_DAY:
                        # Check time-based trigger
                        should_execute = self.autosorter.should_trigger_autosorter(user_id, autosorter_config)
                    elif autosorter_config.trigger_type == TriggerType.TRANSACTION_BASED:
                        # Check transaction-based trigger
                        should_execute = self.autosorter.should_trigger_autosorter(user_id, autosorter_config)
                    elif autosorter_config.trigger_type == TriggerType.DATE_RANGE:
                        # Check date range trigger
                        should_execute = self.autosorter.should_trigger_autosorter(user_id, autosorter_config)
                    else:
                        # automation_trigger rules are handled separately
                        logger.debug(f"[AUTOMATION] Skipping automation_trigger rule {rule.rule_id} in main execution")
                        continue
                    
                    if should_execute:
                        # Check if this specific rule was already executed today
                        if hasattr(rule, "last_executed") and rule.last_executed:
                            # Ensure both datetimes are timezone-aware for comparison
                            last_executed = rule.last_executed
                            if last_executed.tzinfo is None:
                                last_executed = last_executed.replace(tzinfo=timezone.utc)
                            today = datetime.now(timezone.utc)
                            if last_executed.date() == today.date():
                                logger.info(
                                    f"[AUTOMATION] Autosorter rule {rule.rule_id} already executed today, skipping"
                                )
                                continue

                        triggered_rules.append((rule, autosorter_config))
                        logger.info(
                            f"[AUTOMATION] Trigger activated for autosorter rule {rule.rule_id} (trigger_type: {autosorter_config.trigger_type.value})"
                        )
                    else:
                        logger.debug(
                            f"[AUTOMATION] No trigger for autosorter rule {rule.rule_id} (trigger_type: {autosorter_config.trigger_type.value})"
                        )

                except Exception as e:
                    logger.error(
                        f"[AUTOMATION] Error checking trigger for autosorter rule {rule.rule_id}: {e}"
                    )
                    results["errors"].append(
                        f"Error checking trigger for rule {rule.rule_id}: {str(e)}"
                    )

            if not triggered_rules:
                logger.info(
                    f"[AUTOMATION] No autosorter rules triggered for user {user_id}"
                )
                return results

            logger.info(
                f"[AUTOMATION] Executing {len(triggered_rules)} autosorter rules for user {user_id}"
            )

            for rule, autosorter_config in triggered_rules:
                try:
                    results["executed"] += 1

                    # Execute the distribution
                    distribution_result = self.autosorter.execute_distribution(
                        user_id, autosorter_config
                    )

                    if distribution_result.get("success"):
                        results["success"] += 1
                        executed_rules.append(rule)
                        total_distributed = distribution_result.get(
                            "total_distributed", 0
                        )
                        logger.info(
                            f"[AUTOMATION] Autosorter rule {rule.rule_id} distributed £{total_distributed/100:.2f}"
                        )

                        # Store execution results in the rule config for display
                        if "execution_history" not in rule.config:
                            rule.config["execution_history"] = []

                        execution_record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "total_distributed": total_distributed,
                            "priority_pots": distribution_result.get("priority_pots", {}),
                            "goal_pots": distribution_result.get("goal_pots", {}),
                            "investment_pots": distribution_result.get("investment_pots", {}),
                            "success": True,
                        }

                        # Keep only last 5 executions
                        rule.config["execution_history"] = [
                            execution_record
                        ] + rule.config["execution_history"][:4]

                        # Update the rule in database with config and execution time
                        self.rules_manager.update_rule(
                            rule.rule_id, {
                                "config": rule.config,
                                "last_executed": datetime.now(timezone.utc)
                            }
                        )
                    else:
                        error_msg = distribution_result.get("error", "Unknown error")
                        results["errors"].append(
                            f"Autosorter rule {rule.rule_id}: {error_msg}"
                        )
                        logger.error(
                            f"[AUTOMATION] Autosorter rule {rule.rule_id} failed: {error_msg}"
                        )

                        # Send failure alert
                        send_failure_alert(rule.name, "autosorter", error_msg, user_id)

                        # Store failed execution result
                        if "execution_history" not in rule.config:
                            rule.config["execution_history"] = []

                        execution_record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "success": False,
                            "error": error_msg
                        }

                        # Keep only last 5 executions
                        rule.config["execution_history"] = [
                            execution_record
                        ] + rule.config["execution_history"][:4]

                        # Update the rule in database with config and execution time
                        self.rules_manager.update_rule(
                            rule.rule_id, {
                                "config": rule.config,
                                "last_executed": datetime.now(timezone.utc)
                            }
                        )

                except Exception as e:
                    error_msg = f"Exception during execution: {str(e)}"
                    results["errors"].append(
                        f"Autosorter rule {rule.rule_id}: {error_msg}"
                    )
                    logger.error(
                        f"[AUTOMATION] Exception during autosorter rule {rule.rule_id} execution: {e}"
                    )

            # Update execution times for successful rules
            if executed_rules:
                self._update_autosorter_execution_times(executed_rules)

        except Exception as e:
            logger.error(
                f"[AUTOMATION] Error during autosorter execution for user {user_id}: {e}"
            )
            results["errors"].append(f"General autosorter error: {str(e)}")

        # Include executed_rules in the return value
        results["executed_rules"] = executed_rules
        return results

    def _trigger_automation_trigger_rules(self, user_id: str, enabled_rules: List[AutomationRule], results: Dict[str, Any], force_manual: bool = False) -> None:
        """Trigger automation_trigger rules based on results from other automation rules."""
        try:
            # Get automation_trigger rules
            automation_trigger_rules = [
                rule for rule in enabled_rules 
                if rule.rule_type == "autosorter" and rule.config.get("trigger_type") == "automation_trigger"
            ]

            if not automation_trigger_rules:
                return

            logger.info(f"[AUTOMATION] Found {len(automation_trigger_rules)} automation_trigger rules to process")

            for rule in automation_trigger_rules:
                try:
                    # Check if we should trigger this rule based on other automation results
                    # If force_manual is True, trigger all automation_trigger rules regardless of conditions
                    should_trigger = force_manual or self._should_trigger_automation_rule(rule, results)
                    
                    if should_trigger:
                        logger.info(f"[AUTOMATION] Triggering automation_trigger rule {rule.rule_id}")
                        
                        # Create autosorter configuration
                        autosorter_config = self._create_autosorter_config(rule.config, rule)
                        
                        # Execute the autosorter
                        distribution_result = self.autosorter.execute_distribution(user_id, autosorter_config)
                        
                        if distribution_result.get("success"):
                            logger.info(f"[AUTOMATION] Automation_trigger rule {rule.rule_id} executed successfully")
                            # Update execution time
                            self.rules_manager.update_rule(rule.rule_id, {
                                "last_executed": datetime.now(timezone.utc)
                            })
                        else:
                            logger.error(f"[AUTOMATION] Automation_trigger rule {rule.rule_id} failed: {distribution_result.get('error')}")
                    else:
                        logger.debug(f"[AUTOMATION] Automation_trigger rule {rule.rule_id} not triggered based on conditions")

                except Exception as e:
                    logger.error(f"[AUTOMATION] Error executing automation_trigger rule {rule.rule_id}: {e}")

        except Exception as e:
            logger.error(f"[AUTOMATION] Error in _trigger_automation_trigger_rules: {e}")

    def _should_trigger_automation_rule(self, rule: AutomationRule, results: Dict[str, Any]) -> bool:
        """Determine if an automation_trigger rule should be triggered based on other automation results."""
        try:
            # Get trigger conditions from rule config
            trigger_conditions = rule.config.get("automation_trigger", {})
            
            # Check if any pot sweeps moved significant amounts
            if trigger_conditions.get("trigger_on_sweep", True):
                pot_sweeps_moved = results.get("pot_sweeps", {}).get("total_moved", 0)
                min_sweep_amount = trigger_conditions.get("min_sweep_amount", 100000)  # Default £1000
                if pot_sweeps_moved >= min_sweep_amount:
                    logger.info(f"[AUTOMATION] Triggering due to pot sweep amount: £{pot_sweeps_moved/100:.2f} >= £{min_sweep_amount/100:.2f}")
                    return True
            
            # Check if any auto topups were successful
            if trigger_conditions.get("trigger_on_topup", True):
                auto_topup_success = results.get("auto_topup", {}).get("success", 0)
                if auto_topup_success > 0:
                    logger.info(f"[AUTOMATION] Triggering due to successful auto topups: {auto_topup_success}")
                    return True
            
            # Check if any autosorter rules were executed
            if trigger_conditions.get("trigger_on_autosorter", False):
                autosorter_executed = results.get("autosorter", {}).get("executed", 0)
                if autosorter_executed > 0:
                    logger.info(f"[AUTOMATION] Triggering due to other autosorter executions: {autosorter_executed}")
                    return True
            
            return False

        except Exception as e:
            logger.error(f"[AUTOMATION] Error checking automation trigger conditions: {e}")
            return False

    def _trigger_autosorter_rules(self, user_id: str, enabled_rules: List[AutomationRule]) -> None:
        """Trigger autosorter rules manually (used by other automation rules)."""
        try:
            # Get autosorter rules that can be triggered
            autosorter_rules = [
                rule for rule in enabled_rules 
                if rule.rule_type == "autosorter" and rule.config.get("trigger_type") in ["automation_trigger", "manual_only"]
            ]

            for rule in autosorter_rules:
                try:
                    logger.info(f"[AUTOMATION] Manually triggering autosorter rule {rule.rule_id}")
                    
                    # Create autosorter configuration
                    autosorter_config = self._create_autosorter_config(rule.config, rule)
                    
                    # Execute the autosorter
                    distribution_result = self.autosorter.execute_distribution(user_id, autosorter_config)
                    
                    if distribution_result.get("success"):
                        logger.info(f"[AUTOMATION] Manually triggered autosorter rule {rule.rule_id} executed successfully")
                        # Update execution time
                        self.rules_manager.update_rule(rule.rule_id, {
                            "last_executed": datetime.now(timezone.utc)
                        })
                    else:
                        logger.error(f"[AUTOMATION] Manually triggered autosorter rule {rule.rule_id} failed: {distribution_result.get('error')}")

                except Exception as e:
                    logger.error(f"[AUTOMATION] Error executing manually triggered autosorter rule {rule.rule_id}: {e}")

        except Exception as e:
            logger.error(f"[AUTOMATION] Error in _trigger_autosorter_rules: {e}")

    def _create_autosorter_config(self, config: Dict, rule: Optional[AutomationRule] = None) -> AutosorterConfig:
        """Create AutosorterConfig from rule configuration with enhanced trigger support."""
        # Determine trigger type (default to legacy payday_date for backward compatibility)
        trigger_type_str = config.get("trigger_type", "payday_date")
        
        # Handle automation_trigger as a special case - it's triggered by other automation rules
        if trigger_type_str == "automation_trigger":
            logger.info(f"[AUTOMATION] Processing automation_trigger rule - will be triggered by other automation rules")
            trigger_type_str = "manual_only"  # Treat as manual-only for now, but can be triggered programmatically
        
        try:
            trigger_type = TriggerType(trigger_type_str)
        except ValueError as e:
            logger.error(f"[AUTOMATION] Invalid trigger type '{trigger_type_str}': {e}")
            # Fall back to payday_date for invalid trigger types
            trigger_type = TriggerType.PAYDAY_DATE
        
        # Parse trigger-specific configurations
        time_of_day_trigger = None
        transaction_trigger = None
        date_range_trigger = None
        
        if trigger_type == TriggerType.TIME_OF_DAY:
            time_config = config.get("time_of_day_trigger", {})
            time_of_day_trigger = TimeOfDayTrigger(
                day_of_month=time_config.get("day_of_month", 25),
                hour=time_config.get("hour", 9),
                minute=time_config.get("minute", 0)
            )
        elif trigger_type == TriggerType.TRANSACTION_BASED:
            transaction_config = config.get("transaction_trigger", {})
            transaction_trigger = TransactionTrigger(
                description_pattern=transaction_config.get("description_pattern", ""),
                amount_min=transaction_config.get("amount_min"),
                amount_max=transaction_config.get("amount_max"),
                category=transaction_config.get("category"),
                merchant=transaction_config.get("merchant"),
                days_to_look_back=transaction_config.get("days_to_look_back", 3)
            )
        elif trigger_type == TriggerType.DATE_RANGE:
            range_config = config.get("date_range_trigger", {})
            preferred_time = None
            if "preferred_hour" in range_config and "preferred_minute" in range_config:
                preferred_time = time(
                    range_config.get("preferred_hour", 9),
                    range_config.get("preferred_minute", 0)
                )
            date_range_trigger = DateRangeTrigger(
                start_day=range_config.get("start_day", 25),
                end_day=range_config.get("end_day", 27),
                preferred_time=preferred_time
            )
        
        # Clean holding_reserve_percentage to prevent NaN and convert to decimal
        holding_reserve_percentage = config.get("holding_reserve_percentage")
        if holding_reserve_percentage is not None:
            if isinstance(holding_reserve_percentage, float) and (holding_reserve_percentage != holding_reserve_percentage):  # NaN check
                logger.warning(f"[AUTOMATION] NaN holding_reserve_percentage detected, setting to None")
                holding_reserve_percentage = None
            elif isinstance(holding_reserve_percentage, (int, float)) and holding_reserve_percentage > 1:
                # Convert whole number percentage (e.g., 5.0) to decimal (0.05)
                holding_reserve_percentage = holding_reserve_percentage / 100
                logger.info(f"[AUTOMATION] Converted holding_reserve_percentage {config.get('holding_reserve_percentage')} to {holding_reserve_percentage}")
        
        # Create autosorter configuration
        autosorter_config = AutosorterConfig(
            holding_pot_id=config.get("holding_pot_id"),
            bills_pot_id=config.get("bills_pot_id"),
            priority_pots=self._parse_pot_allocations(
                config.get("priority_pots", [])
            ),
            goal_pots=self._parse_pot_allocations(
                config.get("goal_pots", [])
            ),
            investment_pots=self._parse_pot_allocations(
                config.get("investment_pots", [])
            ),
            holding_reserve_amount=config.get("holding_reserve_amount"),
            holding_reserve_percentage=holding_reserve_percentage,
            min_holding_balance=config.get("min_holding_balance", 10000),
            include_goal_pots=config.get("include_goal_pots", True),  # Default to True for backward compatibility
            trigger_type=trigger_type,
            payday_date=config.get("payday_date", 25),  # Legacy support
            time_of_day_trigger=time_of_day_trigger,
            transaction_trigger=transaction_trigger,
            date_range_trigger=date_range_trigger
        )
        
        return autosorter_config

    def _parse_pot_allocations(self, pot_configs: List[Dict]) -> List[PotAllocation]:
        """Parse pot allocation configurations from rule config."""
        allocations = []

        for pot_config in pot_configs:
            allocation_type = pot_config.get("allocation_type")
            
            # Handle percentage values - convert from whole numbers (1-100) to decimals (0.01-1.0)
            percentage = pot_config.get("percentage")
            if percentage is not None:
                if isinstance(percentage, float) and (percentage != percentage):  # NaN check
                    logger.warning(f"[AUTOMATION] NaN percentage detected in pot config, setting to None")
                    percentage = None
                elif isinstance(percentage, (int, float)) and percentage > 1:
                    # Convert whole number percentage (e.g., 5.0) to decimal (0.05)
                    percentage = percentage / 100
                    logger.info(f"[AUTOMATION] Converted percentage {pot_config.get('percentage')} to {percentage}")
            
            # Handle amount values for percentage-based allocations
            amount = pot_config.get("amount")
            if allocation_type == "percentage" and amount is not None and percentage is None:
                # If allocation_type is "percentage" but we have "amount" instead of "percentage"
                # Convert the amount to a percentage based on a reasonable assumption
                # This is a fallback for misconfigured rules
                logger.warning(f"[AUTOMATION] Pot {pot_config.get('pot_name', 'Unknown')} has allocation_type='percentage' but uses 'amount' field. Converting amount {amount} to percentage.")
                # Assume this is meant to be a percentage value (e.g., amount=5000 means 5%)
                if isinstance(amount, (int, float)) and amount > 1:
                    percentage = amount / 100
                    amount = None  # Clear the amount since we're using percentage
            
            allocation = PotAllocation(
                pot_id=pot_config.get("pot_id"),
                pot_name=pot_config.get("pot_name"),
                allocation_type=allocation_type,
                amount=amount,
                percentage=percentage,
                goal_amount=pot_config.get("goal_amount"),
                max_allocation=pot_config.get("max_allocation"),
                priority=pot_config.get("priority", 0),
                use_all_remaining=pot_config.get("use_all_remaining", False),
            )
            allocations.append(allocation)

        return allocations

    def _execute_auto_topup(
        self, user_id: str, enabled_rules: List[AutomationRule]
    ) -> Dict[str, Any]:
        """Execute auto topup automation rules."""
        results = {"executed": 0, "success": 0, "errors": []}

        try:
            # Get auto topup rules
            topup_rules = [
                rule for rule in enabled_rules if rule.rule_type == "auto_topup"
            ]

            if not topup_rules:
                return results

            logger.info(
                f"[AUTOMATION] Executing {len(topup_rules)} auto topup rules for user {user_id}"
            )

            for rule in topup_rules:
                try:
                    results["executed"] += 1

                    # Parse rule configuration
                    config = rule.config if hasattr(rule, "config") else {}

                    # Create topup rule object
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

                    # Execute the topup
                    success = self.auto_topup.execute_topup_rule(user_id, topup_rule)

                    if success:
                        results["success"] += 1
                        logger.info(
                            f"[AUTOMATION] Auto topup rule {rule.rule_id} executed successfully"
                        )

                        # Store execution results in the rule config for display
                        if "execution_history" not in rule.config:
                            rule.config["execution_history"] = []

                        execution_record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "amount": config.get("amount", 0),
                            "source_account_id": config.get("source_account_id"),
                            "target_pot_id": config.get("target_pot_id"),
                            "success": True,
                        }

                        # Keep only last 5 executions
                        rule.config["execution_history"] = [
                            execution_record
                        ] + rule.config["execution_history"][:4]

                        # Update the rule in database with config and execution time
                        self.rules_manager.update_rule(
                            rule.rule_id, {
                                "config": rule.config,
                                "last_executed": datetime.now(timezone.utc)
                            }
                        )
                    else:
                        error_msg = f"Auto topup rule {rule.rule_id} failed"
                        results["errors"].append(error_msg)

                        # Send failure alert
                        send_failure_alert(rule.name, "auto_topup", "Topup execution failed", user_id)

                        # Store failed execution result
                        if "execution_history" not in rule.config:
                            rule.config["execution_history"] = []

                        execution_record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "success": False,
                            "error": "Topup execution failed"
                        }

                        # Keep only last 5 executions
                        rule.config["execution_history"] = [
                            execution_record
                        ] + rule.config["execution_history"][:4]

                        # Update the rule in database with config and execution time
                        self.rules_manager.update_rule(
                            rule.rule_id, {
                                "config": rule.config,
                                "last_executed": datetime.now(timezone.utc)
                            }
                        )

                except Exception as e:
                    error_msg = f"Auto topup rule {rule.rule_id}: {str(e)}"
                    results["errors"].append(error_msg)
                    logger.error(f"[AUTOMATION] {error_msg}")

        except Exception as e:
            results["errors"].append(f"Auto topup execution error: {str(e)}")
            logger.error(f"[AUTOMATION] Auto topup execution error: {e}")

        return results



    def _get_unsorted_transactions(self, user_id: str) -> List[Transaction]:
        """Get transactions that haven't been sorted into pots yet."""
        try:
            # Get transactions that don't have pot assignments
            # This is a simplified version - in a real implementation, you'd track which transactions
            # have been processed by automation rules
            transactions = (
                self.db.query(Transaction)
                .filter_by(user_id=user_id, is_load=0)  # Exclude top-ups
                .order_by(Transaction.created.desc())
                .limit(100)
                .all()
            )  # Limit to recent transactions

            return transactions

        except Exception as e:
            logger.error(f"[AUTOMATION] Error getting unsorted transactions: {e}")
            return []

    def _update_execution_times(self, enabled_rules: List[AutomationRule]) -> None:
        """Update last execution time for successful rules."""
        try:
            current_time = datetime.now(timezone.utc)

            for rule in enabled_rules:
                # Update execution time for rules that were successfully executed
                # In a more sophisticated implementation, you'd track which specific rules succeeded
                self.rules_manager.update_execution_time(rule.rule_id, current_time)

        except Exception as e:
            logger.error(f"[AUTOMATION] Error updating execution times: {e}")

    def _update_autosorter_execution_times(
        self, executed_rules: List[AutomationRule]
    ) -> None:
        """Update last execution time for autosorter rules that were actually executed."""
        try:
            current_time = datetime.now(timezone.utc)

            for rule in executed_rules:
                # Update execution time for autosorter rules that were actually executed
                self.rules_manager.update_execution_time(rule.rule_id, current_time)
                logger.info(
                    f"[AUTOMATION] Updated execution time for autosorter rule {rule.rule_id}"
                )

        except Exception as e:
            logger.error(f"[AUTOMATION] Error updating autosorter execution times: {e}")

    def get_automation_status(self, user_id: str) -> Dict[str, Any]:
        """
        Get the current status of automation for a user.

        Args:
            user_id: Monzo user ID

        Returns:
            Dict containing automation status information
        """
        try:
            # Get all rules for the user
            all_rules = self.rules_manager.get_rules_by_user(user_id)
            enabled_rules = self.rules_manager.get_enabled_rules(user_id)

            # Get rule counts by type
            rule_counts = {}
            for rule in all_rules:
                rule_type = rule.rule_type
                if rule_type not in rule_counts:
                    rule_counts[rule_type] = {"total": 0, "enabled": 0}
                rule_counts[rule_type]["total"] += 1
                if rule.enabled:
                    rule_counts[rule_type]["enabled"] += 1

            return {
                "total_rules": len(all_rules),
                "enabled_rules": len(enabled_rules),
                "rule_counts": rule_counts,
                "last_execution": self._get_last_execution_time(user_id),
            }

        except Exception as e:
            logger.error(f"[AUTOMATION] Error getting automation status: {e}")
            return {"error": str(e)}

    def _get_last_execution_time(self, user_id: str) -> Optional[datetime]:
        """Get the last execution time for any automation rule for this user."""
        try:
            rules = self.rules_manager.get_rules_by_user(user_id)
            if not rules:
                return None

            # Find the most recent execution time
            last_execution = None
            for rule in rules:
                if hasattr(rule, "last_executed") and rule.last_executed:
                    if last_execution is None or rule.last_executed > last_execution:
                        last_execution = rule.last_executed

            return last_execution

        except Exception as e:
            logger.error(f"[AUTOMATION] Error getting last execution time: {e}")
            return None
