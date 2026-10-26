"""Immutable discovery lineage, separate from reader observations and support."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from app.evidence_policy import ORIGIN_CONTRACT


@dataclass(frozen=True)
class QAObservation:
    observation_id: str
    requirement_id: str
    chunk_id: str
    payload: str

    @classmethod
    def capture(
        cls,
        requirement_id: str,
        chunk: Any,
        prediction: Any,
        *,
        question: str | None = None,
        reader_identity: dict[str, Any] | None = None,
    ) -> QAObservation:
        payload = json.dumps(
            {
                "span": prediction.span.model_dump() if prediction.span else None,
                "diagnostics": prediction.diagnostics,
                "question": question,
                "reader": reader_identity,
            },
            sort_keys=True,
            allow_nan=False,
        )
        key = f"{requirement_id}:{chunk.id}:{payload}"
        return cls(
            hashlib.sha256(key.encode()).hexdigest(),
            requirement_id,
            str(chunk.id),
            payload,
        )

    def record(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "requirement_id": self.requirement_id,
            "chunk_id": self.chunk_id,
            **json.loads(self.payload),
        }


def qa_raw_candidates(diagnostic: dict[str, Any]) -> list[dict[str, Any]]:
    """The unchanged reader raw-candidate shape and three-candidate budget."""
    choices = diagnostic.get("raw_candidates")
    if choices is None:
        parts = diagnostic.get("parts", [])
        if diagnostic.get("part_count", 1) == 1 and parts:
            diagnostic = parts[0]
        choices = diagnostic.get("raw_candidates")
    if choices is None:
        raw = diagnostic.get("raw_span")
        choices = (
            [{**raw, "null_margin": diagnostic.get("null_margin")}]
            if isinstance(raw, dict)
            else []
        )
    return choices[:3]


@dataclass(frozen=True)
class EvidenceProposal:
    proposal_id: str
    requirement_id: str
    origin: Literal["qa_reader", "source_pattern"]
    document_id: str
    document_version: int
    content_hash: str
    chunk_id: str
    chunk_start: int
    chunk_end: int
    document_start: int
    document_end: int
    text: str
    pattern_id: str | None = None
    grammar_version: str | None = None
    qa_observation_id: str | None = None

    def record(self) -> dict[str, Any]:
        return {
            "contract": ORIGIN_CONTRACT,
            "proposal_id": self.proposal_id,
            "requirement_id": self.requirement_id,
            "origin": self.origin,
            "document_id": self.document_id,
            "document_version": self.document_version,
            "content_hash": self.content_hash,
            "chunk_id": self.chunk_id,
            "chunk_range": {"start": self.chunk_start, "end": self.chunk_end},
            "document_range": {"start": self.document_start, "end": self.document_end},
            "text": self.text,
            "pattern_id": self.pattern_id,
            "grammar_version": self.grammar_version,
            "qa_observation_id": self.qa_observation_id,
        }


def validate_source(source: Any) -> None:
    """Defense in depth after the SQL/current immutable-source resolver."""
    identity = source.identity
    if (
        type(identity.get("document_version")) is not int
        or identity["document_version"] < 1
        or hashlib.sha256(source.body.encode()).hexdigest()
        != identity.get("content_hash")
    ):
        raise ValueError("proposal_source_identity_invalid")
    for item in source.chunks:
        metadata = item.chunk.metadata or {}
        if (
            str(item.chunk.document_id) != identity.get("document_id")
            or metadata.get("document_version") != identity["document_version"]
            or metadata.get("content_hash") != identity["content_hash"]
            or type(item.start) is not int
            or type(item.end) is not int
            or not 0 <= item.start < item.end <= len(source.body)
            or item.end - item.start != len(item.chunk.content)
            or source.body[item.start : item.end] != item.chunk.content
        ):
            raise ValueError("proposal_source_mapping_invalid")


def make_proposal(
    requirement_id: str,
    source: Any,
    chunk: Any,
    start: int,
    end: int,
    *,
    origin: Literal["qa_reader", "source_pattern"],
    pattern_id: str | None = None,
    grammar_version: str | None = None,
    observation: QAObservation | None = None,
) -> EvidenceProposal:
    validate_source(source)
    located = next((item for item in source.chunks if item.chunk.id == chunk.id), None)
    if (
        located is None
        or located.chunk.content != chunk.content
        or located.chunk.document_id != chunk.document_id
        or (located.chunk.metadata or {}).get("document_version")
        != (chunk.metadata or {}).get("document_version")
        or (located.chunk.metadata or {}).get("content_hash")
        != (chunk.metadata or {}).get("content_hash")
        or type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(chunk.content)
    ):
        raise ValueError("proposal_origin_mapping_invalid")
    if origin == "qa_reader":
        if (
            observation is None
            or observation.chunk_id != str(chunk.id)
            or observation.requirement_id != requirement_id
            or pattern_id is not None
            or grammar_version is not None
        ):
            raise ValueError("proposal_qa_lineage_invalid")
        observed = observation.record()
        if not isinstance(observed.get("span"), dict):
            raise ValueError("proposal_qa_lineage_invalid")
        diagnostics = observed["diagnostics"]
        raw = qa_raw_candidates(diagnostics)
        if not any(
            isinstance(item, dict)
            and item.get("start") == start
            and item.get("end") == end
            for item in raw
        ):
            raise ValueError("proposal_qa_lineage_invalid")
    elif (
        origin != "source_pattern"
        or not pattern_id
        or not grammar_version
        or observation is not None
    ):
        raise ValueError("proposal_pattern_lineage_invalid")
    text = chunk.content[start:end]
    key = (
        f"{requirement_id}:{origin}:{chunk.id}:{start}:{end}:{pattern_id}:{observation}"
    )
    return EvidenceProposal(
        hashlib.sha256(key.encode()).hexdigest(),
        requirement_id,
        origin,
        str(chunk.document_id),
        source.identity["document_version"],
        source.identity["content_hash"],
        str(chunk.id),
        start,
        end,
        located.start + start,
        located.start + end,
        text,
        pattern_id,
        grammar_version,
        observation.observation_id if observation else None,
    )
