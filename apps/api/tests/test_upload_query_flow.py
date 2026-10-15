"""HTTP regression test: upload a document, let it process, then query it.

Guards the end-to-end path a user takes against a live SQLite API:

* ``POST /api/documents/upload`` used to return HTTP 500 because
  ``DocumentResponse.model_validate`` read SQLAlchemy's declarative
  ``Document.metadata`` registry instead of the ``metadata_`` JSON column.
* An answered ``POST /api/queries`` used to return HTTP 500 because citation
  UUIDs were stored in a JSON column without JSON-mode serialization.
* An unsupported question used to clear the refusal threshold because keyword
  overlap counted function words ("what", "are") as evidence.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "data" / "sample" / "refund_policy.md"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Uploads are written relative to the working directory (data/uploads/...).
    monkeypatch.chdir(tmp_path)
    from app.main import app

    with TestClient(app) as client:
        yield client


def _wait_until_ready(api: TestClient, document_id: str) -> dict:
    deadline = time.monotonic() + 10
    while True:
        response = api.get(f"/api/documents/{document_id}")
        assert response.status_code == 200, response.text
        document = response.json()
        if document["status"] in {"ready", "error"} or time.monotonic() > deadline:
            return document
        time.sleep(0.05)


def test_upload_process_and_query_refund_policy(api: TestClient) -> None:
    with SAMPLE.open("rb") as handle:
        response = api.post(
            "/api/documents/upload",
            files=[("files", (SAMPLE.name, handle, "text/markdown"))],
        )

    assert response.status_code == 200, response.text
    [uploaded] = response.json()["documents"]
    assert uploaded["title"] == SAMPLE.name
    assert "metadata" in uploaded

    document = _wait_until_ready(api, uploaded["id"])
    assert document["status"] == "ready", document.get("metadata")
    assert document["chunk_count"] and document["chunk_count"] > 0
    assert isinstance(document["metadata"], dict)

    listing = api.get("/api/documents")
    assert listing.status_code == 200, listing.text
    assert uploaded["id"] in {d["id"] for d in listing.json()["documents"]}

    answered = api.post(
        "/api/queries",
        json={"question": "How many days do I have to request a refund?"},
    )
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["refused"] is False
    assert body["sources"], body
    assert uploaded["id"] in {source["document_id"] for source in body["sources"]}
    assert body["confidence"] >= 0.5

    refused = api.post("/api/queries", json={"question": "What are the salary bands?"})
    assert refused.status_code == 200, refused.text
    body = refused.json()
    assert body["refused"] is True
    assert body["sources"] == []
    assert body["answer"] is None
    assert body["confidence"] < 0.5
