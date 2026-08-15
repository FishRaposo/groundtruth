"""Add document snapshots, workspace scoping, and notification outbox.

Revision ID: 005
Revises: 004
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "workspace_id", sa.String(100), nullable=False, server_default="default"
        ),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    for table in ("workflow_definitions", "workflow_instances"):
        op.add_column(
            table,
            sa.Column(
                "workspace_id", sa.String(100), nullable=False, server_default="default"
            ),
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id", sa.String(100), nullable=False, server_default="default"
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("chunks", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("change_summary", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_number"
        ),
    )
    op.create_index(
        "ix_document_versions_document_id", "document_versions", ["document_id"]
    )
    op.create_index(
        "ix_document_versions_workspace_id", "document_versions", ["workspace_id"]
    )

    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("recipient", sa.String(512), nullable=False),
        sa.Column("payload", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("deduplication_key", sa.String(255), nullable=False, unique=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="delivered"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_outbox_workspace_id", "notification_outbox", ["workspace_id"]
    )
    op.create_index(
        "ix_notification_outbox_event_type", "notification_outbox", ["event_type"]
    )


def downgrade() -> None:
    op.drop_table("notification_outbox")
    op.drop_table("document_versions")
    for table in ("workflow_instances", "workflow_definitions"):
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_column("documents", "workspace_id")
