"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-21 19:49:15.106768
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1001")
    op.create_table('demo_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('reviewers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('workspaces',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('auth_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_table('customers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('account_ref', sa.String(length=32), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('contact_name', sa.String(length=200), nullable=False),
    sa.Column('contact_email', sa.String(length=254), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'contact_email')
    )
    op.create_index(op.f('ix_customers_workspace_id'), 'customers', ['workspace_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('current_version_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'slug')
    )
    op.create_index(op.f('ix_documents_workspace_id'), 'documents', ['workspace_id'], unique=False)
    op.create_table('escalation_rules',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('condition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outcome', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_escalation_rules_workspace_id'), 'escalation_rules', ['workspace_id'], unique=False)
    op.create_table('memberships',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reviewer_id', 'workspace_id')
    )
    op.create_index(op.f('ix_memberships_workspace_id'), 'memberships', ['workspace_id'], unique=False)
    op.create_table('account_users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_account_users_customer_id'), 'account_users', ['customer_id'], unique=False)
    op.create_index(op.f('ix_account_users_workspace_id'), 'account_users', ['workspace_id'], unique=False)
    op.create_table('customer_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_customer_sessions_demo_session_id'), 'customer_sessions', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_customer_sessions_workspace_id'), 'customer_sessions', ['workspace_id'], unique=False)
    op.create_table('document_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('source_format', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('import_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'version')
    )
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_versions_workspace_id'), 'document_versions', ['workspace_id'], unique=False)
    op.create_table('invoices',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('amount_cents', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoices_workspace_id'), 'invoices', ['workspace_id'], unique=False)
    op.create_table('subscriptions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('plan', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('billing_cycle', sa.String(length=16), nullable=False),
    sa.Column('seats_purchased', sa.Integer(), nullable=False),
    sa.Column('seats_used', sa.Integer(), nullable=False),
    sa.Column('price_per_seat_cents', sa.Integer(), nullable=False),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('previous_plan', sa.String(length=32), nullable=True),
    sa.Column('plan_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_customer_id'), 'subscriptions', ['customer_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_workspace_id'), 'subscriptions', ['workspace_id'], unique=False)
    op.create_table('support_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('submitted_via', sa.String(length=24), nullable=False),
    sa.Column('from_name', sa.String(length=200), nullable=False),
    sa.Column('from_email', sa.String(length=254), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('scenario_key', sa.String(length=64), nullable=True),
    sa.Column('is_template', sa.Boolean(), nullable=False),
    sa.Column('source_request_id', sa.UUID(), nullable=True),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=True),
    sa.Column('priority', sa.String(length=16), nullable=True),
    sa.Column('resolution', sa.String(length=32), nullable=True),
    sa.Column('state_reason', sa.Text(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_support_requests_customer_id'), 'support_requests', ['customer_id'], unique=False)
    op.create_index(op.f('ix_support_requests_demo_session_id'), 'support_requests', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_support_requests_state'), 'support_requests', ['state'], unique=False)
    op.create_index(op.f('ix_support_requests_workspace_id'), 'support_requests', ['workspace_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('actor', sa.String(length=120), nullable=False),
    sa.Column('event', sa.String(length=48), nullable=False),
    sa.Column('tool_name', sa.String(length=48), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_demo_session_id'), 'audit_log', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_audit_log_request_id'), 'audit_log', ['request_id'], unique=False)
    op.create_index(op.f('ix_audit_log_workspace_id'), 'audit_log', ['workspace_id'], unique=False)
    op.create_table('chunks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('document_version_id', sa.UUID(), nullable=False),
    sa.Column('section', sa.String(length=300), nullable=False),
    sa.Column('section_slug', sa.String(length=160), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chunks_document_version_id'), 'chunks', ['document_version_id'], unique=False)
    op.create_index('ix_chunks_embedding_hnsw', 'chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index(op.f('ix_chunks_workspace_id'), 'chunks', ['workspace_id'], unique=False)
    op.create_index('ix_chunks_ws_active', 'chunks', ['workspace_id', 'active'], unique=False)
    op.create_table('proposals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('current_version', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_proposals_request_id'), 'proposals', ['request_id'], unique=False)
    op.create_index(op.f('ix_proposals_workspace_id'), 'proposals', ['workspace_id'], unique=False)
    op.create_table('tickets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('number', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('group', sa.String(length=64), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('adapter', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=120), nullable=True),
    sa.Column('external_url', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('notes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_tickets_customer_id'), 'tickets', ['customer_id'], unique=False)
    op.create_index(op.f('ix_tickets_demo_session_id'), 'tickets', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_tickets_workspace_id'), 'tickets', ['workspace_id'], unique=False)
    op.create_table('proposal_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('proposal_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('action_hash', sa.String(length=64), nullable=False),
    sa.Column('author', sa.String(length=120), nullable=False),
    sa.Column('edit_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['proposal_id'], ['proposals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('proposal_id', 'version')
    )
    op.create_index(op.f('ix_proposal_versions_proposal_id'), 'proposal_versions', ['proposal_id'], unique=False)
    op.create_index(op.f('ix_proposal_versions_workspace_id'), 'proposal_versions', ['workspace_id'], unique=False)
    op.create_table('approvals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('proposal_id', sa.UUID(), nullable=False),
    sa.Column('proposal_version_id', sa.UUID(), nullable=False),
    sa.Column('action_hash', sa.String(length=64), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('actor', sa.String(length=120), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('invalidated_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['proposal_id'], ['proposals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proposal_version_id'], ['proposal_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approvals_request_id'), 'approvals', ['request_id'], unique=False)
    op.create_index(op.f('ix_approvals_workspace_id'), 'approvals', ['workspace_id'], unique=False)
    op.create_index('uq_approvals_one_active_per_proposal', 'approvals', ['proposal_id'], unique=True, postgresql_where=sa.text("status = 'active' AND decision = 'approved'"))
    op.create_table('proposal_evidence',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('proposal_version_id', sa.UUID(), nullable=False),
    sa.Column('document_version_id', sa.UUID(), nullable=False),
    sa.Column('chunk_id', sa.UUID(), nullable=False),
    sa.Column('cited', sa.Boolean(), nullable=False),
    sa.Column('score', sa.Double(), nullable=True),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proposal_version_id'], ['proposal_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_proposal_evidence_document_version_id'), 'proposal_evidence', ['document_version_id'], unique=False)
    op.create_index(op.f('ix_proposal_evidence_proposal_version_id'), 'proposal_evidence', ['proposal_version_id'], unique=False)
    op.create_index(op.f('ix_proposal_evidence_workspace_id'), 'proposal_evidence', ['workspace_id'], unique=False)
    op.create_table('executions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('demo_session_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('proposal_version_id', sa.UUID(), nullable=False),
    sa.Column('approval_id', sa.UUID(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('adapter', sa.String(length=32), nullable=False),
    sa.Column('action_type', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('ticket_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['demo_session_id'], ['demo_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proposal_version_id'], ['proposal_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['support_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_executions_demo_session_id'), 'executions', ['demo_session_id'], unique=False)
    op.create_index(op.f('ix_executions_request_id'), 'executions', ['request_id'], unique=False)
    op.create_index(op.f('ix_executions_workspace_id'), 'executions', ['workspace_id'], unique=False)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_executions_workspace_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_request_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_demo_session_id'), table_name='executions')
    op.drop_table('executions')
    op.drop_index(op.f('ix_proposal_evidence_workspace_id'), table_name='proposal_evidence')
    op.drop_index(op.f('ix_proposal_evidence_proposal_version_id'), table_name='proposal_evidence')
    op.drop_index(op.f('ix_proposal_evidence_document_version_id'), table_name='proposal_evidence')
    op.drop_table('proposal_evidence')
    op.drop_index('uq_approvals_one_active_per_proposal', table_name='approvals', postgresql_where=sa.text("status = 'active' AND decision = 'approved'"))
    op.drop_index(op.f('ix_approvals_workspace_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_request_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_proposal_versions_workspace_id'), table_name='proposal_versions')
    op.drop_index(op.f('ix_proposal_versions_proposal_id'), table_name='proposal_versions')
    op.drop_table('proposal_versions')
    op.drop_index(op.f('ix_tickets_workspace_id'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_demo_session_id'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_customer_id'), table_name='tickets')
    op.drop_table('tickets')
    op.drop_index(op.f('ix_proposals_workspace_id'), table_name='proposals')
    op.drop_index(op.f('ix_proposals_request_id'), table_name='proposals')
    op.drop_table('proposals')
    op.drop_index('ix_chunks_ws_active', table_name='chunks')
    op.drop_index(op.f('ix_chunks_workspace_id'), table_name='chunks')
    op.drop_index('ix_chunks_embedding_hnsw', table_name='chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_chunks_document_version_id'), table_name='chunks')
    op.drop_table('chunks')
    op.drop_index(op.f('ix_audit_log_workspace_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_request_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_demo_session_id'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_support_requests_workspace_id'), table_name='support_requests')
    op.drop_index(op.f('ix_support_requests_state'), table_name='support_requests')
    op.drop_index(op.f('ix_support_requests_demo_session_id'), table_name='support_requests')
    op.drop_index(op.f('ix_support_requests_customer_id'), table_name='support_requests')
    op.drop_table('support_requests')
    op.drop_index(op.f('ix_subscriptions_workspace_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_customer_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_invoices_workspace_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_customer_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_document_versions_workspace_id'), table_name='document_versions')
    op.drop_index(op.f('ix_document_versions_document_id'), table_name='document_versions')
    op.drop_table('document_versions')
    op.drop_index(op.f('ix_customer_sessions_workspace_id'), table_name='customer_sessions')
    op.drop_index(op.f('ix_customer_sessions_demo_session_id'), table_name='customer_sessions')
    op.drop_table('customer_sessions')
    op.drop_index(op.f('ix_account_users_workspace_id'), table_name='account_users')
    op.drop_index(op.f('ix_account_users_customer_id'), table_name='account_users')
    op.drop_table('account_users')
    op.drop_index(op.f('ix_memberships_workspace_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_escalation_rules_workspace_id'), table_name='escalation_rules')
    op.drop_table('escalation_rules')
    op.drop_index(op.f('ix_documents_workspace_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_customers_workspace_id'), table_name='customers')
    op.drop_table('customers')
    op.drop_table('auth_sessions')
    op.drop_table('workspaces')
    op.drop_table('reviewers')
    op.drop_table('demo_sessions')
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
