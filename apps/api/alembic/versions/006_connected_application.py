"""Add durable connected identities, outcomes and ingestion attempts.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("owner_id", sa.String(100), nullable=True))
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    for table in ("queries", "conversations"):
        op.add_column(table, sa.Column("owner_id", sa.String(100), nullable=True))
        op.add_column(table, sa.Column("workspace_id", sa.String(100), nullable=True))
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    op.add_column("queries", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.create_index("ix_queries_conversation_id", "queries", ["conversation_id"])
    op.add_column("queries", sa.Column("outcome", sa.String(32), nullable=True))
    op.add_column("queries", sa.Column("refusal_reason", sa.Text(), nullable=True))
    op.add_column("queries", sa.Column("provenance", sa.JSON(), nullable=True))
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("workspace_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("active_slot", sa.String(36), unique=True, nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index(
        "ix_ingestion_jobs_workspace_id", "ingestion_jobs", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    for name in ("conversation_id", "outcome", "refusal_reason", "provenance"):
        op.drop_column("queries", name)
    for table in ("queries", "conversations"):
        op.drop_column(table, "owner_id")
        op.drop_column(table, "workspace_id")
    op.drop_column("documents", "owner_id")
