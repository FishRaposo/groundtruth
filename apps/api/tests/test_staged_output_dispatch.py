"""Staged version markers in either channel cannot downgrade verification."""

from copy import deepcopy

import pytest
from app.services import output_dispatch as dispatch


@pytest.mark.parametrize("marker", ["contract", "profile", "certificate", "inputs"])
@pytest.mark.parametrize("channel", ["presented", "retained"])
def test_staged_marker_never_falls_back_to_old_output(monkeypatch, marker, channel):
    selection = {}
    captured = {}
    marked = selection if channel == "presented" else captured
    if marker == "contract":
        marked["contract"] = "requirement-evidence-v5"
    elif marker == "profile":
        marked["evidence_profile"] = {
            "evidence_reading_profile": "contextual_source_v3"
        }
    elif marker == "certificate":
        marked["staged_output_certificate"] = {"approved": True}
    else:
        marked["staged_request_inputs"] = {"approved": True}
    monkeypatch.setattr(
        dispatch.procedure_output, "verify_output", lambda *a, **k: True
    )
    context = {
        "question": "UNITONLY",
        "answer": "forged",
        "citations": [],
        "source_snapshots": {},
        "query_context": {"provenance": {"answer_selection": deepcopy(captured)}},
    }
    assert dispatch.has_output_contract(selection, context["query_context"])
    assert dispatch.verify_output(selection, **context) is False
    with pytest.raises(ValueError):
        dispatch.certify_output(selection, **context)
