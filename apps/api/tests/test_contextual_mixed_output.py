"""UNITONLY model protocol fixtures, never inference or application acceptance.

The default consumer composition uses a retained engineering request capture;
its source graphs and all NLI scores are explicitly synthetic UNITONLY records.
"""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.evidence_policy import EvidencePolicy, reading_version  # noqa: E402
from app.services import contextual_mixed_output as output  # noqa: E402
from app.services.answer_requirements import Requirement, plan_requirements  # noqa: E402
from app.services.evidence_proposals import QAObservation, make_proposal  # noqa: E402
from app.services.source_pattern_grammar import collect_source_proposals  # noqa: E402

from tests.test_contextual_output import fixture as old_fixture  # noqa: E402

PROFILE = "contextual_source_v2"
PROC_BODY = (
    "This complete procedure applies to ordinary Larch transfers. "
    "Verify the approval. Copy the identifier onto the register. "
    "Never reopen the register."
)
PROC_QUESTION = "Give the complete ordered method for ordinary Larch transfers."


def mirror(data):
    data["query_context"]["provenance"]["answer_selection"] = deepcopy(
        data["selection"]
    )


def produce(data):
    return output.build_output(
        data["selection"],
        **{
            k: v
            for k, v in data.items()
            if k not in {"selection", "answer", "citations"}
        },
    )


def reconstruct(data):
    return output.reconstruct_certificate(
        data["selection"], **{k: v for k, v in data.items() if k != "selection"}
    )


def unit_guard(selection, requirement, snapshot, request_plan):
    return {
        "status": "discharged",
        "fixture_kind": "UNITONLY_consumer_guard",
        "requirement_id": requirement.id,
        "document_id": snapshot["document_id"],
        "body_sha256": hashlib.sha256(snapshot["body"].encode()).hexdigest(),
        "actual_question": request_plan.record()["question"],
    }


def manual_plan(data, requirements, question, *, extra=None):
    record = dict(
        contract=reading_version(PROFILE).request_plan,
        question=question,
        requirements=[asdict(r) for r in requirements],
        unresolved=[],
        resolved_request=True,
        fixture_kind="UNITONLY_manual_plan",
        **(extra or {}),
    )

    def callback(actual, context):
        if actual != question:
            raise ValueError("UNITONLY actual-question mismatch")
        return SimpleNamespace(
            requirements=requirements,
            question=question,
            uses=(),
            record=lambda: deepcopy(record),
            resolved_request=True,
        )

    data["question"] = question
    data["selection"]["request_plan"] = deepcopy(record)
    data["request_reconstructor"] = callback


def whole(candidate, snapshot):
    return {
        "contract": "whole-source-fact-support-v1",
        "verification_method": "nli_entailment",
        "requirement_id": candidate["requirement_id"],
        "source_identity": {
            k: snapshot[k]
            for k in ("document_id", "document_version", "content_hash", "workspace_id")
        },
        "source_range": {"start": 0, "end": len(snapshot["body"])},
        "premise": snapshot["body"],
        "hypothesis": candidate["hypothesis"],
        "assessment": deepcopy(candidate["support"]),
    }


def fixture(*args, **kwargs):
    data = old_fixture(*args, **kwargs)
    selection = data["selection"]
    selection["contract"] = reading_version(PROFILE).requirement
    selection["evidence_profile"] = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        PROFILE,
    ).record()
    requirements = plan_requirements(
        data["question"], reading_profile="contextual_source_v1"
    )
    manual_plan(
        data,
        requirements,
        data["question"],
        extra={"new_unknown_field": {"preserve": "whole-record"}},
    )
    selection["pattern_observations"] = []
    for candidate in selection["candidates"]:
        candidate["whole_source_support"] = whole(
            candidate, data["source_snapshots"][candidate["document_id"]]
        )
    data["source_guard_reconstructor"] = unit_guard
    mirror(data)
    return data


def observed_proposal(selection, req, source, chunk, start, end):
    value = chunk.content[start:end]
    payload = json.dumps(
        {
            "span": {"start": start, "end": end, "text": value},
            "diagnostics": {
                "raw_candidates": [
                    {"start": start, "end": end, "text": value, "null_margin": -3.0}
                ]
            },
            "question": req.question,
            "reader": deepcopy(selection["qa_observations"][0]["reader"]),
        },
        sort_keys=True,
        allow_nan=False,
    )
    observed = QAObservation(
        hashlib.sha256(f"{req.id}:{chunk.id}:{payload}".encode()).hexdigest(),
        req.id,
        chunk.id,
        payload,
    )
    return observed, make_proposal(
        req.id, source, chunk, start, end, origin="qa_reader", observation=observed
    ).record()


