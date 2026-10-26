"""A complete method needs every mandatory action, including its terminal clauses."""

import pytest
from app.config import Settings
from app.services import answer_support as support

from tests.test_procedure_extent import CONTROL, LONG, seed_procedure, select

pytest_plugins = ["tests.test_connected_contract"]


async def test_long_procedure_can_return_every_step_with_all_proofs_supported(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is None, [c.get("decision") for c in result.candidates]
    text = "".join(span.text for spans in result.passages.values() for span in spans)
    assert text == LONG[46:]
    assert len(result.chunks) == 2


async def test_terminal_prohibition_is_mandatory_even_if_every_other_pair_entails(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(
        db,
        chunks,
        document,
        monkeypatch,
        reject=lambda pair: "reopen" in pair.hypothesis.lower(),
    )
    assert result.reason is not None
    assert not result.passages


async def test_unparsed_governing_sentence_cannot_disappear(connected_db, monkeypatch):
    db, _ = connected_db
    body = CONTROL + " Supervisor permission may be withheld."
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None


async def test_body_scope_supports_nonworksheet_operational_procedure(
    connected_db, monkeypatch
):
    db, _ = connected_db
    body = LONG.replace(
        "This is a Harbor docket worksheet convention. Do not skip the approval check. "
        "The following complete procedure applies to ordinary worksheets with no seal.",
        "Harbor docket transfer procedure. This complete procedure applies to "
        "ordinary Harbor docket transfers. "
        "Do not skip the approval check.",
    )
    document, chunks = await seed_procedure(db, body, [body[:1200], body[1100:]])
    result = await select(
        db,
        chunks,
        document,
        monkeypatch,
        question=(
            "Give the complete ordered method for ordinary Harbor docket transfers."
        ),
    )
    assert result.reason is None, [c.get("decision") for c in result.candidates]
    assert "Do not reopen the transfer after closure." in "".join(
        span.text for spans in result.passages.values() for span in spans
    )


async def test_content_budget_is_distinct_and_does_not_poison_runtime_readiness(
    monkeypatch,
):
    class Backend:
        def token_lengths(self, pairs):
            return [513] * len(pairs)

        def logits(self, pairs):
            raise AssertionError("Overbudget input must never reach inference")

    monkeypatch.setattr(support, "validate_assets", lambda directory: directory)
    monkeypatch.setattr(support, "_load_backend", lambda directory: Backend())
    verifier = support.LocalSupportVerifier()
    config = Settings(
        ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH="unused-test-asset-boundary"
    )
    with pytest.raises(support.SupportUnavailableError) as caught:
        await verifier.assess(
            [support.SupportPair("source", "claim", "r1", "source")], config
        )
    assert type(caught.value).__name__ == "SupportInputBudgetExceeded"
    assert verifier.metadata(config)["readiness"] == "ready"


async def test_full_raw_cannot_be_clipped_into_separate_favorable_actions(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch, raw_text=LONG[156:368])
    assert result.reason is not None
    assert (
        result.requirements[0]["reason"]
        == "procedure_raw_not_in_mandatory_action_premise"
    )


async def test_step_cap_refuses_whole_procedure_before_support(
    connected_db, monkeypatch
):
    db, _ = connected_db
    header = CONTROL[:156]
    body = (
        header
        + "1. Verify the signed supervisor approval. "
        + " ".join(f"{i}. Scan the docket." for i in range(2, 34))
    )
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(
        db,
        chunks,
        document,
        monkeypatch,
        raw_text="Verify the signed supervisor approval.",
    )
    assert result.reason is not None
    assert result.requirements[0]["reason"] == "procedure_support_budget_exceeded"


async def test_named_actor_or_advisory_sentence_is_not_rewritten_as_you_must(
    connected_db, monkeypatch
):
    db, _ = connected_db
    body = CONTROL.replace(
        "2. Copy the docket identifier onto the transfer register.",
        "2. The supervisor should copy the docket identifier onto the "
        "transfer register.",
    )
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None
    assert any(
        c.get("unparsed_source_form", "").startswith("The supervisor should")
        for c in result.candidates
    )


NARRATIVE = (
    "Staging rollback: pause the deployment queue, select the last healthy image, "
    "and run the staging smoke test before resuming traffic. "
    "The approval owner is the release captain. The observation window is 12 minutes. "
    "Never use this procedure for production."
)


async def test_qa_null_proposal_is_not_revived_as_a_complete_method(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch, qa_null=True)
    assert result.reason is not None
    assert not result.chunks and not result.passages
    assert result.requirements[0]["reason"] == "qa_no_answer"


async def test_explicit_requested_workspace_is_not_lost_in_full_body_path(
    connected_db, monkeypatch
):
    from dataclasses import replace

    from app.services import requirement_answers

    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    request = replace(
        requirement_answers.plan_requirements(
            "Give the complete ordered method for ordinary Harbor docket "
            "worksheets with no seal."
        )[0],
        source_workspace="ops-b",
    )
    monkeypatch.setattr(
        requirement_answers, "plan_requirements", lambda question: (request,)
    )
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None
    assert result.requirements[0]["reason"] == "requested_workspace_mismatch"


async def test_existing_narrative_workflow_retains_full_immutable_method(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db, NARRATIVE, [NARRATIVE])
    result = await select(
        db,
        chunks,
        document,
        monkeypatch,
        question="How do I roll back the staging deployment?",
        raw_text="pause the deployment queue",
    )
    assert result.reason is None, result.requirements
    assert result.requirements[0]["witnesses"][0]["value"] == NARRATIVE
    proof = result.requirements[0]["procedure_completeness"]
    assert proof["structure"] == "narrative"
    assert proof["step_count"] is None and proof["step_ranges"] == []
    assert any(
        unit["kind"] == "whole_method"
        and unit["source_range"] == {"start": 0, "end": len(NARRATIVE)}
        for unit in proof["proof_units"]
    )
