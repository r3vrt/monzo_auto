"""
SQLAlchemy models for the Monzo app. Integrates with Monzo API models for type hints.
"""

from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

# from monzo.models import Account  # For type hints and future relationships (no longer needed)
from app.db import Base


class User(Base):
    """
    User model for storing Monzo OAuth credentials and user info.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    monzo_user_id = Column(String, unique=True, nullable=False, index=True)
    monzo_access_token = Column(String, nullable=False)
    monzo_refresh_token = Column(String, nullable=True)
    monzo_token_type = Column(
        String, nullable=True, doc="OAuth2 token type (usually 'Bearer')"
    )
    monzo_token_expires_in = Column(
        Integer, nullable=True, doc="Lifetime of the access token in seconds"
    )
    monzo_client_id = Column(
        String, nullable=True, doc="Monzo client ID associated with the token"
    )
    monzo_token_obtained_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        doc="Timestamp when the token was obtained",
    )
    monzo_client_secret = Column(
        String, nullable=True, doc="Monzo client secret used for OAuth (sensitive)"
    )
    monzo_redirect_uri = Column(
        String, nullable=True, doc="Monzo redirect URI used for OAuth"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<User monzo_user_id={self.monzo_user_id}>"


class Account(Base):
    """
    Account model for storing Monzo account data.

    Attributes:
        id (str): Monzo account ID (primary key).
        user_id (str): Foreign key to User.monzo_user_id.
        description (str): Human-readable account name.
        type (str): Account type (e.g., 'uk_retail').
        created (datetime): When the account was created.
        closed (bool): Whether the account is closed.
        updated_at (datetime): Last update timestamp.
        is_active (bool): Whether the account is active for syncing/imported (True = syncing, False = not synced).
    """

    __tablename__ = "accounts"

    id = Column(String, primary_key=True, nullable=False, doc="Monzo account ID")
    user_id = Column(String, nullable=False, doc="Foreign key to User.monzo_user_id")
    description = Column(String, nullable=False)
    type = Column(String, nullable=False)
    created = Column(DateTime(timezone=True), nullable=False)
    closed = Column(Integer, nullable=False, doc="0 = open, 1 = closed")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True = syncing/imported, False = not synced",
    )
    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of the last successful sync for this account",
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} description={self.description} type={self.type} closed={self.closed}>"


class Pot(Base):
    """
    Pot model for storing Monzo pot data.

    Attributes:
        id (str): Monzo pot ID (primary key).
        account_id (str): Foreign key to Account.id.
        user_id (str): Foreign key to User.monzo_user_id.
        name (str): Pot name.
        style (str): Pot style (e.g., 'beach_ball').
        balance (int): Pot balance in minor units (e.g., pennies).
        currency (str): Currency code (e.g., 'GBP').
        created (datetime): When the pot was created.
        updated (datetime): When the pot was last updated.
        deleted (bool): Whether the pot is deleted.
        pot_current_id (str): ID used to pull transactions for this pot (from metadata).
    """

    __tablename__ = "pots"

    id = Column(String, primary_key=True, nullable=False, doc="Monzo pot ID")
    account_id = Column(String, nullable=False, doc="Foreign key to Account.id")
    user_id = Column(String, nullable=False, doc="Foreign key to User.monzo_user_id")
    name = Column(String, nullable=False)
    style = Column(String, nullable=True)
    balance = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    created = Column(DateTime(timezone=True), nullable=False)
    updated = Column(DateTime(timezone=True), nullable=False)
    deleted = Column(Integer, nullable=False, doc="0 = active, 1 = deleted")
    goal = Column(Integer, nullable=True, default=0, doc="Goal amount in minor units (e.g., pennies)")
    pot_current_id = Column(
        String,
        nullable=True,
        doc="ID used to pull transactions for this pot (from metadata)",
    )

    def __repr__(self) -> str:
        return f"<Pot id={self.id} name={self.name} balance={self.balance} deleted={self.deleted}>"


class UserPotCategory(Base):
    """
    User pot category assignments for structured pot management.

    This replaces fuzzy name matching with explicit user-configured categories.
    """

    __tablename__ = "user_pot_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String, nullable=False, index=True, doc="Foreign key to User.monzo_user_id"
    )
    pot_id = Column(String, nullable=False, index=True, doc="Foreign key to Pot.id")
    category = Column(
        String, nullable=False, doc="Pot category (e.g., 'bills', 'savings', 'holding')"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<UserPotCategory user_id={self.user_id} pot_id={self.pot_id} category={self.category}>"


class Transaction(Base):
    """
    Transaction model for storing Monzo transaction data.

    Attributes:
        id (str): Monzo transaction ID (primary key).
        account_id (str): Foreign key to Account.id.
        user_id (str): Foreign key to User.monzo_user_id.
        created (datetime): When the transaction was created.
        amount (int): Transaction amount in minor units (e.g., pennies).
        currency (str): Currency code (e.g., 'GBP').
        description (str): Transaction description.
        category (str): Transaction category.
        merchant (str): Merchant ID (optional).
        notes (str): Notes (optional).
        is_load (bool): True if top-up, False otherwise.
        settled (datetime): When the transaction settled (nullable).
        txn_metadata (str): JSON metadata (as string).
        pot_current_id (str): ID used to identify which pot the transaction belongs to (from metadata).
    """

    __tablename__ = "transactions"

    id = Column(String, primary_key=True, nullable=False, doc="Monzo transaction ID")
    account_id = Column(String, nullable=False, doc="Foreign key to Account.id")
    user_id = Column(String, nullable=False, doc="Foreign key to User.monzo_user_id")
    created = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=True)
    merchant = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    is_load = Column(Integer, nullable=False, doc="0 = not load, 1 = load")
    settled = Column(DateTime(timezone=True), nullable=True)
    txn_metadata = Column(String, nullable=True, doc="JSON metadata as string")
    pot_current_id = Column(
        String,
        nullable=True,
        doc="ID used to identify which pot the transaction belongs to (from metadata)",
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} amount={self.amount} description={self.description}>"


class BillsPotTransaction(Base):
    """
    Bills pot transaction model for storing bills-specific transaction data.

    This provides a dedicated table for bills pot transactions with additional
    bills-specific fields and better organization.

    Attributes:
        id (str): Monzo transaction ID (primary key).
        bills_pot_id (str): Foreign key to Pot.id (the bills pot).
        user_id (str): Foreign key to User.monzo_user_id.
        created (datetime): When the transaction was created.
        amount (int): Transaction amount in minor units (e.g., pennies).
        currency (str): Currency code (e.g., 'GBP').
        description (str): Transaction description.
        category (str): Transaction category.
        merchant (str): Merchant ID (optional).
        notes (str): Notes (optional).
        is_load (bool): True if top-up, False otherwise.
        settled (datetime): When the transaction settled (nullable).
        txn_metadata (str): JSON metadata (as string).
        pot_account_id (str): The pot account ID used to pull this transaction.
        transaction_type (str): Type of transaction ('subscription', 'pot_transfer', 'other').
        is_pot_withdrawal (bool): True if this is an actual pot withdrawal (has pot_withdrawal_id in metadata).
        created_at (datetime): When this record was created in our database.
    """

    __tablename__ = "bills_pot_transactions"

    id = Column(String, primary_key=True, nullable=False, doc="Monzo transaction ID")
    bills_pot_id = Column(
        String, nullable=False, index=True, doc="Foreign key to Pot.id (the bills pot)"
    )
    user_id = Column(
        String, nullable=False, index=True, doc="Foreign key to User.monzo_user_id"
    )
    created = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=True)
    merchant = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    is_load = Column(Integer, nullable=False, doc="0 = not load, 1 = load")
    settled = Column(DateTime(timezone=True), nullable=True)
    txn_metadata = Column(String, nullable=True, doc="JSON metadata as string")
    pot_account_id = Column(
        String, nullable=False, doc="The pot account ID used to pull this transaction"
    )
    transaction_type = Column(
        String,
        nullable=True,
        doc="Type of transaction ('subscription', 'pot_transfer', 'other')",
    )
    is_pot_withdrawal = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if this is an actual pot withdrawal",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        doc="When this record was created in our database",
    )

    def __repr__(self) -> str:
        return f"<BillsPotTransaction id={self.id} amount={self.amount} description={self.description} type={self.transaction_type}>"