def mixed_fixture(body=PROC_BODY):
    data = fixture()
    selection = data["selection"]
    first = plan_requirements(data["question"], reading_profile="contextual_source_v1")[
        0
    ]
    question = data["question"] + " " + PROC_QUESTION
    req = Requirement(
        "r2",
        PROC_QUESTION,
        len(data["question"]) + 1,
        len(question),
        PROC_QUESTION,
        "procedure",
        "ordinary Larch transfers",
        ("Larch",),
    )
    manual_plan(data, (first, req), question)
    doc = "00000000-0000-0000-0000-000000000002"
    chunk = "10000000-0000-0000-0000-000000000002"
    identity = {
        "document_id": doc,
        "document_version": 3,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "workspace_id": None,
    }
    member = {
        k: identity[k] for k in ("document_id", "document_version", "content_hash")
    }
    member["chunk_id"] = chunk
    snapshot = dict(
        **identity,
        body=body,
        chunks=[{"id": chunk, "index": 0, "content": body}],
        metadata={},
    )
    data["source_snapshots"][doc] = snapshot
    c = SimpleNamespace(id=chunk, document_id=doc, content=body, metadata=identity)
    source = SimpleNamespace(
        body=body,
        identity=identity,
        chunks=(SimpleNamespace(chunk=c, start=0, end=len(body)),),
        metadata={},
        captured_scope=None,
    )
    left = body.index("Verify the approval.")
    right = left + len("Verify the approval.")
    observed, proposal = observed_proposal(selection, req, source, c, left, right)
    patterns = [
        p.record()
        for p in collect_source_proposals(
            req, [source], reading_profile=PROFILE
        ).proposals
    ]
    proof = output.procedure_obligations(req, source, proposal)
    for unit in proof["proof_units"]:
        if unit["verification_method"] == "nli_entailment":
            unit.update(deepcopy(selection["candidates"][0]["support"]))
    candidate = dict(
        **member,
        requirement_id=req.id,
        origin="qa_reader",
        proposal=proposal,
        duplicate_proposals=patterns,
        raw_span={"start": left, "end": right},
        null_margin=-3.0,
        decision="supported",
        procedure_completeness=proof,
    )
    witness = dict(
        **member,
        value=body,
        span={"start": 0, "end": len(body), "text": body},
        document_range={"start": 0, "end": len(body)},
        entailment_margin=5.0,
        proof_edges=[],
        proposals=[proposal, *patterns],
        procedure_completeness=proof,
    )
    row = {
        "id": req.id,
        "kind": req.kind,
        "original_text": req.original_text,
        "input_range": {"start": req.input_start, "end": req.input_end},
        "prepared_question": req.question,
        "source_workspace": None,
        "depends_on": [],
        "status": "supported",
        "witnesses": [witness],
        "procedure_completeness": proof,
    }
    selection["requirements"].append(row)
    selection["candidates"].append(candidate)
    selection["proposals"].extend([proposal, *patterns])
    selection["qa_observations"].append(observed.record())
    selection["selected_proposal_ids"].extend(
        p["proposal_id"] for p in [proposal, *patterns]
    )
    selection["inspected_sources"].append(member)
    mirror(data)
    return data


def test_pure_producer_and_independent_replay_bind_actual_factual_output():
    data = fixture()
    actual = produce(data)
    assert actual["answer"] == data["answer"]
    assert actual["citations"] == data["citations"]
    assert actual["certificate"]["contract"] == reading_version(PROFILE).output
    assert actual["certificate"]["request_plan"]["new_unknown_field"] == {
        "preserve": "whole-record"
    }
    assert reconstruct(data) == actual["certificate"]


@pytest.mark.parametrize(
    "change",
    [
        "answer",
        "source_version",
        "source_body",
        "request_field",
        "retained_capture",
        "raw_range",
        "nli_logits",
        "nli_batch_float",
        "citation",
    ],
)
def test_actual_output_and_model_source_request_tampering_refuses(change):
    data = fixture()
    if change == "answer":
        data["answer"] += " invented answer"
    elif change == "source_version":
        next(iter(data["source_snapshots"].values()))["document_version"] += 1
    elif change == "source_body":
        next(iter(data["source_snapshots"].values()))["body"] += " tail"
    elif change == "request_field":
        data["selection"]["request_plan"]["new_unknown_field"] = {}
        mirror(data)
    elif change == "retained_capture":
        data["query_context"]["provenance"]["answer_selection"]["threshold"] = 3.0
    elif change == "raw_range":
        data["selection"]["proposals"][0]["chunk_range"]["start"] = True
        mirror(data)
    elif change == "nli_logits":
        data["selection"]["candidates"][0]["support"]["logits"][1] = 0.0
        mirror(data)
    elif change == "nli_batch_float":
        data["selection"]["evidence_support"]["batch_size"] = 8.0
        mirror(data)
    else:
        data["citations"][0]["answer_spans"][0]["end"] -= 1
    with pytest.raises(ValueError):
        reconstruct(data)


def test_missing_or_pending_source_guard_never_becomes_a_publication_success():
    data = fixture()
    data["source_guard_reconstructor"] = None
    assert (
        produce(data)["certificate"]["source_guards"][0]["consumer_proof"]["method"]
        == "whole_source_fact_support"
    )
    data["source_guard_reconstructor"] = lambda *args: {"status": "pending"}
    with pytest.raises(output.PendingConsumerProof):
        produce(data)


def test_v2_fact_requires_actual_whole_source_model_input_before_acceptance():
    data = fixture()
    for candidate in data["selection"]["candidates"]:
        candidate.pop("whole_source_support", None)
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_whole_procedure_plus_fact_preserves_both_origins_and_all_instruction_text():
    data = mixed_fixture()
    actual = produce(data)
    assert (
        PROC_BODY in actual["answer"]
        and "Never reopen the register." in actual["answer"]
    )
    procedure = next(
        g
        for g in actual["certificate"]["assessed_inventory"]
        if g["requirement_id"] == "r2"
    )
    assert {p["origin"] for p in procedure["origins"]} == {
        "qa_reader",
        "source_pattern",
    }
    data.update(answer=actual["answer"], citations=actual["citations"])
    assert reconstruct(data) == actual["certificate"]


