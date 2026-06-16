"""Regression tests for OCR availability handling (offline default).

Covers:
- OCRService.process_document raises a typed OCRUnavailableError (not a bare
  RuntimeError) when the optional OCR deps are absent.
- OCRService._document_path derives the on-disk path from the document id +
  title extension (the Document model has no ``file_path`` attribute).
- The v1 OCR endpoints return a clean 503 instead of a raw 500 when OCR is
  unavailable.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from app.api.deps import get_current_user
from app.api.v1.documents import _require_ocr
from app.main import app
from app.services.document.processing import ocr as ocr_module
from app.services.document.processing.ocr import (
    OCRService,
    OCRUnavailableError,
    ocr_available,
)
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


class _Doc:
    """Minimal stand-in matching the Document attributes OCR relies on."""

    def __init__(self, title: str) -> None:
        self.id = uuid.uuid4()
        self.title = title


def test_document_path_derives_from_id_and_extension() -> None:
    doc = _Doc("Quarterly Report.PDF")
    path = OCRService._document_path(doc)
    assert path == f"data/uploads/{doc.id}/{doc.id}.pdf"


def test_document_path_never_uses_raw_title() -> None:
    # A traversal-style title must not influence the resolved path.
    doc = _Doc("../../evil.pdf")
    path = OCRService._document_path(doc)
    assert ".." not in path
    assert path == f"data/uploads/{doc.id}/{doc.id}.pdf"


async def test_process_document_raises_typed_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the offline default regardless of the host environment.
    monkeypatch.setattr(ocr_module, "_OCR_AVAILABLE", False)
    service = OCRService()
    with pytest.raises(OCRUnavailableError):
        await service.process_document(_Doc("doc.pdf"))


def test_require_ocr_raises_503_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr_module, "_OCR_AVAILABLE", False)
    assert ocr_available() is False
    with pytest.raises(HTTPException) as exc:
        _require_ocr()
    assert exc.value.status_code == 503


@pytest_asyncio.fixture
async def auth_client(monkeypatch: pytest.MonkeyPatch):
    """Client with auth bypassed so we can exercise the OCR guard directly."""
    monkeypatch.setattr(ocr_module, "_OCR_AVAILABLE", False)

    async def _fake_user() -> dict[str, Any]:
        return {"id": str(uuid.uuid4()), "name": "test", "is_admin": True}

    app.dependency_overrides[get_current_user] = _fake_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


async def test_ocr_endpoint_returns_503_when_unavailable(auth_client) -> None:
    response = await auth_client.post(f"/api/v1/documents/{uuid.uuid4()}/ocr")
    assert response.status_code == 503
    assert "OCR is not available" in response.json()["detail"]


async def test_detect_template_endpoint_returns_503_when_unavailable(
    auth_client,
) -> None:
    response = await auth_client.post(
        f"/api/v1/documents/{uuid.uuid4()}/detect-template"
    )
    assert response.status_code == 503
