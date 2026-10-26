"""Current evidence identity cannot erase historical or unranked authority."""

import uuid

import pytest
from app.api import health
from app.config import Settings
from app.models.document import Document, DocumentStatus, SourceType
from app.models.query import Query, SourceCitation
from app.portfolio.coverage import _requirement_evidence_sources
from app.services.connected_query import source_access
from pydantic import ValidationError

pytest_plugins = ["tests.test_connected_contract"]


def test_runtime_advertises_new_complete_version_algorithm(monkeypatch):
    monkeypatch.setattr(
        health,
        "get_settings",
        lambda: Settings(
            ANSWER_SELECTION_MODE="reader", ANSWER_SUPPORT_MODE="local_nli"
        ),
    )
    assert (
        health.runtime_metadata()["answer_selection"]["contract"]
        == "requirement-evidence-v2"
    )


@pytest.mark.parametrize(
    "contract",
    ["requirement-evidence-v1", "requirement-evidence-v2", "requirement-evidence-v99"],
)
async def test_diagnostic_only_document_never_bypasses_reauthorization(
    connected_db, contract
):
    db, _ = connected_db
    document = Document(
        title="Private",
        owner_id="someone-else",
        workspace_id="ops-a",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
    )
    db.add(document)
    await db.flush()
    row = Query(
        question="Who?",
        answer=None,
        sources=[],
        provenance={
            "answer_selection": {
                "contract": contract,
                "inspected_sources": [
                    {
                        "document_id": str(document.id),
                        "chunk_id": str(uuid.uuid4()),
                        "document_version": 1,
                        "content_hash": "a" * 64,
                    }
                ],
            }
        },
    )
    assert not await source_access(
        db, row, {"id": "reader", "workspace_id": "ops-a", "is_admin": False}
    )


@pytest.mark.parametrize(
    "contract", ["requirement-evidence-v1", "requirement-evidence-v2"]
)
def test_scoring_accounts_for_known_contract_inspections(contract):
    source = {"document_id": str(uuid.uuid4()), "chunk_id": str(uuid.uuid4())}
    response = {
        "provenance": {
            "answer_selection": {"contract": contract, "inspected_sources": [source]}
        }
    }
    assert source in _requirement_evidence_sources(response)


def citation(**changes):
    return {
        "chunk_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "document_title": "Source",
        "content_preview": "Exact",
        "relevance_score": 0.0,
        "citation_index": 1,
        **changes,
    }


def test_context_only_zero_is_explicit_and_cannot_claim_a_measured_score():
    source = SourceCitation(**citation(score_status="not_ranked"))
    assert getattr(source, "score_status", None) == "not_ranked"
    with pytest.raises(ValidationError):
        SourceCitation(**citation(score_status="not_ranked", relevance_score=0.7))
    assert getattr(SourceCitation(**citation()), "score_status", None) is None


async def test_new_procedure_contract_requires_measured_complete_cover(
    connected_db, monkeypatch
):
    from copy import deepcopy

    from app.services.requirement_contract import (
        complete_procedure,
        procedure_completeness,
    )

    from tests.test_procedure_extent import seed_procedure, select

    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch)
    proof = result.requirements[0]["procedure_completeness"]
    assert complete_procedure(proof)
    unknown_length = deepcopy(proof)
    unknown_length["proof_units"][0]["pair_tokens"] = None
    assert not complete_procedure(unknown_length)
    missing_continuation = deepcopy(proof)
    missing_continuation["fragments"].pop()
    assert not complete_procedure(missing_continuation)
    assert (
        procedure_completeness(
            {"contract": "requirement-evidence-v1", "requirements": result.requirements}
        )
        is False
    )
    assert (
        procedure_completeness(
            {"contract": "requirement-evidence-v2", "requirements": result.requirements}
        )
        is True
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "entire_step",
        "middle_clause",
        "final_prohibition",
        "namespace_substitution",
        "raw_context_substitution",
    ],
)
async def test_v40_required_action_inventory_cannot_be_undischarged(
    connected_db, monkeypatch, mutation
):
    """Internal malformed-record check, not a claimed public mutation endpoint."""
    from copy import deepcopy

    from app.services.requirement_contract import complete_procedure

    from tests.test_procedure_extent import seed_procedure, select

    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    assert complete_procedure(proof)
    if mutation in {"entire_step", "middle_clause", "final_prohibition"}:
        names = {
            u["name"]
            for u in proof["proof_units"]
            if (
                u["name"].startswith("step_8_")
                if mutation == "entire_step"
                else u["name"]
                == (
                    "step_8_action_2"
                    if mutation == "middle_clause"
                    else "step_8_action_3"
                )
            )
        }
        assert names
        proof["proof_units"] = [
            u for u in proof["proof_units"] if u["name"] not in names
        ]
        proof["structure_edges"] = [
            e for e in proof["structure_edges"] if e["target"] not in names
        ]
        proof["mandatory_proof_count"] = len(proof["proof_units"])
    else:
        unit = next(u for u in proof["proof_units"] if u["name"] == "step_8_action_1")
        unit["source_range"] = {
            "start": 0,
            "end": 45 if mutation == "namespace_substitution" else 1929,
        }
        unit["kind"] = (
            "namespace" if mutation == "namespace_substitution" else "instruction"
        )
        unit["hypothesis"] = "This is a Harbor docket worksheet convention."
    assert not complete_procedure(proof), (
        "Required source actions cannot vanish behind updated counts or broad checks"
    )
