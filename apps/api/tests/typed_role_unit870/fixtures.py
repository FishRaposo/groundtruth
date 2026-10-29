"""Real SQLite/version/planning paths; only parser/QA/NLI are UNITONLY boundaries."""

from copy import deepcopy

from app.models.query import QueryRequest
from app.services import connected_query, request_parser
from app.services.answer_reader import ReaderSelection, reader_service

from tests.staged_plan_unit837.fixtures_request import ACTORS, DEPENDENT, LABELS
from tests.staged_plan_unit837.fixtures_source import capture
from tests.test_contextual_source_proof import ACTION_SPEC, HEADER_SPEC
from tests.test_planning_relevance860 import _published_case
from tests.test_staged_snapshot_store849 import publish_library

PROCEDURE = [
    ("Give", "VERB", "give", "ROOT", 0),
    ("the", "DET", "the", "det", 3),
    ("full", "ADJ", "full", "amod", 3),
    ("routine", "NOUN", "routine", "dobj", 0),
    ("for", "ADP", "for", "prep", 3),
    ("Cedar", "PROPN", "Cedar", "compound", 6),
    ("inspection", "NOUN", "inspection", "pobj", 4),
    (".", "PUNCT", ".", "punct", 0),
]


async def actor_case(connected_db, monkeypatch):
    db, config, document, other, question, capture = await _published_case(
        connected_db, monkeypatch
    )
    monkeypatch.setattr(connected_query, "settings", config)
    calls = []

    async def null_qa(question, contexts, config=None):
        calls.append(tuple(contexts))
        return [
            ReaderSelection(
                None,
                {
                    "raw_candidates": [],
                    "null_margin": 9.0,
                    "reason": "UNITONLY no QA actor inference",
                },
            )
            for _ in contexts
        ]

    monkeypatch.setattr(reader_service, "select_atomic", null_qa)
    principal = {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False}
    request = QueryRequest.model_validate(
        {
            "question": question,
            "retrieval_method": "keyword",
            "memory_policy": "disabled",
        }
    )
    return db, config, principal, request, calls, document, other