@pytest.mark.parametrize(
    "mutation",
    [
        "instruction",
        "order",
        "citation_order",
        "inventory_tail",
        "row_inventory",
        "source_version",
        "exact_model_fields",
    ],
)
def test_actual_procedure_inventory_answer_citations_are_rebuilt(mutation):
    data = mixed_fixture()
    actual = produce(data)
    data.update(answer=actual["answer"], citations=actual["citations"])
    if mutation == "instruction":
        data["answer"] = data["answer"].replace("Never reopen the register.", "")
    elif mutation == "order":
        data["answer"] = data["answer"].replace(
            "Verify the approval. Copy the identifier onto the register.",
            "Copy the identifier onto the register. Verify the approval.",
        )
    elif mutation == "citation_order":
        data["citations"].reverse()
    elif mutation == "inventory_tail":
        data["selection"]["requirements"][1]["witnesses"][0]["procedure_completeness"][
            "inventory"
        ]["ordered_ranges"].pop()
        mirror(data)
    elif mutation == "row_inventory":
        data["selection"]["requirements"][1]["procedure_completeness"] = deepcopy(
            data["selection"]["requirements"][1]["procedure_completeness"]
        )
        data["selection"]["requirements"][1]["procedure_completeness"]["inventory"][
            "source_body"
        ] = "forged"
        mirror(data)
    elif mutation == "source_version":
        data["source_snapshots"]["00000000-0000-0000-0000-000000000002"][
            "document_version"
        ] += 1
    else:
        unit = next(
            u
            for u in data["selection"]["candidates"][1]["procedure_completeness"][
                "proof_units"
            ]
            if u["verification_method"] == "exact_source_copy"
        )
        unit["logits"] = [0, 5, 0]
        mirror(data)
    with pytest.raises(ValueError):
        reconstruct(data)


def test_selected_fragments_bind_exact_actual_answer_ranges():
    actual = produce(mixed_fixture())
    for fragment in actual["certificate"]["selected_fragments"]:
        offset = fragment["answer_range"]
        assert actual["answer"][offset["start"] : offset["end"]] == fragment["text"]


def dependency_fixture():
    from app.services.linguistic_dependencies import resolve_linguistic_requirement
    from app.services.requirement_binding import support_claim

    data = fixture(
        "Who owns the Copper check?",
        ("The owner of the Copper check is the records steward.",),
        ("the records steward",),
    )
    selection = data["selection"]
    first = plan_requirements(data["question"], reading_profile="contextual_source_v1")[
        0
    ]
    original = "What is that role's availability?"
    question = data["question"] + " " + original
    req = Requirement(
        "r2",
        original,
        len(data["question"]) + 1,
        len(question),
        original,
        "availability",
        "that role",
        (),
        depends_on=("r1",),
        relation="availability",
        attribute="availability",
    )
    manual_plan(data, (first, req), question)
    old_callback = data["request_reconstructor"]
    start = question.index("that role")
    uses = (
        SimpleNamespace(
            requirement_id="r2",
            references=(SimpleNamespace(start=start, end=start + 9, text="that role"),),
        ),
    )

    def callback(actual, context):
        plan = old_callback(actual, context)
        plan.uses = uses
        return plan

    data["request_reconstructor"] = callback
    effective, binding = resolve_linguistic_requirement(
        req, callback(question, {}), {"r1": "the records steward"}
    )
    body = "The records steward is available from 09:00 to 11:00."
    value = "09:00 to 11:00"
    doc = "00000000-0000-0000-0000-000000000002"
    chunk = "10000000-0000-0000-0000-000000000002"
    identity = {
        "document_id": doc,
        "document_version": 3,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }
    snapshot = dict(
        **identity,
        workspace_id=None,
        body=body,
        chunks=[{"id": chunk, "index": 0, "content": body}],
        metadata={},
    )
    data["source_snapshots"][doc] = snapshot
    member = dict(**identity, chunk_id=chunk)
    c = SimpleNamespace(id=chunk, document_id=doc, content=body, metadata=identity)
    source = SimpleNamespace(
        body=body,
        identity=identity,
        chunks=[SimpleNamespace(chunk=c, start=0, end=len(body))],
    )
    a = body.index(value)
    b = a + len(value)
    observed, proposal = observed_proposal(selection, effective, source, c, a, b)
    claim = support_claim(effective, body, a, b, reading_profile=PROFILE)
    assert not claim.rejection and not claim.checks and not claim.proof_edges
    assessment = deepcopy(selection["candidates"][0]["support"])
    span = {
        "start": claim.support_start,
        "end": claim.support_end,
        "text": body[claim.support_start : claim.support_end],
    }
    candidate = dict(
        **member,
        requirement_id=req.id,
        origin="qa_reader",
        proposal=proposal,
        raw_span={"start": a, "end": b},
        null_margin=-3.0,
        hypothesis=claim.hypothesis,
        validated_answer_span={
            "start": claim.start,
            "end": claim.end,
            "text": claim.value,
        },
        condition="applies",
        decision="supported",
        primary_support_range={"start": claim.premise_start, "end": claim.premise_end},
        proof_edges=[],
        support=assessment,
        support_checks=[],
    )
    candidate["whole_source_support"] = whole(candidate, snapshot)
    witness = dict(
        **member,
        value=claim.value,
        span=span,
        document_range={"start": span["start"], "end": span["end"]},
        entailment_margin=5.0,
        proof_edges=[],
        proposals=[proposal],
    )
    row = {
        "id": req.id,
        "kind": req.kind,
        "original_text": req.original_text,
        "input_range": {"start": req.input_start, "end": req.input_end},
        "prepared_question": effective.question,
        "source_workspace": None,
        "depends_on": ["r1"],
        "status": "supported",
        "witnesses": [witness],
        "dependency_binding": binding,
    }
    selection["requirements"].append(row)
    selection["candidates"].append(candidate)
    selection["qa_observations"].append(observed.record())
    selection["proposals"].append(proposal)
    selection["inspected_sources"].append(member)
    selection["selected_proposal_ids"].append(proposal["proposal_id"])
    mirror(data)
    return data


