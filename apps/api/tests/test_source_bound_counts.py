"""Retained actual parser/QA inputs, UNITONLY NLI; no new model-quality claim."""

import hashlib
import json
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from app.config import Settings
from app.evidence_policy import EvidencePolicy, recorded_evidence_policy
from app.models.chunk import ChunkWithScore
from app.models.query import AnswerSpan
from app.services import request_parser, requirement_answers
from app.services.answer_reader import ReaderSelection, reader_service
from app.services.answer_support import SupportAssessment, support_service
from app.services.count_runtime import capture_count, count_identity, reconstruct_count
from app.services.linguistic_requirements import plan_request
from app.services.literal_quantity import QuantityUnresolved, compile_quantity_binding
from app.services.procedure_evidence import single_chunk_source
from app.services.request_parser import make_capture, validate_capture

from tests.test_linguistic_reading_profile import CONTROLS


def fixture():
    return json.loads(
        (Path(__file__).parent / "fixtures/count_source_captures_v736.json").read_text(
            encoding="utf8"
        )
    )


def requirement(data):
    return plan_request(data["question"], data["request_plan_capture"]).requirements[0]


def chunk(body):
    return ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=body,
        chunk_index=0,
        relevance_score=1.0,
        metadata={
            "document_version": 1,
            "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        },
    )


def config():
    return Settings(
        **CONTROLS,
        REQUEST_PARSER_MODE="local_dependency",
        QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1",
        SUPPORT_MIN_MARGIN=2,
        READER_NULL_THRESHOLD=4,
    )


def test_legacy_policy_serialization_is_unchanged_and_new_policy_cannot_downgrade():
    legacy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v2",
    )
    before = legacy.record()
    assert before["contract"] == "evidence-profile-v6"
    assert "quantity_verification_profile" not in before
    strict = replace(legacy, quantity_verification_profile="literal_source_count_v1")
    assert strict.record()["contract"] == "evidence-profile-v7"
    assert strict.output_contract == "procedure-output-cover-v7"
    assert recorded_evidence_policy(strict.record()) == strict
    stripped = deepcopy(strict.record())
    stripped.pop("quantity_verification_profile")
    assert recorded_evidence_policy(stripped).record() != stripped
    with pytest.raises(ValueError):
        replace(strict, quantity_verification_profile="made_up")
    with pytest.raises(ValueError):
        replace(strict, evidence_reading_profile="clause_bound_v1")
    with pytest.raises(ValueError):
        Settings(QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1")


async def test_count_field_runs_before_NLI_and_same_field_origins_do_not_conflict(
    monkeypatch,
):
    data = fixture()
    req = requirement(data)
    good = chunk("There are 4 tokens assigned to Copper alignment.")
    bad = chunk(data["actual_bad_candidate"]["whole_source_support"]["premise"])
    observed = {o["span"]["text"]: o for o in data["qa_observations"]}

    async def parse(text, settings):
        assert text in data["captures"]
        return deepcopy(data["captures"][text])

    async def qa(question, contents, config):
        assert question == req.question
        return [
            ReaderSelection(
                AnswerSpan(**observed[body]["span"]),
                deepcopy(observed[body]["diagnostics"]),
            )
            for body in contents
        ]

    assessed = []

    async def assess(pairs, config):
        assessed.extend(pairs)
        # Deliberately willing to accept anything, including the old wrong unit.
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 32)
            for p in pairs
        ]

    monkeypatch.setattr(request_parser, "capture_async", parse)
    monkeypatch.setattr(reader_service, "select_atomic", qa)
    monkeypatch.setattr(
        reader_service,
        "metadata",
        lambda config=None: deepcopy(data["reader_metadata"]),
    )
    monkeypatch.setattr(support_service, "assess", assess)

    async def resolve(member):
        return single_chunk_source(member)

    candidates = []
    witnesses = await requirement_answers._find_witnesses(
        req, [good, bad], config(), candidates, resolve_source=resolve
    )
    assert {w.value for w in witnesses} == {"4", "4 tokens"}
    assert len({count_identity(w.quantity_binding) for w in witnesses}) == 1
    assert assessed and all("7 minutes" not in p.hypothesis for p in assessed)
    assert any(
        c.get("raw_span", {}).get("text") == "7 minutes"
        or c.get("decision") == "whole_literal_count_relation_unresolved"
        for c in candidates
    )
    assert all(
        c.get("support") is None
        for c in candidates
        if c.get("decision") == "whole_literal_count_relation_unresolved"
    )
    for witness in witnesses:
        raw = witness.proposals[0]["chunk_range"]
        claim, proof = reconstruct_count(
            witness.quantity_binding, req, single_chunk_source(good), good, raw
        )
        assert claim.value == witness.value and proof == witness.quantity_binding


