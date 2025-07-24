"""Add user_pot_categories table

Revision ID: 7d15f4015bfd
Revises: 
Create Date: 2025-07-22 20:09:53.186800

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d15f4015bfd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create user_pot_categories table
    op.create_table('user_pot_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('pot_id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better performance
    op.create_index(op.f('ix_user_pot_categories_user_id'), 'user_pot_categories', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_pot_categories_pot_id'), 'user_pot_categories', ['pot_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f('ix_user_pot_categories_pot_id'), table_name='user_pot_categories')
    op.drop_index(op.f('ix_user_pot_categories_user_id'), table_name='user_pot_categories')
    
    # Drop table
    op.drop_table('user_pot_categories')
