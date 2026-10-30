"""Reader boundary regressions; immutable SQL/upload behavior remains real."""

import pytest
from app.config import Settings, get_settings
from pydantic import ValidationError

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def test_invalid_answer_selection_fails_configuration():
    with pytest.raises(ValidationError):
        Settings(ANSWER_SELECTION_MODE="invented")


async def test_missing_reader_is_execution_error_not_successful_refusal(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    settings = get_settings()
    monkeypatch.setitem(settings.__dict__, "ANSWER_SELECTION_MODE", "reader")
    monkeypatch.setitem(settings.__dict__, "READER_MODEL_PATH", "missing-local-reader")
    doc = await upload(client)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Which revision should I revert staging to?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 503, response.text
    history = (await client.get("/api/queries")).json()["queries"]
    assert history[0]["outcome"] == "error"
    assert history[0]["refused"] is False


def test_period_boundaries_preserve_the_supporting_paragraph():
    from app.services.answer_reader import passage_span

    span = passage_span("🧭 Revert to R42. Observe health.", 2, 16)
    assert span.text == "\U0001f9ed Revert to R42. Observe health."
    assert (span.start, span.end) == (0, 32)


async def test_reader_paraphrase_copies_exact_canonical_support(
    real_client, monkeypatch
):
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection, reader_service

    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    quote = (
        "\U0001f9ed Staging rollback uses release R42. "
        "Verify deployment health before resuming traffic."
    )

    async def external_reader(question, contexts, config=None):
        assert question == "Which revision should I revert staging to?"
        assert contexts == [quote]
        return [
            ReaderSelection(
                AnswerSpan(
                    start=0, end=36, text="🧭 Staging rollback uses release R42."
                ),
                {"null_margin": -8.0, "decision": "answer"},
            )
        ]

    # Only the slow external model boundary is substituted; upload/retrieval,
    # source publication, quote validation, SQL history and HTTP are real.
    monkeypatch.setattr(reader_service, "select", external_reader)
    doc = await upload(client, quote)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Which revision should I revert staging to?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["refused"] is False
    assert result["sources"][0]["quoted_text"] == quote
    assert result["sources"][0]["answer_spans"] == [
        {"start": 0, "end": 36, "text": "🧭 Staging rollback uses release R42."}
    ]
    assert "Verify deployment" not in result["answer"]
    assert result["provenance"]["answer_selection"]["mode"] == "reader"
    history = (await client.get(f"/api/queries/{result['id']}")).json()
    assert history["sources"] == result["sources"]


def test_answer_span_rejects_utf16_or_reconstructed_offsets():
    import uuid

    from app.models.query import SourceCitation

    for span in [
        {"start": 3, "end": 6, "text": "R42"},
        {"start": 2, "end": 5, "text": "r42"},
    ]:
        with pytest.raises(ValidationError):
            SourceCitation(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Runbook",
                content_preview="",
                relevance_score=1,
                citation_index=1,
                quoted_text="🧭 R42",
                answer_spans=[span],
            )


async def test_reader_null_is_refusal_with_raw_diagnostics(real_client, monkeypatch):
    from app.services.answer_reader import ReaderSelection, reader_service

    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")

    async def null_reader(question, contexts, config=None):
        return [
            ReaderSelection(None, {"decision": "no_answer", "null_margin": 9.0})
            for _ in contexts
        ]

    monkeypatch.setattr(reader_service, "select", null_reader)
    doc = await upload(client)
    result = (
        await client.post(
            "/api/queries",
            json={
                "question": "What is staging rollback salary?",
                "document_ids": [doc["id"]],
                "retrieval_method": "keyword",
            },
        )
    ).json()
    assert result["outcome"] == "refused" and result["refused"]
    assert result["answer"] is None and result["sources"] == []
    assert (
        result["provenance"]["answer_selection"]["candidates"][0]["null_margin"] == 9.0
    )


async def test_conflict_is_guarded_before_reader_can_discard_opposition(
    real_client, monkeypatch
):
    import uuid

    from app.models.document import Document
    from app.services.answer_reader import reader_service

    client, factory, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    first = await upload(client, "Staging rollback uses R42.")
    second = await upload(client, "Staging rollback uses R43.")
    async with factory() as db:
        for doc in [first, second]:
            document = await db.get(Document, uuid.UUID(doc["id"]))
            document.metadata_ = {
                **document.metadata_,
                "conflict_group": "staging-revision",
            }
        await db.commit()

    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection

    async def opposing_reader(question, contexts, config=None):
        assert set(contexts) == {
            "Staging rollback uses R42.",
            "Staging rollback uses R43.",
        }
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=26, text=text) if "R42" in text else None,
                {"decision": "answer" if "R42" in text else "no_answer"},
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", opposing_reader)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Which revision should I revert staging to?",
            "document_ids": [first["id"], second["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "refused"
    assert "conflicting" in response.json()["refusal_reason"]


async def test_corrupt_assets_fail_before_importing_model(tmp_path):
    import hashlib
    import json

    from app.reader_setup import FILES, MODEL, REVISION
    from app.services.answer_reader import LocalReader

    root = tmp_path / "reader assets with spaces"
    root.mkdir()
    files = {}
    for filename in FILES:
        (root / filename).write_text("original", encoding="utf-8")
        files[filename] = hashlib.sha256(b"original").hexdigest()
    (root / "groundtruth-reader.json").write_text(
        json.dumps({"model": MODEL, "revision": REVISION, "files": files})
    )
    (root / "model.safetensors").write_text("corrupt")
    service = LocalReader()
    with pytest.raises(RuntimeError, match="no fallback") as error:
        await service.select(
            "question", ["context"], Settings(READER_MODEL_PATH=str(root))
        )
    assert "integrity" in str(error.value.__cause__)
    assert (
        service.metadata(
            Settings(ANSWER_SELECTION_MODE="reader", READER_MODEL_PATH=str(root))
        )["readiness"]
        == "error"
    )


async def test_cancelled_and_concurrent_reader_requests_keep_contexts_isolated(
    monkeypatch,
):
    import asyncio
    import threading

    from app.models.query import AnswerSpan
    from app.services.answer_reader import LocalReader, ReaderSelection

    service = LocalReader()
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(service, "_load", lambda config: None)

    def slow_model(question, context, config):
        if question == "cancel":
            entered.set()
            assert release.wait(5)
        return ReaderSelection(AnswerSpan(start=0, end=len(context), text=context), {})

    monkeypatch.setattr(service, "_context", slow_model)
    cancelled = asyncio.create_task(service.select("cancel", ["private-alpha"]))
    assert await asyncio.to_thread(entered.wait, 5)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    second = asyncio.create_task(service.select("second", ["public-beta"]))
    release.set()
    assert (await second)[0].span.text == "public-beta"
    results = await asyncio.gather(
        service.select("one", ["one"]), service.select("two", ["two"])
    )
    assert [result[0].span.text for result in results] == ["one", "two"]


class _Tensor:
    def __init__(self, value):
        self.value = value

    def tolist(self):
        return self.value

    def __getitem__(self, index):
        return _Tensor(self.value[index])


class _Encoding(dict):
    def sequence_ids(self, window):
        return [None, 0, None, 1, 1, 1, None]


@pytest.mark.parametrize(
    "cls_score,expected",
    [(0.0, "\U0001f9ed Header. Restore R42. Observe health."), (20.0, None)],
)
def test_sliding_windows_select_canonical_unicode_offsets(
    monkeypatch, cls_score, expected
):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.services.answer_reader import LocalReader

    context = "🧭 Header. Restore R42. Observe health."

    class Tokenizer:
        cls_token_id = 101

        def __call__(self, question, text, **kwargs):
            assert text == context and question == "Which revision?"
            assert kwargs["max_length"] == 384 and kwargs["stride"] == 128
            assert kwargs["truncation"] == "only_second"
            return _Encoding(
                input_ids=_Tensor([[101, 9, 102, 1, 2, 3, 102]] * 2),
                offset_mapping=_Tensor(
                    [
                        [(0, 0), (0, 5), (0, 0), (2, 8), (2, 8), (2, 8), (0, 0)],
                        [(0, 0), (0, 5), (0, 0), (10, 17), (18, 21), (23, 30), (0, 0)],
                    ]
                ),
                overflow_to_sample_mapping=_Tensor([0, 0]),
            )

    def model(**kwargs):
        # A large question-token logit must never become source evidence.
        logits = [
            [cls_score, 100.0, 0.0, 1.0, 1.0, 1.0, 0.0],
            [cls_score, 100.0, 0.0, 1.0, 5.0, 1.0, 0.0],
        ]
        return SimpleNamespace(start_logits=_Tensor(logits), end_logits=_Tensor(logits))

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    service = LocalReader()
    service._tokenizer, service._model = Tokenizer(), model
    result = service._context("Which revision?", context, Settings())
    assert (result.span.text if result.span else None) == expected
    assert result.diagnostics["windows"] == 2
    assert result.diagnostics["best_span_score"] == 10.0
    assert result.diagnostics["null_margin"] == cls_score * 2 - 10.0
    if result.span:
        assert (result.span.start, result.span.end) == (0, 38)


def test_ordered_steps_preserve_contiguous_passage():
    from app.services.answer_reader import passage_span

    context = "1. Pause traffic.\n2. Restore R42.\n3. Verify health."
    span = passage_span(context, 28, 31)
    assert span.text == context and (span.start, span.end) == (0, 51)


async def test_cancelled_http_reader_records_interrupted_not_refused(
    real_client, monkeypatch
):
    import asyncio

    from app.services.answer_reader import reader_service

    client, _, _ = real_client
    entered = asyncio.Event()
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")

    async def blocked_model(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(reader_service, "select", blocked_model)
    doc = await upload(client)
    task = asyncio.create_task(
        client.post(
            "/api/queries",
            json={
                "question": "Which staging rollback release?",
                "document_ids": [doc["id"]],
                "retrieval_method": "keyword",
            },
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    item = (await client.get("/api/queries")).json()["queries"][0]
    assert item["outcome"] == "interrupted" and item["refused"] is False


@pytest.mark.parametrize("unrelated_supported", [False])
async def test_unrelated_conflict_pair_does_not_hide_supported_answer(
    real_client, monkeypatch, unrelated_supported
):
    import uuid

    from app.models.document import Document
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection, reader_service

    client, factory, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    old = await upload(client, "Warehouse rollback uses R31.")
    other = await upload(client, "Warehouse rollback uses R32.")
    current = await upload(client, "Staging rollback is authorized by Morgan.")
    async with factory() as db:
        for doc in [old, other]:
            document = await db.get(Document, uuid.UUID(doc["id"]))
            document.metadata_ = {**document.metadata_, "conflict_group": "warehouse"}
        await db.commit()

    async def reader(question, contexts, config=None):
        assert set(contexts) == {
            "Warehouse rollback uses R31.",
            "Warehouse rollback uses R32.",
            "Staging rollback is authorized by Morgan.",
        }
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=len(text), text=text)
                if text.startswith("Staging") or unrelated_supported
                else None,
                {"decision": "answer" if text.startswith("Staging") else "no_answer"},
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", reader)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who authorizes staging rollback?",
            "document_ids": [old["id"], other["id"], current["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    assert "Morgan" in result["answer"]
    assert {source["document_id"] for source in result["sources"]} == {current["id"]}
    assert "Warehouse" not in result["answer"]


async def test_revoked_reader_citation_does_not_leak_raw_span_provenance(
    real_client, monkeypatch
):
    import uuid

    from app.models.document import Document
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection, reader_service

    client, factory, keys = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")

    async def reader(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=41, text=text),
                {"raw_span": {"text": text}, "decision": "answer"},
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", reader)
    doc = await upload(client, "Staging rollback is authorized by Morgan.")
    result = (
        await client.post(
            "/api/queries",
            json={
                "question": "Who authorizes staging rollback?",
                "document_ids": [doc["id"]],
                "retrieval_method": "keyword",
            },
        )
    ).json()
    assert result["outcome"] == "completed", result
    async with factory() as db:
        document = await db.get(Document, uuid.UUID(doc["id"]))
        document.owner_id = keys["reader"]
        await db.commit()
    response = await client.get(f"/api/queries/{result['id']}")
    assert response.status_code == 200
    restricted = response.json()
    assert restricted["evidence_access"] == "restricted"
    assert "Morgan" not in response.text
    assert restricted["provenance"] is None


async def test_reader_failure_history_exposes_safe_identity_not_success(
    real_client, monkeypatch
):
    from app.services.answer_reader import reader_service

    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")

    async def failing_model(*args, **kwargs):
        raise RuntimeError("private-local-path must not appear in HTTP evidence")

    monkeypatch.setattr(reader_service, "select", failing_model)
    doc = await upload(client)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Which staging rollback release?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 503
    detail = (
        await client.get(f"/api/queries/{response.json()['detail']['query_id']}")
    ).json()
    assert detail["outcome"] == "error" and detail["refused"] is False
    assert detail["provenance"]["answer_selection"]["mode"] == "reader"
    assert detail["provenance"]["answer_selection"]["decision"] == "error"
    assert "private-local-path" not in str(detail)


@pytest.mark.parametrize("revoke_at", ["reader", "first_token"])
async def test_stream_checks_revoked_evidence_before_each_body_yield(
    real_client, monkeypatch, revoke_at
):
    import asyncio
    import json
    import uuid

    from app.main import app
    from app.models.document import Document
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection, reader_service

    client, factory, keys = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    doc = await upload(client, "Staging rollback is authorized by Morgan.")

    async def revoke():
        async with factory() as db:
            document = await db.get(Document, uuid.UUID(doc["id"]))
            document.owner_id = keys["reader"]
            await db.commit()

    async def reader(question, contexts, config=None):
        if revoke_at == "reader":
            await revoke()
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=41, text=text), {"decision": "answer"}
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", reader)
    body = json.dumps(
        {
            "question": "Who authorizes staging rollback?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        }
    ).encode()
    requested = False
    messages = []

    async def receive():
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/queries/stream",
        "raw_path": b"/api/queries/stream",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"x-api-key", b"owner"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    if revoke_at == "reader":
        await asyncio.wait_for(app(scope, receive, send), timeout=10)
    else:
        # Exercise the actual response iterator boundary. Outer ASGI middleware
        # can prefetch already-authorized fragments while a downstream send is
        # waiting to commit revocation; that is not a later generator check.
        from app.api.queries import stream_query
        from app.models.query import QueryRequest

        async with factory() as db:
            response = await stream_query(
                QueryRequest.model_validate_json(body),
                db,
                {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False},
            )
            first = await anext(response.body_iterator)
            assert "Morgan" not in str(first)
            await revoke()
            pieces = [first]
            async for piece in response.body_iterator:
                pieces.append(piece)
            messages = [
                {
                    "type": "http.response.body",
                    "body": piece.encode() if isinstance(piece, str) else piece,
                }
                for piece in pieces
            ]
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode()
    assert "Morgan" not in response_body, response_body
    events = [
        json.loads(line[6:])
        for line in response_body.splitlines()
        if line.startswith("data: ")
    ]
    terminal = next(event for event in events if event["type"] == "done")
    assert terminal["evidence_access"] == "restricted"
    assert terminal["answer"] is None and terminal["sources"] == []
    if revoke_at == "reader":
        assert all(event["type"] != "token" for event in events)
    history = await client.get(f"/api/queries/{terminal['id']}")
    assert history.json()["evidence_access"] == "restricted"
    assert "Morgan" not in history.text


@pytest.mark.parametrize(
    "context,start,end",
    [
        (
            (
                "Do not ask Dr. Morgan to approve staging rollback. "
                "Ask the release lead instead."
            ),
            15,
            21,
        ),
        ("Do not enable e.g. public sharing before approval.", 19, 33),
        ("Do not enable approx. public sharing before approval.", 22, 36),
    ],
)
def test_uncertain_period_boundary_keeps_negation_and_qualifiers(context, start, end):
    from app.services.answer_reader import passage_span

    span = passage_span(context, start, end)
    assert span.text == context
    assert span.start == 0 and span.end == len(context)


@pytest.mark.parametrize(
    "question,context,raw,answerable",
    [
        (
            "How much is copier access?",
            (
                "The copier guide does not define an access price. "
                "The weekly allowance is 18 sheets."
            ),
            "access price",
            False,
        ),
        (
            "How many sheets may an operator print?",
            (
                "The copier guide does not define an access price. "
                "The weekly allowance is 18 sheets."
            ),
            "18",
            True,
        ),
        (
            "How much is copier access?",
            "Copier access costs twelve dollars.",
            "twelve",
            True,
        ),
        (
            "What action must operators avoid?",
            "Operators must not open the copier cover.",
            "open the copier cover",
            True,
        ),
        (
            "Which minimum quota rule applies?",
            "Do not set the copier quota below ten sheets.",
            "the copier quota",
            True,
        ),
        (
            "How is the shuttle desk opened after confirmation?",
            (
                "Open the shuttle desk after supervisor confirmation. "
                "The shuttle travel duration is not specified."
            ),
            "Open the shuttle desk after supervisor confirmation",
            True,
        ),
        (
            "What authorizes opening?",
            "This handbook does not state an opening authority.",
            "an opening authority",
            False,
        ),
        (
            "How much does premium access cost?",
            (
                "Standard access price is not specified. "
                "Premium access costs 12 dollars."
            ),
            "12 dollars",
            True,
        ),
        (
            "What is the sampling rate?",
            ("The replacement fee is not specified. The sampling rate is 20 Hz."),
            "20 Hz",
            True,
        ),
        (
            "Who must not set the schedule?",
            "Operators do not set the schedule; the supervisor sets it.",
            "Operators",
            True,
        ),
        (
            "How much time does cooling take?",
            "Cooling takes overnight.",
            "overnight",
            True,
        ),
    ],
)
def test_reader_rejects_absent_requested_quantity_without_losing_prohibitions(
    monkeypatch, question, context, raw, answerable
):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.services.answer_reader import LocalReader

    start = context.index(raw)
    end = start + len(raw)

    class Tokenizer:
        cls_token_id = 101

        def __call__(self, *args, **kwargs):
            return _Encoding(
                input_ids=_Tensor([[101, 9, 102, 1, 2, 3, 102]]),
                offset_mapping=_Tensor(
                    [
                        [
                            (0, 0),
                            (0, 5),
                            (0, 0),
                            (start, end),
                            (start, end),
                            (start, end),
                            (0, 0),
                        ]
                    ]
                ),
                overflow_to_sample_mapping=_Tensor([0]),
            )

    def model(**kwargs):
        logits = _Tensor([[0.0, 100.0, 0.0, 5.0, 1.0, 1.0, 0.0]])
        return SimpleNamespace(start_logits=logits, end_logits=logits)

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    reader = LocalReader()
    reader._tokenizer, reader._model = Tokenizer(), model
    result = reader._context(question, context, Settings(READER_NULL_THRESHOLD=0))
    assert (result.span is not None) is answerable
    assert result.diagnostics["null_margin"] == -10.0
    if answerable:
        assert result.span.text == context
    else:
        assert result.diagnostics["decision"] == "no_answer"


@pytest.mark.parametrize(
    "prefix", ["Walk me through", "Please walk me through", "Could you walk me through"]
)
def test_procedural_imperative_preserves_all_subject_qualifiers(monkeypatch, prefix):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.services.answer_reader import LocalReader

    context = "After the supervisor signs off, open the lantern desk."
    question = (
        f"{prefix} the steps for opening the lantern desk "
        "after the supervisor signs off."
    )
    expected_question = (
        "What are the steps for opening the lantern desk "
        "after the supervisor signs off?"
    )

    class Tokenizer:
        cls_token_id = 101

        def __call__(self, text, *args, **kwargs):
            # This complete external boundary maps the actual question to logits.
            # Any qualifier lost in normalization produces a null answer.
            query_id = 10 if text == expected_question else 11
            return _Encoding(
                input_ids=_Tensor([[101, query_id, 102, 1, 2, 3, 102]]),
                offset_mapping=_Tensor(
                    [[(0, 0), (0, 5), (0, 0), (0, 53), (0, 53), (0, 53), (0, 0)]]
                ),
                overflow_to_sample_mapping=_Tensor([0]),
            )

    def model(**kwargs):
        null = 0.0 if kwargs["input_ids"].tolist()[0][1] == 10 else 20.0
        logits = _Tensor([[null, 100.0, 0.0, 5.0, 1.0, 1.0, 0.0]])
        return SimpleNamespace(start_logits=logits, end_logits=logits)

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    reader = LocalReader()
    reader._tokenizer, reader._model = Tokenizer(), model
    result = reader._context(question, context, Settings(READER_NULL_THRESHOLD=0))
    assert result.span is not None
    assert result.span.text == context


@pytest.mark.parametrize(
    "question",
    [
        "Walk me through why the gate remains closed.",
        "Walk me through whether lane access is authorized.",
        "Walk me through the duration of cooling.",
    ],
)
def test_ambiguous_walkthrough_intent_stays_unchanged(question):
    from app.services.answer_reader import reader_question

    assert reader_question(question) == question


async def test_reader_preserves_genuine_multiple_document_answers(
    real_client, monkeypatch
):
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection, reader_service

    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    first = await upload(client, "Staging rollback is authorized by Morgan.")
    second = await upload(client, "Warehouse rollback is authorized by Taylor.")

    async def reader(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=len(text), text=text), {"decision": "answer"}
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", reader)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who authorizes staging and warehouse rollback?",
            "document_ids": [first["id"], second["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["outcome"] == "completed"
    assert "Morgan" in result["answer"] and "Taylor" in result["answer"]
    assert {source["document_id"] for source in result["sources"]} == {
        first["id"],
        second["id"],
    }


@pytest.mark.parametrize("select_current,answerable", [(True, True), (False, False)])
def test_absence_check_uses_the_actual_selected_span_occurrence(
    monkeypatch, select_current, answerable
):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.services.answer_reader import LocalReader

    context = (
        "The retired guide does not specify ten minutes. "
        "The current waiting period is ten minutes."
    )
    start = (
        context.rindex("ten minutes")
        if select_current
        else context.index("ten minutes")
    )
    end = start + 11

    class Tokenizer:
        cls_token_id = 101

        def __call__(self, *args, **kwargs):
            return _Encoding(
                input_ids=_Tensor([[101, 9, 102, 1, 2, 3, 102]]),
                offset_mapping=_Tensor(
                    [
                        [
                            (0, 0),
                            (0, 5),
                            (0, 0),
                            (start, end),
                            (start, end),
                            (start, end),
                            (0, 0),
                        ]
                    ]
                ),
                overflow_to_sample_mapping=_Tensor([0]),
            )

    def model(**kwargs):
        logits = _Tensor([[0.0, 100.0, 0.0, 5.0, 1.0, 1.0, 0.0]])
        return SimpleNamespace(start_logits=logits, end_logits=logits)

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    reader = LocalReader()
    reader._tokenizer, reader._model = Tokenizer(), model
    result = reader._context(
        "What is the current waiting period?",
        context,
        Settings(READER_NULL_THRESHOLD=0),
    )
    assert (result.span is not None) is answerable
    assert result.diagnostics["raw_span"]["start"] == start


def test_absence_veto_yields_to_a_polar_question_about_the_same_verb():
    from app.services.answer_reader import support_rejection

    clause = (
        "Meridian is a symbolic puzzle only: its transform of ABC is BCA, "
        "and it does not describe a biological sample."
    )
    start = clause.index("it does not")
    end = start + len("it does not")
    assert (
        support_rejection(
            clause,
            start,
            end,
            "Does Meridian symbolic puzzle describe a biological sample?",
        )
        is None
    )


def test_absence_veto_keeps_wh_questions_and_unmatched_negated_verbs():
    from app.services.answer_reader import support_rejection

    clause = "The retired guide does not specify ten minutes."
    start = clause.index("ten minutes")
    end = start + len("ten minutes")
    assert (
        support_rejection(clause, 0, end, "How long is the wait?")
        == "selected_clause_explicitly_absent"
    )
    assert (
        support_rejection(clause, 0, end, "Does the guide state the wait?")
        == "selected_clause_explicitly_absent"
    )
    assert support_rejection(clause, 0, end, "Does the guide specify the wait?") is None
