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
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # Fresh database: the app's create_all builds otp_codes with this column
    if not insp.has_table("otp_codes"):
        return
    columns = [c["name"] for c in insp.get_columns("otp_codes")]
    if "session_id" not in columns:
        with op.batch_alter_table("otp_codes") as batch_op:
            batch_op.add_column(sa.Column("session_id", sa.String(length=200), nullable=True))
    
    # Ensure otp column is nullable (in case it was created as NOT NULL)
    with op.batch_alter_table("otp_codes") as batch_op:
        batch_op.alter_column('otp',
                        existing_type=sa.String(length=6),
                        nullable=True,
                        existing_nullable=True)


def downgrade() -> None:
    # Remove session_id column (optional - only if you want to rollback)
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # Fresh database: the app's create_all builds otp_codes with this column
    if not insp.has_table("otp_codes"):
        return
    columns = [c["name"] for c in insp.get_columns("otp_codes")]
    if "session_id" in columns:
        with op.batch_alter_table("otp_codes") as batch_op:
            batch_op.drop_column("session_id")

