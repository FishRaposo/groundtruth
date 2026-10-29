"""Complete pure new-contract replay; UNITONLY source graphs/NLI, not inference."""

from copy import deepcopy
from dataclasses import asdict

import pytest
from app.evidence_policy import EvidencePolicy
from app.services import contextual_mixed_output as mixed
from app.services import planning_declarations as d
from app.services import staged_output as output
from app.services import staged_plan_replay as replay
from app.services import staged_source_proof as source_proof
from app.services.staged_plan_binding import reconstruct_staged_plan

from tests.staged_plan_unit837.test_binding import args as catalogue_args
from tests.test_contextual_mixed_output import consumer_fixture


def complete_fixture():
    data = consumer_fixture()
    selection = data["selection"]
    snapshot = next(iter(data["source_snapshots"].values()))
    snapshot.update(
        snapshot_id="00000000-0000-0000-0000-000000000111",
        title="UNITONLY canonical routine",
        metadata={},
    )
    for chunk in snapshot["chunks"]:
        chunk["metadata"] = {}
    identity = d.SourceIdentity(
        **{k: snapshot[k] for k in d.SourceIdentity.__dataclass_fields__}
    )
    windows = selection["source_guard_records"][0]["source_windows"]
    source = d.SourceSnapshot(
        identity,
        snapshot["title"],
        snapshot["body"],
        "{}",
        tuple(
            d.SourceChunk(
                c["id"],
                c["index"],
                d.RawRange(
                    snapshot["body"].index(c["content"]),
                    snapshot["body"].index(c["content"]) + len(c["content"]),
                    c["content"],
                ),
                "{}",
            )
            for c in snapshot["chunks"]
        ),
    )
    captured = d.SourceCaptures(
        identity,
        tuple(
            d.CaptureWindow(w["start"], w["end"], d.canonical(w["capture"]))
            for w in windows
        ),
    )
    arguments = {
        "question": data["question"],
        "capture": selection["request_capture"],
        "manifest": d.PlanningUniverse("{}", (identity,), "bounded_authorized_scan"),
        "snapshots": (source,),
        "source_captures": (captured,),
        "support_metadata": selection["evidence_support"],
        "sql_read_set_json": catalogue_args()["sql_read_set_json"],
        "observations": (),
        "actual_executions": (),
    }
    plan = reconstruct_staged_plan(**arguments)
    assert plan.resolved_request
    actual_inputs = replay.capture_inputs(**arguments)
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v3",
    )
    selection.update(
        contract=policy.requirement_contract,
        evidence_profile=policy.record(),
        request_plan=plan.record(),
        staged_request_inputs=actual_inputs,
    )
    requirement = plan.requirements[0]
    envelope = source_proof.build_envelope(
        snapshot["body"],
        asdict(identity),
        requirement.topic,
        windows,
        question=data["question"],
        requirement_id=requirement.id,
        planning_inputs=actual_inputs,
        retained_inputs=deepcopy(actual_inputs),
        authoritative_snapshots=data["source_snapshots"],
    )
    prior = selection["source_guard_records"][0]
    score = deepcopy(prior["nli_assessments"][0]["assessment"])
    prior.update(
        source_identity=asdict(identity),
        envelope_inventory=envelope,
        nli_assessments=[
            {**row, "assessment": deepcopy(score)}
            for row in envelope["nli_obligations"]
        ],
    )
    _, _, sources = mixed._sources(
        data["source_snapshots"], selection, reading_profile="contextual_source_v3"
    )
    proof = mixed.procedure_obligations(
        requirement,
        sources[0],
        selection["proposals"][0],
        method="consumer_envelope",
        consumer_inventory=envelope,
        reading_profile="contextual_source_v3",
    )
    for record in selection["requirements"]:
        record["procedure_completeness"] = deepcopy(proof)
        for witness in record["witnesses"]:
            witness["procedure_completeness"] = deepcopy(proof)
    for record in selection["candidates"]:
        if "procedure_completeness" in record:
            record["procedure_completeness"] = deepcopy(proof)
    context = {
        "question": data["question"],
        "source_snapshots": data["source_snapshots"],
        "query_context": {"provenance": {"answer_selection": deepcopy(selection)}},
    }
    return selection, context


def test_actual_new_plan_and_source_consumers_produce_complete_verifiable_output():
    selection, context = complete_fixture()
    actual = output.build_output(selection, **context)
    assert actual["answer"] and actual["citations"]
    assert actual["certificate"]["contract"] == "procedure-output-cover-v8"
    assert actual["certificate"]["request_plan"] == selection["request_plan"]
    assert actual["certificate"]["reading_profile"] == "contextual_source_v3"
    selection[output.CERTIFICATE_FIELD] = actual["certificate"]
    assert output.verify_output(
        selection, answer=actual["answer"], citations=actual["citations"], **context
    )
    assert not output.verify_output(
        selection,
        answer=actual["answer"] + "invented",
        citations=actual["citations"],
        **context,
    )


@pytest.mark.parametrize(
    "damage", ["answer", "source", "request", "assessment", "citation"]
)
def test_staged_complete_output_tampering_refuses(damage):
    selection, context = complete_fixture()
    actual = output.build_output(selection, **context)
    selection[output.CERTIFICATE_FIELD] = actual["certificate"]
    if damage == "answer":
        actual["answer"] = actual["answer"].replace("token", "counter")
    elif damage == "source":
        next(iter(context["source_snapshots"].values()))["body"] += "altered"
    elif damage == "request":
        selection["request_plan"]["resolved_request"] = False
    elif damage == "assessment":
        selection["source_guard_records"][0]["nli_assessments"][0]["assessment"][
            "supported"
        ] = False
    else:
        actual["citations"][0]["quoted_text"] += "altered"
    assert not output.verify_output(
        selection, answer=actual["answer"], citations=actual["citations"], **context
    )


def test_successful_publication_recheck_is_transient_but_failures_are_not():
    selection, context = complete_fixture()
    actual = output.build_output(selection, **context)
    selection[output.CERTIFICATE_FIELD] = actual["certificate"]
    for target in (
        selection,
        context["query_context"]["provenance"]["answer_selection"],
    ):
        target["staged_publication_check"] = {"consistent": True, "reason": None}
    assert output.verify_output(
        selection, answer=actual["answer"], citations=actual["citations"], **context
    )
    selection["staged_publication_check"] = {"consistent": False, "reason": "changed"}
    assert not output.verify_output(
        selection, answer=actual["answer"], citations=actual["citations"], **context
    )
