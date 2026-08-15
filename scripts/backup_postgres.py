"""Create a local PostgreSQL custom-format backup; dry-run by default."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def build_backup_command(database_url: str, destination: str) -> list[str]:
    return [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--file",
        destination,
        database_url,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--execute", action="store_true", help="Run pg_dump (default prints the plan)"
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    command = build_backup_command(args.database_url, str(args.destination.resolve()))
    if not args.execute:
        print("Dry run: pg_dump custom-format backup to", args.destination.resolve())
        return 0
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
