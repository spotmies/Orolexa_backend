"""baseline

Revision ID: 0001_baseline
Revises: 
Create Date: 2025-09-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Baseline: no-op, assumes existing tables created by application
    pass


def downgrade() -> None:
    pass
