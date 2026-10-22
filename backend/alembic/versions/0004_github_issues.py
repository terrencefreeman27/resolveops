"""Milestone 4: external issue references (GitHub Issues adapter)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('external_number', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('external_id', sa.String(length=120), nullable=True))
    op.add_column('executions', sa.Column('external_number', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('external_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('executions', 'external_url')
    op.drop_column('executions', 'external_number')
    op.drop_column('executions', 'external_id')
    op.drop_column('tickets', 'external_number')
