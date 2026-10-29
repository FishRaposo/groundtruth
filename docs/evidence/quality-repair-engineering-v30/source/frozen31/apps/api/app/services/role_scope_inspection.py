"""Complete bounded document-first scope for ordinary-session role inspection.

Retrieval rank and chunk existence cannot establish absence of an exception.
This module captures immutable source bodies and the complete authorized current
universe. It does not decide whether any body supports a role assignment.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cancellation import complete_read
from app.models.chunk import Chunk, ChunkWithScore
from app.models.document import Document, DocumentVersion
from app.models.query import QueryRequest
from app.services.access_control.scope import Principal, published_document_scope
from app.services.document.source_context import validated_snapshot_context
from app.services.retrieval.scoped import scored_chunk

ROLE_READ_SET_CONTRACT = "role-scope-inspection-read-set-v1"
MAX_ROLE_DOCUMENTS = 64
MAX_ROLE_BODY_BYTES = 128 * 1024
MAX_ROLE_TOTAL_BYTES = 512 * 1024
MAX_ROLE_CHUNKS = 256
_ROLE_QUALIFIERS = re.compile(
    r"\b(?:if|when|unless|except|provided|subject|only|must|may|can|requires?|"
    r"not|never|after|before|until|during|without)\b",
    re.I,
)
# Inspection needs a complete nominal designator, unlike discovery's deliberately
# free-form argument capture. These are grammatical noun heads, never aliases for
# a requested lead/deputy relation. Unknown titles remain unresolved.
_ROLE_NOUN_HEADS = frozenset(
    "administrator agent analyst archivist assistant auditor captain chair chief "
    "clerk controller coordinator custodian delegate deputy director editor engineer "
    "facilitator head inspector lead librarian manager marshal member moderator "
    "officer operator owner president recorder registrar representative reviewer "
    "secretary specialist steward supervisor technician witness".split()
)
_ROLE_NOMINAL_MODIFIERS = frozenset({"assistant", "chief", "deputy"})
_NOMINAL_FUNCTION_WORDS = frozenset(
    "a an the this that these those each every any all some no either neither "
    "other another "
    "and but or nor if then else once as than so because although though while "
    "when whenever where wherever unless until whether how why what which who "
    "whose whom it they he she we you I is are was were be been being am "
    "does do did has have had must may might can could shall should will would "
    "to for from in on at by with without under over upon despite via per "
    "after before during since through between among of".casefold().split()
)


def _verbal_ing(word: str) -> bool:
    # A productive suffix needs a stem nucleus; lexical ring/string/spring are
    # not participles merely because their spelling contains the letters "ing".
    return re.search(r"[aeiouy].*ing$", word, re.I) is not None


def _nominal_words(words: list[str], *, attributive: bool = False) -> bool:
    return bool(words) and all(
        re.fullmatch(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", word)
        and word.casefold() not in _NOMINAL_FUNCTION_WORDS
        and not word.casefold().endswith(("ly", "ed"))
        and (attributive or not _verbal_ing(word))
        for word in words
    )


def _role_noun_head(word: str) -> bool:
    return (
        word.casefold() in _ROLE_NOUN_HEADS
        or re.fullmatch(r"[^\W\d_]{3,}(?:er|or|ist|ian)", word, re.I) is not None
    )


def _terminal_role_nominal(words: list[str]) -> bool:
    """A complete noun compound, with a basic or productive agent-noun head.

    Occupational suffixes describe a grammatical noun class, not a list of
    source-specific titles or aliases. Every modifier must remain nominal;
    clauses, conjunctions and adverbial tails cannot join this class. Attributive
    gerunds may precede a role head, but a participle after an existing role head
    is unresolved governing prose rather than a newly invented compound title.
    """
    if not _nominal_words(words, attributive=True) or not _role_noun_head(words[-1]):
        return False
    role_seen = False
    for word in words[:-1]:
        if role_seen and _verbal_ing(word):
            return False
        role_seen |= (
            _role_noun_head(word) and word.casefold() not in _ROLE_NOMINAL_MODIFIERS
        )
    return True


def _complete_role_designator(value: str) -> bool:
    """Consume an entire bounded title, proper name or explicitly quoted label.

    A title closes at its terminal noun head. An internal noun may modify that
    head (as in a compound); it does not truncate the title. Only an ``of`` nominal
    complement and the existing literal workspace qualifier may follow. Thus an
    arbitrary tail cannot become a modifier because a broad binder copied it.
    This is intentionally narrower than general English noun-phrase parsing.
    """
    value = re.sub(r"^(?:the|a|an)\s+", "", value.strip(), flags=re.I)
    workspace = re.fullmatch(r"(.+?)\s+in\s+workspace\s+[\w-]+", value, re.I)
    if workspace:
        value = workspace.group(1)
    if re.fullmatch(r'"[^"\n]+"|“[^”\n]+”', value):
        return True
    nominal = re.split(r"\s+of\s+", value, maxsplit=1, flags=re.I)
    words = nominal[0].split()
    if _terminal_role_nominal(words):
        return len(nominal) == 1 or _nominal_words(nominal[1].split())
    # Unquoted names have an explicit lexical shape; lowercase prose cannot be
    # swept into them. A recognized title never falls through to this branch.
    return (
        len(nominal) == 1
        and _nominal_words(words)
        and all(word[0].isupper() for word in words)
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RoleScopeSource:
    body: str
    identity_json: str
    metadata_json: str
    chunks_json: str = "[]"

    @property
    def identity(self) -> dict[str, Any]:
        return json.loads(self.identity_json)

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json)

    @property
    def chunks(self) -> tuple[ChunkWithScore, ...]:
        return tuple(
            ChunkWithScore.model_validate(item) for item in json.loads(self.chunks_json)
        )


@dataclass(frozen=True)
class RoleScopeManifest:
    sources: tuple[RoleScopeSource, ...]
    read_set: dict[str, Any]

    @property
    def complete(self) -> bool:
        return self.read_set["complete"] is True

    @property
    def reason(self) -> str | None:
        return self.read_set["reason"]

    def record(self) -> dict[str, Any]:
        return deepcopy(self.read_set)


def _scope(request: QueryRequest) -> dict[str, Any]:
    return {
        name: None
        if getattr(request, name) is None
        else sorted(str(identifier) for identifier in getattr(request, name))
        for name in ("document_ids", "collection_ids")
    }


def _chunk_manifest_error(
    stored: Any, rows: list[Chunk], body: str, version: int
) -> str | None:
    if (
        not isinstance(stored, list)
        or not stored
        or len(rows) > MAX_ROLE_CHUNKS
        or len(stored) != len(rows)
    ):
        return "role_scope_chunk_manifest_incomplete"
    expected = {}
    for item in stored:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            return "role_scope_chunk_manifest_invalid"
        key = item.get("id")
        if (
            not isinstance(key, str)
            or key in expected
            or not item["content"]
            or item["content"] not in body
        ):
            return "role_scope_chunk_manifest_invalid"
        expected[key] = (item.get("index"), item["content"])
    if any(
        expected.get(str(row.id)) != (row.chunk_index, row.content)
        or (row.metadata_ or {}).get("document_version") != version
        for row in rows
    ):
        return "role_scope_chunk_manifest_changed"
    return None


async def inspect_role_manifest(
    db: AsyncSession, principal: Principal, request: QueryRequest
) -> RoleScopeManifest:
    """A missing/invalid publication is visible and makes inspection incomplete."""
    documents = list(
        (
            await complete_read(
                db.scalars(
                    select(Document)
                    .where(
                        published_document_scope(
                            principal, request.document_ids, request.collection_ids
                        )
                    )
                    .order_by(Document.id)
                    .limit(MAX_ROLE_DOCUMENTS + 1)
                    .execution_options(populate_existing=True)
                )
            )
        ).all()
    )
    records = [
        {
            "document_id": str(document.id),
            "workspace_id": document.workspace_id,
            "owner_id": document.owner_id,
            "document_version": document.version_number,
            "content_hash": document.content_hash,
            "status": document.status.value,
            "metadata_hash": _digest(document.metadata_ or {}),
        }
        for document in documents
    ]
    captured: dict[str, Any] = {
        "contract": ROLE_READ_SET_CONTRACT,
        **_scope(request),
        "workspace_id": principal.get("workspace_id", "default"),
        "complete": False,
        "reason": None,
        "documents": records,
        "limits": {
            "documents": MAX_ROLE_DOCUMENTS,
            "body_bytes": MAX_ROLE_BODY_BYTES,
            "total_body_bytes": MAX_ROLE_TOTAL_BYTES,
            "chunks_per_document": MAX_ROLE_CHUNKS,
        },
    }
    sources: list[RoleScopeSource] = []

    def incomplete(reason):
        captured["reason"] = reason
        return RoleScopeManifest(tuple(sources), captured)

    if len(documents) > MAX_ROLE_DOCUMENTS:
        return incomplete("role_scope_document_budget_exceeded")
    total = 0
    for document, record in zip(documents, records, strict=True):
        snapshot = await complete_read(
            db.scalar(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.workspace_id == document.workspace_id,
                    DocumentVersion.version_number == document.version_number,
                    DocumentVersion.content_hash == document.content_hash,
                )
                .execution_options(populate_existing=True)
            )
        )
        if snapshot is None:
            return incomplete("role_scope_publication_unavailable")
        body = snapshot.normalized_content
        if (
            not isinstance(body, str)
            or not body.strip()
            or hashlib.sha256(body.encode()).hexdigest() != snapshot.content_hash
        ):
            return incomplete("role_scope_publication_invalid")
        size = len(body.encode())
        total += size
        if size > MAX_ROLE_BODY_BYTES or total > MAX_ROLE_TOTAL_BYTES:
            return incomplete("role_scope_body_budget_exceeded")
        rows = list(
            (
                await complete_read(
                    db.scalars(
                        select(Chunk)
                        .where(Chunk.document_id == document.id)
                        .order_by(Chunk.chunk_index)
                        .limit(MAX_ROLE_CHUNKS + 1)
                        .execution_options(populate_existing=True)
                    )
                )
            ).all()
        )
        stored = snapshot.chunks
        error = _chunk_manifest_error(stored, rows, body, document.version_number)
        if error:
            return incomplete(error)
        try:
            validated_snapshot_context(snapshot)
        except (ValueError, TypeError, KeyError):
            return incomplete("role_scope_snapshot_context_invalid")
        if any(body.find(row.content) != body.rfind(row.content) for row in rows):
            return incomplete("role_scope_chunk_mapping_ambiguous")
        record["snapshot_id"] = str(snapshot.id)
        record["snapshot_chunk_hash"] = _digest(stored)
        record["live_chunk_hash"] = _digest(
            [
                {
                    "id": str(row.id),
                    "index": row.chunk_index,
                    "content": row.content,
                    "metadata": row.metadata_,
                }
                for row in rows
            ]
        )
        sources.append(
            RoleScopeSource(
                body,
                json.dumps(record, sort_keys=True),
                json.dumps(document.metadata_ or {}, sort_keys=True),
                json.dumps(
                    [
                        scored_chunk(row, document, 0.0)
                        .model_copy(
                            update={
                                "metadata": {
                                    **(scored_chunk(row, document, 0.0).metadata or {}),
                                    "score_status": "not_ranked",
                                    "ranking_score": None,
                                    "origin": "role-scope-inspection",
                                }
                            }
                        )
                        .model_dump(mode="json")
                        for row in rows
                    ],
                    sort_keys=True,
                ),
            )
        )
    captured.update(complete=True, total_body_bytes=total)
    return RoleScopeManifest(tuple(sources), captured)


def _governing_ranges(requirement, activity, body: str) -> list[tuple[int, int]]:
    """Partition all prose, retaining connectors in the recorded source units.

    A comma inside the shared grammar's ``For target, role is value`` frame
    belongs to that frame. Other commas, coordinations and relative/adjunct
    clauses start independent obligations; recognizing a prefix cannot consume
    them. No content is removed from the immutable inventory.
    """
    from dataclasses import replace

    from app.services.requirement_binding import (
        non_role_attribute_context,
        role_discovery_candidates,
    )

    alternate = replace(
        requirement,
        kind="deputy" if requirement.kind == "owner" else "owner",
        relation="deputy" if requirement.kind == "owner" else "leads",
    )
    result = []
    for sentence in re.finditer(r"[^.!?;\n]+[.!?;\n]?", body):
        text = sentence.group()
        roles = (
            *role_discovery_candidates(requirement, text),
            *role_discovery_candidates(alternate, text),
        )
        protected = {
            comma.start()
            for comma in re.finditer(",", text)
            for role in roles
            if re.match(r"\s*for\s+", text, re.I)
            and role["target_range"]["end"]
            <= comma.start()
            < role["value_range"]["start"]
        }
        # The same scope-prefix comma can govern an independently parsed typed
        # attribute. Keep that frame whole; any later prose still gets a unit.
        prefix = re.match(r"\s*for\s+[^,]+,", text, re.I)
        if prefix and non_role_attribute_context(activity, text):
            protected.add(prefix.end() - 1)
        cursor = 0
        for boundary in re.finditer(
            r",|\b(?:and|but|or|which|who|whose|where|that|with|without|pending|"
            r"provided|unless|except)\b",
            text,
            re.I,
        ):
            if boundary.start() in protected:
                continue
            # Punctuation closes the previous clause. Grammatical connectors
            # stay on the following clause, so unknown material remains visible.
            point = boundary.end() if boundary.group() == "," else boundary.start()
            if text[cursor:point].strip(" ,"):
                result.append((sentence.start() + cursor, sentence.start() + point))
                cursor = point
        if cursor < len(text):
            result.append((sentence.start() + cursor, sentence.end()))
    return result


# A deliberately narrower instruction subtype for absence-of-role inspection.
# Canonical procedure copying still uses its unchanged source grammar. These
# commands describe physical records/objects, not choosing or appointing actors.
_PHYSICAL_COMMANDS = frozenset(
    "attach arrange check close compare copy count inspect label lock mark move "
    "obtain open place print put read record remove retain return save scan sign "
    "take turn unlock verify wait write".split()
)
_PHYSICAL_STATES = frozenset(
    "attached checked closed compared copied counted inspected labelled labeled "
    "locked marked moved obtained opened placed printed read recorded removed "
    "retained returned saved scanned signed taken turned "
    "unlocked verified written".split()
)


def _physical_nominal(text: str) -> bool:
    """A whole, bounded lower-case object phrase; never an arbitrary clause."""
    words = text.split()
    if words and words[0] in {
        "the",
        "a",
        "an",
        "one",
        "two",
        "both",
        "all",
        "each",
        "every",
    }:
        words = words[1:]
    else:
        return False
    if not 1 <= len(words) <= 4 or not _nominal_words(words[-1:], attributive=True):
        return False
    # A finite predicate cannot be smuggled into a coordinated object phrase.
    # Adjectival source states (marked edge, signed card) remain literal modifiers.
    if any(_role_noun_head(w) for w in words):
        return False
    # A bounded article/quantity + object, optionally carrying literal
    # participial state modifiers, cannot consume another finite predicate.
    return all(
        w in _PHYSICAL_STATES or re.fullmatch(r"[a-z]+ed", w) for w in words[:-1]
    )


def _physical_arguments(text: str) -> bool:
    # The only finite subordinate form admitted here is an explicit physical
    # object state. Unknown actor/permission/session conditions remain unresolved.
    condition = re.fullmatch(
        r"(.+?)\s+(?:before|after|until)\s+(.+?)\s+(?:is|are)\s+([a-z]+)", text
    )
    if condition:
        text, target, state = condition.groups()
        if state not in _PHYSICAL_STATES or not _physical_nominal(target):
            return False
    parts = re.split(
        r"\s+(?:of|in|into|on|onto|to|from|beside|under|over|at|against|within)\s+",
        text,
    )
    return bool(parts) and all(_physical_nominal(part) for part in parts)


def _typed_role_free_instruction(body: str, first: int, last: int) -> bool:
    from app.services.procedure_support import _SENTENCE, _instruction

    text = body[first:last]
    if re.search(
        r"\b(?:roles?|sessions?|person|responsib\w*|appoint\w*|"
        r"designat\w*|accountable|authority|authori[sz]\w*|"
        r"leadership|acting|serves|as)\b",
        text,
        re.I,
    ) or any(_role_noun_head(w) for w in re.findall(r"[A-Za-z]+", text)):
        return False
    sentences = list(_SENTENCE.finditer(body, first, last))
    if not sentences:
        return False
    for sentence in sentences:
        words = re.findall(r"[A-Za-z]+", sentence.group())
        if any(word[0].isupper() for word in words[1:]):
            return False
        # Every comma, coordination and semicolon starts another obligation.
        # No favorable prefix can classify the remainder of a sentence.
        clauses = re.split(
            r",\s*(?:(?:and|or|but)\s+)?|\b(?:and|or|but)\b|;",
            sentence.group(),
            flags=re.I,
        )
        for clause in clauses:
            clause = clause.strip().rstrip(".!?").strip()
            orientation = re.fullmatch(r"with (.+?) facing (.+)", clause)
            if orientation:
                if not all(_physical_nominal(v) for v in orientation.groups()):
                    return False
                continue
            if not clause:
                return False
            _instruction(clause, 0, len(clause), "role_inspection")
            command = re.sub(r"^(?:do\s+not|never)\s+", "", clause, flags=re.I)
            verb, separator, argument = command.partition(" ")
            if (
                verb.casefold() not in _PHYSICAL_COMMANDS
                or not separator
                or not _physical_arguments(argument.casefold())
            ):
                return False
    return True


def _closed_non_role_procedure(body: str, *, topic: str | None = None) -> bool:
    """A narrow whole-source classification, not an absence-by-keyword shortcut.

    Reuse the canonical declaration and imperative grammars. Every nonblank
    character must belong to a known structural range or typed instruction;
    opaque preludes, trailing commentary, unclassified conditions and
    role-bearing commands stay unresolved. Many valid procedures are excluded.
    """
    from app.services.procedure_evidence import ProcedureRejected
    from app.services.procedure_paragraphs import ParagraphRejected, _paragraphs, parse

    try:
        parsed = parse(body)
        if parsed is None:
            from app.services.requirement_binding import (
                _SECTION_HEAD,
                _canonical_argument,
            )

            heading = _SECTION_HEAD.match(body)
            if (
                heading is None
                or topic is None
                or _canonical_argument(heading.group("scope") or heading.group("title"))
                != _canonical_argument(topic)
            ):
                return False
            return _typed_role_free_instruction(body, heading.end(), len(body))
        # parse already checks the exact governance declaration. It does not
        # classify later prose; only its fixed heading + declaration are allowed.
        tail = [(a, b) for a, b in _paragraphs(body) if a >= parsed.governance[0]]
        if len(tail) != 2:
            return False
        intervals = [
            parsed.title,
            parsed.heading,
            parsed.declaration,
            *parsed.paragraphs,
            parsed.end_marker,
            parsed.governance,
        ]
        cursor = 0
        for first, last in sorted(intervals):
            if first < cursor or body[cursor:first].strip():
                return False
            cursor = last
        if body[cursor:].strip():
            return False
        for first, last in parsed.paragraphs:
            if not _typed_role_free_instruction(body, first, last):
                return False
        return True
    except (ParagraphRejected, ProcedureRejected):
        return False


def inspect_role_contexts(  # noqa: C901 - exhaustively classify every captured clause
    manifest: RoleScopeManifest, interpretation
) -> dict[str, Any]:
    """Exhaustive bounded typed classification, independent of QA and NLI.

    Unknown governing prose remains unresolved even without a repeated activity
    name. Only completely parsed assignments/other typed facts can be excluded.
    """
    from dataclasses import replace

    from app.services.requirement_binding import (
        condition_relation,
        named_anchors,
        non_role_attribute_context,
        relation_present,
        role_argument_identity,
        role_discovery_candidates,
        source_relation_scope,
    )
    from app.services.role_scope_policy import canonical_role_scope

    current = interpretation.prepared("session")
    activity = interpretation.prepared("activity")
    contexts = []
    direct, general = [], []
    complete = manifest.complete
    for source in manifest.sources:
        units = []
        source_direct = source_activity = False
        if (
            current.source_workspace
            and current.source_workspace != source.identity["workspace_id"]
        ):
            contexts.append(
                {
                    **source.identity,
                    "body": source.body,
                    "body_length": len(source.body),
                    "disposition": "requested_workspace_excluded",
                    "units": [],
                }
            )
            continue
        # A registered complete procedure with no role field is another form of
        # evidence. A shared activity name alone cannot make it an exception.
        procedure_only = _closed_non_role_procedure(source.body, topic=activity.topic)
        pieces = (
            [(0, len(source.body))]
            if procedure_only
            else _governing_ranges(current, activity, source.body)
        )
        for left, right in pieces:
            text = source.body[left:right].strip().rstrip(",")
            text = re.sub(r"^(?:and|but|or)\s+", "", text, flags=re.I)
            if not text:
                continue
            assignments = role_discovery_candidates(current, text)
            # Other literal role predicates are still parsed by the shared
            # authority, rather than recognized by a second role regex here.
            all_roles = list(assignments)
            alternate = replace(
                current,
                kind="deputy" if current.kind == "owner" else "owner",
                relation="deputy" if current.kind == "owner" else "leads",
            )
            all_roles.extend(role_discovery_candidates(alternate, text))
            disposition = "unresolved"
            target = None
            unit_assignments = []
            if procedure_only:
                disposition = "irrelevant_typed_procedure"
            elif assignments:
                decisions = []
                for item in assignments:
                    target = item["target"]
                    normalized = canonical_role_scope(target)
                    if normalized == canonical_role_scope(current.topic):
                        status = "session_assignment"
                    elif normalized == canonical_role_scope(activity.topic):
                        status = "activity_assignment"
                    elif item["relation_scope"] == "irrelevant" and (
                        (
                            set(named_anchors(target))
                            and not set(current.anchors).intersection(
                                named_anchors(target)
                            )
                        )
                        or re.sub(r"^(?:special|emergency)\s+", "", normalized)
                        == canonical_role_scope(current.topic)
                    ):
                        status = "irrelevant_typed_assignment"
                    else:
                        status = "unresolved"
                    if not _complete_role_designator(item["value"]):
                        status = "unresolved"
                    # Binding/condition rejection may hide a negation, modality
                    # or qualifier. No favorable model score can erase it.
                    effective = current if status == "session_assignment" else activity
                    bound = role_discovery_candidates(effective, text)
                    if status in {"session_assignment", "activity_assignment"} and (
                        not any(candidate["rejection"] is None for candidate in bound)
                        or condition_relation(effective, text, source.metadata)
                        != "applies"
                        or _ROLE_QUALIFIERS.search(text)
                    ):
                        status = "unresolved"
                    decisions.append(status)
                    unit_assignments.append({"scope": status, "value": item["value"]})
                disposition = (
                    "unresolved"
                    if "unresolved" in decisions
                    else (
                        "session_assignment"
                        if "session_assignment" in decisions
                        else "activity_assignment"
                        if "activity_assignment" in decisions
                        else "irrelevant_typed_assignment"
                    )
                )
            elif (
                all_roles
                and all(_complete_role_designator(item["value"]) for item in all_roles)
                and not _ROLE_QUALIFIERS.search(text)
            ):
                disposition = "irrelevant_typed_role"
            elif not re.search(
                r"\b(?:lead|deputy|nomination|assignment|roster|appendix|except|unless|must|requires?)\b",
                text,
                re.I,
            ) and (
                source_relation_scope(current, text) == "irrelevant"
                or (
                    not relation_present(current, text)
                    and non_role_attribute_context(activity, text)
                )
            ):
                disposition = "irrelevant_typed_attribute"
            if disposition == "unresolved":
                complete = False
            source_direct |= disposition == "session_assignment"
            source_activity |= disposition == "activity_assignment"
            units.append(
                {
                    "source_range": {"start": left, "end": right},
                    "text": source.body[left:right],
                    "target": target,
                    "disposition": disposition,
                    "assignments": unit_assignments,
                }
            )
        if source_direct:
            direct.append(source.identity["document_id"])
        if source_activity:
            general.append(source.identity["document_id"])
        contexts.append(
            {
                **source.identity,
                "body": source.body,
                "body_length": len(source.body),
                "disposition": "unresolved"
                if any(unit["disposition"] == "unresolved" for unit in units)
                else "classified",
                "units": units,
            }
        )
    chosen_scope = "session_assignment" if direct else "activity_assignment"
    values = {
        role_argument_identity(item["value"])
        for context in contexts
        for unit in context["units"]
        for item in unit.get("assignments", [])
        if item["scope"] == chosen_scope
    }
    ambiguous_assignments = len(values) > 1
    complete = complete and not ambiguous_assignments
    return {
        "requirement_id": current.id,
        "complete": complete,
        "reason": manifest.reason
        if not manifest.complete
        else None
        if complete
        else "role_scope_assignments_unconfirmed"
        if ambiguous_assignments
        else "role_scope_inspection_unresolved",
        "session_documents": direct,
        "activity_documents": general,
        "contexts": contexts,
    }


async def check_role_read_set(
    db: AsyncSession,
    principal: Principal,
    request: QueryRequest,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Re-enumerate membership as well as known rows before each publication."""
    if (
        not isinstance(expected, dict)
        or expected.get("contract") != ROLE_READ_SET_CONTRACT
        or expected.get("complete") is not True
        or any(expected.get(name) != value for name, value in _scope(request).items())
        or expected.get("workspace_id") != principal.get("workspace_id", "default")
    ):
        return {"consistent": False, "reason": "role_scope_inspection_snapshot_invalid"}
    actual = await inspect_role_manifest(db, principal, request)
    # Publication check metadata is deliberately outside the captured universe.
    baseline = {
        key: value
        for key, value in expected.items()
        if key not in {"after_proofs", "before_publication"}
    }
    equal = actual.complete and actual.read_set == baseline
    return {
        "consistent": bool(equal),
        "reason": None if equal else "role_scope_inspection_changed",
    }