async def labels_case(connected_db, monkeypatch):
    db, config, principal, request, calls, document, other = await actor_case(
        connected_db, monkeypatch
    )
    question, observed = capture([LABELS])
    previous = request_parser.capture_async

    async def syntax(text, config):
        return deepcopy(observed) if text == question else await previous(text, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    return (
        db,
        config,
        principal,
        request.model_copy(update={"question": question}),
        calls,
        document,
        other,
    )


async def chunked_actor_case(connected_db, monkeypatch):
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus, SourceType
    from app.services.document.versioning import DocumentVersionManager

    from tests import test_planning_relevance860

    original = test_planning_relevance860.publish_library

    async def publish(db, body):
        if "Rowan" not in body:
            return await original(db, body)
        document = Document(
            title="UNITONLY split source",
            source_type=SourceType.TEXT,
            status=DocumentStatus.READY,
            owner_id="owner-a",
            workspace_id="ops-a",
            metadata_={},
        )
        db.add(document)
        await db.commit()
        cut = body.index("Rowan") + 2
        chunks = [
            Chunk(
                document_id=document.id,
                content=literal,
                chunk_index=index,
                metadata_={"UNITONLY": True, "document_version": 1},
            )
            for index, literal in enumerate((body[:cut], body[cut:]))
        ]
        db.add_all(chunks)
        await db.flush()
        version = await DocumentVersionManager(db).create_version(
            str(document.id), body, chunks, workspace_id="ops-a", document=document
        )
        return document, version

    monkeypatch.setattr(test_planning_relevance860, "publish_library", publish)
    return await actor_case(connected_db, monkeypatch)


async def composite_case(connected_db, monkeypatch):
    db, config, principal, request, calls, document, other = await actor_case(
        connected_db, monkeypatch
    )
    header = [
        (
            "Cedar"
            if word == "Onyx"
            else "inspection"
            if word == "calibration"
            else word,
            pos,
            "Cedar"
            if word == "Onyx"
            else "inspection"
            if word == "calibration"
            else lemma,
            dep,
            head,
        )
        for word, pos, dep, head, lemma in HEADER_SPEC
    ]
    action = [
        (word, pos, lemma, dep, head) for word, pos, dep, head, lemma in ACTION_SPEC
    ]
    body, body_capture = capture([header, action])
    routine, _ = await publish_library(db, body)
    question, question_capture = capture([ACTORS, PROCEDURE])
    previous = request_parser.capture_async

    async def syntax(raw, config):
        if raw == body:
            return deepcopy(body_capture)
        if raw == question:
            return deepcopy(question_capture)
        return await previous(raw, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    return (
        db,
        config,
        principal,
        request.model_copy(update={"question": question}),
        calls,
        document,
        routine,
    )


async def dependent_case(connected_db, monkeypatch):
    db, config, principal, request, calls, document, other = await actor_case(
        connected_db, monkeypatch
    )
    fields = [
        [
            (actor, "PROPN", actor, "compound", 1),
            ("availability", "NOUN", "availability", "nsubj", 5),
            ("for", "ADP", "for", "prep", 1),
            ("Cedar", "PROPN", "Cedar", "compound", 4),
            ("inspection", "NOUN", "inspection", "pobj", 2),
            ("is", "AUX", "be", "ROOT", 5),
            (value, "NOUN", value, "attr", 5),
            (".", "PUNCT", ".", "punct", 5),
        ]
        for actor, value in (
            ("Rowan", "mornings"),
            ("Juniper", "afternoons"),
            ("Meadow", "evenings"),
        )
    ]
    body, body_capture = capture(fields)
    await publish_library(db, body)
    question, question_capture = capture([DEPENDENT])
    previous = request_parser.capture_async

    async def syntax(raw, config):
        if raw == body:
            return deepcopy(body_capture)
        if raw == question:
            return deepcopy(question_capture)
        return await previous(raw, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    return (
        db,
        config,
        principal,
        request.model_copy(update={"question": question}),
        calls,
        document,
        other,
    )


async def curated_actor_case(connected_db, monkeypatch):
    from tests import test_planning_relevance860

    original = test_planning_relevance860.publish_library

    async def publish(db, body):
        return await original(
            db, body, metadata={"conflict_group": "UNITONLY870-group"}
        )

    monkeypatch.setattr(test_planning_relevance860, "publish_library", publish)
    return await actor_case(connected_db, monkeypatch)


async def required_case(connected_db, monkeypatch):
    from tests.required_copy_fixtures880 import CAPTURES

    db, config, principal, request, calls, _, _ = await actor_case(
        connected_db, monkeypatch
    )
    root, _ = await publish_library(
        db, CAPTURES["root"]["annotation"]["raw_text"], title="UNITONLY root"
    )
    target, _ = await publish_library(
        db, CAPTURES["appendix"]["annotation"]["raw_text"], title="Appendix Alpha"
    )
    previous = request_parser.capture_async

    async def syntax(raw, config):
        for value in CAPTURES.values():
            if value["annotation"]["raw_text"] == raw:
                return deepcopy(value)
        return await previous(raw, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    return (
        db,
        config,
        principal,
        request.model_copy(
            update={"question": CAPTURES["question"]["annotation"]["raw_text"]}
        ),
        calls,
        root,
        target,
    )


async def required_only_case(connected_db, monkeypatch):
    from app.models.document import Document

    from tests.test_contextual_scope_sql import PRINCIPAL
    from tests.test_required_copy_runtime880 import prepared

    db, config, request, _, member, target = await prepared(connected_db, monkeypatch)
    monkeypatch.setattr(config, "SUPPORT_MODEL_PATH", "UNITONLY870-no-assets")
    monkeypatch.setattr(config, "SUPPORT_MIN_MARGIN", 2.0)
    monkeypatch.setattr(connected_query, "settings", config)
    calls = []

    async def null_qa(question, contexts, config=None):
        calls.append(tuple(contexts))
        return [
            ReaderSelection(None, {"raw_candidates": [], "null_margin": 9.0})
            for _ in contexts
        ]

    monkeypatch.setattr(reader_service, "select_atomic", null_qa)
    root = await db.get(Document, member.document_id)
    return (
        db,
        config,
        PRINCIPAL,
        QueryRequest.model_validate(
            {
                **request.model_dump(),
                "retrieval_method": "keyword",
                "memory_policy": "disabled",
            }
        ),
        calls,
        root,
        target,
    )
