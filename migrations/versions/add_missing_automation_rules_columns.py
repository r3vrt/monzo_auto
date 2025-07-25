"""Add missing columns to automation_rules table

Revision ID: add_missing_automation_rules_columns
Revises: fix_execution_metadata_column
Create Date: 2025-07-25 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_automation_rules_cols'
down_revision = 'fix_execution_metadata_column'
branch_labels = None
depends_on = None


def upgrade():
    """Add missing columns to automation_rules table."""
    # Add user_id column if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='user_id'
            ) THEN
                ALTER TABLE automation_rules ADD COLUMN user_id VARCHAR;
            END IF;
        END $$;
    """)
    
    # Add enabled column if it doesn't exist (replace is_active)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='enabled'
            ) THEN
                ALTER TABLE automation_rules ADD COLUMN enabled BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    """)
    
    # Add updated_at column if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='updated_at'
            ) THEN
                ALTER TABLE automation_rules ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
            END IF;
        END $$;
    """)
    
    # Add last_executed column if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='last_executed'
            ) THEN
                ALTER TABLE automation_rules ADD COLUMN last_executed TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)
    
    # Add unique constraint on rule_id if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name='automation_rules' AND constraint_name='automation_rules_rule_id_key'
            ) THEN
                ALTER TABLE automation_rules ADD CONSTRAINT automation_rules_rule_id_key UNIQUE (rule_id);
            END IF;
        END $$;
    """)
    
    # Add index on user_id if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename='automation_rules' AND indexname='ix_automation_rules_user_id'
            ) THEN
                CREATE INDEX ix_automation_rules_user_id ON automation_rules (user_id);
            END IF;
        END $$;
    """)
    
    # Add index on rule_id if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename='automation_rules' AND indexname='ix_automation_rules_rule_id'
            ) THEN
                CREATE INDEX ix_automation_rules_rule_id ON automation_rules (rule_id);
            END IF;
        END $$;
    """)
    
    # Remove old is_active column if it exists and enabled column was added
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='is_active'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='automation_rules' AND column_name='enabled'
            ) THEN
                ALTER TABLE automation_rules DROP COLUMN is_active;
            END IF;
        END $$;
    """)


def downgrade():
    """Remove added columns from automation_rules table."""
    # Remove indexes
    op.execute("DROP INDEX IF EXISTS ix_automation_rules_user_id")
    op.execute("DROP INDEX IF EXISTS ix_automation_rules_rule_id")
    
    # Remove unique constraint
    op.execute("ALTER TABLE automation_rules DROP CONSTRAINT IF EXISTS automation_rules_rule_id_key")
    
    # Remove columns
    op.drop_column('automation_rules', 'last_executed')
    op.drop_column('automation_rules', 'updated_at')
    op.drop_column('automation_rules', 'enabled')
    op.drop_column('automation_rules', 'user_id') 