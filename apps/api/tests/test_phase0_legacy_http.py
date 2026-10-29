"""Real SQLite legacy HTTP contracts, separate from scoped connected execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("stream", [False, True])
def test_legacy_upload_query_and_json_safe_saved_citations(
    tmp_path: Path, stream: bool
):
    # A fresh interpreter isolates the legacy singleton settings/database from
    # connected fixtures. No provider, live server, or shared database is used.
    code = r"""
import json, sys
from fastapi.testclient import TestClient
from app.main import app
from app.models.document import DocumentResponse
with TestClient(app) as client:
    uploaded = client.post('/api/documents/upload', files=[('files', (
        'refund_policy.md',
        b'Customers may request a refund within 30 days of purchase. '
        b'Refunds are issued to the original payment method within 5 business days.',
        'text/markdown'))])
    assert uploaded.status_code == 200, uploaded.text
    [doc] = uploaded.json()['documents']
    ready = client.get('/api/documents/' + doc['id'])
    assert ready.status_code == 200, ready.text
    assert ready.json()['status'] == 'ready', ready.text
    assert isinstance(ready.json()['metadata'], dict)
    metadata = DocumentResponse.model_validate(ready.json()).metadata
    assert metadata == ready.json()['metadata']
    question = {'question': 'How many days do I have to request a refund?'}
    path = '/api/queries/stream' if sys.argv[1] == 'True' else '/api/queries'
    answered = client.post(path, json=question)
    assert answered.status_code == 200, answered.text
    if sys.argv[1] == 'True':
        events = [json.loads(line[6:]) for line in answered.text.splitlines()
                  if line.startswith('data: ')]
        citations = next(e['sources'] for e in events if e['type'] == 'citations')
        assert events[-1]['type'] == 'done', events
    else:
        body = answered.json()
        assert body['refused'] is False, body
        assert body['confidence'] >= 0.5, body
        citations = body['sources']
    assert citations and citations[0]['document_id'] == doc['id'], citations
    refused = client.post(path, json={'question':'What are the salary bands?'})
    assert refused.status_code == 200, refused.text
    if sys.argv[1] == 'True':
        events = [json.loads(line[6:]) for line in refused.text.splitlines()
                  if line.startswith('data: ')]
        assert events[-1]['type'] == 'refused', events
    else:
        body = refused.json()
        assert body['refused'] is True, body
        assert body['sources'] == [] and body['answer'] is None, body
        assert body['confidence'] < 0.5, body
print('legacy upload, answered/refused HTTP and JSON-safe persistence/SSE OK')
"""
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(ROOT / "apps" / "api"),
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
        [sys.executable, "-c", code, str(stream)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "JSON-safe persistence/SSE OK" in result.stdout


def test_document_response_keeps_plain_dict_and_orm_metadata():
    from datetime import datetime
    from uuid import uuid4

    from app.models.document import (
        Document,
        DocumentResponse,
        DocumentStatus,
        SourceType,
    )

    row = Document(
        id=uuid4(),
        title="terms.md",
        source_type=SourceType.MARKDOWN,
        source_url=None,
        status=DocumentStatus.READY,
        metadata_={"terms": "retained"},
        created_at=datetime(2026, 10, 24),
        updated_at=datetime(2026, 10, 24),
        version_number=0,
        workspace_id="default",
    )
    response = DocumentResponse.model_validate(row)
    assert response.metadata == {"terms": "retained"}
    plain = response.model_dump(mode="json")
    assert "metadata" in plain and "metadata_" not in plain
    assert DocumentResponse.model_validate(plain).metadata == response.metadata
    assert json.loads(response.model_dump_json())["metadata"] == response.metadata
