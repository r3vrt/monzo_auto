"""add_pot_current_id_to_transactions

Revision ID: c31bebf1b6e8
Revises: 7d15f4015bfd
Create Date: 2025-07-22 22:42:46.328739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c31bebf1b6e8'
down_revision: Union[str, Sequence[str], None] = '7d15f4015bfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add pot_current_id column to transactions table
    op.add_column('transactions', sa.Column('pot_current_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove pot_current_id column from transactions table
    op.drop_column('transactions', 'pot_current_id')
