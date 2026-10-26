"""A model-approved chunk prefix must never certify a complete procedure."""

import hashlib
import uuid

import pytest
from app.config import Settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, SourceType
from app.models.query import QueryRequest
from app.services.answer_reader import ReaderSelection, passage_span, reader_service
from app.services.answer_support import SupportAssessment, support_service
from app.services.document.versioning import DocumentVersionManager
from app.services.requirement_answers import select_requirement_answer
from app.services.retrieval.scoped import scored_chunk

pytest_plugins = ["tests.test_connected_contract"]

QUESTION = (
    "Give the complete ordered method for ordinary Harbor docket "
    "worksheets with no seal."
)
CONTROL = (
    "This is a Harbor docket worksheet convention. Do not skip the "
    "approval check. The following complete procedure applies to ordinary "
    "worksheets with no seal. 1. Verify the signed supervisor approval "
    "before starting the Harbor docket transfer. 2. Copy the docket "
    "identifier onto the transfer register. 3. Compare the register total "
    "with the docket total. 4. Close the transfer register and place the "
    "completed docket in the archive tray. Do not reopen the transfer "
    "after closure."
)
LONG = (
    "This is a Harbor docket worksheet convention. Do not skip the "
    "approval check. The following complete procedure applies to ordinary "
    "worksheets with no seal. 1. Verify the signed supervisor approval "
    "before starting the Harbor docket transfer. Check that the approval "
    "names the docket identifier and the current operating date, and place "
    "the approval beside the register. 2. Copy the docket identifier onto "
    "the transfer register. Copy the receiving desk, the dispatch date, "
    "and the operator initials onto the same register row so the transfer "
    "can be traced during the handover. 3. Compare the register total with "
    "the docket total. Count every listed envelope, compare each envelope "
    "identifier with the dispatch list, and record the checked count "
    "beside the register total before moving the envelopes. 4. Place the "
    "checked envelopes in the transfer basket. Arrange the envelopes in "
    "dispatch list order, attach the register copy to the basket handle, "
    "and leave the original dispatch list on the supervisor desk. 5. Carry "
    "the transfer basket to the receiving desk. Ask the receiving clerk to "
    "compare the basket count with the register copy and to initial the "
    "count field while the basket remains on the desk. 6. Record the "
    "receiving clerk initials in the original register. Record the "
    "handover time beside the initials, confirm that the receiving desk "
    "has the register copy, and retain the original register for the "
    "closure check. 7. Compare the completed register with the supervisor "
    "approval. Confirm that the docket identifier, envelope count, "
    "receiving clerk initials, and handover time are all present, and "
    "obtain the supervisor closure signature on the final line. 8. Close "
    "the transfer register and place the completed docket in the archive "
    "tray. Lock the archive tray, return the archive key to the "
    "supervisor, and end the transfer only after the supervisor records "
    "receipt of the key. Do not reopen the transfer after closure."
)
PRINCIPAL = {"id": "writer", "workspace_id": "ops-a", "is_admin": False}


async def seed_procedure(db, body=LONG, pieces=None):
    document = Document(
        title="Harbor docket",
        owner_id="writer",
        workspace_id="ops-a",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
    )
    db.add(document)
    await db.flush()
    chunks = [
        Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            content=piece,
            chunk_index=i,
            metadata_={"document_version": 1},
            embedding=[1.0] * 32,
        )
        for i, piece in enumerate(pieces or [body[:1292], body[1171:]])
    ]
    db.add_all(chunks)
    await db.flush()
    await DocumentVersionManager(db).create_version(
        str(document.id),
        body,
        chunks,
        workspace_id="ops-a",
        document=document,
    )
    return document, [
        scored_chunk(c, document, 0.9 - i * 0.1) for i, c in enumerate(chunks)
    ]


