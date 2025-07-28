"""Remove deprecated sync_meta table

Revision ID: 3585abcf6cc3
Revises: c979368b4acc
Create Date: 2025-07-23 17:08:29.400640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3585abcf6cc3'
down_revision: Union[str, Sequence[str], None] = 'c979368b4acc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the deprecated sync_meta table if it exists
    op.execute('DROP TABLE IF EXISTS sync_meta')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate the sync_meta table (for rollback purposes)
    op.create_table('sync_meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
