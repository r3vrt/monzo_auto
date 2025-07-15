"""Monzo API service integration."""

import datetime
import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from flask import current_app
from monzo import MonzoAPIError, MonzoAuthenticationError, MonzoClient

from app.services.database_service import db_service
from app.services.account_utils import get_selected_account_ids
from app.services.transaction_service import batch_fetch_transactions


class MonzoService:
    """Service class for Monzo API interactions."""

    def __init__(self):
        """Initialize the Monzo service."""
        self.client = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure the client is initialized before use."""
        if not self._initialized:
            self._initialize_client()
            self._initialized = True

    def _initialize_client(self) -> None:
        """Initialize the Monzo client with configuration from database."""
        try:
            # Load credentials from database
            client_id = db_service.get_setting("auth.client_id", "")
            client_secret = db_service.get_setting("auth.client_secret", "")
            redirect_uri = db_service.get_setting("auth.redirect_uri", "")
            
            if not client_id or not client_secret:
                # No credentials configured yet
                return
            
            # Initialize client with credentials from database
            self.client = MonzoClient(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri
            )

            # Try to load existing auth tokens if available
            try:
                # Check if we have tokens stored in database
                access_token = db_service.get_setting("auth.access_token", "")
                refresh_token = db_service.get_setting("auth.refresh_token", "")
                
                if access_token and refresh_token:
                    # Set the tokens on the client
                    self.client.access_token = access_token
                    self.client.refresh_token = refresh_token
            except Exception as e:
                # No tokens available, user needs to authenticate
                pass

        except Exception as e:
            current_app.logger.error(f"Failed to initialize Monzo client: {e}")

    def _save_tokens_to_db(self):
        """Save current tokens to database."""
        if self.client:
            db_service.save_setting("auth.access_token", self.client.access_token or "", data_type="string")
            db_service.save_setting("auth.refresh_token", self.client.refresh_token or "", data_type="string")

    def _call_with_token_refresh(self, api_call, *args, **kwargs):
        """Execute an API call with automatic token refresh on 401 errors.

        Args:
            api_call: The API method to call
            *args: Arguments to pass to the API call
            **kwargs: Keyword arguments to pass to the API call

        Returns:
            The result of the API call

        Raises:
            MonzoAuthenticationError: If token refresh fails or authentication is required
        """
        try:
            result = api_call(*args, **kwargs)
            # Save tokens after successful call in case they were refreshed
            self._save_tokens_to_db()
            return result
        except MonzoAuthenticationError as e:
            current_app.logger.warning(f"MonzoAuthenticationError encountered: {e}. Attempting token refresh.")
            # Try to refresh the token
            try:
                if self.client and self.client.refresh_token:
                    self.client.refresh_access_token()
                    current_app.logger.info("Token refresh successful. Retrying API call.")
                    # Save refreshed tokens
                    self._save_tokens_to_db()
                    # Retry the original call with the new token
                    result = api_call(*args, **kwargs)
                    return result
                else:
                    current_app.logger.error("No refresh token available - manual reauthentication required.")
                    raise MonzoAuthenticationError(
                        "No refresh token available - manual reauthentication required"
                    )

            except Exception as refresh_error:
                current_app.logger.error(f"Token refresh failed: {refresh_error}")
                raise MonzoAuthenticationError(f"Token refresh failed: {refresh_error}")

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Get the OAuth authorization URL.

        Args:
            state: Optional CSRF token

        Returns:
            Authorization URL for user to visit
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        return self.client.get_authorization_url(state=state)

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response data
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            result = self.client.exchange_code_for_token(code)
            # Save tokens to database after successful exchange
            self._save_tokens_to_db()
            return result
        except MonzoAPIError as e:
            raise

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens (alias for compatibility).

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in authorization

        Returns:
            Token response data
        """
        return self.exchange_code_for_token(code)

    def get_user_info(self) -> Dict[str, Any]:
        """Get information about the authenticated user (alias for whoami).

        Returns:
            User information
        """
        return self.whoami()

    def clear_tokens(self) -> None:
        """Clear stored authentication tokens.

        This clears only the access and refresh tokens while preserving
        the OAuth configuration (client_id, client_secret, redirect_uri).
        """
        try:
            # Clear tokens from database
            db_service.save_setting("auth.access_token", "", data_type="string")
            db_service.save_setting("auth.refresh_token", "", data_type="string")
            
            # Clear tokens from client if it exists
            if self.client:
                self.client.access_token = None
                self.client.refresh_token = None
        except Exception as e:
            current_app.logger.error(f"Failed to clear tokens: {e}")

    def ensure_recent_authentication(self) -> None:
        """Ensure recent authentication for full transaction access.

        This performs a full reauthentication to access transaction data
        beyond the 90-day limit.
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            self.client.ensure_recent_authentication()
        except MonzoAPIError as e:
            raise

    def get_accounts(self) -> List[dict]:
        """Get user accounts.

        Returns:
            List of account dictionaries
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            accounts = self._call_with_token_refresh(self.client.get_accounts)
            # Use to_dict if available, else __dict__
            result = []
            for account in accounts:
                if hasattr(account, "to_dict") and callable(
                    getattr(account, "to_dict")
                ):
                    result.append(account.to_dict())
                elif hasattr(account, "__dict__"):
                    result.append(dict(account.__dict__))
                else:
                    result.append(str(account))  # fallback: string representation
            return result
        except MonzoAPIError as e:
            raise

    def get_balance(self, account_id: str) -> Dict[str, Any]:
        """Get account balance.

        Args:
            account_id: The account ID

        Returns:
            Balance information
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            balance = self._call_with_token_refresh(self.client.get_balance, account_id)
            # Use to_dict if available, else __dict__
            if hasattr(balance, "to_dict") and callable(getattr(balance, "to_dict")):
                return balance.to_dict()
            elif hasattr(balance, "__dict__"):
                return dict(balance.__dict__)
            else:
                return {"balance": str(balance)}  # fallback: string representation
        except MonzoAPIError as e:
            raise

    def get_transactions(
        self,
        account_id: str,
        limit: int = 100,
        ensure_recent_auth: bool = False,
        since: Optional[str] = None,
        before: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get account transactions.

        Args:
            account_id: The account ID
            limit: Number of transactions to retrieve
            ensure_recent_auth: Whether to ensure recent authentication for full access
            since: ISO8601 string for the earliest transaction to fetch
            before: ISO8601 string for the latest transaction to fetch

        Returns:
            List of transaction dictionaries
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            kwargs = {"limit": limit, "ensure_recent_auth": ensure_recent_auth}
            if since is not None:
                kwargs["since"] = since
            if before is not None:
                kwargs["before"] = before
            transactions = self._call_with_token_refresh(
                self.client.get_transactions, account_id, **kwargs
            )
            result = []
            for transaction in transactions:
                if isinstance(transaction, dict):
                    result.append(transaction)
                elif hasattr(transaction, "to_dict") and callable(
                    getattr(transaction, "to_dict")
                ):
                    result.append(transaction.to_dict())
                elif hasattr(transaction, "__dict__"):
                    result.append(dict(transaction.__dict__))
                else:
                    result.append({"raw": str(transaction)})
            return result
        except MonzoAPIError as e:
            raise

    def get_pots(self, account_id: str) -> List[Dict[str, Any]]:
        """Get user pots for a specific account.

        Args:
            account_id: The account ID

        Returns:
            List of pot dictionaries
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            pots = self._call_with_token_refresh(self.client.get_pots, account_id)
            if pots:
                pass
            result = []
            for i, pot in enumerate(pots):
                try:
                    if hasattr(pot, "to_dict") and callable(getattr(pot, "to_dict")):
                        pot_dict = pot.to_dict()
                    elif hasattr(pot, "__dict__"):
                        pot_dict = dict(pot.__dict__)
                    else:
                        pot_dict = {"id": str(pot), "name": "Unknown"}

                    result.append(pot_dict)

                except Exception as e:
                    result.append({"id": f"error_{i}", "name": "Error"})
            return result
        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def get_pot_by_name(
        self, account_id: str, pot_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific pot by name.

        Args:
            account_id: The account ID
            pot_name: The name of the pot to find

        Returns:
            Pot dictionary if found, None otherwise
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            # First, try to use the library's built-in method if it exists
            if hasattr(self.client, "get_pot_by_name"):
                try:
                    pot = self._call_with_token_refresh(
                        self.client.get_pot_by_name, account_id, pot_name
                    )
                    if pot:
                        if hasattr(pot, "to_dict") and callable(
                            getattr(pot, "to_dict")
                        ):
                            return pot.to_dict()
                        elif hasattr(pot, "__dict__"):
                            return dict(pot.__dict__)
                        else:
                            return {"id": str(pot), "name": pot_name}
                    return None
                except Exception as e:
                    pass

            # Fallback: get all pots and search by name
            pots = self._call_with_token_refresh(self.client.get_pots, account_id)
            if pots:
                pass
            for i, pot in enumerate(pots):
                try:
                    if hasattr(pot, "to_dict") and callable(getattr(pot, "to_dict")):
                        pot_dict = pot.to_dict()
                    elif hasattr(pot, "__dict__"):
                        pot_dict = dict(pot.__dict__)
                    elif hasattr(pot, "name"):  # Direct attribute access
                        pot_dict = {
                            "id": getattr(pot, "id", ""),
                            "name": getattr(pot, "name", ""),
                            "balance": getattr(pot, "balance", 0),
                            "currency": getattr(pot, "currency", "GBP"),
                        }
                    else:
                        continue
                    if pot_dict.get("name", "").lower() == pot_name.lower():
                        return pot_dict

                except Exception as e:
                    continue

            # Get available pot names for better error reporting
            available_names = []
            for pot in pots:
                try:
                    if hasattr(pot, "name"):
                        available_names.append(getattr(pot, "name", "Unknown"))
                    elif hasattr(pot, "to_dict"):
                        pot_dict = pot.to_dict()
                        available_names.append(pot_dict.get("name", "Unknown"))
                    elif hasattr(pot, "__dict__"):
                        pot_dict = dict(pot.__dict__)
                        available_names.append(pot_dict.get("name", "Unknown"))
                except:
                    available_names.append("Unknown")
            return None

        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def get_pot_balance(self, pot_id: str) -> Dict[str, Any]:
        """Get balance for a specific pot.

        Args:
            pot_id: The pot ID

        Returns:
            Pot balance information
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            # Try to get pot details which should include balance
            try:
                pot = self._call_with_token_refresh(self.client.get_pot, pot_id)
            except KeyError as e:
                # Fallback: try to get balance from the pots list instead
                return self._get_pot_balance_from_list(pot_id)
            except Exception as e:
                # Fallback: try to get balance from the pots list instead
                return self._get_pot_balance_from_list(pot_id)

            try:
                if hasattr(pot, "to_dict") and callable(getattr(pot, "to_dict")):
                    pot_dict = pot.to_dict()
                elif hasattr(pot, "__dict__"):
                    pot_dict = dict(pot.__dict__)
                elif hasattr(pot, "balance"):  # Direct attribute access
                    pot_dict = {
                        "id": getattr(pot, "id", pot_id),
                        "balance": getattr(pot, "balance", 0),
                        "currency": getattr(pot, "currency", "GBP"),
                    }
                else:
                    return self._get_pot_balance_from_list(pot_id)
                return pot_dict

            except Exception as e:
                return self._get_pot_balance_from_list(pot_id)

        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def _get_pot_balance_from_list(self, pot_id: str) -> Dict[str, Any]:
        """Fallback method to get pot balance from the pots list.

        Args:
            pot_id: The pot ID

        Returns:
            Pot balance information
        """
        try:
            # Get all pots and find the one we need
            accounts = self.get_accounts()
            if not accounts:
                return {"balance": 0, "currency": "GBP"}

            account_id = accounts[0]["id"]
            pots = self.get_pots(account_id)

            for pot in pots:
                if pot.get("id") == pot_id:
                    return {
                        "id": pot.get("id", pot_id),
                        "balance": pot.get("balance", 0),
                        "currency": pot.get("currency", "GBP"),
                    }
            return {"balance": 0, "currency": "GBP"}

        except Exception as e:
            return {"balance": 0, "currency": "GBP"}

    def withdraw_from_pot(
        self, pot_id: str, amount: int, destination_account_id: str
    ) -> Dict[str, Any]:
        """Withdraw money from a pot to the main account.

        Args:
            pot_id: The pot ID to withdraw from
            amount: Amount to withdraw in pence
            destination_account_id: The account ID to transfer to

        Returns:
            Transfer result
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            # Generate a unique dedupe_id for this withdrawal
            import time
            import uuid

            dedupe_id = f"auto_topup_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            # Use the library's withdraw_from_pot method with the optional dedupe_id
            if hasattr(self.client, "withdraw_from_pot"):
                # The library expects: (pot_id, destination_account_id, amount, dedupe_id)
                result = self._call_with_token_refresh(
                    self.client.withdraw_from_pot,
                    pot_id,
                    destination_account_id,
                    amount,
                    dedupe_id,
                )

                if hasattr(result, "to_dict") and callable(getattr(result, "to_dict")):
                    return result.to_dict()
                elif hasattr(result, "__dict__"):
                    return dict(result.__dict__)
                else:
                    return {"result": str(result)}
            else:
                raise MonzoAPIError(
                    "withdraw_from_pot method not found in Monzo client"
                )

        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def deposit_to_pot(
        self, pot_id: str, amount: int, source_account_id: str
    ) -> Dict[str, Any]:
        """Deposit money from the main account to a pot.

        Args:
            pot_id: The pot ID to deposit to
            amount: Amount to deposit in pence
            source_account_id: The account ID to transfer from

        Returns:
            Transfer result
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            # Generate a unique dedupe_id for this deposit
            import time
            import uuid

            dedupe_id = f"sweep_deposit_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            # Use the library's deposit_into_pot method with the optional dedupe_id
            if hasattr(self.client, "deposit_into_pot"):
                # The library expects: (pot_id, source_account_id, amount, dedupe_id)
                result = self._call_with_token_refresh(
                    self.client.deposit_into_pot,
                    pot_id,
                    source_account_id,
                    amount,
                    dedupe_id,
                )

                if hasattr(result, "to_dict") and callable(getattr(result, "to_dict")):
                    return result.to_dict()
                elif hasattr(result, "__dict__"):
                    return dict(result.__dict__)
                else:
                    return {"result": str(result)}
            else:
                raise MonzoAPIError("deposit_into_pot method not found in Monzo client")

        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def create_webhook(self, account_id: str, url: str) -> Dict[str, Any]:
        """Create a webhook for an account.

        Args:
            account_id: The account ID
            url: Webhook URL

        Returns:
            Webhook information
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            webhook = self._call_with_token_refresh(
                self.client.create_webhook, account_id, url
            )
            return webhook.to_dict()
        except MonzoAPIError as e:
            raise

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook.

        Args:
            webhook_id: The webhook ID

        Returns:
            True if successful
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            self._call_with_token_refresh(self.client.delete_webhook, webhook_id)
            return True
        except MonzoAPIError as e:
            raise

    def whoami(self) -> Dict[str, Any]:
        """Get information about the authenticated user.

        Returns:
            User information
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")

        try:
            user_info = self._call_with_token_refresh(self.client.whoami)
            # Use to_dict if available, else __dict__
            if hasattr(user_info, "to_dict") and callable(
                getattr(user_info, "to_dict")
            ):
                return user_info.to_dict()
            elif hasattr(user_info, "__dict__"):
                return dict(user_info.__dict__)
            else:
                return {"name": str(user_info)}  # fallback: string representation
        except MonzoAPIError as e:
            raise

    def get_all_transactions(
        self, account_id: str, since: Optional[str] = None, before: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all transactions for an account using the Monzo library's _get_all_transactions endpoint.

        This method uses pagination to fetch all transactions, not just the most recent 100.

        Args:
            account_id: The account ID
            since: ISO 8601 timestamp to get transactions since
            before: ISO 8601 timestamp to get transactions before

        Returns:
            List of all transaction dictionaries
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")
        try:
            if hasattr(self.client, "_get_all_transactions"):
                transactions = self._call_with_token_refresh(
                    self.client._get_all_transactions,
                    account_id,
                    since=since,
                    before=before,
                )
            else:
                transactions = self.get_transactions(
                    account_id, limit=100, since=since, before=before
                )
            result = []
            for transaction in transactions:
                if isinstance(transaction, dict):
                    result.append(transaction)
                elif hasattr(transaction, "to_dict") and callable(
                    getattr(transaction, "to_dict")
                ):
                    result.append(transaction.to_dict())
                elif hasattr(transaction, "__dict__"):
                    result.append(dict(transaction.__dict__))
                else:
                    result.append({"raw": str(transaction)})
            return result
        except MonzoAPIError as e:
            raise

    def autosorter(
        self,
        source_pot: str,
        destination_pots: Optional[Dict[str, Dict[str, float | bool]]] = None,
        allocation_strategy: str = "free_selection",
        priority_pots: Optional[List[str]] = None,
        goal_allocation_method: str = "even",
        bills_pot_name: str = "",
        pay_cycle: Optional[Dict] = None,
        enable_bills_pot: bool = False,
        savings_pot_name: str = "",
    ) -> None:
        """Distribute funds from a source pot to destination pots, filling bills pot for the pay cycle first."""
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")
        selected_accounts = get_selected_account_ids()
        if not selected_accounts:
            raise Exception("No selected account for autosorter.")
        account_id = selected_accounts[0]
        pots = self.get_pots(account_id)
        # Filter out deleted pots for all logic
        active_pots = [pot for pot in pots if not pot.get("deleted", False)]
        pot_map = {pot["name"]: pot for pot in active_pots}
        src_pot = pot_map.get(source_pot) if source_pot in pot_map else None
        if not src_pot:
            raise Exception(f"Source pot '{source_pot}' not found.")
        src_balance = src_pot.get("balance", 0) / 100.0  # pounds
        if src_balance <= 0:
            return
        # Step 1: Calculate bills pot top-up needed for the pay cycle (only if enabled)
        bills_topup = 0.0
        if (
            enable_bills_pot
            and bills_pot_name
            and pay_cycle
            and pay_cycle.get("payday")
        ):
            bills_pot = pot_map.get(bills_pot_name)
            if bills_pot:
                payday_day = int(pay_cycle["payday"])
                today = date.today()
                if pay_cycle.get("frequency") == "biweekly":
                    days_since_last_payday = (today.day - payday_day) % 14
                    if days_since_last_payday < 0:
                        days_since_last_payday += 14
                    last_payday = today - datetime.timedelta(
                        days=days_since_last_payday
                    )
                    cycle_start = last_payday - datetime.timedelta(days=14)
                    cycle_end = last_payday
                elif pay_cycle.get("frequency") == "monthly":
                    if today.day >= payday_day:
                        last_payday = today.replace(day=payday_day)
                    else:
                        if today.month == 1:
                            prev_month = 12
                            prev_year = today.year - 1
                        else:
                            prev_month = today.month - 1
                            prev_year = today.year
                        try:
                            last_payday = today.replace(
                                year=prev_year, month=prev_month, day=payday_day
                            )
                        except ValueError:
                            last_day = (
                                datetime.date(prev_year, prev_month + 1, 1)
                                - datetime.timedelta(days=1)
                            ).day
                            last_payday = today.replace(
                                year=prev_year,
                                month=prev_month,
                                day=min(payday_day, last_day),
                            )
                    if last_payday.month == 1:
                        prev_cycle_month = 12
                        prev_cycle_year = last_payday.year - 1
                    else:
                        prev_cycle_month = last_payday.month - 1
                        prev_cycle_year = last_payday.year
                    try:
                        cycle_start = last_payday.replace(
                            year=prev_cycle_year, month=prev_cycle_month, day=payday_day
                        )
                    except ValueError:
                        last_day = (
                            datetime.date(prev_cycle_year, prev_cycle_month + 1, 1)
                            - datetime.timedelta(days=1)
                        ).day
                        cycle_start = last_payday.replace(
                            year=prev_cycle_year,
                            month=prev_cycle_month,
                            day=min(payday_day, last_day),
                        )
                    cycle_end = last_payday
                else:
                    cycle_start = today - datetime.timedelta(days=60)
                    cycle_end = today - datetime.timedelta(days=30)
                # Ensure since and before are RFC3339 datetimes (no microseconds)
                if isinstance(cycle_start, datetime.datetime):
                    since_dt = cycle_start.replace(microsecond=0)
                else:
                    since_dt = datetime.datetime.combine(cycle_start, datetime.time.min)
                if isinstance(cycle_end, datetime.datetime):
                    before_dt = cycle_end.replace(microsecond=0)
                else:
                    before_dt = datetime.datetime.combine(cycle_end, datetime.time.min)
                since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                before = before_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                txns = batch_fetch_transactions(account_id, since, before, batch_days=10)
                bills_pot_account_id = None
                for txn in txns:
                    metadata = txn.get("metadata", {})
                    if (
                        "pot_account_id" in metadata
                        and metadata.get("pot_id") == bills_pot["id"]
                    ):
                        bills_pot_account_id = metadata["pot_account_id"]
                        break
                outgoings = 0.0
                if bills_pot_account_id:
                    try:
                        pot_txns = batch_fetch_transactions(bills_pot_account_id, since, before, batch_days=10)
                        for txn in pot_txns:
                            if txn.get("amount", 0) < 0:
                                outgoings += abs(txn["amount"]) / 100.0
                    except Exception as e:
                        for txn in txns:
                            if (
                                txn.get("pot_id") == bills_pot["id"]
                                and txn.get("amount", 0) < 0
                            ):
                                outgoings += abs(txn["amount"]) / 100.0
                else:
                    for txn in txns:
                        if (
                            txn.get("pot_id") == bills_pot["id"]
                            and txn.get("amount", 0) < 0
                        ):
                            outgoings += abs(txn["amount"]) / 100.0
                bills_balance = bills_pot.get("balance", 0) / 100.0
                bills_topup = max(0, outgoings - bills_balance)
                if bills_topup > 0:
                    amt_pence = int(round(bills_topup * 100))
                    self.deposit_to_pot(bills_pot["id"], amt_pence, account_id)
                src_balance -= bills_topup
        # Step 2: Distribute the rest based on allocation strategy
        allocations = {}
        if allocation_strategy == "free_selection":
            if destination_pots:
                total_percent = sum(
                    info["amount"]
                    for name, info in destination_pots.items()
                    if info["is_percent"] and name in pot_map
                )
                total_fixed = sum(
                    info["amount"]
                    for name, info in destination_pots.items()
                    if not info["is_percent"] and name in pot_map
                )
                for pot_name, info in destination_pots.items():
                    if (
                        pot_name == source_pot
                        or pot_name == bills_pot_name
                        or pot_name not in pot_map
                    ):
                        continue
                    if info["is_percent"]:
                        amt = (info["amount"] / 100.0) * src_balance
                    else:
                        amt = info["amount"]
                    allocations[pot_name] = amt
                total_alloc = sum(allocations.values())
                if total_alloc > src_balance:
                    scale = src_balance / total_alloc
                    for pot_name in allocations:
                        allocations[pot_name] *= scale
        elif allocation_strategy in ["all_goals", "priority_goals"]:
            priority_pots = [p for p in (priority_pots or []) if p in pot_map]
            if allocation_strategy == "priority_goals" and priority_pots:
                for pot_name in priority_pots:
                    if (
                        pot_name == source_pot
                        or pot_name == bills_pot_name
                        or pot_name not in pot_map
                    ):
                        continue
                    pot = pot_map.get(pot_name)
                    if pot and pot.get("goal_amount"):
                        needed = (pot["goal_amount"] - pot.get("balance", 0)) / 100.0
                        amt = min(needed, src_balance)
                        if amt > 0:
                            allocations[pot_name] = amt
                            src_balance -= amt
            remaining_pots_with_goals = [
                pot
                for pot in active_pots
                if (
                    pot["name"] != source_pot
                    and pot["name"] != bills_pot_name
                    and pot.get("goal_amount")
                    and pot["name"] not in allocations
                )
            ]
            if not remaining_pots_with_goals:
                return
            if goal_allocation_method == "even":
                per_pot = src_balance / len(remaining_pots_with_goals)
                for pot in remaining_pots_with_goals:
                    needed = (pot["goal_amount"] - pot.get("balance", 0)) / 100.0
                    amt = min(per_pot, needed)
                    allocations[pot["name"]] = max(0, amt)
            elif goal_allocation_method == "relative":
                needs = {
                    pot["name"]: max(
                        0, (pot["goal_amount"] - pot.get("balance", 0)) / 100.0
                    )
                    for pot in remaining_pots_with_goals
                }
                total_needed = sum(needs.values())
                if total_needed == 0:
                    return
                
                # First, top up pots that are within £20 of their goal
                pots_to_remove = []
                for pot in remaining_pots_with_goals:
                    pot_name = pot["name"]
                    current_balance = pot.get("balance", 0) / 100.0
                    goal_amount = pot["goal_amount"] / 100.0
                    remaining_needed = goal_amount - current_balance
                    
                    # If remaining amount is under £20 and we have enough source balance
                    if 0 < remaining_needed <= 20.0 and remaining_needed <= src_balance:
                        allocations[pot_name] = remaining_needed
                        src_balance -= remaining_needed
                        pots_to_remove.append(pot_name)
                
                # Remove topped up pots from remaining pots for relative distribution
                remaining_pots_with_goals = [
                    pot for pot in remaining_pots_with_goals 
                    if pot["name"] not in pots_to_remove
                ]
                
                # Now do relative distribution with remaining pots and balance
                if remaining_pots_with_goals:
                    needs = {
                        pot["name"]: max(
                            0, (pot["goal_amount"] - pot.get("balance", 0)) / 100.0
                        )
                        for pot in remaining_pots_with_goals
                    }
                    total_needed = sum(needs.values())
                    if total_needed > 0:
                        max_per_pot = src_balance * 0.20  # 20% maximum per pot
                    for pot in remaining_pots_with_goals:
                        share = needs[pot["name"]] / total_needed
                        amt = share * src_balance
                        amt = min(amt, needs[pot["name"]], max_per_pot)  # Cap at 20% of source balance
                        allocations[pot["name"]] = amt
        # Step 3: Execute allocations
        for pot_name, amt in allocations.items():
            if amt < 0.01:
                continue
            dest_pot = pot_map.get(pot_name)
            if not dest_pot:
                continue
            amt_pence = int(round(amt * 100))
            if amt_pence < 1:
                continue
            try:
                self.deposit_to_pot(dest_pot["id"], amt_pence, account_id)
            except Exception as e:
                pass
        # Step 4: Check flex account balance and adjust remaining balance for savings pot
        accounts = self.get_accounts()
        flex_account = None
        for account in accounts:
            if account.get("type") == "uk_monzo_flex":
                flex_account = account
                break
        
        flex_account_balance = 0.0
        if flex_account:
            flex_account_balance = self.get_balance(flex_account["id"]).get("balance", 0) / 100.0
        
        if flex_account_balance < 0:
            # If flex account is negative, leave 20% of remaining balance in source pot
            buffer_amount = src_balance * 0.20
            src_balance -= buffer_amount
        # Step 5: Transfer remaining balance to savings pot if configured
        if savings_pot_name:
            savings_pot = pot_map.get(savings_pot_name)
            if savings_pot:
                remaining_balance = src_balance
                if remaining_balance > 0:
                    amt_pence = int(round(remaining_balance * 100))
                    self.deposit_to_pot(savings_pot["id"], amt_pence, account_id)

    def annotate_transaction(self, transaction_id: str, notes: str) -> dict:
        """Annotate a transaction with a note using the Monzo API.

        Args:
            transaction_id (str): The transaction ID to annotate.
            notes (str): The note to add to the transaction.
        Returns:
            dict: The updated transaction as a dictionary.
        Raises:
            MonzoAPIError: If the API request fails.
            MonzoAuthenticationError: If authentication fails.
        """
        self._ensure_initialized()
        if not self.client:
            raise MonzoAuthenticationError("Client not initialized")
        try:
            # The Monzo API expects the note in the metadata dict with key 'notes'
            txn = self._call_with_token_refresh(
                self.client.annotate_transaction, transaction_id, {"notes": notes}
            )
            if hasattr(txn, "to_dict") and callable(getattr(txn, "to_dict")):
                return txn.to_dict()
            elif hasattr(txn, "__dict__"):
                return dict(txn.__dict__)
            else:
                return dict(txn)
        except MonzoAPIError as e:
            raise
        except Exception as e:
            raise

    def find_and_annotate_transaction(self, account_id: str, dedupe_id: str, notes: str) -> bool:
        """Find a transaction by dedupe_id and annotate it with notes.
        
        Args:
            account_id (str): The account ID to search in
            dedupe_id (str): The dedupe_id to search for
            notes (str): The notes to add to the transaction
            
        Returns:
            bool: True if transaction was found and annotated, False otherwise
        """
        try:
            # Search recent transactions for one with this dedupe_id
            recent_txns = self.get_transactions(account_id, limit=20)
            for txn in recent_txns:
                if txn.get("metadata", {}).get("dedupe_id") == dedupe_id:
                    transaction_id = txn.get("id")
                    if transaction_id:
                        self.annotate_transaction(transaction_id, notes)
                        return True
            return False
        except Exception as e:
            current_app.logger.warning(f"Failed to find and annotate transaction: {e}")
            return False



