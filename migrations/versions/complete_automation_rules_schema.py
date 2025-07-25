"""Complete automation_rules table schema

Revision ID: complete_automation_rules_schema
Revises: add_missing_automation_rules_columns
Create Date: 2025-07-25 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'complete_automation_rules_schema'
down_revision = 'add_automation_rules_cols'
branch_labels = None
depends_on = None


def upgrade():
    """Create complete automation_rules table with all required columns."""
    # Drop existing automation_rules table if it exists
    op.execute("DROP TABLE IF EXISTS automation_rules CASCADE")
    
    # Create automation_rules table with complete schema
    op.create_table('automation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('rule_type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=True),
        sa.Column('last_executed', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add unique constraint on rule_id
    op.create_unique_constraint('automation_rules_rule_id_key', 'automation_rules', ['rule_id'])
    
    # Add indexes
    op.create_index('ix_automation_rules_user_id', 'automation_rules', ['user_id'])
    op.create_index('ix_automation_rules_rule_id', 'automation_rules', ['rule_id'])


def downgrade():
    """Drop automation_rules table."""
    op.drop_table('automation_rules') 