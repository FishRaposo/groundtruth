"""UNITONLY routing controls; verifier results are not inference observations."""

from copy import deepcopy

import pytest
from app.evidence_policy import CONTEXTUAL_CONTRACT


def record():
    return {
        "contract": CONTEXTUAL_CONTRACT,
        "evidence_profile": {"evidence_reading_profile": "contextual_source_v1"},
    }


@pytest.mark.parametrize("location", ["selection", "capture"])
def test_contextual_markers_never_fall_through_to_legacy(monkeypatch, location):
    from app.services import contextual_output, output_dispatch, procedure_output

    selected = record() if location == "selection" else {"contract": "unknown"}
    capture = {"provenance": {"answer_selection": record()}}
    calls = []
    monkeypatch.setattr(
        contextual_output, "verify_output", lambda *a, **k: calls.append("new") or False
    )
    monkeypatch.setattr(
        procedure_output, "verify_output", lambda *a, **k: calls.append("old") or True
    )
    assert output_dispatch.has_output_contract(selected, query_context=capture)
    assert not output_dispatch.verify_output(selected, query_context=capture)
    assert calls == ["new"]


@pytest.mark.parametrize(
    "marker",
    [
        {"contract": CONTEXTUAL_CONTRACT},
        {"evidence_profile": {"contract": "evidence-profile-v5"}},
        {"evidence_profile": {"evidence_reading_profile": "contextual_source_v1"}},
        {"contextual_output_certificate": {}},
    ],
)
def test_each_new_marker_requires_new_reconstruction(marker):
    from app.services.output_dispatch import is_contextual

    assert is_contextual(marker)
    assert is_contextual({}, query_context={"provenance": {"answer_selection": marker}})


def test_existing_procedure_dispatch_is_preserved(monkeypatch):
    from app.services import output_dispatch, procedure_output

    legacy = {
        "evidence_profile": {
            "procedure_verification_profile": "source_declared_procedure_copy_v1"
        },
        "requirements": [{"kind": "procedure", "status": "supported"}],
    }
    original = deepcopy(legacy)
    monkeypatch.setattr(procedure_output, "verify_output", lambda *a, **k: True)
    assert output_dispatch.has_output_contract(legacy)
    assert output_dispatch.verify_output(legacy, question="legacy")
    assert legacy == original


def test_plain_legacy_record_does_not_gain_an_output_certificate():
    from app.services.output_dispatch import has_output_contract

    assert not has_output_contract({"contract": "requirement-evidence-v1"})
