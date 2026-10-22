"""Milestone 3: document lifecycle, policy facts, stale proposals, workspace-scoped simulated fixtures

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")


def upgrade() -> None:
    # documents: who created / soft-deleted it
    op.add_column('documents', sa.Column('created_by', sa.String(length=120), nullable=True))
    op.add_column('documents', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('deleted_by', sa.String(length=120), nullable=True))

    # document_versions: import pipeline status is separate from lifecycle status
    op.add_column('document_versions', sa.Column('import_status', sa.String(length=16),
                                                 server_default='ready', nullable=False))
    op.add_column('document_versions', sa.Column('filename', sa.String(length=200), nullable=True))
    op.add_column('document_versions', sa.Column('size_bytes', sa.Integer(), nullable=True))
    op.add_column('document_versions', sa.Column('policy_facts', JSONB, server_default=EMPTY, nullable=False))
    op.add_column('document_versions', sa.Column('created_by', sa.String(length=120), nullable=True))
    op.add_column('document_versions', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('document_versions', sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE document_versions SET import_status = 'failed' WHERE status = 'failed'")

    # chunks: policy facts declared inside the section
    op.add_column('chunks', sa.Column('policy_facts', JSONB, server_default=EMPTY, nullable=False))

    # proposals: why/when they went stale
    op.add_column('proposals', sa.Column('stale_reason', sa.Text(), nullable=True))
    op.add_column('proposals', sa.Column('stale_at', sa.DateTime(timezone=True), nullable=True))

    op.create_unique_constraint('uq_escalation_rules_ws_key', 'escalation_rules', ['workspace_id', 'key'])

    op.create_table('sim_fixtures',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('match_text', sa.Text(), nullable=False),
    sa.Column('classification', JSONB, nullable=False),
    sa.Column('synthesis', JSONB, nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'key'),
    )
    op.create_index(op.f('ix_sim_fixtures_workspace_id'), 'sim_fixtures', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_table('sim_fixtures')
    op.drop_constraint('uq_escalation_rules_ws_key', 'escalation_rules')
    for col in ('stale_at', 'stale_reason'):
        op.drop_column('proposals', col)
    op.drop_column('chunks', 'policy_facts')
    for col in ('retired_at', 'processed_at', 'created_by', 'policy_facts', 'size_bytes', 'filename', 'import_status'):
        op.drop_column('document_versions', col)
    for col in ('deleted_by', 'deleted_at', 'created_by'):
        op.drop_column('documents', col)
