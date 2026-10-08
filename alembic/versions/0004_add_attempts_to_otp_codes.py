"""add attempts to otp_codes

Revision ID: 0004_add_otp_attempts
Revises: 0003_add_session_id
Create Date: 2026-10-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_add_otp_attempts'
down_revision = '0003_add_session_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Count failed verification attempts so an OTP can be invalidated after MAX_OTP_ATTEMPTS
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # Fresh database: the app's create_all builds otp_codes with this column
    if not insp.has_table("otp_codes"):
        return
    columns = [c["name"] for c in insp.get_columns("otp_codes")]
    if "attempts" not in columns:
        with op.batch_alter_table("otp_codes") as batch_op:
            batch_op.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # Fresh database: the app's create_all builds otp_codes with this column
    if not insp.has_table("otp_codes"):
        return
    columns = [c["name"] for c in insp.get_columns("otp_codes")]
    if "attempts" in columns:
        with op.batch_alter_table("otp_codes") as batch_op:
            batch_op.drop_column("attempts")
