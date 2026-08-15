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
