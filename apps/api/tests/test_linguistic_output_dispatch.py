"""A new reading profile cannot escape publication/history verification."""

from copy import deepcopy

import pytest
from app.evidence_policy import resolve_evidence_policy
from app.services import output_dispatch

from tests.test_linguistic_runtime_dispatch import config


def selection():
    policy = resolve_evidence_policy(config())
    return {
        "contract": policy.requirement_contract,
        "evidence_profile": policy.record(),
    }


@pytest.mark.parametrize("marker", ["all", "contract", "profile", "profile_contract"])
def test_any_retained_linguistic_marker_requires_output_verification(marker):
    row = selection()
    if marker == "contract":
        row = {"contract": row["contract"]}
    elif marker == "profile":
        row = {"evidence_profile": {"evidence_reading_profile": "contextual_source_v2"}}
    elif marker == "profile_contract":
        row = {"evidence_profile": {"contract": "evidence-profile-v6"}}
    assert output_dispatch.has_output_contract(row)
    assert output_dispatch.is_contextual(row)
    assert output_dispatch.verify_output(row) is False


def test_linguistic_selection_cannot_be_certified_by_legacy_procedure_path(monkeypatch):
    calls = []
    monkeypatch.setattr(
        output_dispatch.procedure_output,
        "certify_output",
        lambda *a, **k: calls.append(a),
    )
    row = selection()
    with pytest.raises(ValueError):
        output_dispatch.certify_output(row)
    assert not calls


def test_retained_linguistic_trace_marker_cannot_be_downgraded(monkeypatch):
    retained = deepcopy(selection())
    monkeypatch.setattr(
        output_dispatch.procedure_output, "retained_selection", lambda context: retained
    )
    assert output_dispatch.has_output_contract({}, {"trace": "UNITONLY"})
    assert (
        output_dispatch.verify_output({}, query_context={"trace": "UNITONLY"}) is False
    )
