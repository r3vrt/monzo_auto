"""add goal field to pots

Revision ID: 3736dace38ed
Revises: c979368b4acc
Create Date: 2025-01-23 20:07:15.123456

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3736dace38ed'
down_revision = '3585abcf6cc3'
branch_labels = None
depends_on = None


def upgrade():
    # Add goal field to pots table
    op.add_column('pots', sa.Column('goal', sa.Integer(), nullable=True, default=0))


def downgrade():
    # Remove goal field from pots table
    op.drop_column('pots', 'goal')
