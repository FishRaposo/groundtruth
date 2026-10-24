"""Regression checks for fresh-install migration compatibility."""

from pathlib import Path


def test_content_hash_is_not_added_twice_in_migration_chain() -> None:
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    initial = (versions / "001_initial_schema.py").read_text(encoding="utf-8")
    conversations = (versions / "003_add_conversations_and_webhooks.py").read_text(
        encoding="utf-8"
    )
    assert 'sa.Column("content_hash"' in initial
    assert "op.add_column('documents', sa.Column('content_hash'" not in conversations
    assert "op.drop_column('documents', 'content_hash')" not in conversations


def test_model_datetimes_are_naive_utc() -> None:
    """PostgreSQL columns must stay naive so utc_now() binds safely.

    asyncpg rejects timezone-aware values bound to ``timestamp`` columns and
    naive values bound to ``timestamp with time zone`` columns. The codebase
    convention is naive UTC via ``app.utils.time.utc_now``; a single tz-aware
    column silently works on SQLite but fails on PostgreSQL.
    """
    import app.models  # noqa: F401
    import app.models.collection  # noqa: F401
    import app.models.webhook  # noqa: F401
    from app.db.session import Base
    from sqlalchemy import DateTime

    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime) and column.type.timezone
    ]
    assert offenders == []
