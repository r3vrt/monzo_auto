"""Configuration service for business logic related to application configuration."""

from typing import Any, Dict, Optional

from app.services.database_service import db_service
from app.services.account_utils import get_account_names


def get_automation_config() -> Dict[str, Any]:
    """Get automation config. Must be called within a Flask app context.
    
    Returns:
        Dict[str, Any]: Automation configuration dictionary
    """
    return db_service.get_setting("general.automation_tasks", {})


def get_config_overview() -> Dict[str, Any]:
    """Get the configuration overview data for the overview page.

    Returns:
        Dict[str, Any]: Configuration data for rendering.
    """
    config = {
        "auth": {
            "monzo_client_id": db_service.get_setting("auth.client_id", "not_configured"),
            "monzo_redirect_uri": db_service.get_setting("auth.redirect_uri", "not_configured"),
        },
        "general": {
            "debug_mode": db_service.get_setting("general.debug_mode", False),
            "auto_sync": db_service.get_setting("general.auto_sync", True),
            "sync_interval_minutes": db_service.get_setting("general.sync_interval_minutes", 30),
            "log_level": db_service.get_setting("general.log_level", "INFO"),
            "max_retries": db_service.get_setting("general.max_retries", 3),
            "timeout_seconds": db_service.get_setting("general.timeout_seconds", 30),
        },
        "auto_topup": db_service.get_setting("general.auto_topup", {}),
        "sweep_pots": db_service.get_setting("general.sweep_pots", {}),
        "autosorter": db_service.get_setting("general.autosorter", {}),
        "task_schedules": db_service.get_setting("general.task_schedules", {}),
        "automation_tasks": db_service.get_setting("general.automation_tasks", {}),
    }
    return config


def get_account_display_name(account_id: str, default_name: str = "Unknown Account") -> str:
    """Get the display name for an account, using custom name if available.
    
    Args:
        account_id (str): The account ID to look up.
        default_name (str): Default name to use if no custom name is found.
        
    Returns:
        str: The custom name if available, otherwise the default name.
    """
    account_names = get_account_names()
    return account_names.get(account_id, default_name)
