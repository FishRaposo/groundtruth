"""Complete additive access/audit schema without granting legacy keys admin."""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _create(name, *columns):
    if name not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(name, *columns)


def _index(table, column):
    name = f"ix_{table}_{column}"
    existing = sa.inspect(op.get_bind()).get_indexes(table)
    if not any(index["name"] == name for index in existing):
        op.create_index(name, table, [column])


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("api_keys")
    if not any(column["name"] == "is_admin" for column in columns):
        op.add_column(
            "api_keys",
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    _create(
        "collections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=True),
        sa.Column("is_public", sa.String(20), nullable=False, server_default="private"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
    )
    _create(
        "collection_documents",
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE")
        ),
    )
    _create(
        "collection_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("group_id", sa.String(100), nullable=True),
        sa.Column("permission", sa.String(20), nullable=False, server_default="read"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    _create(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("api_key_id", sa.String(100), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    for table, fields in (
        ("collections", ("owner_id", "organization_id")),
        ("collection_shares", ("collection_id", "user_id", "group_id")),
        ("audit_logs", ("user_id", "api_key_id", "created_at")),
    ):
        for column in fields:
            _index(table, column)


def downgrade() -> None:
    raise RuntimeError(
        "Access and audit data are retained; restore a reviewed backup to downgrade."
    )
