"""Immutable contextual-v2 request plan, reconstructed from actual dependencies.

The model graph proposes syntax. Closed declared frames retain every original
argument; unknown language stays atomic and blocks global request resolution.
No source support, authorization or model truth follows from request resolution.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from app.services.answer_requirements import Requirement, _requirement_anchors
from app.services.dependency_frames import ConditionClause, resolve_frames
from app.services.request_parser import validate_capture

CONTRACT = "linguistic-request-plan-v1"
PROFILE = "contextual_source_v2"
MAX_REQUIREMENTS = 8


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


@dataclass(frozen=True)
class LiteralRange:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class RequirementUse:
    requirement_id: str
    original: LiteralRange
    scopes: tuple[LiteralRange, ...] = ()
    conditions: tuple[LiteralRange, ...] = ()
    modality: tuple[LiteralRange, ...] = ()
    units: tuple[LiteralRange, ...] = ()
    governors: tuple[LiteralRange, ...] = ()
    references: tuple[LiteralRange, ...] = ()
    order_after: tuple[str, ...] = ()
    order_evidence: tuple[LiteralRange, ...] = ()
    scope_kind: str = "unresolved"
    grammar: str = "unresolved"
    head_token_indices: tuple[int, ...] = ()
    consumed_token_indices: tuple[int, ...] = ()
    extent: str = "unspecified"
    condition_ast: tuple[ConditionClause, ...] = ()


@dataclass(frozen=True)
class Unresolved:
    reason: str
    evidence: tuple[LiteralRange, ...]


@dataclass(frozen=True)
class TokenConsumption:
    evidence: LiteralRange
    role: str
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class RequestPlan:
    question: str
    requirements: tuple[Requirement, ...]
    uses: tuple[RequirementUse, ...]
    unresolved: tuple[Unresolved, ...]
    consumption: tuple[TokenConsumption, ...] = ()
    graph_sha256: str = ""
    capture_sha256: str = ""
    model_identity_json: str = ""
    question_sha256: str = ""
    graph_json: str = ""

    @property
    def resolved_request(self) -> bool:
        return bool(self.requirements) and not self.unresolved

    def record(self):
        return json.loads(
            _canonical(
                dict(
                    contract=CONTRACT,
                    reading_profile=PROFILE,
                    support_or_permissions="NOT_ASSESSED",
                    resolved_request=self.resolved_request,
                    **asdict(self),
                )
            )
        )


def _range(span):
    return LiteralRange(*span)


def _ranges(spans):
    return tuple(_range(s) for s in spans)


def _consumption(question, annotation, frames, syntax):
    rows = []
    for token in annotation["tokens"]:
        index = token["i"]
        owners = tuple(f"r{n + 1}" for n, f in enumerate(frames) if index in f.tokens)
        role = "declared_frame_syntax" if index in syntax else "request_argument"
        if any(f.errors and index in f.tokens for f in frames):
            role = "unresolved_argument"
        for name in (
            "conditions",
            "modality",
            "units",
            "governors",
            "references",
            "scopes",
        ):
            if any(
                s.start <= token["start"] and token["end"] <= s.end
                for f in frames
                for s in getattr(f, name)
            ):
                role = name
                break
        rows.append(
            TokenConsumption(
                LiteralRange(
                    token["start"],
                    token["end"],
                    question[token["start"] : token["end"]],
                ),
                role,
                owners,
            )
        )
    return tuple(rows)


def plan_request(question, capture) -> RequestPlan:
    annotation = validate_capture(question, capture)
    frames, syntax = resolve_frames(question, annotation)
    requirements, uses, unresolved = [], [], []
    frame_rids = {}
    for n, frame in enumerate(frames):
        frame_rids[n] = len(requirements) + 1
        kinds = (
            ("owner", "deputy")
            if frame.kind == "role_pair" and not frame.errors
            else ("generic" if frame.errors else frame.kind,)
        )
        for kind in kinds:
            prev_rid = f"r{len(requirements)}" if requirements else ""
            rid = f"r{len(requirements) + 1}"
            prepared = frame.question
            if frame.kind == "role_pair" and frame.topic:
                prepared = (
                    f"Who leads {frame.topic}?"
                    if kind == "owner"
                    else f"Who is the deputy for {frame.topic}?"
                )
            requirements.append(
                Requirement(
                    rid,
                    frame.original.text,
                    frame.original.start,
                    frame.original.end,
                    prepared,
                    kind,
                    frame.topic,
                    _requirement_anchors(frame.topic),
                    tuple(f"r{frame_rids[i]}" for i in frame.dependencies),
                    frame.relation,
                    frame.attribute,
                    source_workspace=frame.source_workspace,
                )
            )
            uses.append(
                RequirementUse(
                    rid,
                    _range(frame.original),
                    _ranges(frame.scopes),
                    _ranges(frame.conditions),
                    _ranges(frame.modality),
                    _ranges(frame.units),
                    _ranges(frame.governors),
                    _ranges(frame.references),
                    (prev_rid,) if frame.order and prev_rid else (),
                    _ranges(frame.order),
                    "session"
                    if re.search(r"\bsessions?\b", frame.topic, re.I)
                    else "activity"
                    if frame.topic
                    else "unresolved",
                    frame.grammar,
                    frame.heads,
                    frame.tokens,
                    "whole_requested"
                    if frame.kind == "procedure"
                    and "procedure_extent_not_declared" not in frame.errors
                    else "unspecified",
                    frame.condition_ast,
                )
            )
        unresolved.extend(
            Unresolved(reason, (_range(frame.original),)) for reason in frame.errors
        )
    if len(requirements) > MAX_REQUIREMENTS:
        unresolved.append(
            Unresolved(
                "requirement_budget_exceeded",
                (LiteralRange(0, len(question), question),),
            )
        )
    return RequestPlan(
        question,
        tuple(requirements),
        tuple(uses),
        tuple(unresolved),
        _consumption(question, annotation, frames, syntax),
        capture["annotation_sha256"],
        capture["capture_sha256"],
        _canonical(capture["parser"]),
        hashlib.sha256(question.encode()).hexdigest(),
        _canonical(annotation),
    )


def validate_request_plan(record, *, question, capture) -> bool:
    try:
        return type(record) is dict and _canonical(record) == _canonical(
            plan_request(question, capture).record()
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ):
        return False
