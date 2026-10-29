"""Actual typed pipeline; UNITONLY inference and parser protocol boundaries."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from app.services import connected_query, staged_output, staged_role_consumer
from app.services import staged_availability_evidence as fields
from app.services import staged_role_evidence as role
from app.services.answer_support import support_service
from app.services.procedure_output import load_snapshots, retained_selection
from app.services.staged_availability_evidence import AvailabilityEvidence

from tests.staged_role_unit850.test_role_evidence import Backend, backend_context

from .fixtures import (
    actor_case,
    chunked_actor_case,
    composite_case,
    curated_actor_case,
    dependent_case,
    labels_case,
    required_case,
    required_only_case,
)

pytest_plugins = ["tests.test_connected_contract"]


async def test_cross_chunk_role_value_refuses_without_truncation_or_model_error(
    connected_db, monkeypatch
):
    db, _, principal, request, _, _, _ = await chunked_actor_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None
        assert row.outcome == "refused" and row.answer is None
        rows = row.provenance["answer_selection"]["requirements"]
        assert any("cross-chunk" in record.get("reason", "") for record in rows)


async def test_actual_pipeline_answers_literal_labels_without_actor_projection(
    connected_db, monkeypatch
):
    db, _, principal, request, calls, _, _ = await labels_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", row.refusal_reason
        selection = row.provenance["answer_selection"]
        assert {record["kind"] for record in selection["requirements"]} == {
            "role_catalogue",
            "role_label",
        }
        assert all(
            label in row.answer for label in ("coordinator", "observer", "recorder")
        )
        assert not any(actor in row.answer for actor in ("Rowan", "Juniper", "Meadow"))
        assert all(not contexts for contexts in calls)
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"


async def test_required_copy_two_document_dispatch(connected_db, monkeypatch):
    db, _, principal, request, _, root, target = await required_only_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", row.refusal_reason
        proof = row.provenance["answer_selection"]["requirements"][0]["witnesses"][0][
            "procedure_completeness"
        ]
        documents = proof["required_copy"]["documents"]
        assert proof["method"] == "required_copy_v1"
        assert [document["identity"]["document_id"] for document in documents] == [
            str(root.id),
            str(target.id),
        ]
        assert all(document["body"] in row.answer for document in documents)
        assert row.answer.index(documents[0]["body"]) < row.answer.index(
            documents[1]["body"]
        )
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"


async def test_required_copy_dispatch_emits_each_actual_document_in_order(
    connected_db, monkeypatch
):
    db, _, principal, request, _, root, target = await required_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", (
            row.refusal_reason,
            [
                {
                    key: value
                    for key, value in candidate.items()
                    if key in {"decision", "reason", "source_guard_failure"}
                }
                for candidate in row.provenance["answer_selection"]["candidates"]
            ],
        )
        proof = row.provenance["answer_selection"]["requirements"][0]["witnesses"][0][
            "procedure_completeness"
        ]
        assert proof["method"] == "required_copy_v1"
        documents = proof["required_copy"]["documents"]
        assert [document["identity"]["document_id"] for document in documents] == [
            str(root.id),
            str(target.id),
        ]
        assert all(document["body"] in row.answer for document in documents)
        assert row.answer.index(documents[0]["body"]) < row.answer.index(
            documents[1]["body"]
        )
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"


async def test_actual_typed_curated_comparison_keeps_all_sources(
    connected_db, monkeypatch
):
    db, _, principal, request, _, document, other = await curated_actor_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None
        assert row.outcome == "completed", row.refusal_reason
        conflicts = row.provenance["answer_selection"]["conflicts"]
        assert len(conflicts) == 4
        assert all(
            {member["document_id"] for member in record["inspection_sources"]}
            == {str(document.id), str(other.id)}
            for record in conflicts
        )
        assert all(
            record["inspection_complete"] and not record["relevant"]
            for record in conflicts
        )
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"


async def test_actual_pipeline_answers_typed_incumbents_with_a_set_parent(
    connected_db, monkeypatch
):
    db, config, principal, request, qa_calls, _, _ = await actor_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", (
            row.refusal_reason,
            row.provenance["answer_selection"].get("request_plan"),
        )
        assert row.answer and all(
            actor in row.answer for actor in ("Rowan", "Juniper", "Meadow")
        )
        selection = row.provenance["answer_selection"]
        assert selection["contract"] == "requirement-evidence-v5"
        assert {record["kind"] for record in selection["requirements"]} == {
            "role_catalogue",
            "role_assignment",
        }
        parent = next(
            record
            for record in selection["requirements"]
            if record["kind"] == "role_catalogue"
        )
        assert parent["status"] == "supported"
        assert parent["witnesses"][0]["typed_set_proof"]
        assert all(not contexts for contexts in qa_calls)
        await connected_query.finish_query(db, row, principal)
        shown = await connected_query.present_query(db, row, principal)
        assert shown.outcome == "completed" and shown.answer == row.answer


async def test_same_activity_roles_and_complete_routine_have_separate_productions(
    connected_db, monkeypatch
):
    db, config, principal, request, qa_calls, _, _ = await composite_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", row.refusal_reason
        assert all(
            text in row.answer
            for text in ("Rowan", "Juniper", "Meadow", "Frobnicate the token.")
        )
        assert {
            record["kind"]
            for record in row.provenance["answer_selection"]["requirements"]
        } == {"role_catalogue", "role_assignment", "procedure"}
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"


async def test_dependent_availability_uses_supported_actual_actor_values(
    connected_db, monkeypatch
):
    db, config, principal, request, qa_calls, _, _ = await dependent_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.provenance is not None and isinstance(row.answer, str)
        assert row.outcome == "completed", row.refusal_reason
        assert all(
            text in row.answer
            for text in (
                "Rowan",
                "Juniper",
                "Meadow",
                "mornings",
                "afternoons",
                "evenings",
            )
        )
        availability = [
            record
            for record in row.provenance["answer_selection"]["requirements"]
            if record["kind"] == "availability"
        ]
        assert len(availability) == 4
        assert all(record["status"] == "supported" for record in availability)
        assert "Move the card." not in row.answer
        assert all(not contexts for contexts in qa_calls)
        await connected_query.finish_query(db, row, principal)
        assert (
            await connected_query.present_query(db, row, principal)
        ).outcome == "completed"
        selection = row.provenance["answer_selection"]
        snapshots = await load_snapshots(
            db, selection, query_context=row.retrieval_trace
        )
        actual = selection["staged_request_inputs"]
        captured = retained_selection(row.retrieval_trace)
        assert captured is not None
        replay = staged_role_consumer.reconstruct_selection(
            selection,
            question=row.question,
            planning_inputs=actual,
            retained_inputs=captured["staged_request_inputs"],
            authoritative_snapshots=snapshots,
            retained_selection=captured,
        )
        child = next(
            value
            for value in replay.values()
            if isinstance(value, AvailabilityEvidence)
        )
        actor = replay[child.prepared.actor_fact.requirement_id]
        alternative = next(
            value
            for value in replay.values()
            if isinstance(value, role.RoleEvidence)
            and value.bound_requirement.kind == "role_assignment"
            and value.bound_requirement.id != actor.bound_requirement.id
        )
        forged = {
            **replay,
            actor.bound_requirement.id: replace(
                actor,
                facts=(replace(actor.facts[0], value=alternative.facts[0].value),),
            ),
        }
        actual_child = fields.prepare(
            actors=forged,
            requirement_id=child.bound_requirement.id,
            question=row.question,
            planning_inputs=actual,
            retained_inputs=captured["staged_request_inputs"],
            authoritative_snapshots=snapshots,
            require_runtime=True,
        )
        assert actual_child.actor_fact.value == actor.facts[0].value
        assert actual_child.candidate_value == child.prepared.candidate_value
        changed, retained = deepcopy(selection), deepcopy(row.retrieval_trace)
        for channel in (changed, retained_selection(retained)):
            assert channel is not None
            candidate = next(
                candidate
                for candidate in channel["candidates"]
                if candidate["requirement_id"] == child.bound_requirement.id
            )
            for field in ("observations", "actual_executions"):
                candidate["typed_role_execution"][field][0]["pair"][
                    "requirement_id"
                ] = "unrelated-child"
        assert not staged_output.verify_output(
            changed,
            question=row.question,
            answer=row.answer,
            citations=row.sources,
            source_snapshots=snapshots,
            query_context=retained,
        )

        async def empty_decisions(*args, **kwargs):
            return []

        monkeypatch.setattr(support_service, "assess", empty_decisions)
        with pytest.raises(ValueError) as mismatch:
            await role.assess_dependent_checks(config, child.prepared)
        assert (
            json.loads(mismatch.value.__dict__["dependent_field_execution_json"])[
                "returned_decision_count"
            ]
            == 0
        )

        async def cancel(*args, **kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(support_service, "assess", cancel)
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await role.assess_dependent_checks(config, child.prepared)
        assert (
            json.loads(cancelled.value.__dict__["dependent_field_execution_json"])[
                "stage"
            ]
            == "before_service_return"
        )