def test_dependency_replays_from_prior_selected_value_and_preserves_original_plan():
    actual = produce(dependency_fixture())
    effective = actual["certificate"]["effective_requirements"][1]
    assert (
        effective["dependency_binding"]["bindings"][0]["source_value"]
        == "the records steward"
    )
    assert (
        effective["requirement"]["question"]
        == "What is the records steward's availability?"
    )
    assert effective["requirement"]["kind"] == "availability"
    assert (
        actual["certificate"]["request_plan"]["requirements"][1]["question"]
        == "What is that role's availability?"
    )


@pytest.mark.parametrize(
    "mutation",
    ["unknown_request", "wrong_question", "forged_null", "duplicate_observation"],
)
def test_unselected_qa_observations_are_rebuilt_before_filtering(mutation):
    data = fixture()
    selection = data["selection"]
    observed = deepcopy(selection["qa_observations"][0])
    observed["span"] = None
    observed["diagnostics"] = {"raw_candidates": []}
    if mutation == "unknown_request":
        observed["requirement_id"] = "unknown"
    elif mutation == "wrong_question":
        observed["question"] = "An unasked question?"
    elif mutation == "forged_null":
        observed["diagnostics"]["raw_candidates"] = [
            {"start": True, "end": 999, "text": "forged", "null_margin": -3.0}
        ]
    payload = json.dumps(
        {k: observed[k] for k in ("span", "diagnostics", "question", "reader")},
        sort_keys=True,
        allow_nan=False,
    )
    observed["observation_id"] = hashlib.sha256(
        f"{observed['requirement_id']}:{observed['chunk_id']}:{payload}".encode()
    ).hexdigest()
    selection["qa_observations"].append(observed)
    if mutation == "duplicate_observation":
        selection["qa_observations"].append(deepcopy(observed))
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def consumer_fixture():
    from app.services.contextual_source_proof import (
        build_envelope,
        reconstruct_source_guard,
    )

    from tests.test_contextual_source_proof import fixture as source_fixture

    data = fixture()
    selection = data["selection"]
    body, identity, windows, plan, snapshot = source_fixture()
    identity["document_id"] = "00000000-0000-0000-0000-000000000003"
    snapshot.update(identity)
    chunk = "10000000-0000-0000-0000-000000000003"
    snapshot["chunks"][0]["id"] = chunk
    data["source_snapshots"] = {identity["document_id"]: snapshot}
    data["question"] = plan.question
    req = plan.requirements[0]
    selection["request_plan"] = plan.record()
    records = json.loads(
        (Path(__file__).parent / "fixtures/dependency_graphs_v634.json").read_text(
            encoding="utf-8"
        )
    )["captures"]
    selection["request_capture"] = next(
        c["capture"]
        for c in records
        if c["capture"]["annotation"]["raw_text"] == plan.question
    )
    data["request_reconstructor"] = None
    data["source_guard_reconstructor"] = None
    inventory = build_envelope(body, identity, req.topic, plan, windows)
    assessment = deepcopy(selection["candidates"][0]["support"])
    selection["source_guard_records"] = [
        {
            "requirement_id": req.id,
            "source_identity": identity,
            "requested_subject": req.topic,
            "source_windows": windows,
            "envelope_inventory": inventory,
            "nli_assessments": [
                {**o, "assessment": deepcopy(assessment)}
                for o in inventory["nli_obligations"]
            ],
        }
    ]
    member = {
        k: identity[k] for k in ("document_id", "document_version", "content_hash")
    }
    member["chunk_id"] = chunk
    selection["inspected_sources"] = [member]
    chunks, documents, sources = output._sources(data["source_snapshots"], selection)
    batch = collect_source_proposals(req, sources, reading_profile=PROFILE)
    proposal = batch.proposals[0].record()
    selection["proposals"] = [proposal]
    selection["pattern_observations"] = list(batch.observations)
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    proof = output.procedure_obligations(
        req,
        sources[0],
        proposal,
        method="consumer_envelope",
        consumer_inventory=guard["envelope_inventory"],
    )
    witness = dict(
        **member,
        value=body,
        span={"start": 0, "end": len(body), "text": body},
        document_range={"start": 0, "end": len(body)},
        entailment_margin=guard["entailment_margin"],
        proof_edges=[],
        proposals=[proposal],
        procedure_completeness=proof,
    )
    selection["requirements"] = [
        {
            "id": req.id,
            "kind": req.kind,
            "original_text": req.original_text,
            "input_range": {"start": req.input_start, "end": req.input_end},
            "prepared_question": req.question,
            "source_workspace": None,
            "depends_on": [],
            "status": "supported",
            "witnesses": [witness],
            "procedure_completeness": proof,
        }
    ]
    selection["candidates"] = [
        dict(
            **member,
            requirement_id=req.id,
            origin="source_pattern",
            proposal=proposal,
            raw_span=proposal["chunk_range"],
            null_margin=None,
            decision="supported",
            procedure_completeness=proof,
        )
    ]
    selection["qa_observations"] = []
    selection["selected_proposal_ids"] = [proposal["proposal_id"]]
    mirror(data)
    return data


