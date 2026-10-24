"""Seed synthetic runbooks through a local API; store disposable keys privately.

Run after migrations, using the same DATABASE_URL and execution profile as the
server. Database writes here only bootstrap trusted API identities and fixture
collection grants/metadata; parsing, embeddings and versions use real HTTP routes.
Never use this helper against an owner's database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import insert, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.api_key import ApiKey, generate_api_key  # noqa: E402
from app.models.collection import Collection, collection_documents  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.query import Query  # noqa: E402
from app.portfolio import load_corpus  # noqa: E402
from app.services.embedding import embedding_service  # noqa: E402


def save(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


async def seed(api_url: str, output: Path) -> None:
    if urlparse(api_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Seeding is restricted to an explicitly local API")
    if output.exists():
        raise ValueError(
            "Manifest already exists; use a new disposable database and output"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus()
    settings = get_settings()
    if not settings.connected:
        raise ValueError(
            "Choose local or deterministic embeddings with extractive generation"
        )
    manifest: dict = {
        "schema_version": 1,
        "api_url": api_url.rstrip("/"),
        "corpus_manifest_sha256": corpus["manifest"]["manifest_sha256"],
        "profile": {
            "persistence": "sqlite"
            if settings.DATABASE_URL.startswith("sqlite")
            else "postgresql",
            "indexed": False,
            "embedding": embedding_service.signature,
            "generation": settings.GENERATION_MODE,
            "ingestion": settings.INGESTION_MODE,
        },
        "principals": {},
        "documents": {},
        "seed_status": "incomplete",
    }
    identities = {
        **corpus["manifest"]["principals"],
        "admin-a": {"workspace_id": "ops-a", "role": "admin"},
    }
    async with AsyncSessionLocal() as db:
        for alias, identity in identities.items():
            raw, digest, prefix = generate_api_key()
            identifier = uuid.uuid4()
            db.add(
                ApiKey(
                    id=identifier,
                    name=alias,
                    key_hash=digest,
                    key_prefix=prefix,
                    is_admin=identity["role"] == "admin",
                    rate_limit=100000,
                    metadata_={
                        "workspace_id": identity["workspace_id"],
                        "organization_id": identity["workspace_id"],
                        "group_ids": ["operations"],
                    },
                )
            )
            manifest["principals"][alias] = {
                "id": str(identifier),
                "api_key": raw,
                **identity,
            }
        legacy_id = uuid.uuid4()
        db.add(
            Query(
                id=legacy_id,
                question="Legacy imported entry (compatibility fixture)",
                answer="Historical saved text; source provenance is unknown.",
                owner_id=None,
                workspace_id="ops-a",
                sources=[],
                provenance=None,
                outcome=None,
            )
        )
        manifest["legacy_query_id"] = str(legacy_id)
        await db.commit()
    save(output, manifest)
    async with httpx.AsyncClient(base_url=api_url, timeout=180) as client:
        for fixture in corpus["documents"]:
            principal = manifest["principals"][fixture["owner"]]
            headers = {"X-API-Key": principal["api_key"]}
            first = fixture["versions"][0]
            response = await client.post(
                "/api/documents/upload",
                headers=headers,
                files=[
                    (
                        "files",
                        (
                            fixture["id"] + ".txt",
                            first["content"].encode(),
                            "text/plain",
                        ),
                    )
                ],
            )
            response.raise_for_status()
            document = response.json()["documents"][0]
            identifier = document["id"]
            for version in fixture["versions"][1:]:
                response = await client.post(
                    f"/api/v1/documents/{identifier}/versions",
                    headers=headers,
                    files={
                        "file": (
                            fixture["id"] + ".txt",
                            version["content"].encode(),
                            "text/plain",
                        )
                    },
                    data={"base_version": str(version["version_number"] - 1)},
                )
                response.raise_for_status()
            # These are declared corpus fixture grants, never replacement chunks.
            async with AsyncSessionLocal() as db:
                stored = await db.scalar(
                    select(Document).where(Document.id == uuid.UUID(identifier))
                )
                if stored is None or stored.status.value != "ready":
                    raise RuntimeError(
                        f"Canonical ingestion did not publish {fixture['id']}"
                    )
                if stored.content_hash != fixture["versions"][-1]["content_hash"]:
                    raise RuntimeError(
                        f"Published content differs from frozen source {fixture['id']}"
                    )
                stored.title = fixture["title"]
                stored.metadata_ = {
                    **(stored.metadata_ or {}),
                    **fixture["metadata"],
                    "portfolio_logical_id": fixture["id"],
                    "synthetic": True,
                }
                if fixture["visibility"] != "private":
                    collection = Collection(
                        name=fixture["title"] + " fixtures",
                        owner_id=principal["id"],
                        organization_id=fixture["workspace_id"],
                        is_public=fixture["visibility"],
                    )
                    db.add(collection)
                    await db.flush()
                    await db.execute(
                        insert(collection_documents).values(
                            collection_id=collection.id, document_id=stored.id
                        )
                    )
                await db.commit()
            manifest["documents"][fixture["id"]] = {
                "document_id": identifier,
                "versions": {
                    str(v["version_number"]): {"content_hash": v["content_hash"]}
                    for v in fixture["versions"]
                },
            }
            save(output, manifest)
        admin = manifest["principals"]["admin-a"]
        response = await client.post(
            "/api/v1/workflows/definitions",
            headers={"X-API-Key": admin["api_key"]},
            json={
                "name": "Local evidence review",
                "description": "Synthetic review fixture for the real workflow engine.",
                "steps": [
                    {"name": "Review source evidence", "approvers": [admin["id"]]}
                ],
            },
        )
        response.raise_for_status()
        manifest["workflow_definition_id"] = response.json()["id"]
    manifest["browser"] = {
        "question": "How do I roll back the staging deployment?",
        "expected_quote": "pause the deployment queue",
        "document_id": manifest["documents"]["dev-rollback"]["document_id"],
    }
    manifest["seed_status"] = "complete"
    save(output, manifest)
    print(
        f"Seeded {len(manifest['documents'])} synthetic documents; "
        f"private manifest: {output}"
    )
    print("Keys were not printed. Keep the manifest outside tracked files.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8400")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--confirm-disposable-database", action="store_true", required=True
    )
    args = parser.parse_args()
    asyncio.run(seed(args.api_url, args.manifest))


if __name__ == "__main__":
    main()
