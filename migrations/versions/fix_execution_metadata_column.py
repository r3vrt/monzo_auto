"""Fix execution_metadata column in automation_rules table

Revision ID: fix_execution_metadata_column
Revises: 34d70b1c45b8
Create Date: 2025-07-25 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fix_execution_metadata_column'
down_revision = '34d70b1c45b8'
branch_labels = None
depends_on = None


def upgrade():
    # Add execution_metadata column to automation_rules table if it doesn't exist
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='automation_rules' AND column_name='execution_metadata'
            ) THEN 
                ALTER TABLE automation_rules ADD COLUMN execution_metadata JSON;
            END IF;
        END $$;
    """)


def downgrade():
    # Remove execution_metadata column from automation_rules table
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='automation_rules' AND column_name='execution_metadata'
            ) THEN 
                ALTER TABLE automation_rules DROP COLUMN execution_metadata;
            END IF;
        END $$;
    """) 