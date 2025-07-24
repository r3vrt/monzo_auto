"""
MonzoClient utility for handling OAuth, token management, and Monzo API calls using monzo_apy.
"""

from typing import Any, Dict, List, Optional

from monzo.client import MonzoClient as MonzoApyClient

from app.db import get_db_session
from app.models import User


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
        self.client = MonzoApyClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            access_token=self.tokens.get("access_token"),
            refresh_token=self.tokens.get("refresh_token"),
            timeout=self.timeout,
        )

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
        """
        if not self.redirect_uri:
            raise ValueError("MonzoClient requires redirect_uri for token refresh")
        tokens = self.client.refresh_access_token()
        self.tokens = tokens
        return tokens

    def _with_token_refresh(self, func, *args, **kwargs):
        """
        Helper to wrap Monzo API calls and refresh token on invalid/expired token error.
        Retries the call once after refreshing.
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check for token error (Monzo API returns 401 or specific error message)
            response = getattr(e, "response", None)
            if response is not None and getattr(response, "status_code", None) == 401:
                # Try to refresh token
                tokens = self.refresh_access_token()
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
                # Retry the original call
                return func(*args, **kwargs)
            # If not a token error, re-raise
            raise

    def get_accounts(self) -> List[Any]:
        """
        Returns a list of the user's Monzo accounts (Account objects).
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(self.client.get_accounts)

    def get_pots(self, account_id: str) -> List[Any]:
        """
        Returns a list of pots for the given account (Pot objects).
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(self.client.get_pots, account_id)

    def get_transactions(
        self,
        account_id: str,
        since: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 100,
    ) -> List[Any]:
        """
        Returns a list of transactions for the given account (Transaction objects).
        Automatically refreshes token if needed.
        """
        return self._with_token_refresh(
            self.client.get_transactions,
            account_id,
            since=since,
            before=before,
            limit=limit,
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
