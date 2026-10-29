"""Immutable request proposals only; no reading-policy or publication registry."""

import json
from dataclasses import asdict, dataclass


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


@dataclass(frozen=True)
class Literal:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class RequestNode:
    id: str
    kind: str
    operation: str
    evidence: tuple[Literal, ...]
    head_indices: tuple[int, ...]
    token_indices: tuple[int, ...]
    scopes: tuple[Literal, ...] = ()
    feature_json: str = "{}"
    proposed_question: str = ""
    grammar: str = "unknown"


@dataclass(frozen=True)
class DeferredSlot:
    id: str
    kind: str
    node_id: str
    evidence: tuple[Literal, ...]
    parameters_json: str


@dataclass(frozen=True)
class HardUnknown:
    reason: str
    evidence: tuple[Literal, ...]
    head_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class RequestEdge:
    kind: str
    source_id: str
    target_id: str
    evidence: tuple[Literal, ...]


@dataclass(frozen=True)
class TokenUse:
    token: Literal
    whitespace: str
    owners: tuple[str, ...]


@dataclass(frozen=True)
class PartialRequest:
    question: str
    question_sha256: str
    capture_sha256: str
    raw_capture_json: str
    nodes: tuple[RequestNode, ...]
    deferred: tuple[DeferredSlot, ...]
    unknowns: tuple[HardUnknown, ...]
    edges: tuple[RequestEdge, ...]
    tokens: tuple[TokenUse, ...]
    features_json: str
    frame_proposals_json: str

    def record(self):
        return json.loads(
            canonical(dict(contract="partial-request-obligations-v1", **asdict(self)))
        )
