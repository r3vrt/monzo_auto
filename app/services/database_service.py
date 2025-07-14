"""Database service for handling database operations."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import current_app

from app.database import (
    Account,
    AuditLog,
    Pot,
    TaskExecution,
    Transaction,
    UserSettings,
    get_db_session,
    close_db_session,
)


class DatabaseService:
    """Service class for database operations."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def save_task_execution(
        self,
        task_name: str,
        result: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        process_id: Optional[int] = None,
    ) -> bool:
        """Save task execution to database.
        
        Args:
            task_name: Name of the task
            result: Result data dictionary
            success: Whether the task was successful
            error_message: Error message if task failed
            execution_time_ms: Execution time in milliseconds
            process_id: Process ID that ran the task
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        return self._execute_db_operation(
            lambda session: self._save_task_execution_impl(
                session, task_name, result, success, error_message, execution_time_ms, process_id
            )
        )

    def _save_task_execution_impl(
        self,
        session,
        task_name: str,
        result: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        process_id: Optional[int] = None,
    ) -> None:
        """Internal implementation of save_task_execution."""
        execution = TaskExecution(
            task_name=task_name,
            timestamp=datetime.utcnow(),
            success=success,
            result_data=json.dumps(result) if result else None,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            process_id=process_id,
        )
        session.add(execution)
        session.commit()

    def _execute_db_operation(self, operation):
        """Execute a database operation with consistent error handling.
        
        Args:
            operation: Function that takes a session and performs the operation
            
        Returns:
            bool: True if operation succeeded, False otherwise
        """
        session = None
        try:
            session = get_db_session()
            operation(session)
            return True
        except Exception as e:
            self.logger.exception(f"Database operation failed", extra={"operation": "db_operation"})
            if session:
                session.rollback()
            return False
        finally:
            close_db_session(session)
    
    def get_task_history(
        self, task_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get task execution history from database.
        
        Args:
            task_name: Name of the task
            limit: Maximum number of records to return
            
        Returns:
            List of task execution records
        """
        try:
            session = get_db_session()
            executions = (
                session.query(TaskExecution)
                .filter(TaskExecution.task_name == task_name)
                .order_by(TaskExecution.timestamp.desc())
                .limit(limit)
                .all()
            )
            
            result = []
            for execution in executions:
                record = {
                    "timestamp": execution.timestamp.isoformat(),
                    "success": execution.success,
                    "result": json.loads(execution.result_data) if execution.result_data else {},
                }
                if execution.error_message:
                    record["error"] = execution.error_message
                result.append(record)
            
            return result
        except Exception as e:
            self.logger.exception(f"Failed to get task history", extra={"operation": "get_task_history"})
            return []
        finally:
            close_db_session(session)
    
    def save_setting(
        self, key: str, value: Any, data_type: str = "string", description: Optional[str] = None
    ) -> bool:
        """Save a setting to the database.
        
        Args:
            key: Setting key
            value: Setting value
            data_type: Data type (string, int, float, bool, json)
            description: Optional description
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            session = get_db_session()
            
            # Convert value based on data type
            if data_type == "json" and not isinstance(value, str):
                value = json.dumps(value)
            elif data_type in ["int", "float", "bool"]:
                value = str(value)
            
            # Check if setting exists
            existing = session.query(UserSettings).filter(UserSettings.key == key).first()
            
            if existing:
                existing.value = value
                existing.data_type = data_type
                existing.updated_at = datetime.utcnow()
                if description:
                    existing.description = description
            else:
                setting = UserSettings(
                    key=key,
                    value=value,
                    data_type=data_type,
                    description=description,
                )
                session.add(setting)
            
            session.commit()
            return True
        except Exception as e:
            self.logger.exception(f"Failed to save setting {key}", extra={"operation": "save_setting"})
            if session:
                session.rollback()
            return False
        finally:
            close_db_session(session)
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting from the database.
        
        Args:
            key: Setting key
            default: Default value if setting not found
            
        Returns:
            Setting value or default
        """
        def operation(session):
            setting = session.query(UserSettings).filter(UserSettings.key == key).first()
            
            if not setting:
                return default
            
            # Convert value based on data type
            if setting.data_type == "json":
                return json.loads(setting.value) if setting.value else default
            elif setting.data_type == "int":
                return int(setting.value) if setting.value else default
            elif setting.data_type == "float":
                return float(setting.value) if setting.value else default
            elif setting.data_type == "bool":
                return setting.value.lower() == "true" if setting.value else default
            else:
                return setting.value if setting.value else default
        
        try:
            session = get_db_session()
            result = operation(session)
            return result
        except Exception as e:
            self.logger.exception(f"Failed to get setting {key}", extra={"operation": "get_setting"})
            return default
        finally:
            close_db_session(session)
    
    def save_account(self, account_data: Dict[str, Any]) -> bool:
        """Save or update account information.
        
        Args:
            account_data: Account data dictionary
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            session = get_db_session()
            
            account = session.query(Account).filter(Account.id == account_data["id"]).first()
            
            if account:
                # Update existing account
                for key, value in account_data.items():
                    if hasattr(account, key):
                        setattr(account, key, value)
                account.updated_at = datetime.utcnow()
            else:
                # Create new account
                account = Account(**account_data)
                session.add(account)
            
            session.commit()
            return True
        except Exception as e:
            self.logger.exception(f"Failed to save account {account_data.get('id')}", extra={"operation": "save_account"})
            if session:
                session.rollback()
            return False
        finally:
            close_db_session(session)
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts from database.
        
        Returns:
            List of account dictionaries
        """
        try:
            session = get_db_session()
            accounts = session.query(Account).all()
            
            result = []
            for account in accounts:
                account_dict = {
                    "id": account.id,
                    "name": account.name,
                    "type": account.type,
                    "currency": account.currency,
                    "is_selected": account.is_selected,
                    "custom_name": account.custom_name,
                    "last_sync": account.last_sync.isoformat() if account.last_sync else None,
                }
                result.append(account_dict)
            
            return result
        except Exception as e:
            self.logger.exception(f"Failed to get accounts", extra={"operation": "get_accounts"})
            return []
        finally:
            close_db_session(session)
    
    def save_pot(self, pot_data: Dict[str, Any]) -> bool:
        """Save or update pot information.
        
        Args:
            pot_data: Pot data dictionary
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            session = get_db_session()
            
            pot = session.query(Pot).filter(Pot.id == pot_data["id"]).first()
            
            if pot:
                # Update existing pot
                for key, value in pot_data.items():
                    if hasattr(pot, key):
                        setattr(pot, key, value)
                pot.updated_at = datetime.utcnow()
            else:
                # Create new pot
                pot = Pot(**pot_data)
                session.add(pot)
            
            session.commit()
            return True
        except Exception as e:
            self.logger.exception(f"Failed to save pot {pot_data.get('id')}", extra={"operation": "save_pot"})
            if session:
                session.rollback()
            return False
        finally:
            close_db_session(session)
    
    def get_pots(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pots from database.
        
        Args:
            account_id: Optional account ID to filter by
            
        Returns:
            List of pot dictionaries
        """
        try:
            session = get_db_session()
            query = session.query(Pot)
            
            if account_id:
                query = query.filter(Pot.account_id == account_id)
            
            pots = query.all()
            
            result = []
            for pot in pots:
                pot_dict = {
                    "id": pot.id,
                    "account_id": pot.account_id,
                    "name": pot.name,
                    "balance": pot.balance,
                    "goal_amount": pot.goal_amount,
                    "currency": pot.currency,
                    "last_sync": pot.last_sync.isoformat() if pot.last_sync else None,
                }
                result.append(pot_dict)
            
            return result
        except Exception as e:
            self.logger.exception(f"Failed to get pots", extra={"operation": "get_pots"})
            return []
        finally:
            close_db_session(session)
    
    def log_audit_event(
        self,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Log an audit event.
        
        Args:
            action: Action performed
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            details: Additional details
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            bool: True if logged successfully, False otherwise
        """
        try:
            session = get_db_session()
            
            audit_log = AuditLog(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details_json=json.dumps(details) if details else None,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            
            session.add(audit_log)
            session.commit()
            return True
        except Exception as e:
            self.logger.exception(f"Failed to log audit event", extra={"operation": "log_audit_event"})
            if session:
                session.rollback()
            return False
        finally:
            close_db_session(session)


# Global database service instance
db_service = DatabaseService() 