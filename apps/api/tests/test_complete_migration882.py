"""Real Alembic/bootstrap parity; no startup create_all can hide schema gaps."""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.config import get_settings
from app.db.session import Base
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

API = Path(__file__).parents[1]


def configuration(database, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "DATABASE_URL", "sqlite+aiosqlite:///" + database.as_posix()
    )
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    return config


def schema(database):
    with closing(sqlite3.connect(database)) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        return {
            name: {
                row[1]
                for row in connection.execute(
                    'PRAGMA table_info("' + name.replace('"', '""') + '")'
                )
            }
            for name in names
        }


def assert_model_columns(database):
    actual = schema(database)
    missing = {
        table.name: sorted(set(table.columns.keys()) - actual.get(table.name, set()))
        for table in Base.metadata.sorted_tables
        if set(table.columns.keys()) - actual.get(table.name, set())
    }
    assert missing == {}


def insert_legacy_key(database):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO api_keys(id,name,key_hash,key_prefix) "
            "VALUES('00000000000000000000000000000001','UNITONLY',"
            "'UNITONLY-non-secret-hash','unit')"
        )
        connection.commit()


def test_fresh_alembic_head_has_all_model_columns_before_startup(tmp_path, monkeypatch):
    database = tmp_path / "fresh.sqlite"
    config = configuration(database, monkeypatch)
    command.upgrade(config, "head")
    assert_model_columns(database)
    with closing(sqlite3.connect(database)) as connection:
        assert [
            row[0]
            for row in connection.execute("SELECT version_num FROM alembic_version")
        ] == ScriptDirectory.from_config(config).get_heads()


def test_existing008_key_survives_upgrade_without_admin_grant(tmp_path, monkeypatch):
    database = tmp_path / "existing.sqlite"
    config = configuration(database, monkeypatch)
    command.upgrade(config, "008")
    insert_legacy_key(database)
    command.upgrade(config, "head")
    assert_model_columns(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT name,is_admin FROM api_keys").fetchall() == [
            ("UNITONLY", 0)
        ]
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT count(*) FROM api_keys").fetchone() == (1,)


def test_bootstrapped008_grants_admin_and_audit_are_preserved(tmp_path, monkeypatch):
    from app.models.collection import AuditLog, Collection, CollectionShare

    database = tmp_path / "bootstrapped008.sqlite"
    config = configuration(database, monkeypatch)
    command.upgrade(config, "008")
    insert_legacy_key(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "ALTER TABLE api_keys ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"
        )
        connection.execute("UPDATE api_keys SET is_admin=1")
        connection.commit()
    engine = create_engine("sqlite:///" + database.as_posix())
    try:
        # Simulate a database that the previous portable startup had populated.
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            collection = Collection(name="UNITONLY", owner_id="unit-owner")
            session.add(collection)
            session.flush()
            session.add(
                CollectionShare(
                    collection_id=collection.id,
                    user_id="unit-member",
                    permission="write",
                    created_by="unit-owner",
                )
            )
            session.add(
                AuditLog(
                    user_id="unit-owner", action="share", resource_type="collection"
                )
            )
            session.commit()
    finally:
        engine.dispose()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert_model_columns(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT is_admin FROM api_keys").fetchall() == [(1,)]
        assert connection.execute("SELECT owner_id FROM collections").fetchall() == [
            ("unit-owner",)
        ]
        assert connection.execute(
            "SELECT user_id,permission FROM collection_shares"
        ).fetchall() == [("unit-member", "write")]
        assert connection.execute("SELECT action FROM audit_logs").fetchall() == [
            ("share",)
        ]


@pytest.mark.asyncio
async def test_portable_bootstrap_repairs008_and_keeps_revision(tmp_path, monkeypatch):
    from app.db import migrate

    database = tmp_path / "bootstrap.sqlite"
    config = configuration(database, monkeypatch)
    await asyncio.to_thread(command.upgrade, config, "008")
    insert_legacy_key(database)
    engine = create_async_engine(get_settings().DATABASE_URL)
    monkeypatch.setattr(migrate, "async_engine", engine)
    try:
        await migrate.migrate()
        await migrate.migrate()
    finally:
        await engine.dispose()
    assert_model_columns(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT name,is_admin FROM api_keys").fetchall() == [
            ("UNITONLY", 0)
        ]
        assert [
            row[0]
            for row in connection.execute("SELECT version_num FROM alembic_version")
        ] == ScriptDirectory.from_config(config).get_heads()
