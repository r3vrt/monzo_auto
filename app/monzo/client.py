"""
MonzoClient utility for handling OAuth, token management, and Monzo API calls using monzo_apy.
"""

import logging
from typing import Any, Dict, List, Optional

from monzo.client import MonzoClient as MonzoApyClient

from app.db import get_db_session
from app.models import User

logger = logging.getLogger(__name__)


class MonzoClient:
    """
    Wrapper for monzo_apy MonzoClient to handle OAuth, token management, and Monzo API calls.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = None,
        tokens: Optional[Dict[str, Any]] = None,
        timeout: int = 5,
    ):
        if not client_id or not client_secret:
            raise ValueError(
                "MonzoClient requires client_id and client_secret (no env fallback)"
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or ""
        self.tokens = tokens or {}
        self.timeout = timeout
        
        # Create the underlying client with only the parameters it accepts
        client_kwargs = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "access_token": self.tokens.get("access_token"),
            "refresh_token": self.tokens.get("refresh_token"),
        }
        
        # Only add timeout if the MonzoApyClient accepts it
        try:
            self.client = MonzoApyClient(**client_kwargs, timeout=self.timeout)
        except TypeError:
            # If timeout is not accepted, create without it
            self.client = MonzoApyClient(**client_kwargs)

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Returns the Monzo OAuth authorization URL for user login.
        """
        if not self.redirect_uri:
            raise ValueError("MonzoClient requires redirect_uri for authorization URL")
        return self.client.get_authorization_url(state=state)

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchanges the OAuth code for access and refresh tokens.
        """
        if not self.redirect_uri:
            raise ValueError("MonzoClient requires redirect_uri for token exchange")
        tokens = self.client.exchange_code_for_token(code)
        self.tokens = tokens
        return tokens

    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refreshes the access token using the refresh token.
        Note: redirect_uri is not required for token refresh, only for initial auth.
        """
        try:
            logger.info("Attempting to refresh access token")
            tokens = self.client.refresh_access_token()
            self.tokens = tokens
            logger.info("Access token refreshed successfully")
            return tokens
        except Exception as e:
            # Check if refresh token is invalid/expired
            error_msg = str(e).lower()
            logger.error(f"Token refresh failed: {error_msg}")
            if any(term in error_msg for term in ['invalid_grant', 'refresh_token', 'expired']):
                logger.warning("Refresh token has expired, user needs to reauthenticate")
                raise Exception("Refresh token has expired. Please reauthenticate.") from e
            raise

    def _with_token_refresh(self, func, *args, **kwargs):
        """
        Helper to wrap Monzo API calls and refresh token on invalid/expired token error.
        Retries the call once after refreshing.
        
        This method provides comprehensive error detection for token-related issues,
        including HTTP 401 errors and various error messages that indicate token problems.
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check for token error - more comprehensive error detection
            should_refresh = False
            
            # Check for HTTP 401 (Unauthorized)
            response = getattr(e, "response", None)
            if response is not None and getattr(response, "status_code", None) == 401:
                should_refresh = True
            
            # Check for token-related error messages
            error_msg = str(e).lower()
            if any(term in error_msg for term in ['unauthorized', 'token', 'expired', 'invalid']):
                should_refresh = True
                
            # Check for specific Monzo API errors
            if hasattr(e, 'error') and e.error:
                error_detail = str(e.error).lower()
                if any(term in error_detail for term in ['unauthorized', 'token', 'expired', 'invalid']):
                    should_refresh = True
            
            if should_refresh:
                logger.warning(f"Token refresh needed due to error: {error_msg}")
                try:
                    # Try to refresh token
                    tokens = self.refresh_access_token()
                    logger.info("Token refresh successful")
                    # Update tokens in DB
                    user_id = tokens.get("user_id") or self.tokens.get("user_id")
                    if user_id:
                        with next(get_db_session()) as db:
                            user = db.query(User).filter_by(monzo_user_id=user_id).first()
                            if user:
                                access_token = tokens.get("access_token")
                                if access_token is not None:
                                    user.monzo_access_token = access_token
                                refresh_token = tokens.get("refresh_token")
                                if refresh_token is not None:
                                    user.monzo_refresh_token = refresh_token
                                obtained_at = tokens.get("obtained_at")
                                if obtained_at is not None and hasattr(
                                    user, "monzo_token_obtained_at"
                                ):
                                    user.monzo_token_obtained_at = obtained_at
                                db.commit()
                    # Update self.tokens for future calls
                    self.tokens = tokens
                    # Update the underlying client with new tokens
                    # Use the correct attribute names for monzo_apy client
                    if hasattr(self.client, 'access_token'):
                        self.client.access_token = tokens.get("access_token")
                    if hasattr(self.client, 'refresh_token'):
                        self.client.refresh_token = tokens.get("refresh_token")
                    # Some versions might use different attribute names
                    if hasattr(self.client, '_access_token'):
                        self.client._access_token = tokens.get("access_token")
                    if hasattr(self.client, '_refresh_token'):
                        self.client._refresh_token = tokens.get("refresh_token")
                    # Retry the original call
                    return func(*args, **kwargs)
                except Exception as refresh_error:
                    # If refresh fails, check if it's a refresh token issue
                    refresh_error_msg = str(refresh_error).lower()
                    if any(term in refresh_error_msg for term in ['invalid_grant', 'refresh_token', 'expired']):
                        raise Exception("Refresh token has expired. Please reauthenticate via the UI.") from refresh_error
                    # If refresh fails for other reasons, raise the original error with refresh context
                    raise Exception(f"Token refresh failed after authorization error: {refresh_error}") from e
            
            # If not a token error, re-raise original exception
            raise

    def get_accounts(self) -> List[Any]:
        """
        Returns a list of the user's Monzo accounts (Account objects).
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(self.client.get_accounts)

    def get_pots(self, account_id: Optional[str]) -> List[Any]:
        """
        Returns a list of pots. If account_id is None, fetch pots for all user accounts.
        Automatically refreshes token if needed.
        """
        # If no account specified, aggregate pots from all (open) accounts
        if not account_id:
            pots: List[Any] = []
            accounts = self.get_accounts()
            for acc in accounts:
                try:
                    if getattr(acc, "closed", False):
                        continue
                    # Call underlying client with positional account_id arg
                    acc_pots = self._with_token_refresh(self.client.get_pots, acc.id)
                    pots.extend(acc_pots or [])
                except Exception as e:
                    logger.error(f"Error fetching pots for account {getattr(acc,'id','?')}: {e}")
                    continue
            return pots
        
        # Single account mode
        return self._with_token_refresh(self.client.get_pots, account_id)

    def get_transactions(
        self,
        account_id: str,
        since: Optional[str] = None,
        before: Optional[str] = None,
        auto_paginate: bool = False,
    ) -> List[Any]:
        """
        Returns a list of all transactions for the given account (Transaction objects).
        Automatically refreshes token if needed.
        
        Args:
            account_id: The account ID
            since: ISO 8601 timestamp or transaction ID to get transactions since
            before: ISO 8601 timestamp to get transactions before
            auto_paginate: If True, automatically fetch all transactions using pagination
        """
        return self._with_token_refresh(
            self.client.get_transactions,
            account_id,
            since=since,
            before=before,
            auto_paginate=auto_paginate,
        )

    def get_balance(self, account_id: str) -> Any:
        """
        Returns the balance for the given account (Balance object).
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(self.client.get_balance, account_id)

    def deposit_to_pot(
        self, pot_id: str, account_id: str, amount: int, dedupe_id: Optional[str] = None
    ) -> Any:
        """
        Deposits money from an account into a pot.
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(
            self.client.deposit_to_pot, pot_id, account_id, amount, dedupe_id=dedupe_id
        )

    def withdraw_from_pot(
        self, pot_id: str, account_id: str, amount: int, dedupe_id: Optional[str] = None
    ) -> Any:
        """
        Withdraws money from a pot into an account.
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(
            self.client.withdraw_from_pot,
            pot_id,
            account_id,
            amount,
            dedupe_id=dedupe_id,
        )