def test_default_request_and_actual_source_consumer_compose_without_models():
    data = consumer_fixture()
    actual = produce(data)
    guard = actual["certificate"]["source_guards"][0]["consumer_proof"]
    assert guard["method"] == "consumer_envelope" and guard["supported"] is True
    assert "Frobnicate the token." in actual["answer"]
    assert (
        actual["certificate"]["assessed_inventory"][0]["descriptor"][
            "procedure_completeness"
        ]["proof_units"]
        == []
    )
    data.update(answer=actual["answer"], citations=actual["citations"])
    assert reconstruct(data) == actual["certificate"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_assessment",
        "invented_supported",
        "raw_body",
        "guard_inventory",
        "capture_question",
        "empty_proof_positive",
    ],
)
def test_actual_consumer_inputs_cannot_be_replaced_by_a_producer_guard(mutation):
    data = consumer_fixture()
    row = data["selection"]["source_guard_records"][0]
    if mutation == "missing_assessment":
        row["nli_assessments"].pop()
    elif mutation == "invented_supported":
        row["nli_assessments"][0]["assessment"]["supported"] = False
    elif mutation == "raw_body":
        row["nli_assessments"][0]["premise"] += " forged"
    elif mutation == "guard_inventory":
        row["envelope_inventory"]["ordered_ranges"].pop()
    elif mutation == "capture_question":
        data["selection"]["request_capture"]["annotation"]["raw_text"] += "?"
    else:
        for assessed in row["nli_assessments"]:
            assessed["assessment"].update(
                label="neutral",
                logits=[-1.0, 0.0, 5.0],
                entailment_margin=-5.0,
                supported=False,
            )
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def two_facts(*, negative=False):
    body = "The Copper check lasts 7 minutes. The Copper check lasts 9 minutes."
    data = fixture(bodies=(body,), values=("7 minutes",))
    other = fixture(bodies=(body,), values=("9 minutes",))
    for key in ("proposals", "qa_observations", "candidates"):
        data["selection"][key].extend(other["selection"][key])
    if negative:
        candidate = data["selection"]["candidates"][1]
        candidate["whole_source_support"]["assessment"].update(
            label="neutral",
            logits=[-1.0, 0.0, 5.0],
            entailment_margin=-5.0,
            supported=False,
        )
        candidate["decision"] = "support_rejected"
    data["source_guard_reconstructor"] = None
    mirror(data)
    return data


def test_unselected_positive_conflict_is_reconstructed_before_selection():
    with pytest.raises(ValueError, match="Conflicting retained"):
        produce(two_facts())


def test_actual_negative_whole_source_candidate_is_retained_without_false_conflict():
    actual = produce(two_facts(negative=True))
    assert [c["supported"] for c in actual["certificate"]["assessed_inventory"]] == [
        True,
        False,
    ]
    assert len(actual["certificate"]["retained_supported_inventory"]) == 1
    assert (
        len(actual["certificate"]["source_guards"][0]["consumer_proof"]["observations"])
        == 2
    )


def role_fixture(*, pattern_only=False):
    data = fixture(
        "Who leads Alder review?",
        ("The archivist leads Alder review.",),
        ("The archivist",),
    )
    selection = data["selection"]
    req = plan_requirements(data["question"], reading_profile="contextual_source_v1")[0]
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    batch = collect_source_proposals(req, sources, reading_profile=PROFILE)
    assert len(batch.proposals) == 1
    pattern = batch.proposals[0].record()
    selection["proposals"].append(pattern)
    selection["pattern_observations"] = list(batch.observations)
    candidate = selection["candidates"][0]
    witness = selection["requirements"][0]["witnesses"][0]
    if pattern_only:
        selection["proposals"] = [pattern]
        selection["qa_observations"] = []
        candidate.update(origin="source_pattern", proposal=pattern, null_margin=None)
        witness["proposals"] = [pattern]
        selection["selected_proposal_ids"] = [pattern["proposal_id"]]
    else:
        candidate["duplicate_proposals"] = [pattern]
        witness["proposals"].append(pattern)
        selection["selected_proposal_ids"].append(pattern["proposal_id"])
    data["source_guard_reconstructor"] = None
    mirror(data)
    return data


