"""Real vector storage and functional FTS index; no unknown vector backfill."""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE chunks ADD COLUMN embedding_vector vector(384)")
        op.execute(
            "CREATE INDEX ix_chunks_embedding_vector_hnsw ON chunks USING hnsw (embedding_vector vector_cosine_ops) WITH (m=16, ef_construction=64)"
        )
        op.execute(
            "CREATE INDEX ix_chunks_content_fts ON chunks USING gin (to_tsvector('english', content))"
        )
    else:
        op.add_column("chunks", sa.Column("embedding_vector", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding_vector")
