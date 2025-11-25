"""add firmware tables

Revision ID: 0002_add_firmware_tables
Revises: 0001_baseline
Create Date: 2025-01-20 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '0002_add_firmware_tables'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create firmware_metadata table
    op.create_table(
        'firmware_metadata',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('release_notes', sa.String(), nullable=True),
        sa.Column('rollout_percent', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('min_version', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('uploaded_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_firmware_metadata_version'), 'firmware_metadata', ['version'], unique=True)
    
    # Create firmware_reports table
    op.create_table(
        'firmware_reports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(length=100), nullable=False),
        sa.Column('firmware_version', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=True),
        sa.Column('reported_at', sa.DateTime(), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_firmware_reports_device_id'), 'firmware_reports', ['device_id'], unique=False)
    op.create_index(op.f('ix_firmware_reports_reported_at'), 'firmware_reports', ['reported_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_firmware_reports_reported_at'), table_name='firmware_reports')
    op.drop_index(op.f('ix_firmware_reports_device_id'), table_name='firmware_reports')
    op.drop_table('firmware_reports')
    op.drop_index(op.f('ix_firmware_metadata_version'), table_name='firmware_metadata')
    op.drop_table('firmware_metadata')

