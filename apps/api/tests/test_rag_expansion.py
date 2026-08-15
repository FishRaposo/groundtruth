"""Contracts for offline reranking, conversation memory, and local evaluation."""

from __future__ import annotations

import json
import sys
import types
import uuid

import pytest
from app.db.session import Base
from app.models.conversation import Conversation, Message
from app.models.query import QueryRequest
from app.services.conversation.memory import (
    BoundedMemoryPolicy,
    SQLConversationMemory,
    prepare_memory_context,
    select_bounded_history,
)
from app.services.evaluation.evalforge_adapter import (
    GroundTruthEvaluationAdapter,
    load_evalforge_fixture,
)
from app.services.reranking.colbert import CrossEncoderReranker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


@pytest.mark.asyncio
async def test_cross_encoder_disabled_uses_deterministic_lexical_fallback() -> None:
    relevant = _Chunk("remote work policy allows three days")
    irrelevant = _Chunk("office catering menu")
    reranker = CrossEncoderReranker(enabled=False)

    first = await reranker.rerank(
        "remote work policy",
        [(irrelevant.content, irrelevant), (relevant.content, relevant)],
    )
    second = await reranker.rerank(
        "remote work policy",
        [(irrelevant.content, irrelevant), (relevant.content, relevant)],
    )

    assert first == second
    assert first[0][0] is relevant
    assert reranker.last_method == "lexical_fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ImportError("missing"), TypeError("incompatible")])
async def test_cross_encoder_missing_optional_dependency_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    reranker = CrossEncoderReranker(enabled=True)

    def unavailable() -> None:
        raise failure

    monkeypatch.setattr(reranker, "_load_model", unavailable)
    chunk = _Chunk("grounded citations")

    result = await reranker.rerank("citations", [(chunk.content, chunk)])

    assert result[0][0] is chunk
    assert reranker.last_method == "lexical_fallback"


def test_cross_encoder_model_load_is_local_files_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            captured.update(model_name=model_name, **kwargs)

    module = types.ModuleType("sentence_transformers")
    module.CrossEncoder = FakeCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    CrossEncoderReranker(enabled=True)._load_model()

    assert captured["local_files_only"] is True


def test_old_query_request_remains_valid_and_memory_defaults_off() -> None:
    request = QueryRequest(question="What is the policy?")

    assert request.conversation_id is None
    assert request.memory_policy is BoundedMemoryPolicy.DISABLED


def test_bounded_history_keeps_latest_complete_turns_within_budget() -> None:
    history = [
        {"role": "user", "content": "old question with four words"},
        {"role": "assistant", "content": "old answer with four words"},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "new answer"},
    ]

    selected = select_bounded_history(history, max_tokens=4)

    assert selected == history[-2:]


def test_evalforge_fixture_adapter_is_dependency_free_and_deterministic(
    tmp_path: object,
) -> None:
    path = tmp_path / "suite.json"  # type: ignore[operator]
    path.write_text(  # type: ignore[attr-defined]
        json.dumps(
            {
                "name": "groundtruth-offline",
                "tests": [
                    {
                        "id": "citation-case",
                        "input": "What is the policy?",
                        "expected": "Remote work is allowed [1].",
                        "actual": "Remote work is allowed [1].",
                        "judges": ["semantic_match", "citation"],
                    },
                    {
                        "id": "refusal-case",
                        "input": "What is not documented?",
                        "actual": "I cannot answer from the available evidence.",
                        "judges": ["refusal"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    suite = load_evalforge_fixture(path)
    adapter = GroundTruthEvaluationAdapter()
    first = adapter.evaluate_sync(suite)
    second = adapter.evaluate_sync(suite)

    assert first == second
    assert first["suite"] == "groundtruth-offline"
    assert first["summary"] == {"passed": 2, "failed": 0, "total": 2}
    assert first["tests"][0]["id"] == "citation-case"
    assert first["tests"][0]["passed"] is True


def test_evalforge_fixture_rejects_duplicate_test_ids(tmp_path: object) -> None:
    path = tmp_path / "suite.json"  # type: ignore[operator]
    path.write_text(  # type: ignore[attr-defined]
        json.dumps(
            {
                "name": "duplicates",
                "tests": [
                    {"id": "same", "input": "one", "actual": "one"},
                    {"id": "same", "input": "two", "actual": "two"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate test id: same"):
        load_evalforge_fixture(path)


def test_query_request_accepts_additive_conversation_fields() -> None:
    conversation_id = uuid.uuid4()
    request = QueryRequest(
        question="Follow up",
        conversation_id=conversation_id,
        memory_policy="recent",
        memory_max_tokens=512,
    )

    assert request.conversation_id == conversation_id
    assert request.memory_policy is BoundedMemoryPolicy.RECENT
    assert request.memory_max_tokens == 512


@pytest.mark.asyncio
async def test_sql_conversation_memory_persists_and_selects_recent_turns() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[Conversation.__table__, Message.__table__],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        conversation = Conversation(title="Test")
        session.add(conversation)
        await session.commit()

        memory = SQLConversationMemory(session)
        await memory.append(
            str(conversation.id), {"role": "user", "content": "old question"}
        )
        await memory.append(
            str(conversation.id), {"role": "assistant", "content": "old answer"}
        )
        await memory.append(
            str(conversation.id), {"role": "user", "content": "latest question"}
        )
        await memory.append(
            str(conversation.id), {"role": "assistant", "content": "latest answer"}
        )
        await session.commit()

        assert await memory.recent(str(conversation.id), max_tokens=4) == [
            {"role": "user", "content": "latest question"},
            {"role": "assistant", "content": "latest answer"},
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_context_reads_before_persisting_current_question() -> None:
    calls: list[str] = []

    class FakeMemory:
        async def recent(
            self, conversation_id: str, *, max_tokens: int
        ) -> list[dict[str, str]]:
            calls.append(f"recent:{conversation_id}:{max_tokens}")
            return [{"role": "user", "content": "Earlier question"}]

        async def append(self, conversation_id: str, message: dict[str, str]) -> None:
            calls.append(f"append:{conversation_id}:{message['content']}")

    context = await prepare_memory_context(
        conversation_id="conversation-1",
        policy=BoundedMemoryPolicy.RECENT,
        max_tokens=50,
        question="Current question",
        memory=FakeMemory(),  # type: ignore[arg-type]
    )

    assert context == "Conversation history:\nUser: Earlier question"
    assert calls == [
        "recent:conversation-1:50",
        "append:conversation-1:Current question",
    ]
