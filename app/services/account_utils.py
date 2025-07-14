"""Account utility functions to avoid circular imports."""

from typing import List, Dict

from app.services.database_service import db_service


def get_selected_account_ids() -> List[str]:
    """Load selected account IDs from database.

    Returns:
        List[str]: List of selected account IDs.
    """
    return db_service.get_setting("selected_account_ids", [])


def get_account_names() -> Dict[str, str]:
    """Load custom account names from database.

    Returns:
        Dict[str, str]: Dictionary mapping account IDs to custom names.
    """
    return db_service.get_setting("account_names", {})


def save_selected_account_ids(account_ids: List[str]) -> bool:
    """Save selected account IDs to database.

    Args:
        account_ids: List of account IDs to save

    Returns:
        bool: True if saved successfully, False otherwise
    """
    return db_service.save_setting("selected_account_ids", account_ids, data_type="json")


def save_account_names(account_names: Dict[str, str]) -> bool:
    """Save custom account names to database.

    Args:
        account_names: Dictionary mapping account IDs to custom names

    Returns:
        bool: True if saved successfully, False otherwise
    """
    return db_service.save_setting("account_names", account_names, data_type="json") 