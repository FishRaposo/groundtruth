"""Reset script for dropping and recreating the GroundTruth database."""

import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import Base
from app.models import Document, Chunk, Query  # noqa: F401


async def reset_database(database_url: str, run_seed: bool) -> None:
    """Drop all tables then recreate them from SQLAlchemy metadata."""
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("All tables dropped.")
        await conn.run_sync(Base.metadata.create_all)
        print("All tables recreated.")
    await engine.dispose()

    if run_seed:
        import subprocess

        script_dir = os.path.dirname(os.path.abspath(__file__))
        seed_script = os.path.join(script_dir, "seed.py")
        print("\nRunning seed script...")
        result = subprocess.run(
            [sys.executable, seed_script],
            cwd=os.path.dirname(script_dir),
        )
        if result.returncode != 0:
            print("Seed script failed.")
            sys.exit(1)


def main() -> int:
    """Entry point for the database reset script."""
    parser = argparse.ArgumentParser(description="Reset the GroundTruth database")
    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirm that all data will be deleted",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Run the seed script after resetting",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL (default: DATABASE_URL env var)",
    )
    args = parser.parse_args()

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            "DATABASE_URL not set. Provide --database-url or set the DATABASE_URL environment variable."
        )
        return 1

    if not args.confirm:
        print("Use --confirm to acknowledge data loss.")
        return 1

    print(f"Resetting database: {database_url.split('@')[-1]}")
    asyncio.run(reset_database(database_url, args.seed))
    print("Reset complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