@pytest.mark.parametrize(
    "mutation",
    [
        "value",
        "offset",
        "source_version",
        "source_hash",
        "method",
        "capture",
        "request",
    ],
)
async def test_proof_reconstructs_against_actual_sources_and_request(
    monkeypatch, mutation
):
    data = fixture()
    req = requirement(data)
    member = chunk("There are 4 tokens assigned to Copper alignment.")
    source = single_chunk_source(member)

    async def parse(text, config):
        return deepcopy(data["captures"][text])

    monkeypatch.setattr(request_parser, "capture_async", parse)
    raw = {"start": 10, "end": 11}
    _, record = await capture_count(req, source, member, raw, config())
    altered = deepcopy(record)
    if mutation == "value":
        altered["binding"]["canonical_value"]["number"] = "7"
    elif mutation == "offset":
        raw = {"start": 10, "end": 18}
    elif mutation == "source_version":
        source.identity["document_version"] = 2
    elif mutation == "source_hash":
        source.identity["content_hash"] = "0" * 64
    elif mutation == "method":
        altered["binding"]["method"] = "model_confidence"
    elif mutation == "capture":
        altered["request_capture"]["annotation"]["tokens"][7]["head"] = 1
    else:
        req = replace(req, attribute="minute count")
    with pytest.raises(ValueError):
        reconstruct_count(altered, req, source, member, raw)


def test_actual_positive_NLI_does_not_establish_the_wrong_attribute():
    data = fixture()
    req = requirement(data)
    bad = data["actual_bad_candidate"]
    assert (
        bad["support"]["supported"]
        and bad["support"]["entailment_margin"] == 3.891302950680256
    )
    with pytest.raises(QuantityUnresolved):
        compile_quantity_binding(
            req,
            bad["whole_source_support"]["premise"],
            bad["raw_span"]["start"],
            bad["raw_span"]["end"],
            source_identity=bad["whole_source_support"]["source_identity"],
        )


def _unitonly_second_count(raw, data, *, foreign_parent=False):
    """Coherent synthetic graph; never represented as a new model observation."""
    annotation = deepcopy(data["captures"][raw]["annotation"])
    text = raw.replace("Copper", "count ")
    annotation["raw_text"] = text
    annotation["raw_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    for token in annotation["tokens"]:
        if token["text"] == "Copper":
            token.update(
                text="count", end=token["start"] + 5, whitespace="  ", lemma="count"
            )
    if foreign_parent:
        annotation["tokens"][7]["head"] = 1
        annotation["tokens"][1]["children"].append(7)
        annotation["tokens"][8]["children"].remove(7)
    annotation["sentences"][0]["text"] = text
    cover, at = [], 0
    for token in annotation["tokens"]:
        if at < token["start"]:
            cover.append(
                {
                    "start": at,
                    "end": token["start"],
                    "kind": "raw-gap",
                    "text": text[at : token["start"]],
                }
            )
        cover.append(
            {
                "start": token["start"],
                "end": token["end"],
                "kind": "raw-token",
                "text": text[token["start"] : token["end"]],
            }
        )
        at = token["end"]
    if at < len(text):
        cover.append(
            {"start": at, "end": len(text), "kind": "raw-gap", "text": text[at:]}
        )
    annotation["lossless_input_cover"] = cover
    capture = make_capture(annotation)
    validate_capture(text, capture)
    return text, capture


@pytest.mark.parametrize("foreign_parent", [False, True])
def test_count_label_cannot_bind_to_another_count_in_the_namespace(foreign_parent):
    data = fixture()
    req = requirement(data)
    question, request_capture = _unitonly_second_count(
        req.question, data, foreign_parent=foreign_parent
    )
    body, source_capture = _unitonly_second_count(
        "There are 4 tokens assigned to Copper alignment.", data
    )
    req = replace(req, question=question, topic="count alignment")
    identity = {
        "document_id": "UNITONLY",
        "document_version": 1,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }
    options = {
        "source_identity": identity,
        "request_capture": request_capture,
        "source_capture": source_capture,
    }
    if foreign_parent:
        with pytest.raises(QuantityUnresolved, match="source_counted_np_mismatch"):
            compile_quantity_binding(
                req, body, body.index("4"), body.index("4") + 1, **options
            )
    else:
        proof = compile_quantity_binding(
            req, body, body.index("4"), body.index("4") + 1, **options
        )
        assert (
            proof["counted_np_alignment"]["declared"]["method"]
            == "captured_field_label_to_source_lemma_v1"
        )
