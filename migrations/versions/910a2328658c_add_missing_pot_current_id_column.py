"""add_missing_pot_current_id_column

Revision ID: 910a2328658c
Revises: exec_metadata_automation
Create Date: 2025-07-25 20:59:53.531579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '910a2328658c'
down_revision: Union[str, Sequence[str], None] = 'exec_metadata_automation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add pot_current_id column to transactions table if it doesn't exist
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='transactions' AND column_name='pot_current_id') THEN ALTER TABLE transactions ADD COLUMN pot_current_id VARCHAR; END IF; END $$;")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove pot_current_id column from transactions table
    op.drop_column('transactions', 'pot_current_id')
