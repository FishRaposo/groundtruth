"""The API publishes the same JSON evidence that history will reconstruct."""

import pytest
from app.evidence_policy import EvidencePolicy, resolve_evidence_policy
from app.services import connected_query
from app.services.request_parser import _native

from tests.test_linguistic_runtime_dispatch import config


def test_model_tuple_measurements_become_detached_native_json_before_v2_proof():
    selection = {"support": {"logits": (0.0, 5.0, 0.0)}}
    saved = connected_query.publication_snapshot(
        selection, resolve_evidence_policy(config())
    )
    _native(saved)
    assert saved["support"]["logits"] == [0.0, 5.0, 0.0]
    assert selection["support"]["logits"] == (0.0, 5.0, 0.0)


def test_nonfinite_model_measurement_prevents_v2_publication():
    with pytest.raises(ValueError):
        connected_query.publication_snapshot(
            {"logits": [float("nan")]}, resolve_evidence_policy(config())
        )


def test_legacy_library_snapshot_keeps_its_existing_python_shape():
    selection = {"logits": (0.0, 5.0, 0.0)}
    assert (
        connected_query.publication_snapshot(
            selection, EvidencePolicy("qa_only_v1", "literal_v1")
        )
        is selection
    )
