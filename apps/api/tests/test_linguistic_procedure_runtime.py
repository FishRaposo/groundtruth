"""UNITONLY model/consumer doubles, real proposal and exact-copy wiring."""

import pytest
from app.evidence_policy import reading_version, source_copy_version
from app.models.query import QueryRequest
from app.services import procedure_evidence, request_parser, requirement_answers
from app.services.answer_reader import ReaderSelection
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import single_chunk_source

from tests.test_composite_procedures import chunk
from tests.test_dependency_frames import planned
from tests.test_linguistic_runtime_dispatch import config


@pytest.mark.parametrize("supported", [True, False])
async def test_explicit_composite_procedure_uses_full_source_nli_and_copy_guard(
    monkeypatch, supported
):
    from app.services import contextual_source_proof, linguistic_procedure_runtime

    plan = planned("e628-request-order")
    requirement = plan.requirements[1]
    body = (
        "The following instructions govern the standard Zinc review routine only, "
        "including references that omit the activity name. "
        "First, inspect the counter. Do not reset it until readings are stored."
    )
    member = chunk(body)
    source = single_chunk_source(member)
    calls = []

    async def resolve(*args, **kwargs):
        return source

    async def qa(*args, **kwargs):
        return [ReaderSelection(None, {"decision": "no_answer", "null_margin": 9.0})]

    async def capture(text, settings):
        calls.append(("syntax_capture", text))
        return {"UNITONLY": "source scope proof is independently tested"}

    def envelope(text, identity, subject, request_plan, windows, *, source_copy_policy):
        assert request_plan is plan and windows[0]["start"] == 0
        assert (
            source_copy_policy
            == source_copy_version(reading_profile="contextual_source_v2").policy
        )
        return {
            "contract": reading_version("contextual_source_v2").procedure,
            "source_identity": identity,
            "source_body": text,
            "literal_scope": {
                "disclosure": "Source-declared scope: standard Zinc review routine."
            },
            "nli_obligations": [
                {
                    "name": name,
                    "premise": text,
                    "hypothesis": f"This routine {verb} {subject}.",
                    "source_range": {"start": 0, "end": len(text)},
                }
                for name, verb in [
                    ("namespace", "is for"),
                    ("applicability", "applies to"),
                ]
            ],
        }

    async def nli(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (0.0, 5.0, 0.0), 5.0, True, 64)
            if supported
            else SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 64)
            for _ in pairs
        ]

    async def current(_):
        return True

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(linguistic_procedure_runtime, "resolve_version", resolve)
    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    monkeypatch.setattr(request_parser, "capture_async", capture)
    monkeypatch.setattr(contextual_source_proof, "build_envelope", envelope)
    candidates = []
    inspected = {member.id: member}
    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=plan.question),
        None,
        requirement,
        config(),
        candidates,
        inspected,
        [],
        current,
        request_plan=plan,
        source_window_cache={},
    )
    assert bool(found) is supported
    records = [
        c["source_guard_record"] for c in candidates if "source_guard_record" in c
    ]
    assert len(records) == 1
    assert len(records[0]["nli_assessments"]) == 2
    assert records[0]["nli_assessments"][0]["assessment"]["supported"] is supported
    assert all(p.premise == body for p in calls if hasattr(p, "premise"))
    if supported:
        assert found[0].value == body
        assert "Do not reset" in found[0].value
        assert found[0].completeness["method"] == "consumer_envelope"
        assert found[0].proposals[0]["origin"] == "source_pattern"