@pytest.mark.parametrize("pattern_only", [False, True])
def test_method_distinct_factual_origins_rebuild_one_actual_claim(pattern_only):
    actual = produce(role_fixture(pattern_only=pattern_only))
    origins = actual["certificate"]["assessed_inventory"][0]["origins"]
    assert {p["origin"] for p in origins} == (
        {"source_pattern"} if pattern_only else {"qa_reader", "source_pattern"}
    )
    assert actual["answer"].count("The archivist leads Alder review.") == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_origin",
        "reordered_origin",
        "hypothesis",
        "whole_source_range",
        "whole_source_version",
        "whole_source_logits",
        "dependency_value",
        "dependency_omitted",
    ],
)
def test_shared_fact_and_effective_dependency_inputs_refuse_tampering(mutation):
    data = dependency_fixture() if mutation.startswith("dependency") else role_fixture()
    selection = data["selection"]
    candidate = selection["candidates"][0]
    if mutation == "missing_origin":
        selection["selected_proposal_ids"].pop()
    elif mutation == "reordered_origin":
        selection["requirements"][0]["witnesses"][0]["proposals"].reverse()
    elif mutation == "hypothesis":
        candidate["hypothesis"] += " forged"
    elif mutation == "whole_source_range":
        candidate["whole_source_support"]["source_range"]["end"] -= 1
    elif mutation == "whole_source_version":
        candidate["whole_source_support"]["source_identity"]["document_version"] += 1
    elif mutation == "whole_source_logits":
        candidate["whole_source_support"]["assessment"]["logits"][1] = False
    elif mutation == "dependency_value":
        selection["requirements"][1]["dependency_binding"]["bindings"][0][
            "source_value"
        ] = "the supervisor"
    else:
        selection["requirements"][1].pop("dependency_binding")
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


@pytest.mark.parametrize("documents", [8, 9])
def test_exact_eight_document_citation_budget(documents):
    names = ["Copper", "Alder", "Birch", "Cedar", "Larch", "Onyx", "Quartz", "Willow"]
    question = " ".join(f"How long is the {n} check?" for n in names)
    data = fixture(
        question,
        tuple(f"The {n} check lasts 7 minutes." for n in names),
        ("7 minutes",) * 8,
    )
    if documents == 9:
        selection = data["selection"]
        snapshot = deepcopy(next(iter(data["source_snapshots"].values())))
        doc = "00000000-0000-0000-0000-000000000009"
        chunk = "10000000-0000-0000-0000-000000000009"
        snapshot["document_id"] = doc
        snapshot["chunks"][0]["id"] = chunk
        data["source_snapshots"][doc] = snapshot
        member = {
            k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
        }
        member["chunk_id"] = chunk
        req = data["request_reconstructor"](question, {}).requirements[0]
        c = SimpleNamespace(
            id=chunk, document_id=doc, content=snapshot["body"], metadata=member
        )
        source = SimpleNamespace(
            body=snapshot["body"],
            identity=snapshot,
            chunks=[SimpleNamespace(chunk=c, start=0, end=len(snapshot["body"]))],
        )
        original = selection["proposals"][0]
        observed, proposal = observed_proposal(
            selection,
            req,
            source,
            c,
            original["chunk_range"]["start"],
            original["chunk_range"]["end"],
        )
        candidate = deepcopy(selection["candidates"][0])
        candidate.update(member, proposal=proposal)
        candidate["whole_source_support"] = whole(candidate, snapshot)
        witness = deepcopy(selection["requirements"][0]["witnesses"][0])
        witness.update(member, proposals=[proposal])
        selection["candidates"].append(candidate)
        selection["proposals"].append(proposal)
        selection["qa_observations"].append(observed.record())
        selection["inspected_sources"].append(member)
        selection["selected_proposal_ids"].append(proposal["proposal_id"])
        selection["requirements"][0]["witnesses"].append(witness)
        mirror(data)
        with pytest.raises(ValueError, match="Eight-document"):
            produce(data)
    else:
        assert len(produce(data)["citations"]) == 8


def fragmented_fixture():
    data = mixed_fixture(
        PROC_BODY + " Ã‰pingler le jeton ðŸ§­; retain this unknown instruction."
    )
    selection = data["selection"]
    snapshot = data["source_snapshots"]["00000000-0000-0000-0000-000000000002"]
    body = snapshot["body"]
    cut = body.index("Never reopen")
    second = "10000000-0000-0000-0000-000000000004"
    snapshot["chunks"][0]["content"] = body[:cut]
    snapshot["chunks"].append({"id": second, "index": 1, "content": body[cut - 10 :]})
    member = {
        k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
    }
    selection["inspected_sources"].append(dict(**member, chunk_id=second))
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    source = next(
        s for s in sources if s.identity["document_id"] == snapshot["document_id"]
    )
    req = data["request_reconstructor"](data["question"], {}).requirements[1]
    candidate = selection["candidates"][1]
    witness = selection["requirements"][1]["witnesses"][0]
    proof = output.procedure_obligations(req, source, candidate["proposal"])
    for unit in proof["proof_units"]:
        if unit["verification_method"] == "nli_entailment":
            unit.update(deepcopy(selection["candidates"][0]["support"]))
    candidate["procedure_completeness"] = proof
    witness["procedure_completeness"] = proof
    selection["requirements"][1]["procedure_completeness"] = proof
    witness["span"] = {"start": 0, "end": cut, "text": body[:cut]}
    witness["document_range"] = {"start": 0, "end": cut}
    mirror(data)
    return data


