"""create_initial_tables

Revision ID: 93e2b5db4393
Revises: 
Create Date: 2025-07-25 20:02:48.991525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93e2b5db4393'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('monzo_user_id', sa.String(), nullable=False),
        sa.Column('monzo_access_token', sa.String(), nullable=False),
        sa.Column('monzo_refresh_token', sa.String(), nullable=True),
        sa.Column('monzo_token_type', sa.String(), nullable=True),
        sa.Column('monzo_token_expires_in', sa.Integer(), nullable=True),
        sa.Column('monzo_client_id', sa.String(), nullable=True),
        sa.Column('monzo_token_obtained_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('monzo_client_secret', sa.String(), nullable=True),
        sa.Column('monzo_redirect_uri', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_monzo_user_id'), 'users', ['monzo_user_id'], unique=True)

    # Create accounts table
    op.create_table('accounts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create pots table
    op.create_table('pots',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('style', sa.String(), nullable=True),
        sa.Column('balance', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted', sa.Integer(), nullable=False),
        sa.Column('goal', sa.Integer(), nullable=True, default=0),
        sa.Column('pot_current_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create transactions table
    op.create_table('transactions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('merchant', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('is_load', sa.Integer(), nullable=False),
        sa.Column('settled', sa.DateTime(timezone=True), nullable=True),
        sa.Column('txn_metadata', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create bills_pot_transactions table
    op.create_table('bills_pot_transactions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('bills_pot_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('merchant', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('is_load', sa.Integer(), nullable=False),
        sa.Column('settled', sa.DateTime(timezone=True), nullable=True),
        sa.Column('txn_metadata', sa.String(), nullable=True),
        sa.Column('pot_account_id', sa.String(), nullable=False),
        sa.Column('transaction_type', sa.String(), nullable=True),
        sa.Column('is_pot_withdrawal', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bills_pot_transactions_bills_pot_id'), 'bills_pot_transactions', ['bills_pot_id'], unique=False)
    op.create_index(op.f('ix_bills_pot_transactions_user_id'), 'bills_pot_transactions', ['user_id'], unique=False)

    # Create automation_rules table
    op.create_table('automation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('rule_type', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order
    op.drop_table('automation_rules')
    op.drop_index(op.f('ix_bills_pot_transactions_user_id'), table_name='bills_pot_transactions')
    op.drop_index(op.f('ix_bills_pot_transactions_bills_pot_id'), table_name='bills_pot_transactions')
    op.drop_table('bills_pot_transactions')
    op.drop_table('transactions')
    op.drop_table('pots')
    op.drop_table('accounts')
    op.drop_index(op.f('ix_users_monzo_user_id'), table_name='users')
    op.drop_table('users')
