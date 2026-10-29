"""HTTP regression test: upload a document, let it process, then query it.

Guards the end-to-end path a user takes against a live SQLite API:

* ``POST /api/documents/upload`` used to return HTTP 500 because
  ``DocumentResponse.model_validate`` read SQLAlchemy's declarative
  ``Document.metadata`` registry instead of the ``metadata_`` JSON column.
* An answered ``POST /api/queries`` used to return HTTP 500 because citation
  UUIDs were stored in a JSON column without JSON-mode serialization.
* An unsupported question used to clear the refusal threshold because keyword
  overlap counted function words ("what", "are") as evidence.

The flow runs in a fresh interpreter with the legacy profile because API-key
auth is enforced whenever settings are connected: this regression targets the
legacy singleton path, like ``test_phase0_legacy_http``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "data" / "sample" / "refund_policy.md"


def test_upload_process_and_query_refund_policy(tmp_path: Path) -> None:
    # A fresh interpreter isolates the legacy singleton settings/database from
    # connected fixtures. No provider, live server, or shared database is used.
    code = r"""
import sys, time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

sample = Path(sys.argv[1])
with TestClient(app) as client:
    with sample.open('rb') as handle:
        uploaded = client.post('/api/documents/upload', files=[('files', (
            sample.name, handle.read(), 'text/markdown'))])
    assert uploaded.status_code == 200, uploaded.text
    [doc] = uploaded.json()['documents']
    assert doc['title'] == sample.name
    assert 'metadata' in doc

    deadline = time.monotonic() + 10
    while True:
        document = client.get('/api/documents/' + doc['id'])
        assert document.status_code == 200, document.text
        document = document.json()
        if document['status'] in {'ready', 'error'} or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    assert document['status'] == 'ready', document.get('metadata')
    assert document['chunk_count'] and document['chunk_count'] > 0
    assert isinstance(document['metadata'], dict)

    listing = client.get('/api/documents')
    assert listing.status_code == 200, listing.text
    assert doc['id'] in {d['id'] for d in listing.json()['documents']}

    answered = client.post('/api/queries', json={
        'question': 'How many days do I have to request a refund?'})
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body['refused'] is False
    assert body['sources'], body
    assert doc['id'] in {source['document_id'] for source in body['sources']}
    assert body['confidence'] >= 0.5

    refused = client.post('/api/queries', json={
        'question': 'What are the salary bands?'})
    assert refused.status_code == 200, refused.text
    body = refused.json()
    assert body['refused'] is True
    assert body['sources'] == []
    assert body['answer'] is None
    assert body['confidence'] < 0.5
print('upload, process, answered/refused query OK')
"""
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(REPO_ROOT / "apps" / "api"),
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        OPENAI_API_KEY="",
        APP_ENV="test",
        AUTH_ENABLED="false",
        RATE_LIMIT_ENABLED="false",
        EMBEDDING_MODE="legacy",
        GENERATION_MODE="legacy",
        INGESTION_MODE="inline",
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(SAMPLE)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "upload, process, answered/refused query OK" in result.stdout
