"""Additive, introspected bootstrap for portable and existing application databases.

No destructive rewrites or guessed embedding backfills. The deployment owns the
database URL; uploaded content never chooses a database or a migration command.
"""

from sqlalchemy import inspect, text

from app.db.session import Base, async_engine

BOOTSTRAP_REVISION = "009"

ADDITIONS = {
    "api_keys": {"is_admin": "BOOLEAN NOT NULL DEFAULT FALSE"},
    "ingestion_jobs": {"claim_token": "VARCHAR(36)", "lease_expires_at": "TIMESTAMP"},
    "workflow_instances": {"transition_version": "INTEGER NOT NULL DEFAULT 0"},
    "documents": {"owner_id": "VARCHAR(100)"},
    "queries": {
        "owner_id": "VARCHAR(100)",
        "workspace_id": "VARCHAR(100)",
        "conversation_id": "UUID",
        "outcome": "VARCHAR(32)",
        "refusal_reason": "TEXT",
        "provenance": "JSON",
    },
    "conversations": {"owner_id": "VARCHAR(100)", "workspace_id": "VARCHAR(100)"},
    "chunks": {"embedding_vector": "JSON"},
}

ADDITIVE_INDEXES = {
    "documents": ("owner_id",),
    "queries": ("owner_id", "workspace_id", "conversation_id"),
    "conversations": ("owner_id", "workspace_id"),
}


async def create_additive_indexes(conn) -> None:
    """Repair only the indexes explicitly introduced by migration 006."""
    for table, columns in ADDITIVE_INDEXES.items():
        for column in columns:
            await conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" '
                    f'ON "{table}" ("{column}")'
                )
            )


async def migrate() -> None:
    import app.models  # noqa: F401
    import app.models.collection  # noqa: F401
    import app.models.webhook  # noqa: F401

    async with async_engine.begin() as conn:
        postgres = conn.dialect.name == "postgresql"
        if postgres:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        if "alembic_version" in tables:
            revisions = list(
                (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars()
            )
            if any(
                revision not in {"005", "006", "007", "008", BOOTSTRAP_REVISION}
                for revision in revisions
            ):
                raise RuntimeError(
                    "Unsupported schema revision; upgrade historical "
                    "Alembic migrations first."
                )
        for table, additions in ADDITIONS.items():
            if table not in tables:
                continue
            columns = await conn.run_sync(
                lambda sync, name=table: {
                    column["name"] for column in inspect(sync).get_columns(name)
                }
            )
            for column, sql_type in additions.items():
                if column not in columns:
                    kind = (
                        "vector(384)"
                        if column == "embedding_vector" and postgres
                        else sql_type
                    )
                    await conn.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {kind}')
                    )
        await conn.run_sync(Base.metadata.create_all)
        # create_all skips an existing table's new indexes. Match the explicit
        # 006 indexes before stamping the current equivalent additive schema.
        await create_additive_indexes(conn)
        await conn.execute(
            text(
                (
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num "
                    "VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
        )
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(
            text("INSERT INTO alembic_version(version_num) VALUES (:revision)"),
            {"revision": BOOTSTRAP_REVISION},
        )
        if postgres:
            await conn.execute(
                text(
                    (
                        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_vector_hnsw"
                        " ON chunks USING hnsw (embedding_vector vector_cosine_ops)"
                        " WITH (m=16, ef_construction=64)"
                    )
                )
            )
            await conn.execute(
                text(
                    (
                        "CREATE INDEX IF NOT EXISTS ix_chunks_content_fts ON chunks"
                        " USING gin (to_tsvector('english', content))"
                    )
                )
            )


def main() -> None:
    import asyncio

    asyncio.run(migrate())
    print(
        (
            "Additive GroundTruth schema migration complete; historical"
            " evidence remains unknown."
        )
    )


if __name__ == "__main__":
    main()
