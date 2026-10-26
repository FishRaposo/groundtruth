"""Lease-fenced ingestion claims and conditional workflow transitions."""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs", sa.Column("claim_token", sa.String(36), nullable=True)
    )
    op.add_column(
        "ingestion_jobs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "workflow_instances",
        sa.Column(
            "transition_version", sa.Integer(), server_default="0", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("workflow_instances", "transition_version")
    op.drop_column("ingestion_jobs", "claim_token")
    op.drop_column("ingestion_jobs", "lease_expires_at")
