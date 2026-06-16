"""Regression tests for upload path sanitization (path traversal hardening).

The upload handler must never write outside the per-document upload directory,
even when the attacker-controlled multipart filename contains path separators
or ``..`` traversal sequences.
"""

import os
import uuid

import pytest
from app.api.documents import (
    _detect_source_type,
    _resolve_storage_path,
    _safe_extension,
)
from app.services.ingestion import IngestionService
from fastapi import HTTPException


def _within(child: str, parent: str) -> bool:
    real_child = os.path.realpath(child)
    real_parent = os.path.realpath(parent)
    return os.path.commonpath([real_parent, real_child]) == real_parent


def test_resolve_storage_path_stays_inside_upload_dir(tmp_path) -> None:
    upload_dir = str(tmp_path)
    # The stored name is derived from a trusted UUID; even so the helper must
    # keep the result contained.
    path = _resolve_storage_path(upload_dir, f"{uuid.uuid4()}.pdf")
    assert _within(path, upload_dir)


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../../evil.pdf",
        "../../../etc/passwd.pdf",
        "..\\..\\evil.pdf",
        "subdir/evil.pdf",
        "/abs/evil.pdf",
    ],
)
def test_resolve_storage_path_neutralizes_traversal(tmp_path, malicious_name) -> None:
    upload_dir = str(tmp_path)
    # basename() strips directory components, so the file lands directly in the
    # upload dir and never escapes it.
    path = _resolve_storage_path(upload_dir, malicious_name)
    assert _within(path, upload_dir)
    assert os.path.dirname(os.path.realpath(path)) == os.path.realpath(upload_dir)


def test_safe_extension_only_returns_supported_extensions() -> None:
    assert _safe_extension("report.pdf") == ".pdf"
    assert _safe_extension("notes.MD") == ".md"
    assert _safe_extension("page.HTM") == ".htm"
    # A traversal payload still resolves only to its (supported) extension.
    assert _safe_extension("../../evil.pdf") == ".pdf"


def test_safe_extension_rejects_unsupported_types() -> None:
    with pytest.raises(HTTPException) as exc:
        _safe_extension("../../evil.exe")
    assert exc.value.status_code == 400


def test_detect_source_type_rejects_unsupported_types() -> None:
    with pytest.raises(HTTPException):
        _detect_source_type("payload.sh")


def test_ingestion_stored_path_matches_upload_convention() -> None:
    """The ingestion read path must match the sanitized stored name.

    A malicious title must not influence the directory the file is read from:
    only ``{id}/{id}{ext}`` is used.
    """

    class _Doc:
        id = uuid.uuid4()
        title = "../../evil.pdf"

    path = IngestionService._stored_path(_Doc())
    expected = f"data/uploads/{_Doc.id}/{_Doc.id}.pdf"
    assert path == expected
    assert ".." not in path
