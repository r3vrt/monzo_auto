"""add_missing_rule_id_column

Revision ID: 34d70b1c45b8
Revises: 910a2328658c
Create Date: 2025-07-25 21:01:31.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34d70b1c45b8'
down_revision: Union[str, Sequence[str], None] = '910a2328658c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add rule_id column to automation_rules table if it doesn't exist
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='automation_rules' AND column_name='rule_id') THEN ALTER TABLE automation_rules ADD COLUMN rule_id VARCHAR; END IF; END $$;")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove rule_id column from automation_rules table
    op.drop_column('automation_rules', 'rule_id')
