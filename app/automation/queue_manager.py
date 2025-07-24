"""
Queue Manager for Automation Rules - Handles execution order and priority.

This module provides a queuing system to ensure automation rules execute
in the correct order and with proper priority levels.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from queue import PriorityQueue, Empty
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db import get_db_session
from app.models import User, Account
from app.services.auth_service import get_authenticated_monzo_client

logger = logging.getLogger(__name__)


class ExecutionPriority(Enum):
    """Priority levels for automation rule execution."""
    
    CRITICAL = 1      # Highest priority (e.g., critical balance checks)
    HIGH = 2          # High priority (e.g., payday detection)
    NORMAL = 3        # Normal priority (e.g., regular autosorter)
    LOW = 4           # Low priority (e.g., cleanup tasks)
    BACKGROUND = 5    # Background tasks (e.g., logging, analytics)


class QueueItem:
    """Represents an item in the automation execution queue."""
    
    def __init__(
        self,
        priority: ExecutionPriority,
        rule_id: str,
        user_id: str,
        account_id: str,
        rule_type: str,
        execution_func: Callable,
        metadata: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        created_at: Optional[datetime] = None
    ):
        self.priority = priority
        self.rule_id = rule_id
        self.user_id = user_id
        self.account_id = account_id
        self.rule_type = rule_type
        self.execution_func = execution_func
        self.metadata = metadata or {}
        self.depends_on = depends_on or []
        self.created_at = created_at or datetime.now(timezone.utc)
        self.execution_id = f"{rule_id}_{int(self.created_at.timestamp())}"
    
    def __lt__(self, other):
        """Priority queue comparison - lower priority numbers execute first."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        # If same priority, earlier creation time goes first
        return self.created_at < other.created_at
    
    def __repr__(self):
        return f"QueueItem(priority={self.priority.name}, rule_id={self.rule_id}, type={self.rule_type})"


