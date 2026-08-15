"""Safe local PostgreSQL backup and restore command construction."""

from scripts.backup_postgres import build_backup_command
from scripts.restore_postgres import build_restore_command


def test_backup_command_uses_custom_format_and_explicit_destination() -> None:
    command = build_backup_command(
        "postgresql://user:pass@db/groundtruth", "backup.dump"
    )
    assert command == [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--file",
        "backup.dump",
        "postgresql://user:pass@db/groundtruth",
    ]


def test_restore_command_requires_clean_restore_flags() -> None:
    command = build_restore_command(
        "postgresql://user:pass@db/groundtruth", "backup.dump"
    )
    assert command == [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        "postgresql://user:pass@db/groundtruth",
        "backup.dump",
    ]
