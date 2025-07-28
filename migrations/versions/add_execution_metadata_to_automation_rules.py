"""Add execution_metadata field to automation_rules table

Revision ID: add_execution_metadata_to_automation_rules
Revises: 3585abcf6cc3
Create Date: 2025-07-24 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'exec_metadata_automation'
down_revision = '3585abcf6cc3'
branch_labels = None
depends_on = None


def upgrade():
    # Add execution_metadata column to automation_rules table
    op.add_column('automation_rules', sa.Column('execution_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove execution_metadata column from automation_rules table
    op.drop_column('automation_rules', 'execution_metadata') 