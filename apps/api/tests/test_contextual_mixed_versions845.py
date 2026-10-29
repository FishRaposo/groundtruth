"""Shared profile mechanics only; UNITONLY inputs, no v3 publication claim."""

import hashlib
from copy import deepcopy

import pytest
from app.evidence_policy import EvidencePolicy, reading_version
from app.services import contextual_mixed_output as output
from app.services import linguistic_role_consumer as roles
from app.services import staged_plan_binding as binding
from app.services.answer_requirements import Requirement
from app.services.source_pattern_grammar import collect_source_proposals

from tests.staged_plan_unit837.fixtures_request import FIELD
from tests.staged_plan_unit837.test_binding import args as staged_inputs
from tests.test_contextual_mixed_output import PROC_BODY, PROC_QUESTION, fixture
from tests.test_linguistic_role_consumer import role_data

V2 = "contextual_source_v2"
V3 = "contextual_source_v3"


def source_inputs():
    """Version-neutral literal source/requirement DTOs; no request-plan projection."""
    doc = "00000000-0000-0000-0000-000000000091"
    chunk = "10000000-0000-0000-0000-000000000091"
    snapshot = {
        "document_id": doc,
        "document_version": 1,
        "content_hash": hashlib.sha256(PROC_BODY.encode()).hexdigest(),
        "workspace_id": None,
        "body": PROC_BODY,
        "chunks": [{"id": chunk, "index": 0, "content": PROC_BODY, "metadata": {}}],
    }
    chunks, _ = output.factual._source_inventory({doc: snapshot})
    source = chunks[chunk]["source"]
    requirement = Requirement(
        "r1",
        PROC_QUESTION,
        0,
        len(PROC_QUESTION),
        PROC_QUESTION,
        "procedure",
        "ordinary Larch transfers",
        ("Larch",),
    )
    return requirement, source, chunks


def test_explicit_v2_equals_unchanged_default_certificate():
    data = fixture()
    context = {
        k: v for k, v in data.items() if k not in {"selection", "answer", "citations"}
    }
    implicit = output.build_output(data["selection"], **context)
    explicit = output.build_output(data["selection"], reading_profile=V2, **context)
    assert explicit == implicit


@pytest.mark.parametrize(
    "profile", ["contextual_source_v1", "clause_bound_v1", "unknown", True]
)
def test_unknown_or_unshared_profile_refuses_before_fallback(profile):
    with pytest.raises(ValueError, match="Unsupported mixed output reading profile"):
        output.build_output(
            {},
            question="q",
            source_snapshots={},
            query_context={},
            reading_profile=profile,
        )


def test_v3_has_no_default_request_or_source_guard_fallback():
    with pytest.raises(ValueError, match="requirement-evidence-v5"):
        output._settings({}, {}, reading_profile=V3)
    with pytest.raises(
        output.PendingConsumerProof, match="independent.*reconstructors"
    ):
        output.build_output(
            {}, question="q", source_snapshots={}, query_context={}, reading_profile=V3
        )
    with pytest.raises(output.PendingConsumerProof, match="request reconstructor"):
        output._request({}, "q", {}, None, reading_profile=V3)
    with pytest.raises(output.PendingConsumerProof, match="source guard"):
        output._default_source_guard({}, None, {}, None, reading_profile=V3)


def test_actual_reconstructed_staged_plan_transport_preserves_full_record():
    actual = staged_inputs(rows=FIELD)
    plan = binding.reconstruct_staged_plan(**actual)
    assert isinstance(plan, binding.StagedRequestPlan) and plan.resolved_request
    selection = {"request_plan": plan.record()}

    def reconstruct(question, context):
        assert question == actual["question"] and context == {"fixture": "UNITONLY"}
        return binding.reconstruct_staged_plan(**actual)

    rebuilt, record, requirements = output._request(
        selection,
        plan.question,
        {"fixture": "UNITONLY"},
        reconstruct,
        reading_profile=V3,
    )
    assert isinstance(rebuilt, binding.StagedRequestPlan)
    assert record == plan.record()
    assert requirements == plan.requirements
    assert record["contract"] == reading_version(V3).request_plan
    assert record["output_history"] == "NOT_ASSESSED"


def test_v3_pattern_and_unassessed_procedure_headers_use_actual_version():
    requirement, source, chunks = source_inputs()
    batch = collect_source_proposals(requirement, [source], reading_profile=V3)
    assert batch.complete and batch.proposals
    selection = {
        "qa_observations": [],
        "pattern_observations": list(batch.observations),
        "proposals": [row.record() for row in batch.proposals],
    }
    proposals, _ = output._proposals(
        selection, (requirement,), [source], chunks, reading_profile=V3
    )
    proposal = next(iter(proposals.values()))
    record = output.procedure_obligations(
        requirement, source, proposal, reading_profile=V3
    )
    assert record["contract"] == reading_version(V3).procedure
    assert record["source_body"] == PROC_BODY
    assert record["inventory"]  # Unassessed builder, no source guard/output proof.
    with pytest.raises(ValueError, match="consumer.*version"):
        output.procedure_obligations(
            requirement,
            source,
            proposal,
            method="consumer_envelope",
            consumer_inventory={
                "contract": reading_version(V2).procedure,
                "reading_profile": V2,
            },
            reading_profile=V3,
        )


def test_actual_role_manifest_header_dispatch_retains_original_selector():
    data = role_data()
    selection = deepcopy(data["selection"])
    selection["contract"] = reading_version(V3).requirement
    selection["evidence_profile"] = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        V3,
    ).record()
    # _manifest consumes only question for its existing selector; no fake plan.
    selection["request_plan"] = {"question": data["question"]}
    selection["role_scope_read_set"]["contract"] = reading_version(V3).role_manifest
    selector = deepcopy(selection["role_scope_read_set"]["selector"])
    manifest = roles._manifest(selection, data["source_snapshots"])
    assert manifest.record()["contract"] == reading_version(V3).role_manifest
    assert manifest.record()["selector"] == selector
    selection["role_scope_read_set"]["contract"] = reading_version(V2).role_manifest
    with pytest.raises(ValueError):
        roles._manifest(selection, data["source_snapshots"])
