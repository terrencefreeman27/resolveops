"""ai_runs table and proposals.usage (Milestone 2: live provider usage + limits)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('proposals', sa.Column('usage', postgresql.JSONB(astext_type=sa.Text()),
                                         server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_table('ai_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('actor', sa.String(length=120), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_read_input_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_creation_input_tokens', sa.Integer(), nullable=False),
    sa.Column('api_calls', sa.Integer(), nullable=False),
    sa.Column('tool_steps', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_runs_workspace_id'), 'ai_runs', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_ai_runs_demo_session_id'), 'ai_runs', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_ai_runs_request_id'), 'ai_runs', ['request_id'], unique=False)
    op.create_index(op.f('ix_ai_runs_created_at'), 'ai_runs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('ai_runs')
    op.drop_column('proposals', 'usage')