def external_boundaries(monkeypatch, *, reject=None, raw_text=None, qa_null=False):
    calls = []

    async def reader(question, contexts, config=None):
        results = []
        for context in contexts:
            value = raw_text or (
                "Verify the signed supervisor approval before starting the "
                "Harbor docket transfer."
            )
            if value not in context:
                results.append(ReaderSelection(None, {"decision": "no_answer"}))
                continue
            start = context.index(value)
            raw = {
                "start": start,
                "end": start + len(value),
                "text": value,
                "null_margin": -9.0,
            }
            results.append(
                ReaderSelection(
                    None if qa_null else passage_span(context, start, raw["end"]),
                    {"raw_candidates": [raw], "decision": "answer"},
                )
            )
        return results

    async def nli(pairs, config=None):
        calls.extend(pairs)
        return [
            SupportAssessment(
                "neutral" if reject and reject(p) else "entailment",
                (-5.0, 0.0, 5.0) if reject and reject(p) else (-5.0, 5.0, -5.0),
                -5.0 if reject and reject(p) else 10.0,
                not (reject and reject(p)),
                12,
            )
            for p in pairs
        ]

    monkeypatch.setattr(reader_service, "select_atomic", reader)
    monkeypatch.setattr(support_service, "assess", nli)
    return calls


async def select(
    db, chunks, document, monkeypatch, question=QUESTION, document_ids=None, **kwargs
):
    external_boundaries(monkeypatch, **kwargs)
    request = QueryRequest(
        question=question,
        document_ids=document_ids or [document.id],
        retrieval_method="keyword",
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        READER_NULL_THRESHOLD=8,
    )

    async def current(chunk):
        return True

    return await select_requirement_answer(
        db, request, PRINCIPAL, chunks, config, validate_current=current
    )


async def test_accepted_prefix_cannot_complete_without_terminal_steps(
    connected_db, monkeypatch
):
    db, _ = connected_db
    assert (
        hashlib.sha256(LONG.encode()).hexdigest()
        == "595a3378451240757e288f3fb025287dcf1e5d486d9ef900ac1c88f0f5453f74"
    )
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks, document, monkeypatch)
    text = "".join(span.text for spans in result.passages.values() for span in spans)
    assert result.reason is not None or (
        "8. Close the transfer register" in text
        and "Do not reopen the transfer after closure." in text
    ), "A supported local prefix is not the complete immutable procedure"


async def test_complete_control_retains_prerequisite_and_prohibitions(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db, CONTROL, [CONTROL])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is None
    text = "".join(span.text for spans in result.passages.values() for span in spans)
    assert "before starting the Harbor docket transfer" in text
    assert "Do not skip the approval check." in text
    assert text.endswith("Do not reopen the transfer after closure.")


@pytest.mark.parametrize(
    "declaration", ["The following complete procedure", "This complete procedure"]
)
async def test_declaration_governs_intervening_mandatory_prohibition(
    connected_db, monkeypatch, declaration
):
    db, _ = connected_db
    body = (
        CONTROL.replace("Do not skip the approval check. ", "")
        .replace("The following complete procedure", declaration)
        .replace("no seal. 1.", "no seal. Do not skip the approval check. 1.")
    )
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is None, [c.get("decision") for c in result.candidates]
    assert (
        "Do not skip the approval check."
        in result.requirements[0]["witnesses"][0]["value"]
    )


@pytest.mark.parametrize(
    "intervening",
    [
        "The procedure is no longer applicable.",
        "For Raven intake: use the exception method.",
        "Do not use this procedure.",
        'The clerk says "skip approval".',
    ],
)
async def test_declaration_cannot_omit_unknown_foreign_or_withdrawn_scope(
    connected_db, monkeypatch, intervening
):
    db, _ = connected_db
    body = CONTROL.replace("no seal. 1.", f"no seal. {intervening} 1.")
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None


async def test_explicit_foreign_procedure_is_an_independent_end_boundary(
    connected_db, monkeypatch
):
    db, _ = connected_db
    body = CONTROL + " For Raven intake: 1. Scan the pass. 2. File the slip."
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is None, result.requirements
    assert (
        result.requirements[0]["procedure_completeness"]["closure"]["kind"]
        == "independent_section"
    )
    assert "Raven" not in result.requirements[0]["witnesses"][0]["value"]


@pytest.mark.parametrize(
    "tail",
    [
        " Notes: Do not archive without approval.",
        " For Harbor docket: 1. Open the register. 2. Close the register.",
    ],
)
async def test_ambiguous_notes_or_same_subject_restart_cannot_establish_completion(
    connected_db, monkeypatch, tail
):
    db, _ = connected_db
    body = CONTROL + tail
    document, chunks = await seed_procedure(db, body, [body])
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None
