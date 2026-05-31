"""Add workflow tables for document processing.

Revision ID: 004
Revises: 003
Create Date: 2026-05-31

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow_definitions table
    op.create_table(
        'workflow_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps_config', postgresql.JSON, default=list, nullable=False),
        sa.Column('owner_id', sa.String(100), nullable=False, index=True),
        sa.Column('organization_id', sa.String(100), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_system', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create workflow_instances table
    op.create_table(
        'workflow_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_definition_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflow_definitions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('current_step_index', sa.Integer(), default=0),
        sa.Column('triggered_by', sa.String(100), nullable=False),
        sa.Column('trigger_type', sa.String(50), default='manual'),
        sa.Column('metadata', postgresql.JSON, default=dict),
        sa.Column('context', postgresql.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create workflow_steps table
    op.create_table(
        'workflow_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflow_instances.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('approver_ids', postgresql.JSON, default=list),
        sa.Column('approver_role', sa.String(100), nullable=True),
        sa.Column('is_parallel', sa.Boolean(), default=False),
        sa.Column('min_approvals', sa.Integer(), default=1),
        sa.Column('approval_route', sa.String(100), nullable=True),
        sa.Column('rejection_route', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), default='waiting'),
        sa.Column('decisions', postgresql.JSON, default=dict),
        sa.Column('sla_hours', sa.Integer(), default=24),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notifications_sent', postgresql.JSON, default=list),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('workflow_steps')
    op.drop_table('workflow_instances')
    op.drop_table('workflow_definitions')
