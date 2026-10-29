"""Exact exposed source/request binding regressions, before model support."""

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services.linguistic_property_cover import factual_claim

from tests.test_typed_count_fields968 import actual as source_bound_inputs


def actual():
    saved = json.loads(
        (Path(__file__).parent / "fixtures/actual-scalar-source967.json").read_text()
    )
    body = saved["body"]
    assert hashlib.sha256(body.encode()).hexdigest() == saved["body_sha256"]
    _, snapshot, _, plan, _ = source_bound_inputs()
    assert snapshot.body == body
    return body, plan, recorded_evidence_policy(json.loads(plan.evidence_profile_json))


@pytest.mark.parametrize(
    ("kind", "value"),
    [("duration", "14 simulated seconds"), ("location", "virtual bay P")],
)
def test_actual_literal_attribute_paraphrase_reaches_mandatory_ni(kind, value):
    body, plan, policy = actual()
    requirement = next(r for r in plan.requirements if r.kind == kind)
    start = body.index(value)
    claim = factual_claim(
        requirement, body, start, start + len(value), policy=policy, plan=plan
    )
    assert claim.rejection is None
    assert claim.value == value
    assert requirement.attribute in claim.hypothesis
    assert requirement.topic in claim.hypothesis
    assert claim.premise in body
    assert value in claim.premise
    assert "The batch quantity for Citrine" not in body


def test_wrong_duration_unit_and_legacy_profile_stay_unresolved():
    from dataclasses import replace

    body, plan, policy = actual()
    requirement = next(r for r in plan.requirements if r.kind == "duration")
    value = "6 datagram fragments"
    start = body.index(value)
    assert factual_claim(
        requirement, body, start, start + len(value), policy=policy, plan=plan
    ).rejection
    old = replace(policy, source_governance_profile="all_sources_v1")
    value = "14 simulated seconds"
    start = body.index(value)
    assert factual_claim(
        requirement, body, start, start + len(value), policy=old, plan=plan
    ).rejection


@pytest.mark.parametrize("ni_supported", [False, True])
async def test_actual_duration_requires_model_support_before_becoming_a_witness(
    monkeypatch, ni_supported
):
    from app.config import Settings
    from app.services import requirement_answers
    from app.services.answer_reader import ReaderSelection, passage_span
    from app.services.answer_support import SupportAssessment
    from app.services.procedure_evidence import single_chunk_source

    from tests.test_composite_procedures import chunk

    body, plan, _ = actual()
    _, snapshot, identity, _, _ = source_bound_inputs()
    requirement = next(r for r in plan.requirements if r.kind == "duration")
    value = "14 simulated seconds"
    start, end = body.index(value), body.index(value) + len(value)
    member = chunk(body, document=uuid.UUID(identity["document_id"]))
    member.metadata = dict(identity)
    source = single_chunk_source(member)
    pairs_seen = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(body, start, end),
                {
                    "raw_span": {"start": start, "end": end, "text": value},
                    "null_margin": -3.0,
                },
            )
        ]

    async def ni(pairs, **kwargs):
        pairs_seen.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            if ni_supported
            else SupportAssessment("neutral", (-3.0, 0.0, 3.0), -3.0, False, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return source

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", ni)
    config = Settings(
        GENERATION_MODE="extractive",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v4",
        QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1",
        REQUEST_PARSER_MODE="local_dependency",
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
    )
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement,
        [member],
        config,
        candidates,
        resolve_source=resolve,
        request_plan=plan,
    )
    assert pairs_seen
    assert all(requirement.attribute in p.hypothesis for p in pairs_seen)
    assert all(value in p.premise for p in pairs_seen)
    assert bool(found) is ni_supported
    if ni_supported:
        from app.services import contextual_mixed_output as output

        from tests.planning_library_unit830.test_support import metadata

        candidate = next(c for c in candidates if c.get("decision") == "supported")
        snapshot = {
            **source.identity,
            "body": body,
            "metadata": source.metadata,
            "chunks": [{"id": str(member.id), "index": 0, "content": body}],
        }
        chunks, _ = output.factual._source_inventory(
            {str(member.document_id): snapshot}
        )
        chunks[str(member.id)]["source"].metadata = source.metadata
        settings = {
            "evidence_profile": recorded_evidence_policy(
                json.loads(plan.evidence_profile_json)
            ).record(),
            "support": metadata(),
        }
        descriptor, supported, _, _ = output._fact_assessment(
            requirement, candidate, candidate["proposal"], chunks, settings, plan
        )
        assert supported
        assert descriptor["span"]["text"] == found[0].span.text
