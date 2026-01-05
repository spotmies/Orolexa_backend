"""add session_id to otp_codes

Revision ID: 0003_add_session_id
Revises: 0002_add_firmware_tables
Create Date: 2026-01-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_session_id'
down_revision = '0002_add_firmware_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add session_id column to otp_codes table if it doesn't exist
    # This is for backward compatibility with the new OTP service implementation
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'otp_codes' 
                AND column_name = 'session_id'
            ) THEN
                ALTER TABLE otp_codes ADD COLUMN session_id VARCHAR(200);
            END IF;
        END $$;
    """)
    
    # Ensure otp column is nullable (in case it was created as NOT NULL)
    op.alter_column('otp_codes', 'otp',
                    existing_type=sa.String(length=6),
                    nullable=True,
                    existing_nullable=True)


def downgrade() -> None:
    # Remove session_id column (optional - only if you want to rollback)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'otp_codes' 
                AND column_name = 'session_id'
            ) THEN
                ALTER TABLE otp_codes DROP COLUMN session_id;
            END IF;
        END $$;
    """)

