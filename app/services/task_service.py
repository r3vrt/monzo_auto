"""Task service for business logic related to automation tasks."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from flask import current_app

from app.services.database_service import db_service


def save_task_history(
    task_name: str, result: Dict[str, Any], success: bool = True
) -> None:
    """Save task execution history to database.

    Args:
        task_name: Name of the task executed
        result: Result data from the task
        success: Whether the task was successful
    """
    # Use database service instead of JSON files
    db_service.save_task_execution(
        task_name=task_name,
        result=result,
        success=success,
    )


def load_task_history(task_name: str) -> List[Dict[str, Any]]:
    """Load task execution history from database.

    Args:
        task_name: Name of the task to load history for
    Returns:
        List of execution records
    """
    # Use database service instead of JSON files
    return db_service.get_task_history(task_name, limit=10)


def get_task_list() -> List[Dict[str, Any]]:
    """Get the list of available automation tasks.

    Returns:
        List of task dicts
    """
    return [
        {
            "id": "transaction_sync",
            "name": "Transaction Sync",
            "description": "Sync recent transactions",
            "status": "active",
        },
        {
            "id": "auto_topup",
            "name": "Auto Topup",
            "description": "Automatically topup main account from pot when balance is low",
            "status": "active",
        },
        {
            "id": "sweep_pots",
            "name": "Sweep Pots",
            "description": "Move remaining balances from chosen pots into a target pot",
            "status": "active",
        },
        {
            "id": "autosorter",
            "name": "Autosorter",
            "description": "Distribute funds from a source pot to multiple destination pots based on user-defined values or pot goals",
            "status": "active",
        },
        {
            "id": "combined_automation",
            "name": "Combined Sweep & Sort",
            "description": "Run sweep pots and autosorter in sequence as a single scheduled automation.",
            "status": "active",
        },
    ]
