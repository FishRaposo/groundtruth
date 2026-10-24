"""Request-local retrieval through the caller's database and authorized scope.

Portable mode performs exact ranking over SQL-scoped rows. PostgreSQL uses the
same WHERE predicates in indexed FTS/vector statements. No global top-K filter.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk, ChunkWithScore
from app.models.collection import collection_documents
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.services.access_control.scope import Principal, document_scope
from app.services.embedding import embedding_service
from app.services.reranking import reranking_service

STOP_WORDS = frozenset(
    (
        "a an the is are was were what which how when where why who"
        " to of for in on and or do does should can i we my our "
        "please about with from it its this that be by as into"
    ).split()
)


def terms(text: str) -> set[str]:
    text = re.sub(r"\broll[\s-]+back\b", "rollback", text, flags=re.I)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOP_WORDS
    }


def support_terms(text: str) -> set[str]:
    """Conservative lexical coverage contract, separate from retrieval rank.

    Question framing words do not establish a requested fact. Remaining literal
    anchors must mostly occur in the extracted passage; this is not entailment.
    """
    framing = set(
        (
            "during must before after happens start name first action "
            "many give duration long often interval state periodic "
            "schedule number team s"
        ).split()
    )
    aliases = {
        "observe": "observation",
        "paused": "pause",
        "reviewed": "review",
        "accounts": "account",
        "minutes": "minute",
        "days": "day",
    }
    return {aliases.get(word, word) for word in terms(text) - framing}


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions differ; explicit reindexing required.")
    denominator = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        if denominator
        else 0.0
    )


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[ChunkWithScore]
    vector_count: int
    keyword_count: int
    elapsed_ms: float
    method: str
    provenance: dict[str, Any]


async def retrieve_scoped(  # noqa: C901 - four explicit retrieval methods/dialects
    db: AsyncSession,
    query: str,
    *,
    principal: Principal | None = None,
    document_ids: list[uuid.UUID] | None = None,
    collection_ids: list[uuid.UUID] | None = None,
    top_k: int = 5,
    method: str = "reranked",
) -> RetrievalResult:
    started = time.perf_counter()
    predicates = [Document.status == DocumentStatus.READY]
    if principal is not None:
        predicates.append(document_scope(principal))
        # A READY legacy row is not proof that its current chunks were published
        # with an immutable, hashed snapshot. New HTTP answers fail closed until
        # that publication exists; administrators may still inspect old records.
        predicates.extend(
            [
                Document.version_number > 0,
                func.length(Document.content_hash) == 64,
                Chunk.metadata_["document_version"].as_integer()
                == Document.version_number,
                select(DocumentVersion.id)
                .where(
                    DocumentVersion.document_id == Document.id,
                    DocumentVersion.workspace_id == Document.workspace_id,
                    DocumentVersion.version_number == Document.version_number,
                    DocumentVersion.content_hash == Document.content_hash,
                )
                .exists(),
            ]
        )
    if document_ids is not None:
        predicates.append(Document.id.in_(document_ids))
    if collection_ids is not None:
        predicates.append(
            Document.id.in_(
                select(collection_documents.c.document_id).where(
                    collection_documents.c.collection_id.in_(collection_ids)
                )
            )
        )
    statement = (
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(*predicates)
    )
    signature = embedding_service.signature
    query_terms = terms(query)
    keyword: list[tuple[str, float]] = []
    vector: list[tuple[str, float]] = []
    postgres = db.get_bind().dialect.name == "postgresql"
    indexed_rows = None
    if postgres:
        indexed_rows = await postgres_candidates(
            db, statement, query, signature, top_k * 4, method
        )
        rows, vector, keyword = indexed_rows
    else:
        rows = list((await db.execute(statement)).all())
    # An unknown legacy signature is not silently treated as this model.
    compatible = [
        (chunk, doc)
        for chunk, doc in rows
        if (chunk.metadata_ or {}).get("embedding_signature") == signature
    ]
    if not postgres and method in {"vector", "hybrid", "reranked"}:
        if rows and not compatible:
            raise ValueError(
                (
                    "No compatible indexed embeddings in the selected scope. "
                    "Explicitly reindex these documents for the configured "
                    "model."
                )
            )
        embedding = await embedding_service.embed_query(query)
        for chunk, _doc in compatible:
            if chunk.embedding is not None:
                vector.append(
                    (str(chunk.id), max(0.0, cosine(embedding, chunk.embedding)))
                )
        vector.sort(key=lambda pair: (-pair[1], pair[0]))
    for chunk, _doc in rows if not postgres else []:
        overlap = len(query_terms & terms(chunk.content)) / max(len(query_terms), 1)
        if overlap:
            keyword.append((str(chunk.id), overlap))
    keyword.sort(key=lambda pair: (-pair[1], pair[0]))
    candidate_limit = top_k * 4
    vector = vector[:candidate_limit]
    keyword = keyword[:candidate_limit]
    score_map: dict[str, float] = {}
    if method == "keyword":
        score_map = dict(keyword)
    elif method == "vector":
        score_map = dict(vector)
    else:
        for candidates in (vector, keyword):
            for rank, (identifier, _score) in enumerate(candidates):
                score_map[identifier] = score_map.get(identifier, 0.0) + 1 / (61 + rank)
        score_map = {
            identifier: score * 61 / 2 for identifier, score in score_map.items()
        }
    by_id = {str(chunk.id): (chunk, doc) for chunk, doc in rows}
    chunks = []
    for identifier in sorted(score_map, key=lambda key: (-score_map[key], key))[
        :candidate_limit
    ]:
        chunk, doc = by_id[identifier]
        chunks.append(
            ChunkWithScore(
                id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                metadata={
                    **(chunk.metadata_ or {}),
                    "document_title": doc.title,
                    "document_version": doc.version_number,
                    "content_hash": doc.content_hash,
                    "conflict_group": (doc.metadata_ or {}).get("conflict_group"),
                },
                relevance_score=score_map[identifier],
            )
        )
    if method == "reranked":
        chunks = await reranking_service.rerank(query, chunks)
    return RetrievalResult(
        chunks[:top_k],
        len(vector),
        len(keyword),
        (time.perf_counter() - started) * 1000,
        method,
        {
            "embedding": signature,
            "retrieval_method": method,
            "ranking": "heuristic lexical reranking"
            if method == "reranked"
            else method,
            "index": "postgresql-pgvector-fts-scoped"
            if postgres
            else "portable-scoped-exact",
            "generation_method": "source-extractive",
        },
    )


async def postgres_candidates(
    db: AsyncSession,
    scoped_statement,
    query: str,
    signature: dict[str, Any],
    limit: int,
    method: str,
):
    """Both indexed candidate queries retain the complete authorized WHERE.

    The local milestone does not claim these statements ran on this host.
    PostgreSQL integration tests must prove their natural planner/recall behavior.
    """
    from sqlalchemy import bindparam

    from app.db.vector_type import Vector384

    vector, keyword = [], []
    selected = {}
    if method in {"vector", "hybrid", "reranked"}:
        if signature["dimension"] != 384:
            raise ValueError(
                (
                    "PostgreSQL indexed vector retrieval requires the pinned "
                    "384-dimensional local model."
                )
            )
        embedding = await embedding_service.embed_query(query)
        distance = Chunk.embedding_vector.op(
            "<=>", return_type=__import__("sqlalchemy").Float()
        )(bindparam("query_vector", value=embedding, type_=Vector384()))
        compatible = scoped_statement.where(
            Chunk.embedding_vector.isnot(None),
            Chunk.metadata_["embedding_signature"]["revision"].as_string()
            == signature["revision"],
        )
        # pgvector >=0.8 iterates filtered ANN candidates instead of dropping
        # rows after a global top-K. Scoped exact fallback handles sparse scopes.
        await db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
        ranked = list(
            (
                await db.execute(
                    compatible.add_columns(distance.label("distance"))
                    .order_by(distance)
                    .limit(limit)
                )
            ).all()
        )
        if len(ranked) < limit:
            ranked = list(
                (
                    await db.execute(
                        compatible.add_columns(distance.label("distance"))
                        .order_by(distance + 0.0)
                        .limit(limit)
                    )
                ).all()
            )
        for chunk, doc, value in cast(list[Any], ranked):
            selected[str(chunk.id)] = (chunk, doc)
            vector.append((str(chunk.id), max(0.0, 1.0 - float(value))))
        if not ranked and await db.scalar(select(scoped_statement.exists())):
            raise ValueError(
                "No compatible vectors in selected scope; explicitly reindex documents."
            )
    if method in {"keyword", "hybrid", "reranked"}:
        document = func.to_tsvector(literal_column("'english'"), Chunk.content)
        question = func.websearch_to_tsquery(literal_column("'english'"), query)
        rank = func.ts_rank_cd(document, question)
        ranked = list(
            (
                await db.execute(
                    scoped_statement.add_columns(rank.label("rank"))
                    .where(document.op("@@")(question))
                    .order_by(rank.desc())
                    .limit(limit)
                )
            ).all()
        )
        for chunk, doc, value in cast(list[Any], ranked):
            selected[str(chunk.id)] = (chunk, doc)
            keyword.append((str(chunk.id), float(value)))
    return list(selected.values()), vector, keyword
