"""Restore a local PostgreSQL custom-format backup behind an explicit confirmation."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def build_restore_command(database_url: str, source: str) -> list[str]:
    return [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        database_url,
        source,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run pg_restore (default prints the plan)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive replacement of database objects",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if not args.source.is_file():
        parser.error(f"backup file does not exist: {args.source}")
    command = build_restore_command(args.database_url, str(args.source.resolve()))
    if not args.execute:
        print("Dry run: pg_restore clean restore from", args.source.resolve())
        return 0
    if not args.confirm:
        parser.error(
            "--execute requires --confirm because restore replaces database objects"
        )
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