def test_unicode_whole_body_is_copied_once_through_overlapping_chunks():
    data = fragmented_fixture()
    actual = produce(data)
    body = data["source_snapshots"]["00000000-0000-0000-0000-000000000002"]["body"]
    assert actual["answer"].count(body) == 1
    fragments = [
        f
        for f in actual["certificate"]["selected_fragments"]
        if f["requirement_id"] == "r2"
    ]
    assert "".join(f["text"] for f in fragments) == body
    for fragment in fragments:
        offset = fragment["answer_range"]
        assert actual["answer"][offset["start"] : offset["end"]] == fragment["text"]


@pytest.mark.parametrize("mutation", ["tail", "gap", "raw_bool"])
def test_whole_copy_cannot_omit_unrepresented_or_forged_source_ranges(mutation):
    data = fragmented_fixture()
    snapshot = data["source_snapshots"]["00000000-0000-0000-0000-000000000002"]
    if mutation == "tail":
        snapshot["chunks"][1]["content"] = snapshot["chunks"][1]["content"][:-1]
    elif mutation == "gap":
        cut = len(snapshot["chunks"][0]["content"])
        snapshot["chunks"][1]["content"] = snapshot["body"][cut + 1 :]
    else:
        data["selection"]["candidates"][1]["procedure_completeness"]["fragments"][1][
            "document_start"
        ] = True
        mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_default_consumer_negative_procedure_is_replayed_before_positive_filter():
    from app.services.contextual_source_proof import (
        build_envelope,
        reconstruct_source_guard,
    )
    from app.services.linguistic_requirements import plan_request

    data = consumer_fixture()
    selection = data["selection"]
    plan = plan_request(data["question"], selection["request_capture"])
    req = plan.requirements[0]
    snapshot = deepcopy(next(iter(data["source_snapshots"].values())))
    doc = "00000000-0000-0000-0000-000000000004"
    chunk = "10000000-0000-0000-0000-000000000004"
    snapshot["document_id"] = doc
    snapshot["chunks"][0]["id"] = chunk
    data["source_snapshots"][doc] = snapshot
    identity = {
        k: snapshot[k]
        for k in ("document_id", "document_version", "content_hash", "workspace_id")
    }
    member = {
        k: identity[k] for k in ("document_id", "document_version", "content_hash")
    }
    member["chunk_id"] = chunk
    record = deepcopy(selection["source_guard_records"][0])
    record["source_identity"] = identity
    record["envelope_inventory"] = build_envelope(
        snapshot["body"], identity, req.topic, plan, record["source_windows"]
    )
    for row in record["nli_assessments"]:
        row["assessment"].update(
            label="neutral",
            logits=[-1.0, 0.0, 5.0],
            entailment_margin=-5.0,
            supported=False,
        )
    selection["source_guard_records"].append(record)
    selection["inspected_sources"].append(member)
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    source = next(s for s in sources if s.identity["document_id"] == doc)
    proposal = (
        collect_source_proposals(req, [source], reading_profile=PROFILE)
        .proposals[0]
        .record()
    )
    selection["proposals"].append(proposal)
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    proof = output.procedure_obligations(
        req,
        source,
        proposal,
        method="consumer_envelope",
        consumer_inventory=guard["envelope_inventory"],
    )
    selection["candidates"].append(
        dict(
            **member,
            requirement_id=req.id,
            origin="source_pattern",
            proposal=proposal,
            raw_span=proposal["chunk_range"],
            null_margin=None,
            decision="support_rejected",
            procedure_completeness=proof,
        )
    )
    mirror(data)
    actual = produce(data)
    assert [g["supported"] for g in actual["certificate"]["assessed_inventory"]] == [
        True,
        False,
    ]
    assert actual["answer"].count("Frobnicate the token.") == 1
    selection["source_guard_records"][1]["nli_assessments"][0]["assessment"][
        "pair_tokens"
    ] = True
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_recorded_certificate_is_reconstructed_not_accepted_by_its_answer_hash():
    data = consumer_fixture()
    actual = produce(data)
    data.update(answer=actual["answer"], citations=actual["citations"])
    data["selection"][output.CERTIFICATE_FIELD] = actual["certificate"]
    context = {k: v for k, v in data.items() if k != "selection"}
    assert output.verify_output(data["selection"], **context)
    data["selection"][output.CERTIFICATE_FIELD]["source_inventory"].clear()
    assert not output.verify_output(data["selection"], **context)


def test_pattern_only_fact_retains_valid_qa_abstention_observation():
    data = role_fixture(pattern_only=True)
    selection = data["selection"]
    original = fixture(
        "Who leads Alder review?",
        ("The archivist leads Alder review.",),
        ("The archivist",),
    )["selection"]["qa_observations"][0]
    original["span"] = None
    original["diagnostics"] = {"raw_candidates": []}
    payload = json.dumps(
        {k: original[k] for k in ("span", "diagnostics", "question", "reader")},
        sort_keys=True,
        allow_nan=False,
    )
    original["observation_id"] = hashlib.sha256(
        f"{original['requirement_id']}:{original['chunk_id']}:{payload}".encode()
    ).hexdigest()
    selection["qa_observations"] = [original]
    mirror(data)
    assert "The archivist" in produce(data)["answer"]


