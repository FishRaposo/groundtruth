"""GroundTruth demo: one cited answer and one refusal on the real pipeline.

Runs fully offline (in-memory SQLite, deterministic hash embeddings, the
offline generator; no Postgres, Redis, model download or API key) through the
same services the ``POST /api/documents/upload`` and ``POST /api/queries``
handlers use:

    IngestionService -> RetrievalService (vector + keyword, RRF)
    -> RerankingService -> RefusalService (REFUSAL_CONFIDENCE_THRESHOLD)
    -> GenerationService -> CitationService

It ingests ``data/sample/refund_policy.md``, asks one question the policy
answers and one it doesn't, and prints the decision for each. Exits 1 if the
pipeline doesn't produce exactly that: a cited answer, then a refusal.
"""

# The demo selects this checkout's API package and configures the offline
# runtime before importing it: settings and the database engine are created
# when the application modules load.
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import tempfile
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
SAMPLE = REPO_ROOT / "data" / "sample" / "refund_policy.md"
sys.path.insert(0, str(API_ROOT))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""
os.environ["APP_ENV"] = "test"
os.environ["EMBEDDING_MODE"] = "deterministic"
os.environ["GENERATION_MODE"] = "legacy"

import structlog
from loguru import logger

# Keep the demo output to the table: silence library logging before import.
logger.remove()
logging.disable(logging.CRITICAL)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
)

from app.config import get_settings
from app.db.session import AsyncSessionLocal, init_db
from app.models.document import Document, DocumentStatus, SourceType
from app.services.citation import citation_service
from app.services.generation import generation_service
from app.services.ingestion import ingestion_service
from app.services.refusal import refusal_service
from app.services.reranking import reranking_service
from app.services.retrieval import retrieval_service

ANSWERABLE = "How many days do I have to request a refund?"
UNANSWERABLE = "What are the salary bands?"
SOURCES_SHOWN = 3
ANSWER_WIDTH = 160


@dataclass
class Outcome:
    """What the pipeline decided for one question."""

    question: str
    refused: bool
    confidence: float
    answer: str | None
    reason: str = ""
    sources: list[dict[str, object]] = field(default_factory=list)


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


async def ingest(path: Path) -> Document:
    """Store ``path`` the way the upload handler does, then run ingestion."""
    async with AsyncSessionLocal() as session:
        document = Document(
            title=path.name,
            source_type=SourceType.MARKDOWN,
            status=DocumentStatus.PENDING,
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    # The upload handler writes data/uploads/<id>/<id><ext> under the working
    # directory and ingestion reads it back from there.
    stored = Path("data", "uploads", str(document_id), f"{document_id}{path.suffix}")
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(path.read_bytes())
    await ingestion_service.process_document(document_id)

    async with AsyncSessionLocal() as session:
        loaded = await session.get(Document, document_id)
        assert loaded is not None
        return loaded


async def ask(question: str) -> Outcome:
    """Run the ``POST /api/queries`` decision path for one question."""
    settings = get_settings()
    chunks = await retrieval_service.retrieve(
        query=question, top_k=settings.RETRIEVAL_TOP_K
    )
    reranked = await reranking_service.rerank(query=question, chunks=chunks)
    confidence = sum(c.relevance_score for c in reranked) / max(len(reranked), 1)
    refused, reason = refusal_service.should_refuse(
        query=question, chunks=reranked, confidence=confidence
    )
    if refused:
        return Outcome(question, True, confidence, None, reason=reason)

    answer, _usage = await generation_service.generate_answer(
        query=question, context=[c.content for c in reranked], sources=[]
    )
    citations = await citation_service.assemble_citations(
        chunks=reranked, answer=answer
    )
    return Outcome(
        question,
        False,
        confidence,
        answer,
        sources=[c.model_dump(mode="json") for c in citations],
    )


async def run_demo() -> tuple[Document, list[Outcome]]:
    """Ingest the sample policy and ask both questions."""
    await init_db()
    with tempfile.TemporaryDirectory() as workdir, _working_directory(Path(workdir)):
        document = await ingest(SAMPLE)
    outcomes = [await ask(ANSWERABLE), await ask(UNANSWERABLE)]
    return document, outcomes


def _one_line(text: str, width: int) -> str:
    # Present Markdown headings as prose; stored chunks and citations stay exact.
    prose = re.sub(r"(?<!\S)#{1,6}\s+", "", text)
    return textwrap.shorten(" ".join(prose.split()), width=width, placeholder="...")


def render(document: Document, outcomes: list[Outcome]) -> str:
    """Format the demo result as a plain-text table."""
    threshold = get_settings().REFUSAL_CONFIDENCE_THRESHOLD
    lines = [
        "GroundTruth demo: offline, real retrieval/refusal/citation services",
        f"Corpus: {SAMPLE.relative_to(REPO_ROOT).as_posix()} -> "
        f"{document.chunk_count} chunks ({document.status.value})",
        f"Refusal gate: confidence < {threshold:.2f} -> refuse",
        "",
        f"{'Question':<46}  {'Decision':<8}  {'Confidence':>10}  {'Sources':>7}",
        f"{'-' * 46}  {'-' * 8}  {'-' * 10}  {'-' * 7}",
    ]
    for outcome in outcomes:
        decision = "REFUSED" if outcome.refused else "ANSWERED"
        lines.append(
            f"{outcome.question:<46}  {decision:<8}  "
            f"{outcome.confidence:>10.3f}  {len(outcome.sources):>7}"
        )
    for outcome in outcomes:
        lines.append("")
        lines.append(f"Q: {outcome.question}")
        if outcome.refused:
            lines.append(f"   Refused: {outcome.reason}")
            continue
        lines.append(f"   Answer: {_one_line(outcome.answer or '', ANSWER_WIDTH)}")
        shown = outcome.sources[:SOURCES_SHOWN]
        for source in shown:
            lines.append(
                f"   [{source['citation_index']}] {source['document_title']} "
                f"score {source['relevance_score']:.3f}  "
                f'"{_one_line(str(source["content_preview"]), 80)}"'
            )
        if len(outcome.sources) > len(shown):
            lines.append(f"   ... {len(outcome.sources) - len(shown)} more cited")
    return "\n".join(lines)


def main() -> int:
    document, outcomes = asyncio.run(run_demo())
    print(render(document, outcomes))
    answered, refused = outcomes
    ok = (
        not answered.refused
        and bool(answered.sources)
        and "[1]" in (answered.answer or "")
        and refused.refused
        and not refused.sources
    )
    print()
    print(
        "Demo complete: one cited answer, one refusal."
        if ok
        else "Demo FAILED: expected one cited answer and one refusal."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
