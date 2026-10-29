"""Actual request-local staged planning context; never a legacy plan projection."""

import json
from dataclasses import asdict, dataclass

from app.services import planning_declarations as declarations
from app.services.staged_plan_binding import StagedRequestPlan
from app.services.staged_plan_replay import capture_inputs, reconstruct_request
from app.services.staged_planning_runtime import prepare_staged_planning


@dataclass(frozen=True)
class StagedAnswerContext:
    plan: StagedRequestPlan
    inputs_json: str
    snapshots_json: str

    @property
    def requirements(self):
        return self.plan.requirements

    @property
    def uses(self):
        return self.plan.uses

    @property
    def question(self):
        return self.plan.question

    @property
    def resolved_request(self):
        return self.plan.resolved_request

    def record(self):
        return self.plan.record()

    def inputs(self):
        return json.loads(self.inputs_json)

    def snapshots(self):
        return json.loads(self.snapshots_json)


def source_snapshots(inspection):
    return {
        row.identity.document_id: {
            **asdict(row.identity),
            "title": row.title,
            "body": row.body,
            "metadata": json.loads(row.metadata_json),
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "index": chunk.ordinal,
                    "content": chunk.literal.text,
                    "metadata": json.loads(chunk.metadata_json),
                }
                for chunk in row.chunks
            ],
        }
        for row in inspection.snapshots
    }


async def prepare_context(db, principal, request, config):
    evidence = await prepare_staged_planning(db, principal, request, config)
    inspection = evidence.inspection
    inputs = capture_inputs(
        question=evidence.question,
        capture=json.loads(evidence.request_capture_json),
        manifest=inspection.universe,
        snapshots=inspection.snapshots,
        source_captures=inspection.captures,
        support_metadata=json.loads(evidence.requested_support_metadata_json),
        sql_read_set_json=inspection.sql_read_set_json,
        observations=evidence.observations,
        actual_executions=evidence.executions,
    )
    actual = source_snapshots(inspection)
    plan = reconstruct_request(
        inputs,
        question=request.question,
        authoritative_snapshots=actual,
        retained_inputs=inputs,
        require_runtime=True,
    )
    return StagedAnswerContext(
        plan, declarations.canonical(inputs), declarations.canonical(actual)
    )


async def recheck_inputs(db, principal, question, inputs):
    """Reinspect the entire original authorized SQL universe before publication."""
    from app.models.query import QueryRequest
    from app.services.request_planning_manifest import check_planning_read_set

    expected = json.loads(inputs["sql_read_set_json"])
    request = QueryRequest(
        question=question,
        document_ids=expected["document_ids"],
        collection_ids=expected["collection_ids"],
    )
    return await check_planning_read_set(db, principal, request, expected)
