"""Verify the real loopback API against a disposable seeded portfolio instance.

No successful responses are mocked. The private seed manifest supplies temporary
identities; the public report contains no keys. Run again with --restart-check
after explicitly restarting the same server/database to verify durable history.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx


def small_pdf(text: str) -> bytes:
    """Construct an ordinary single-page text PDF without a new dependency."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 40 740 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{start}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def terminal_events(body: str) -> list[dict]:
    events = []
    for line in body.replace("\r\n", "\n").splitlines():
        if line.startswith("data:"):
            event = json.loads(line.removeprefix("data:").strip())
            if event.get("type") in {"done", "refused"}:
                events.append(event)
    return events


async def verify(manifest: dict, restart: dict | None) -> dict:
    base = manifest["api_url"]
    if urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Verification is restricted to an explicitly local API")
    if manifest.get("seed_status") != "complete":
        raise ValueError("Canonical corpus seed did not complete")
    identities = manifest["principals"]
    checks: list[str] = []

    async with httpx.AsyncClient(base_url=base, timeout=180) as client:

        async def request(method, path, *, alias="operator-a", expected=200, **kwargs):
            response = await client.request(
                method,
                path,
                headers={"X-API-Key": identities[alias]["api_key"]},
                **kwargs,
            )
            if response.status_code != expected:
                raise AssertionError(
                    f"{method} {path}: expected {expected}, "
                    f"got {response.status_code}: {response.text[:500]}"
                )
            return response.json() if response.content else None

        if restart:
            recorded = await request("GET", f"/api/queries/{restart['query_id']}")
            assert (
                hashlib.sha256(
                    json.dumps(recorded["sources"], sort_keys=True).encode()
                ).hexdigest()
                == restart["source_snapshot_sha256"]
            )
            source = await request(
                "GET", f"/api/queries/{restart['query_id']}/sources/1"
            )
            assert source
            versions = await request(
                "GET", f"/api/v1/documents/{restart['updated_document_id']}/versions"
            )
            assert versions
            checks.extend(
                [
                    "saved query and exact source snapshot survive restart",
                    "updated/restored document versions survive restart",
                ]
            )
            return {
                "schema_version": 1,
                "observed_at": datetime.now(UTC).isoformat(),
                "checks": checks,
                "restart_of": restart["observed_at"],
            }

        identity = await request("GET", "/api/identity")
        assert identity["workspace_id"] == "ops-a"
        checks.append("authenticated identity comes from trusted key metadata")
        document = manifest["documents"]["dev-rollback"]["document_id"]
        payload = {
            "question": manifest["browser"]["question"],
            "document_ids": [document],
            "retrieval_method": "hybrid",
        }
        answer = await request("POST", "/api/queries", json=payload)
        assert not answer["refused"] and answer["outcome"] == "completed"
        assert answer["sources"] and all(
            source["document_version"] == 2 for source in answer["sources"]
        )
        assert all(source["document_id"] == document for source in answer["sources"])
        assert "source-extractive" == answer["provenance"]["generation_method"]
        source = await request("GET", f"/api/queries/{answer['id']}/sources/1")
        assert (
            manifest["browser"]["expected_quote"].lower() in json.dumps(source).lower()
        )
        await request(
            "GET", f"/api/queries/{answer['id']}", alias="viewer-a", expected=404
        )
        await request(
            "GET", f"/api/queries/{answer['id']}", alias="custodian-b", expected=404
        )
        checks.append(
            "real scoped retrieval cites immutable version2 evidence; "
            "history is owner/workspace isolated"
        )

        private = manifest["documents"]["dev-access"]["document_id"]
        await request(
            "GET", f"/api/documents/{private}", alias="viewer-a", expected=404
        )
        denied = await request(
            "POST",
            "/api/queries",
            alias="viewer-a",
            json={
                "question": "What is the access review interval?",
                "document_ids": [private],
            },
        )
        assert denied["refused"] and not denied["sources"] and not denied.get("answer")
        empty = await request(
            "POST", "/api/queries", json={**payload, "document_ids": []}
        )
        assert empty["refused"] and not empty["sources"]
        checks.append(
            "private/empty filters narrow authorized scope without exposing content"
        )

        continued = await request(
            "POST",
            "/api/queries",
            json={
                **payload,
                "conversation_id": answer["conversation_id"],
                "memory_policy": "recent",
            },
        )
        assert continued["conversation_id"] == answer["conversation_id"]
        assert [item["citation_index"] for item in continued["sources"]] == list(
            range(1, len(continued["sources"]) + 1)
        )
        await request(
            "GET",
            f"/api/conversations/{answer['conversation_id']}",
            alias="viewer-a",
            expected=404,
        )
        checks.append(
            "bounded conversation workflow retains source numbering and owner isolation"
        )

        overlaps = await asyncio.gather(
            *[request("POST", "/api/queries", json=payload) for _ in range(20)]
        )
        assert len({row["id"] for row in overlaps}) == 20
        for row in overlaps:
            assert row["retrieval_trace"]["request_id"] == row["id"]
            assert row["retrieval_trace"]["final_context_chunks"] == len(row["sources"])
            assert all(
                item["document_id"] == document
                for item in row["retrieval_trace"]["scores"]
            )
        checks.append(
            "twenty overlapping requests retain isolated traces "
            "and exact filtered counts"
        )

        response = await client.post(
            "/api/queries/stream",
            headers={"X-API-Key": identities["operator-a"]["api_key"]},
            json=payload,
        )
        response.raise_for_status()
        done = terminal_events(response.text)
        assert len(done) == 1 and not done[0]["refused"]
        assert done[0]["sources"][0]["document_version"] == 2
        checks.append(
            "actual HTTP SSE persists the normal-query source/version contract"
        )
        refused_stream = await client.post(
            "/api/queries/stream",
            headers={"X-API-Key": identities["viewer-a"]["api_key"]},
            json={
                "question": "What is the access review interval?",
                "document_ids": [private],
            },
        )
        refused_stream.raise_for_status()
        terminal = terminal_events(refused_stream.text)
        assert len(terminal) == 1 and terminal[0]["type"] == "refused"
        assert terminal[0]["refused"] and not terminal[0]["sources"]
        assert terminal[0]["id"] and not terminal[0].get("answer")
        checks.append("actual SSE refusal is a saved terminal outcome without leakage")

        fixture_id = uuid.uuid4().hex
        body = small_pdf(
            "Portable PDF recovery. Pause the deployment queue "
            f"before restoring the healthy image. Fixture {fixture_id}."
        )
        upload = await request(
            "POST",
            "/api/documents/upload",
            files=[("files", ("portable-proof.pdf", body, "application/pdf"))],
        )
        uploaded = upload["documents"][0]
        assert uploaded["status"] == "ready" and uploaded["chunk_count"] > 0
        identifier = uploaded["id"]
        await request(
            "POST",
            f"/api/v1/documents/{identifier}/versions",
            data={"base_version": "1"},
            files={
                "file": (
                    "portable-proof.pdf",
                    small_pdf(
                        "Portable PDF recovery revised. Require the release captain "
                        f"before restoring the healthy image. Fixture {fixture_id}."
                    ),
                    "application/pdf",
                )
            },
        )
        snapshot = await request("GET", f"/api/v1/documents/{identifier}/versions/1")
        assert "Portable PDF recovery" in json.dumps(snapshot)
        await request("POST", f"/api/v1/documents/{identifier}/versions/1/restore")
        restored = await request("GET", f"/api/documents/{identifier}")
        assert restored["version_number"] == 3 and restored["status"] == "ready"
        checks.append(
            "actual PDF parsing, version update, immutable snapshot "
            "and regenerated restore publish successfully"
        )

        broken = await request(
            "POST",
            "/api/documents/upload",
            files=[
                ("files", ("quarantine-proof.pdf", b"not a PDF", "application/pdf"))
            ],
        )
        assert broken["documents"][0]["status"] == "error"
        job_id = broken["ingestions"][0]["id"]
        job = await request("GET", f"/api/ingestions/{job_id}")
        assert job["status"] == "error"
        checks.append("malformed PDF creates a durable failed ingestion")
        await request("GET", "/api/v1/admin/usage", alias="viewer-a", expected=403)
        checks.append("ordinary reader receives an explicit admin denial")
        return {
            "schema_version": 1,
            "observed_at": datetime.now(UTC).isoformat(),
            "profile": manifest["profile"],
            "checks": checks,
            "query_id": answer["id"],
            "updated_document_id": identifier,
            "source_snapshot_sha256": hashlib.sha256(
                json.dumps(answer["sources"], sort_keys=True).encode()
            ).hexdigest(),
            "overlapping_requests": len(overlaps),
            "application_errors": 0,
            "limits": [
                "portable SQLite/inline execution; PostgreSQL/Redis deferred",
                "synthetic authored labels; human/model quality unvalidated",
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restart-check", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.seed_manifest.read_text(encoding="utf-8"))
    restart = (
        json.loads(args.restart_check.read_text(encoding="utf-8"))
        if args.restart_check
        else None
    )
    result = asyncio.run(verify(manifest, restart))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"Verified {len(result['checks'])} real connected checks; report: {args.output}"
    )


if __name__ == "__main__":
    main()