def test_alternate_copy_method_cannot_bypass_actual_consumer_negative():
    from app.services.linguistic_requirements import plan_request

    data = consumer_fixture()
    selection = data["selection"]
    req = plan_request(data["question"], selection["request_capture"]).requirements[0]
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    proof = output.procedure_obligations(
        req, sources[0], selection["proposals"][0], method="declared_envelope"
    )
    for unit in proof["proof_units"]:
        if unit["verification_method"] == "nli_entailment":
            unit.update(
                deepcopy(
                    selection["source_guard_records"][0]["nli_assessments"][0][
                        "assessment"
                    ]
                )
            )
    selection["candidates"][0]["procedure_completeness"] = proof
    selection["requirements"][0]["procedure_completeness"] = proof
    selection["requirements"][0]["witnesses"][0]["procedure_completeness"] = proof
    for row in selection["source_guard_records"][0]["nli_assessments"]:
        row["assessment"].update(
            label="neutral",
            logits=[-1.0, 0.0, 5.0],
            entailment_margin=-5.0,
            supported=False,
        )
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_direct_helper_paths_block_models_sql_and_runtime_imports():
    # The legacy app.services __init__ is deliberately bypassed by the existing
    # protocol fixture. This is a direct helper purity claim, not package purity.
    script = f"""
import importlib.abc, runpy, sys, types, app
services = types.ModuleType('app.services')
services.__path__ = [{str(Path(__file__).parents[1] / "app/services")!r}]
sys.modules['app.services'] = services
app.services = services
blocked = ('sqlalchemy', 'torch', 'transformers', 'spacy', 'app.db',
           'app.models', 'app.services.request_parser_runtime',
           'app.services.requirement_answers', 'app.services.procedure_evidence',
           'app.services.procedure_support', 'app.services.source_pattern_proposals')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == p or name.startswith(p + '.') for p in blocked):
            raise RuntimeError('Unexpected pure helper dependency: ' + name)
sys.meta_path.insert(0, Guard())
t = runpy.run_path({str(Path(__file__).resolve())!r})
t['produce'](t['consumer_fixture']())
t['produce'](t['role_fixture']())
t['produce'](t['dependency_fixture']())
assert not any(
    name == p or name.startswith(p + '.')
    for name in sys.modules for p in blocked
)
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-c", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_source_callback_receives_inputs_without_derived_presentation_fields():
    data = fixture()

    def guard(selection, requirement, snapshot, plan):
        return {
            **unit_guard(selection, requirement, snapshot, plan),
            "presentation_fields": sorted(set(selection) & output._PRESENTATION),
        }

    data["source_guard_reconstructor"] = guard
    actual = produce(data)
    data.update(answer=actual["answer"], citations=actual["citations"])
    data["selection"][output.CERTIFICATE_FIELD] = actual["certificate"]
    assert reconstruct(data) == actual["certificate"]


@pytest.mark.parametrize("factory", [fixture, consumer_fixture])
def test_actual_api_citation_ui_fields_preserved_but_evidence_core_reconstructed(
    factory,
):
    data = factory()
    actual = produce(data)
    data.update(answer=actual["answer"], citations=deepcopy(actual["citations"]))
    for citation in data["citations"]:
        citation.update(
            document_title="UNITONLY title",
            score=0.125,
            preview="UNITONLY preview",
            score_status="ranked",
            source_status="current",
        )
    before = deepcopy(data["citations"])
    assert reconstruct(data) == actual["certificate"]
    assert data["citations"] == before


def test_actual_source_consumer_scope_disclosure_is_rendered_and_bound():
    data = consumer_fixture()
    actual = produce(data)
    disclosure = actual["certificate"]["source_guards"][0]["consumer_proof"][
        "literal_scope"
    ]["disclosure"]
    assert actual["answer"].endswith(disclosure)
    recorded = actual["certificate"]["disclosures"][0]
    assert recorded["text"] == disclosure
    offset = recorded["answer_range"]
    assert actual["answer"][offset["start"] : offset["end"]] == disclosure
    for fragment in actual["certificate"]["selected_fragments"]:
        offset = fragment["answer_range"]
        assert actual["answer"][offset["start"] : offset["end"]] == fragment["text"]
    data.update(answer=actual["answer"], citations=actual["citations"])
    assert reconstruct(data) == actual["certificate"]
    data["answer"] = data["answer"].removesuffix(disclosure)
    with pytest.raises(ValueError):
        reconstruct(data)


@pytest.mark.parametrize(
    "field",
    [
        "citation_index",
        "chunk_id",
        "document_id",
        "document_version",
        "content_hash",
        "quoted_text",
        "answer_spans",
    ],
)
def test_api_metadata_cannot_hide_missing_citation_evidence_fields(field):
    data = fixture()
    actual = produce(data)
    data.update(answer=actual["answer"], citations=deepcopy(actual["citations"]))
    data["citations"][0].update(document_title="UNITONLY", preview="irrelevant")
    data["citations"][0].pop(field)
    with pytest.raises(ValueError):
        reconstruct(data)


def test_unreconstructed_activity_disclosure_requires_its_independent_consumer():
    data = fixture()
    data["selection"]["role_scope_interpretations"] = [
        {"activity_fallback": True, "disclosure": "invented producer disclosure"}
    ]
    mirror(data)
    with pytest.raises(output.PendingConsumerProof):
        produce(data)