class AutomationQueueManager:
    """Manages the execution queue for automation rules."""
    
    def __init__(self, max_workers: int = 3, max_queue_size: int = 100):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.queue = PriorityQueue(maxsize=max_queue_size)
        self.workers: List[threading.Thread] = []
        self.running = False
        self.execution_history: Dict[str, Dict[str, Any]] = {}
        self.dependency_graph: Dict[str, List[str]] = {}
        self.completed_tasks: set = set()
        self.lock = threading.Lock()
        
        # Statistics
        self.stats = {
            "total_queued": 0,
            "total_executed": 0,
            "total_failed": 0,
            "queue_size": 0,
            "active_workers": 0,
            "rule_execution_counts": {}  # Track execution count per rule
        }
    
    def start(self):
        """Start the queue manager and worker threads."""
        if self.running:
            logger.warning("[QUEUE] Queue manager is already running")
            return
        
        logger.info(f"[QUEUE] Starting queue manager with {self.max_workers} workers")
        self.running = True
        
        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"AutomationWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"[QUEUE] Started {len(self.workers)} worker threads")
    
    def stop(self):
        """Stop the queue manager and wait for workers to finish."""
        if not self.running:
            return
        
        logger.info("[QUEUE] Stopping queue manager...")
        self.running = False
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5)
        
        logger.info("[QUEUE] Queue manager stopped")
    
    def add_rule_execution(
        self,
        rule_id: str,
        user_id: str,
        account_id: str,
        rule_type: str,
        priority: ExecutionPriority = ExecutionPriority.NORMAL,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trigger_reason: Optional[str] = None
    ) -> bool:
        """
        Add a rule execution to the queue.
        
        Args:
            rule_id: The rule ID to execute
            user_id: Monzo user ID
            account_id: Monzo account ID
            rule_type: Type of rule (pot_sweep, autosorter, auto_topup)
            priority: Execution priority
            depends_on: List of rule IDs this rule depends on
            metadata: Additional metadata for the execution
            
        Returns:
            bool: True if successfully queued, False otherwise
        """
        try:
            # Check if queue is full
            if self.queue.qsize() >= self.max_queue_size:
                logger.warning(f"[QUEUE] Queue is full ({self.max_queue_size} items), dropping execution for rule {rule_id}")
                return False
            
            # Log the rule being added to queue for debugging
            logger.info(f"[QUEUE] Adding rule {rule_id} ({rule_type}) to queue - trigger: {trigger_reason}, priority: {priority.name}")
            
            # Create execution function
            execution_func = self._create_execution_function(rule_id, user_id, account_id, rule_type, trigger_reason)
            
            # Create queue item
            queue_item = QueueItem(
                priority=priority,
                rule_id=rule_id,
                user_id=user_id,
                account_id=account_id,
                rule_type=rule_type,
                execution_func=execution_func,
                metadata=metadata,
                depends_on=depends_on or []
            )
            
            # Add to queue
            self.queue.put(queue_item)
            
            # Update statistics
            with self.lock:
                self.stats["total_queued"] += 1
                self.stats["queue_size"] = self.queue.qsize()
                
                # Track dependencies
                if depends_on:
                    self.dependency_graph[queue_item.execution_id] = depends_on
            
            logger.info(f"[QUEUE] Queued rule {rule_id} (priority: {priority.name}, dependencies: {depends_on}, trigger: {trigger_reason})")
            return True
            
        except Exception as e:
            logger.error(f"[QUEUE] Error queuing rule {rule_id}: {e}")
            return False
    
    def _create_execution_function(
        self, 
        rule_id: str, 
        user_id: str, 
        account_id: str, 
        rule_type: str,
        trigger_reason: Optional[str] = None
    ) -> Callable:
        """Create an execution function for a specific rule."""
        def execute_rule():
            try:
                with next(get_db_session()) as db:
                    # Create authenticated Monzo client
                    monzo = get_authenticated_monzo_client(db, user_id)
                    if not monzo:
                        logger.warning(f"[QUEUE] No valid credentials for user {user_id}, skipping rule {rule_id}")
                        return {"success": False, "error": "No valid credentials"}
                    
                    # Get the rule from database
                    from app.automation.rules import RulesManager
                    rules_manager = RulesManager(db)
                    rule = rules_manager.get_rule_by_id(rule_id)
                    
                    if not rule or not rule.enabled:
                        logger.info(f"[QUEUE] Rule {rule_id} not found or disabled, skipping")
                        return {"success": False, "reason": "rule_not_found_or_disabled"}
                    
                    # Execute the rule using the appropriate automation component
                    logger.info(f"[QUEUE] Executing rule {rule_id} ({rule_type}) - Trigger: {trigger_reason}")
                    result = self._execute_rule_by_type(rule, rule_type, user_id, account_id, db, monzo)
                    
                    # Add trigger reason to result
                    if trigger_reason:
                        result["trigger_reason"] = trigger_reason
                    
                    # Update the database rule with execution results
                    try:
                        from app.automation.rules import RulesManager
                        rules_manager = RulesManager(db)
                        db_rule = rules_manager.get_rule_by_id(rule_id)
                        if db_rule:
                            # Update last_executed timestamp
                            db_rule.last_executed = datetime.now(timezone.utc)
                            
                            # Store execution result in rule metadata
                            if not hasattr(db_rule, 'execution_metadata') or db_rule.execution_metadata is None:
                                db_rule.execution_metadata = {}
                            
                            db_rule.execution_metadata.update({
                                "last_execution": datetime.now(timezone.utc).isoformat(),
                                "last_result": result,
                                "last_trigger_reason": trigger_reason,
                                "execution_count": (db_rule.execution_metadata.get("execution_count", 0) + 1) if db_rule.execution_metadata else 1
                            })
                            
                            db.commit()
                            logger.info(f"[QUEUE] Updated database rule {rule_id} with execution results")
                    except Exception as e:
                        logger.error(f"[QUEUE] Error updating database rule {rule_id}: {e}")
                        # Don't fail the execution if database update fails
                    
                    # Store execution history
                    with self.lock:
                        # Track execution count per rule
                        if rule_id not in self.stats["rule_execution_counts"]:
                            self.stats["rule_execution_counts"][rule_id] = 0
                        self.stats["rule_execution_counts"][rule_id] += 1
                        
                        self.execution_history[rule_id] = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "result": result,
                            "rule_type": rule_type,
                            "user_id": user_id,
                            "account_id": account_id,
                            "execution_count": self.stats["rule_execution_counts"][rule_id]
                        }
                        self.completed_tasks.add(rule_id)
                        self.stats["total_executed"] += 1
                        if not result.get("success"):
                            self.stats["total_failed"] += 1
                    
                    logger.info(f"[QUEUE] Completed rule {rule_id}: {result.get('success', False)}")
                    return result
                    
            except Exception as e:
                logger.error(f"[QUEUE] Error executing rule {rule_id}: {e}")
                with self.lock:
                    self.stats["total_failed"] += 1
                return {"success": False, "error": str(e)}
        
        return execute_rule
    
    def _execute_rule_by_type(self, rule, rule_type: str, user_id: str, account_id: str, db, monzo):
        """Execute a rule based on its type."""
        try:
            if rule_type == "pot_sweep":
                from .pot_sweeps import PotSweeps
                pot_sweeps = PotSweeps(db, monzo)
                config = rule.config if hasattr(rule, "config") else {}
                sweep_rule = pot_sweeps.create_sweep_rule_from_config(config, user_id)
                result = pot_sweeps.execute_sweep_rule(user_id, sweep_rule)
                
                # Enhance result with more details
                if result.get("success"):
                    total_moved = result.get("total_moved", 0)
                    sources_processed = result.get("sources_processed", [])
                    if total_moved > 0:
                        result["reason"] = f"Moved £{total_moved/100:.2f} from {len(sources_processed)} sources"
                    else:
                        result["reason"] = "Sweep executed but no money moved"
                else:
                    result["reason"] = result.get("reason", result.get("error", "Sweep failed"))
                
                return result
                
            elif rule_type == "autosorter":
                from .autosorter import Autosorter
                autosorter = Autosorter(db, monzo)
                config = rule.config if hasattr(rule, "config") else {}
                autosorter_config = self._create_autosorter_config(config, rule)
                result = autosorter.execute_distribution(user_id, autosorter_config)
                
                # Enhance result with more details
                if result.get("success"):
                    total_distributed = result.get("total_distributed", 0)
                    if total_distributed > 0:
                        result["reason"] = f"Distributed £{total_distributed/100:.2f} to pots"
                    else:
                        result["reason"] = "Autosorter executed but no money distributed"
                else:
                    result["reason"] = result.get("error", "Autosorter failed")
                
                return result
                
            elif rule_type == "auto_topup":
                from .auto_topup import AutoTopup
                auto_topup = AutoTopup(db, monzo)
                config = rule.config if hasattr(rule, "config") else {}
                topup_rule = auto_topup.create_topup_rule_from_config(config, user_id)
                result = auto_topup.execute_topup_rule(user_id, topup_rule)
                
                # Use the actual execution result instead of config
                if result.get("success"):
                    amount = result.get("amount", 0)
                    if amount > 0:
                        result["reason"] = f"Topped up £{amount/100:.2f}"
                    else:
                        result["reason"] = result.get("reason", "Topup executed but no money moved")
                else:
                    result["reason"] = result.get("error", result.get("reason", "Topup failed"))
                
                return result
                
            else:
                logger.error(f"[QUEUE] Unknown rule type: {rule_type}")
                return {"success": False, "error": f"Unknown rule type: {rule_type}"}
                
        except Exception as e:
            logger.error(f"[QUEUE] Error executing {rule_type} rule {rule.rule_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def _create_autosorter_config(self, config: dict, rule):
        """Create autosorter configuration from rule config."""
        try:
            from .autosorter import AutosorterConfig, TriggerType, PotAllocation
            
            # Determine trigger type
            trigger_type_str = config.get("trigger_type", "payday_date")
            try:
                trigger_type = TriggerType(trigger_type_str)
            except ValueError:
                trigger_type = TriggerType.PAYDAY_DATE
            
            # Parse pot allocations
            pot_allocations = []
            if "pots" in config:
                for pot_config in config["pots"]:
                    allocation = PotAllocation(
                        pot_name=pot_config.get("name", ""),
                        percentage=pot_config.get("percentage", 0.0),
                        priority=pot_config.get("priority", 0),
                        goal_amount=pot_config.get("goal_amount"),
                        goal_date=pot_config.get("goal_date")
                    )
                    pot_allocations.append(allocation)
            
            return AutosorterConfig(
                rule_id=rule.rule_id,
                user_id=rule.user_id,
                trigger_type=trigger_type,
                pot_allocations=pot_allocations,
                source_pot_name=config.get("source_pot_name", "Main Account"),
                min_amount=config.get("min_amount", 0),
                max_amount=config.get("max_amount"),
                trigger_day=config.get("trigger_day"),
                trigger_hour=config.get("trigger_hour"),
                trigger_minute=config.get("trigger_minute"),
                trigger_interval=config.get("trigger_interval"),
                min_balance=config.get("min_balance"),
                target_balance=config.get("target_balance")
            )
            
        except Exception as e:
            logger.error(f"[QUEUE] Error creating autosorter config: {e}")
            # Return a basic config as fallback
            from .autosorter import AutosorterConfig, TriggerType
            return AutosorterConfig(
                rule_id=rule.rule_id,
                user_id=rule.user_id,
                trigger_type=TriggerType.PAYDAY_DATE,
                pot_allocations=[],
                source_pot_name="Main Account"
            )
    
    def _worker_loop(self):
        """Main worker loop that processes queue items."""
        logger.info(f"[QUEUE] Worker {threading.current_thread().name} started")
        
        with self.lock:
            self.stats["active_workers"] += 1
        
        try:
            while self.running:
                try:
                    # Get item from queue with timeout
                    queue_item = self.queue.get(timeout=1)
                    
                    # Check dependencies
                    if not self._check_dependencies(queue_item):
                        # Re-queue with lower priority if dependencies not met
                        queue_item.priority = ExecutionPriority.LOW
                        self.queue.put(queue_item)
                        continue
                    
                    # Execute the rule
                    logger.info(f"[QUEUE] Worker {threading.current_thread().name} executing: {queue_item}")
                    result = queue_item.execution_func()
                    logger.info(f"[QUEUE] Worker {threading.current_thread().name} completed: {queue_item.rule_id} with result: {result.get('success', False)}")
                    
                    # Mark as completed
                    with self.lock:
                        self.completed_tasks.add(queue_item.rule_id)
                        self.stats["queue_size"] = self.queue.qsize()
                    
                    # Small delay to prevent overwhelming the system
                    time.sleep(0.1)
                    
                except Empty:
                    # Queue is empty, continue loop
                    continue
                except Exception as e:
                    logger.error(f"[QUEUE] Worker error: {e}")
                    time.sleep(1)  # Wait before retrying
                    
        finally:
            with self.lock:
                self.stats["active_workers"] -= 1
            logger.info(f"[QUEUE] Worker {threading.current_thread().name} stopped")
    
    def _check_dependencies(self, queue_item: QueueItem) -> bool:
        """Check if all dependencies for a queue item are satisfied."""
        if not queue_item.depends_on:
            return True
        
        with self.lock:
            for dependency in queue_item.depends_on:
                if dependency not in self.completed_tasks:
                    logger.debug(f"[QUEUE] Rule {queue_item.rule_id} waiting for dependency: {dependency}")
                    return False
        
        return True
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status and statistics."""
        with self.lock:
            return {
                "running": self.running,
                "queue_size": self.queue.qsize(),
                "active_workers": self.stats["active_workers"],
                "total_queued": self.stats["total_queued"],
                "total_executed": self.stats["total_executed"],
                "total_failed": self.stats["total_failed"],
                "completed_tasks": list(self.completed_tasks),
                "dependency_graph": self.dependency_graph.copy(),
                "rule_execution_counts": self.stats["rule_execution_counts"].copy(),
                "execution_history": {k: v for k, v in self.execution_history.items()}
            }
    
    def clear_queue(self):
        """Clear all items from the queue."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Empty:
                break
        
        with self.lock:
            self.stats["queue_size"] = 0
            self.completed_tasks.clear()
            self.dependency_graph.clear()
        
        logger.info("[QUEUE] Queue cleared")


# Global queue manager instance
queue_manager = AutomationQueueManager()


def get_queue_manager() -> AutomationQueueManager:
    """Get the global queue manager instance."""
    return queue_manager


def determine_rule_priority(rule_type: str, trigger_type: str, metadata: Optional[Dict] = None) -> ExecutionPriority:
    """
    Determine the execution priority for a rule based on its type and configuration.
    
    Args:
        rule_type: Type of rule (pot_sweep, autosorter, auto_topup)
        trigger_type: Trigger type (payday_detection, balance_threshold, etc.)
        metadata: Additional metadata
        
    Returns:
        ExecutionPriority: The determined priority level
    """
    # Critical priority rules
    if trigger_type == "balance_threshold":
        return ExecutionPriority.CRITICAL
    
    # High priority rules
    if trigger_type == "payday_detection":
        return ExecutionPriority.HIGH
    
    # Normal priority rules
    if rule_type in ["pot_sweep", "autosorter"]:
        return ExecutionPriority.NORMAL
    
    # Low priority rules
    if rule_type == "auto_topup":
        return ExecutionPriority.LOW
    
    # Background tasks
    if trigger_type == "manual_only":
        return ExecutionPriority.BACKGROUND
    
    # Default to normal priority
    return ExecutionPriority.NORMAL


def determine_dependencies(rule_type: str, trigger_type: str, metadata: Optional[Dict] = None) -> List[str]:
    """
    Determine dependencies for a rule based on its type and configuration.
    
    Args:
        rule_type: Type of rule
        trigger_type: Trigger type
        metadata: Additional metadata
        
    Returns:
        List[str]: List of rule IDs this rule depends on
    """
    dependencies = []
    
    # Autosorter rules with automation_trigger depend on pot sweeps
    if rule_type == "autosorter" and trigger_type == "automation_trigger":
        # This will be populated when pot sweeps complete
        # The actual dependency will be set when the rule is created
        pass
    
    # Add any other dependency logic here
    if metadata and "depends_on" in metadata:
        dependencies.extend(metadata["depends_on"])
    
    return dependencies 