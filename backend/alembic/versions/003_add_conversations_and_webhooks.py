"""Add conversations and webhooks tables.

Revision ID: 003
Revises: 002
Create Date: 2026-05-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('document_ids', postgresql.JSON, default=list),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('max_context_length', sa.Integer(), default=4000),
        sa.Column('context_strategy', sa.String(50), default='recent'),
        sa.Column('message_count', sa.Integer(), default=0),
        sa.Column('total_tokens', sa.Integer(), default=0),
    )
    
    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('retrieved_chunks', postgresql.JSON, default=list),
        sa.Column('sources', postgresql.JSON, default=list),
        sa.Column('generation_time_ms', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSON, default=dict),
    )
    
    # Create conversation_contexts table
    op.create_table(
        'conversation_contexts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chunks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relevance_score', sa.Integer(), default=0),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('access_count', sa.Integer(), default=1),
        sa.Column('added_reason', sa.String(50), default='retrieval'),
    )
    
    # Create webhook_subscriptions table
    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('secret', sa.String(255), nullable=False),
        sa.Column('events', postgresql.JSON, default=list),
        sa.Column('document_filter', postgresql.JSON, nullable=True),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('delivery_count', sa.Integer(), default=0),
        sa.Column('failure_count', sa.Integer(), default=0),
        sa.Column('last_delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
    )
    
    # Create webhook_deliveries table
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('payload', postgresql.JSON, nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('attempt_number', sa.Integer(), default=1),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('success', sa.Integer(), default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    
    # Add columns to documents table
    op.add_column('documents', sa.Column('content_hash', sa.String(64), nullable=True))
    op.add_column('documents', sa.Column('version_number', sa.Integer(), default=1))
    op.add_column('documents', sa.Column('previous_version_id', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    # Drop tables
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_subscriptions')
    op.drop_table('conversation_contexts')
    op.drop_table('messages')
    op.drop_table('conversations')
    
    # Drop columns from documents
    op.drop_column('documents', 'content_hash')
    op.drop_column('documents', 'version_number')
    op.drop_column('documents', 'previous_version_id')
