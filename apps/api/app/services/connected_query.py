"One authenticated execution pipeline for normal and streaming queries."

from __future__ import annotations

import json
import re
import time
import uuid
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.cancellation import complete_read
from app.evidence_policy import resolve_evidence_policy, source_free_pattern_budget
from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentVersion
from app.models.query import (
    Query,
    QueryRequest,
    QueryResponse,
    RetrievalTrace,
    SourceCitation,
)
from app.services.access_control.scope import Principal, document_scope, owned_scope
from app.services.audit import audit_trail
from app.services.requirement_contract import (
    KNOWN_CONTRACTS,
    requirement_record,
    validate_discovery_lineage,
    validate_role_scope_evidence,
)
from app.services.retrieval.scoped import retrieve_scoped, terms

settings = get_settings()


def diagnostic_snapshot(value: Any) -> Any:
    """Save raw offsets/logits without retaining unselected model text."""
    if isinstance(value, list):
        return [diagnostic_snapshot(item) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                {offset: item[offset] for offset in ("start", "end") if offset in item}
                if key == "raw_span" and isinstance(item, dict)
                else diagnostic_snapshot(item)
            )
            for key, item in value.items()
        }
    return value


def publication_snapshot(selection, policy):
    """Use the actual durable JSON wire shape before v2 proof/publication."""
    if policy.dependency_reading:
        return json.loads(json.dumps(selection, allow_nan=False))
    return selection


def execution_provenance(provenance, *, capture_json="", retained_trace=None):
    """Retain actual adapter inputs independently of mutable presentation.

    Existing profiles keep their old wire shape. New staged input snapshots
    originate from the frozen request-local context, not a producer success flag.
    """
    from app.services.procedure_output import retained_selection
    from app.services.staged_output import INPUTS_FIELD

    captured = None
    if capture_json:
        captured = json.loads(capture_json)
    elif retained_trace is not None:
        old = retained_selection(retained_trace)
        if isinstance(old, dict) and INPUTS_FIELD in old:
            captured = old[INPUTS_FIELD]
    if captured is None:
        return provenance
    actual = deepcopy(provenance)
    actual["answer_selection"][INPUTS_FIELD] = deepcopy(captured)
    return actual


def execution_context(selection, requirement_result):
    return {
        "provenance": execution_provenance(
            {"answer_selection": deepcopy(selection)},
            capture_json=requirement_result.staged_execution_capture_json,
        )
    }


def add_inspected_documents(selection, chunk_documents, ids):
    inspected = selection.get("inspected_sources")
    if not isinstance(inspected, list):
        raise ValueError("Missing requirement evidence snapshot")
    for evidence in inspected:
        document_id = uuid.UUID(str(evidence["document_id"]))
        chunk_id = uuid.UUID(str(evidence["chunk_id"]))
        if chunk_id in chunk_documents and chunk_documents[chunk_id] != document_id:
            raise ValueError("Conflicting evidence identity")
        chunk_documents[chunk_id] = document_id
        ids.add(document_id)


def add_procedure_contexts(selection, chunk_documents, ids):
    for context in selection.get("procedure_contexts", []):
        document_id = uuid.UUID(str(context["document_id"]))
        ids.add(document_id)
        for evidence in context["sources"]:
            chunk_id = uuid.UUID(str(evidence["chunk_id"]))
            if (
                uuid.UUID(str(evidence["document_id"])) != document_id
                or chunk_documents.get(chunk_id) != document_id
            ):
                raise ValueError("Procedure context identity mismatch")


def add_role_contexts(selection, ids):
    read_set = selection.get("role_scope_read_set") or {}
    for document in read_set.get("documents", []):
        ids.add(uuid.UUID(str(document["document_id"])))
    for finding in selection.get("role_scope_findings", []):
        for context in finding.get("contexts", []):
            ids.add(uuid.UUID(str(context["document_id"])))


def add_staged_contexts(selection, ids):
    """Authorize every planning body, including nonselected and refusal inputs.

    This is identity enumeration only, not semantic/certificate validation.
    Both presentation and independently retained execution channels call it.
    """
    from app.services.planning_declarations import MAX_DOCUMENTS
    from app.services.staged_output import INPUTS_FIELD
    from app.services.staged_snapshot_store import has_known_input_contract

    if INPUTS_FIELD not in selection:
        return
    record = selection[INPUTS_FIELD]
    if not has_known_input_contract(record):
        raise ValueError("Unrecognized planning source inventory")
    snapshots = record["snapshots"]
    publications = record["manifest"]["publications"]
    if (
        type(snapshots) is not list
        or type(publications) is not list
        or len(snapshots) > MAX_DOCUMENTS
        or len(publications) != len(snapshots)
    ):
        raise ValueError("Invalid bounded planning source inventory")
    selected = [str(uuid.UUID(row["identity"]["document_id"])) for row in snapshots]
    published = [str(uuid.UUID(row["document_id"])) for row in publications]
    if (
        len(set(selected)) != len(selected)
        or len(set(published)) != len(published)
        or set(selected) != set(published)
    ):
        raise ValueError("Planning source membership differs")
    ids.update(uuid.UUID(identifier) for identifier in selected)


def diagnostic_has_captured_source(candidate, selection, chunk_documents) -> bool:
    if source_free_pattern_budget(candidate):
        return True
    if not isinstance(candidate, dict):
        return False
    if candidate.get("chunk_id") is not None:
        identifier = uuid.UUID(str(candidate["chunk_id"]))
        return identifier in chunk_documents and (
            candidate.get("document_id") is None
            or uuid.UUID(str(candidate["document_id"])) == chunk_documents[identifier]
        )
    allowed = {
        "document_id",
        "document_version",
        "content_hash",
        "workspace_id",
        "requirement_id",
        "origin",
        "decision",
        "complete",
        "observed_count",
        "truncated",
    }
    if (
        set(candidate) - allowed
        or candidate.get("origin") != "source_pattern"
        or candidate.get("complete") is not False
    ):
        return False
    keys = ("document_id", "document_version", "content_hash")
    return all(key in candidate for key in keys) and any(
        all(source.get(key) == candidate[key] for key in keys)
        for source in selection.get("inspected_sources", [])
    )


async def source_access(db: AsyncSession, row: Query, principal: Principal) -> bool:  # noqa: C901 - reauthorize every captured evidence family
    # Diagnostics retain evidence from null, conflicting and non-cited candidates.
    # Reauthorize the whole snapshot, not just the chosen answer's citations.
    try:
        ids = {uuid.UUID(str(item["document_id"])) for item in row.sources or []}
        scores = (row.retrieval_trace or {}).get("scores", [])
        chunk_documents = {}
        for item in scores:
            document_id = uuid.UUID(str(item["document_id"]))
            ids.add(document_id)
            if item.get("chunk_id") is not None:
                chunk_id = uuid.UUID(str(item["chunk_id"]))
                if (
                    chunk_id in chunk_documents
                    and chunk_documents[chunk_id] != document_id
                ):
                    return False
                chunk_documents[chunk_id] = document_id
        selection = (row.provenance or {}).get("answer_selection") or {}
        if not isinstance(selection, dict):
            return False
        from app.services.output_dispatch import has_output_contract
        from app.services.procedure_output import retained_selection

        try:
            captured = retained_selection(row.retrieval_trace or {})
        except (KeyError, TypeError, AttributeError, ValueError):
            captured = None
        add_staged_contexts(selection, ids)
        if isinstance(captured, dict):
            add_staged_contexts(captured, ids)
        if isinstance(captured, dict) and has_output_contract(captured):
            add_inspected_documents(captured, chunk_documents, ids)
            add_procedure_contexts(captured, chunk_documents, ids)
            add_role_contexts(captured, ids)

        # V3 presentation verifies integrity separately; SQL scope still covers
        # every saved source, including nonselected/conflicting diagnostics.
        if (
            not has_output_contract(selection)
            and validate_discovery_lineage(selection)["valid"] is False
        ):
            return False
        if (
            not has_output_contract(selection)
            and validate_role_scope_evidence(selection)["valid"] is False
        ):
            return False
        if (
            requirement_record(selection)
            and selection.get("contract") not in KNOWN_CONTRACTS
        ):
            return False
        if selection.get("contract") in KNOWN_CONTRACTS:
            add_inspected_documents(selection, chunk_documents, ids)
            add_procedure_contexts(selection, chunk_documents, ids)
            add_role_contexts(selection, ids)
        candidates = selection.get("candidates", [])
        if any(
            not diagnostic_has_captured_source(candidate, selection, chunk_documents)
            for candidate in candidates
        ):
            # Historical chunk rows can disappear after reindexing. Only the
            # saved document mapping can establish the diagnostic's authority.
            return False
    except (AttributeError, KeyError, TypeError, ValueError):
        return False
    if not ids:
        return True
    allowed = set(
        (
            await complete_read(
                db.scalars(
                    select(Document.id).where(
                        Document.id.in_(ids), document_scope(principal)
                    )
                )
            )
        ).all()
    )
    return ids == allowed


async def citation_status(
    db: AsyncSession, source: dict[str, Any], current: Document | None
) -> str:
    version, digest, passage = (
        source.get("document_version"),
        source.get("content_hash"),
        source.get("quoted_text"),
    )
    if (
        not isinstance(version, int)
        or version <= 0
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
        or not isinstance(passage, str)
        or not passage
        or current is None
    ):
        return "unknown"
    snapshot = await complete_read(
        db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == current.id,
                DocumentVersion.workspace_id == current.workspace_id,
                DocumentVersion.version_number == version,
                DocumentVersion.content_hash == digest,
            )
        )
    )
    from hashlib import sha256

    if (
        snapshot is None
        or sha256(snapshot.normalized_content.encode("utf-8")).hexdigest() != digest
        or passage not in snapshot.normalized_content
        or not any(
            isinstance(chunk, dict) and chunk.get("content") == passage
            for chunk in snapshot.chunks or []
        )
    ):
        return "unknown"
    return (
        "current"
        if current.version_number == version and current.content_hash == digest
        else "superseded"
    )


async def present_query(
    db: AsyncSession, row: Query, principal: Principal
) -> QueryResponse:
    accessible = await source_access(db, row, principal)
    snapshots = row.sources or []
    from app.services.output_dispatch import (
        has_output_contract,
        is_contextual,
        verify_output,
    )
    from app.services.procedure_output import load_snapshots

    selection = (row.provenance or {}).get("answer_selection") or {}
    integrity_invalid = False
    presentation_provenance = row.provenance
    query_context = row.retrieval_trace or {}
    integrity_subject = (
        "answer"
        if is_contextual(selection, query_context=query_context)
        else "procedure"
    )
    if (
        accessible
        and has_output_contract(selection, query_context=query_context)
        and row.outcome == "completed"
    ):
        try:
            integrity_invalid = not verify_output(
                selection,
                question=row.question,
                answer=row.answer,
                citations=row.sources,
                source_snapshots=await load_snapshots(
                    db, selection, query_context=query_context
                ),
                query_context=query_context,
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            integrity_invalid = True
        if integrity_invalid:
            presentation_provenance = {
                "answer_selection": {
                    "presentation_verification": {
                        "status": "invalid",
                        "reason": (
                            f"Recorded {integrity_subject} presentation integrity "
                            "could not be verified."
                        ),
                    }
                }
            }
            snapshots = []
        else:
            presentation_provenance = deepcopy(row.provenance)
            assert presentation_provenance is not None
            presentation_provenance["answer_selection"]["presentation_verification"] = {
                "status": "verified",
                "reason": None,
            }
    if accessible:
        documents = (
            {
                str(doc.id): doc
                for doc in (
                    await complete_read(
                        db.scalars(
                            select(Document).where(
                                Document.id.in_(
                                    [
                                        uuid.UUID(str(item["document_id"]))
                                        for item in snapshots
                                    ]
                                )
                            )
                        )
                    )
                ).all()
            }
            if snapshots
            else {}
        )
        snapshots = [
            {
                **item,
                "source_status": await citation_status(
                    db, item, documents.get(str(item["document_id"]))
                ),
            }
            for item in snapshots
        ]
    return QueryResponse(
        id=row.id,
        question=row.question,
        answer=row.answer if accessible and not integrity_invalid else None,
        sources=[SourceCitation.model_validate(item) for item in snapshots]
        if accessible
        else [],
        retrieval_trace=RetrievalTrace.model_validate(row.retrieval_trace)
        if row.retrieval_trace and accessible and not integrity_invalid
        else None,
        refused=row.refused,
        confidence=row.confidence if accessible and not integrity_invalid else None,
        token_usage=row.token_usage,
        created_at=row.created_at,
        conversation_id=row.conversation_id,
        outcome=row.outcome,
        refusal_reason=(
            f"Recorded {integrity_subject} presentation integrity "
            "could not be verified; "
            "its answer and sources are withheld."
        )
        if integrity_invalid
        else row.refusal_reason
        if accessible
        else (
            "Access to the recorded evidence has changed; its answer "
            "and source content are withheld."
        ),
        execution_mode=(row.provenance or {}).get("generation_mode", "unknown"),
        evidence_access="available"
        if accessible
        and row.provenance
        and not integrity_invalid
        and all(source.get("source_status") != "unknown" for source in snapshots)
        else "unknown"
        if accessible
        else "restricted",
        provenance=presentation_provenance if accessible else None,
    )


async def begin_query(
    db: AsyncSession, request: QueryRequest, principal: Principal
) -> Query:
    if request.conversation_id:
        conversation = await complete_read(
            db.scalar(
                select(Conversation).where(
                    Conversation.id == request.conversation_id,
                    owned_scope(Conversation, principal),
                )
            )
        )
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
    else:
        conversation = Conversation(
            title=request.question[:80],
            owner_id=str(principal["id"]),
            workspace_id=principal.get("workspace_id", "default"),
        )
        db.add(conversation)
        await db.flush()
    row = Query(
        question=request.question,
        owner_id=str(principal["id"]),
        workspace_id=principal.get("workspace_id", "default"),
        conversation_id=conversation.id,
        outcome="processing",
        sources=[],
    )
    db.add(row)
    await db.commit()
    return row


async def prepare_answer(  # noqa: C901 - explicit refusal and generation boundaries
    db: AsyncSession, row: Query, request: QueryRequest, principal: Principal
) -> None:
    started = time.perf_counter()
    policy = resolve_evidence_policy(settings)
    # Plain request-local state must not dirty the ORM row before reads/models:
    # autoflush would hold a SQLite writer lock across later stream yields.
    setattr(row, "_request_evidence_policy", policy)  # noqa: B010 - unmapped request-local attribute
    memory_context = await scoped_memory(db, row, request, principal)
    retrieval_question = request.question
    if memory_context and re.search(
        r"\b(it|its|that|those|this|they|them)\b", request.question, re.I
    ):
        # Bounded previous user questions can resolve a follow-up topic. Prior
        # assistant prose is never a retrieved source or a numbered citation.
        last_user = next(
            (
                item["content"]
                for item in reversed(memory_context)
                if item["role"] == "user"
            ),
            "",
        )
        retrieval_question = f"{last_user} {request.question}"
    result = await retrieve_scoped(
        db,
        retrieval_question,
        principal=principal,
        document_ids=request.document_ids,
        collection_ids=request.collection_ids,
        top_k=request.top_k or settings.RETRIEVAL_TOP_K,
        method=request.retrieval_method,
    )

    async def valid_current_snapshot(candidate):
        metadata = candidate.metadata or {}
        current = await complete_read(db.get(Document, candidate.document_id))
        return (
            await citation_status(
                db,
                {
                    "document_version": metadata.get("document_version"),
                    "content_hash": metadata.get("content_hash"),
                    "quoted_text": candidate.content,
                },
                current,
            )
            == "current"
        )

    chunks = [
        candidate
        for candidate in result.chunks
        if await valid_current_snapshot(candidate)
    ]
    query_terms = terms(retrieval_question)
    confidence = chunks[0].relevance_score if chunks else 0.0
    # Retrieval rank alone cannot establish factual support. Extractive answers
    # require meaningful literal query anchors in an authoritative passage.
    supported = [
        chunk
        for chunk in chunks
        if len(terms(chunk.content) & query_terms) >= min(2, len(query_terms))
        and query_terms
    ]
    from app.services.retrieval.scoped import support_terms

    required_terms = support_terms(retrieval_question)
    supported = [
        chunk
        for chunk in supported
        if len(required_terms & support_terms(chunk.content))
        / max(len(required_terms), 1)
        >= 0.75
    ]
    from app.services.answer_reader import reader_service
    from app.services.answer_support import support_service

    reader_mode = settings.ANSWER_SELECTION_MODE == "reader"
    requirement_mode = reader_mode and settings.ANSWER_SUPPORT_MODE == "local_nli"
    requirement_result = None
    if requirement_mode:
        # Validate the explicitly selected local runtime even when no source
        # produces a candidate. Missing assets are errors, never good refusals.
        await support_service.assess([], config=settings)
        await reader_service.select_atomic(request.question, [], config=settings)
    conflicts: dict[str, set[str]] = {}
    for chunk in chunks if reader_mode else supported:
        group = (chunk.metadata or {}).get("conflict_group")
        if group:
            conflicts.setdefault(group, set()).add(str(chunk.document_id))
    reason = None
    if re.search(
        (
            "ignore (?:all |previous )?instructions|system prompt|jailb"
            "reak|reveal.*(?:secret|private)|bypass.*(?:access|permissi"
            "on)"
        ),
        request.question,
        re.I,
    ):
        reason = "The request attempts to override evidence or access boundaries."
    elif re.search(
        r"\b(retired|outdated|superseded)\b.*\b(instead|follow|use|skip|skips)\b",
        request.question,
        re.I,
    ):
        reason = (
            "A retired or superseded procedure cannot establish the "
            "current action. Inspect the current published version "
            "before proceeding."
        )
    elif not reader_mode and any(len(ids) > 1 for ids in conflicts.values()):
        reason = (
            "The selected sources contain a curated conflicting "
            "procedure group. Human review is required."
        )
    elif not reader_mode and (
        not supported or confidence < settings.CONNECTED_REFUSAL_THRESHOLD
    ):
        reason = (
            "The selected authorized sources do not contain enough "
            "direct evidence for this question."
        )
    spans = {}
    reader_diagnostics = []
    citation_selection = None
    if reader_mode and reason is None:
        if requirement_mode:
            from app.services.requirement_answers import select_requirement_answer

            if settings.GENERATION_MODE != "extractive":
                raise RuntimeError(
                    "Requirement evidence mode requires source-extractive answers."
                )
            requirement_result = await select_requirement_answer(
                db,
                request,
                principal,
                chunks,
                settings,
                validate_current=valid_current_snapshot,
                policy=policy,
            )
            reason = requirement_result.reason
            supported = list(requirement_result.chunks)
            spans = requirement_result.spans
            reader_diagnostics = requirement_result.candidates
            citation_selection = {
                "method": "complete-validated-requirement-cover-v1",
                "citation_limit": None,
                "document_limit": 8,
                "selected_chunks": len(supported),
            }
        else:
            selections = await reader_service.select(
                retrieval_question, [chunk.content for chunk in chunks]
            )
            # Group membership was collected from ALL current authorized candidates
            # before selection. A null prediction on one side cannot erase a known
            # opposing source; relevance requires support on at least one member.
            relevant_groups = {
                (chunk.metadata or {}).get("conflict_group")
                for chunk, selection in zip(chunks, selections, strict=True)
                if selection.span is not None
            }
            if any(
                len(ids) > 1 and group in relevant_groups
                for group, ids in conflicts.items()
            ):
                reason = (
                    "The selected sources contain a curated conflicting "
                    "procedure group. Human review is required."
                )
            supported = []
            for chunk, selection in zip(chunks, selections, strict=True):
                diagnostic = diagnostic_snapshot(selection.diagnostics)
                reader_diagnostics.append({"chunk_id": str(chunk.id), **diagnostic})
                if selection.span is not None:
                    supported.append(chunk)
                    spans[chunk.id] = selection.span
            # Preserve all candidate diagnostics and inspect curated conflicts before
            # picking a compact citation cover. Rank alone must not discard a part.
            if supported and selections and "part_count" in selections[0].diagnostics:
                from app.services.reader_witnesses import select_witness_cover

                cover = select_witness_cover(selections)
                citation_selection = cover.diagnostics
                supported = [chunks[index] for index in cover.indices]
            if not supported and reason is None:
                reason = (
                    "The local reader found no supported answer in the "
                    "selected current authorized sources."
                )
    row.refused = reason is not None
    row.refusal_reason = reason
    row.outcome = "refused" if reason else "completed"
    row.confidence = confidence
    row.provenance = {
        **result.provenance,
        "generation_method": "source-extractive"
        if settings.GENERATION_MODE == "extractive"
        else "provider",
        "generation_mode": settings.GENERATION_MODE,
        "memory": {
            "policy": request.memory_policy.value,
            "selected_messages": len(memory_context),
            "token_budget": request.memory_max_tokens,
            "use": "follow-up topic context only; never numbered source evidence",
        },
        "refusal_threshold": None
        if reader_mode
        else settings.CONNECTED_REFUSAL_THRESHOLD,
        "support_contract": policy.requirement_contract
        if requirement_result is not None
        else reader_service.metadata()["contract"],
        "answer_selection": {
            **reader_service.metadata(config=settings),
            **(
                {
                    "reader_contract": reader_service.metadata(config=settings)[
                        "contract"
                    ],
                    "contract": policy.requirement_contract,
                    "evidence_profile": policy.record(),
                    "requirements": [],
                    "inspected_sources": [],
                    "procedure_contexts": [],
                    "proposals": [],
                    "qa_observations": [],
                    "pattern_observations": [],
                    "selected_proposal_ids": [],
                    "role_scope_read_set": {},
                    "role_scope_interpretations": [],
                    "role_scope_findings": [],
                }
                if requirement_mode
                else {}
            ),
            **(
                {
                    "reader_contract": reader_service.metadata(config=settings)[
                        "contract"
                    ],
                    "contract": policy.requirement_contract,
                    "coverage_semantics": (
                        "Every requested requirement needs current authorized typed "
                        "and model-assessed evidence; not universal entailment."
                    ),
                    "evidence_support": support_service.metadata(settings),
                    "requirements": requirement_result.requirements,
                    "inspected_sources": requirement_result.inspected_sources,
                    "conflicts": requirement_result.conflicts,
                    "followup_retrieval": requirement_result.followups,
                    "procedure_contexts": requirement_result.procedure_contexts,
                    "procedure_read_set": requirement_result.procedure_read_set,
                    "evidence_profile": requirement_result.evidence_profile,
                    "proposals": list(requirement_result.proposals),
                    "qa_observations": list(requirement_result.qa_observations),
                    "pattern_observations": list(
                        requirement_result.pattern_observations
                    ),
                    "selected_proposal_ids": list(
                        requirement_result.selected_proposal_ids
                    ),
                    **(
                        {
                            "staged_request_inputs": (
                                requirement_result.staged_request_inputs
                            )
                        }
                        if policy.staged_request
                        else {}
                    ),
                    "role_scope_read_set": requirement_result.role_scope_read_set,
                    "role_scope_interpretations": list(
                        requirement_result.role_scope_interpretations
                    ),
                    "role_scope_findings": list(requirement_result.role_scope_findings),
                    **(
                        {
                            "request_plan": requirement_result.request_plan,
                            "request_capture": requirement_result.request_capture,
                            "source_guard_records": list(
                                requirement_result.source_guard_records
                            ),
                        }
                        if requirement_result.request_capture
                        else {}
                    ),
                }
                if requirement_result is not None
                else {}
            ),
            "decision": "refused" if reason else "answer",
            "candidates": reader_diagnostics,
            "citation_selection": citation_selection,
            "max_length": settings.READER_MAX_LENGTH if reader_mode else None,
            "stride": settings.READER_STRIDE if reader_mode else None,
            "n_best": settings.READER_N_BEST if reader_mode else None,
            "max_span_tokens": settings.READER_MAX_SPAN_TOKENS if reader_mode else None,
        },
        "support_min_coverage": None if reader_mode else 0.75,
    }
    if requirement_result is not None:
        selection = publication_snapshot(
            (row.provenance or {})["answer_selection"], policy
        )
        row.provenance = {**(row.provenance or {}), "answer_selection": selection}
        lineage = validate_discovery_lineage(selection)
        selection["discovery_lineage"] = lineage
        if lineage["valid"] is False:
            raise RuntimeError("Source proposal lineage could not be validated.")
        role_lineage = validate_role_scope_evidence(selection)
        selection["role_scope_validation"] = role_lineage
        if role_lineage["valid"] is False:
            raise RuntimeError("Role scope policy evidence could not be validated.")
    # Requirement coverage has already enforced an eight-document budget. Each
    # required passage must survive rendering, even across many chunks in one
    # document. Only the explicit legacy profile limits citation count.
    citation_chunks = supported if requirement_mode else supported[:3]
    citations = []
    if not reason:
        for index, chunk in enumerate(citation_chunks, 1):
            metadata = chunk.metadata or {}
            passage = chunk.content
            selected_spans = (
                requirement_result.passages.get(chunk.id, ())
                if requirement_result is not None
                else (spans[chunk.id],)
                if chunk.id in spans
                else ()
            )
            citations.append(
                SourceCitation(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=metadata.get("document_title", "Document"),
                    content_preview=passage[:200],
                    relevance_score=chunk.relevance_score,
                    score_status=metadata.get("score_status"),
                    citation_index=index,
                    document_version=metadata.get("document_version"),
                    content_hash=metadata.get("content_hash"),
                    quoted_text=passage,
                    source_status="current",
                    answer_spans=list(selected_spans),
                ).model_dump(mode="json")
            )
        if settings.GENERATION_MODE == "extractive":
            disclosures = (
                [
                    item["disclosure"]
                    for item in requirement_result.role_scope_interpretations
                    if item.get("activity_fallback")
                ]
                if requirement_result
                else []
            )
            from app.services.procedure_output import render_extractive

            groups = (
                list(requirement_result.procedure_groups) if requirement_result else []
            )
            if policy.procedure_copy and requirement_result is not None:
                ordering = {
                    r["id"]: i for i, r in enumerate(requirement_result.requirements)
                }
                groups.sort(key=lambda g: ordering[g["requirement_id"]])
            from app.services.source_context_scope import contextual_disclosures

            disclosures.extend(
                contextual_disclosures((row.provenance or {})["answer_selection"])
            )
            row.answer, _ = render_extractive(citations, groups, disclosures)
        elif settings.GENERATION_MODE == "provider":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError(
                    (
                        "Provider generation is selected but no provider "
                        "credentials are configured."
                    )
                )
            from app.internal.provider_contracts import OpenAIGenerationProvider
            from app.services.generation import SYSTEM_PROMPT, generation_service

            response = await OpenAIGenerationProvider(
                generation_service._get_client(), settings.LLM_MODEL, SYSTEM_PROMPT
            ).complete(
                request.question
                + (
                    "\nUntrusted conversation context, not evidence: "
                    + str(memory_context)
                    if memory_context
                    else ""
                ),
                [chunk.content for chunk in citation_chunks],
                citations,
            )
            row.answer = response.text
        else:
            raise RuntimeError(
                "Choose extractive or provider generation for connected execution."
            )
    row.sources = citations
    if not reason and requirement_result is not None and policy.dependency_reading:
        from app.services.procedure_output import load_snapshots

        if policy.evidence_reading_profile == "contextual_source_v4":
            from app.services.captured_output import build_output
        elif policy.staged_request:
            from app.services.staged_output import build_output
        else:
            from app.services.contextual_mixed_output import build_output

        selection = (row.provenance or {})["answer_selection"]
        retained = execution_context(selection, requirement_result)
        rebuilt = build_output(
            selection,
            question=row.question,
            source_snapshots=await load_snapshots(
                db, selection, query_context=retained
            ),
            query_context=retained,
        )
        display = {str(c["chunk_id"]): c for c in citations}
        citations = [
            {**display[str(core["chunk_id"])], **core} for core in rebuilt["citations"]
        ]
        row.answer = rebuilt["answer"]
        row.sources = citations
    if not reason and requirement_result is not None and policy.procedure_copy:
        from app.services.output_dispatch import certify_output, has_output_contract
        from app.services.procedure_output import load_snapshots

        selection = (row.provenance or {})["answer_selection"]
        if has_output_contract(selection):
            query_context = execution_context(selection, requirement_result)
            certify_output(
                selection,
                question=row.question,
                answer=row.answer,
                citations=citations,
                source_snapshots=await load_snapshots(
                    db, selection, query_context=query_context
                ),
                query_context=query_context,
            )
    row.token_usage = {
        "prompt_tokens": len(request.question.split())
        + sum(len(chunk.content.split()) for chunk in citation_chunks),
        "completion_tokens": len((row.answer or "").split()),
        "estimated": True,
        "pricing_provenance": "unknown; local extraction has no provider charge",
    }
    usage = row.token_usage or {}
    usage["total_tokens"] = int(usage["prompt_tokens"]) + int(
        usage["completion_tokens"]
    )
    row.token_usage = usage
    row.retrieval_trace = RetrievalTrace(
        query_embedding_dim=int(result.provenance["embedding"]["dimension"]),
        vector_results=result.vector_count,
        keyword_results=result.keyword_count,
        reranked_results=len(chunks),
        final_context_chunks=len(citations),
        confidence=confidence,
        latency_ms=int((time.perf_counter() - started) * 1000),
        scores=[
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "score": chunk.relevance_score,
                "document_version": (chunk.metadata or {}).get("document_version"),
            }
            for chunk in chunks
        ],
        method=result.method,
        execution_mode=settings.EMBEDDING_MODE,
        request_id=str(row.id),
        provenance=execution_provenance(
            row.provenance,
            capture_json=(
                requirement_result.staged_execution_capture_json
                if requirement_result is not None
                else ""
            ),
        ),
        refusal_threshold=None if reader_mode else settings.CONNECTED_REFUSAL_THRESHOLD,
        retrieval_latency_ms=result.elapsed_ms,
    ).model_dump()


async def scoped_memory(
    db: AsyncSession, row: Query, request: QueryRequest, principal: Principal
) -> list[dict[str, str]]:
    if request.memory_policy.value != "recent" or not row.conversation_id:
        return []
    from app.services.conversation.memory import select_bounded_history

    previous = (
        await complete_read(
            db.scalars(
                select(Query)
                .where(
                    Query.conversation_id == row.conversation_id,
                    Query.id != row.id,
                    owned_scope(Query, principal),
                    Query.outcome.in_(["completed", "refused"]),
                )
                .order_by(Query.created_at.desc())
                .limit(50)
            )
        )
    ).all()
    messages = []
    for entry in reversed(previous):
        presented = await present_query(db, entry, principal)
        verification = ((presented.provenance or {}).get("answer_selection") or {}).get(
            "presentation_verification"
        ) or {}
        if (
            presented.evidence_access != "restricted"
            and verification.get("status") != "invalid"
        ):
            messages.extend(
                [
                    {"role": "user", "content": presented.question},
                    {
                        "role": "assistant",
                        "content": presented.answer
                        or presented.refusal_reason
                        or "No supported answer",
                    },
                ]
            )
    return [
        {"role": message["role"], "content": message["content"]}
        for message in select_bounded_history(
            messages, max_tokens=request.memory_max_tokens
        )
    ]


async def revalidate_prepared_evidence(  # noqa: C901 - shared publication coordinator
    db: AsyncSession, row: Query, principal: Principal
) -> None:
    """Recheck current inspection inputs before publishing prepared evidence.

    Historical presentation keeps captured-version semantics; this gate is only
    on the new execution's publication path, after all semantic work. It does
    not commit completion, so interruption can still roll back prepared output.
    """
    provenance = deepcopy(row.provenance or {})
    selection = provenance.get("answer_selection") or {}
    if row.outcome != "completed":
        return
    from app.services.output_dispatch import has_output_contract, verify_output
    from app.services.procedure_evidence import check_read_set, invalidate_inspection
    from app.services.procedure_output import load_snapshots
    from app.services.role_scope_inspection import check_role_read_set

    query_context = row.retrieval_trace or {}
    if has_output_contract(selection, query_context=query_context):
        if not verify_output(
            selection,
            question=row.question,
            answer=row.answer,
            citations=row.sources,
            source_snapshots=await load_snapshots(
                db, selection, query_context=query_context
            ),
            query_context=query_context,
        ):
            raise RuntimeError("Answer output integrity verification failed.")
        selection["presentation_verification"] = {"status": "verified", "reason": None}
        provenance["answer_selection"] = selection
        row.provenance = provenance
    checks = []
    # Every existing normal/SSE publication boundary calls this one coordinator.
    # Never flush the prepared answer or hold a write lock across a yield.
    with db.no_autoflush:
        for name, replay in (
            ("procedure_read_set", check_read_set),
            ("role_scope_read_set", check_role_read_set),
        ):
            read_set = selection.get(name)
            if not read_set:
                continue
            request = QueryRequest(
                question=row.question,
                document_ids=read_set["document_ids"],
                collection_ids=read_set["collection_ids"],
            )
            check = await replay(db, principal, request, read_set)
            read_set["before_publication"] = check
            checks.append(check)
        if "staged_request_inputs" in selection:
            from app.services.staged_answer_planning import recheck_inputs

            check = await recheck_inputs(
                db,
                principal,
                row.question,
                selection["staged_request_inputs"],
            )
            selection["staged_publication_check"] = check
            checks.append(check)
    if not checks:
        return
    check = next((item for item in checks if not item["consistent"]), checks[0])
    if not check["consistent"]:
        invalidate_inspection(selection["requirements"], selection["conflicts"], check)
        from app.services.output_dispatch import is_contextual

        for record in selection.get("requirements", []):
            if record.get("role_scope_interpretation") or is_contextual(selection):
                record.update(status="unsupported", reason=check["reason"])
        selection["decision"] = "refused"
        if "staged_request_inputs" in selection:
            selection["presentation_verification"] = {
                "status": "unverified",
                "reason": check["reason"],
            }
        selection["citation_selection"] = {
            **(selection.get("citation_selection") or {}),
            "selected_chunks": 0,
        }
        row.answer, row.sources = None, []
        row.outcome, row.refused, row.refusal_reason = "refused", True, check["reason"]
        row.token_usage = {
            **(row.token_usage or {}),
            "completion_tokens": 0,
            "total_tokens": int((row.token_usage or {}).get("prompt_tokens", 0)),
        }
    provenance["answer_selection"] = selection
    row.provenance = provenance
    if row.retrieval_trace:
        row.retrieval_trace = {
            **row.retrieval_trace,
            "provenance": execution_provenance(
                provenance,
                retained_trace=row.retrieval_trace,
            ),
            "final_context_chunks": len(row.sources or []),
        }


async def finish_query(db: AsyncSession, row: Query, principal: Principal) -> None:
    conversation = (
        await complete_read(db.get(Conversation, row.conversation_id))
        if row.conversation_id
        else None
    )
    await revalidate_prepared_evidence(db, row, principal)
    if row.conversation_id:
        from datetime import timedelta

        from app.utils.time import utc_now

        turn_started = utc_now()
        db.add_all(
            [
                Message(
                    conversation_id=row.conversation_id,
                    role="user",
                    content=row.question,
                    created_at=turn_started,
                ),
                Message(
                    conversation_id=row.conversation_id,
                    role="assistant",
                    content=row.answer or row.refusal_reason or "No answer",
                    sources=row.sources or [],
                    metadata_={"query_id": str(row.id)},
                    created_at=turn_started + timedelta(microseconds=1),
                ),
            ]
        )
        if conversation:
            conversation.message_count += 2
            conversation.total_tokens += int(
                (row.token_usage or {}).get("total_tokens", 0)
            )
    await audit_trail.record(
        actor_id=str(principal["id"]),
        action="query",
        resource_type="query",
        resource_id=str(row.id),
        workspace_id=principal.get("workspace_id", "default"),
        metadata={
            "outcome": row.outcome,
            "method": (row.provenance or {}).get("retrieval_method"),
        },
        db=db,
    )
    await db.commit()


def query_failure_record(error: Exception | None) -> dict[str, str]:
    """Public diagnostics are fixed categories, never raw exception details."""
    from app.services.contextual_source_proof import SourceGuardError

    if isinstance(error, SourceGuardError):
        return {
            "code": "evidence_integrity_failed",
            "message": (
                "Evidence integrity verification failed; "
                "no answer was published or saved."
            ),
        }
    return {
        "code": "query_execution_failed",
        "message": (
            "Query execution failed; check runtime readiness and retry explicitly."
        ),
    }


async def fail_query(
    db: AsyncSession,
    row: Query,
    *,
    interrupted: bool = False,
    error: Exception | None = None,
) -> None:
    # Preserve the already committed identity without leaking exception details.
    identifier = row.id
    captured = deepcopy(row.provenance or {})
    request_policy = getattr(row, "_request_evidence_policy", None)
    await db.rollback()
    current = await db.get(Query, identifier)
    if current:
        from app.evidence_policy import resolve_evidence_policy
        from app.services.answer_reader import reader_service
        from app.services.answer_support import support_service

        captured_policy = request_policy or resolve_evidence_policy(settings)
        current.outcome = "interrupted" if interrupted else "error"
        failure = (
            {
                "code": "query_interrupted",
                "message": "Execution was interrupted; no completed answer was saved.",
            }
            if interrupted
            else query_failure_record(error)
        )
        fallback = {
            "generation_mode": settings.GENERATION_MODE,
            "answer_selection": {
                **reader_service.metadata(config=settings),
                **(
                    {
                        "reader_contract": reader_service.metadata(config=settings)[
                            "contract"
                        ],
                        "contract": captured_policy.requirement_contract,
                        "inspected_sources": [],
                        "requirements": [],
                        "procedure_contexts": [],
                        "evidence_profile": captured_policy.record(),
                        "proposals": [],
                        "qa_observations": [],
                        "pattern_observations": [],
                        "selected_proposal_ids": [],
                        "role_scope_read_set": {},
                        "role_scope_interpretations": [],
                        "role_scope_findings": [],
                    }
                    if settings.ANSWER_SELECTION_MODE == "reader"
                    and settings.ANSWER_SUPPORT_MODE == "local_nli"
                    else {}
                ),
                **(
                    {"evidence_support": support_service.metadata(settings)}
                    if settings.ANSWER_SUPPORT_MODE == "local_nli"
                    else {}
                ),
                "decision": current.outcome,
            },
        }
        current.provenance = {
            **fallback,
            **captured,
            "execution_failure": failure,
            "answer_selection": {
                **fallback["answer_selection"],
                **captured.get("answer_selection", {}),
                "evidence_support": support_service.metadata(settings),
                "decision": current.outcome,
            },
        }
        for record in (current.provenance or {})["answer_selection"].get(
            "requirements", []
        ):
            record.update(status="unsupported", reason=f"execution_{current.outcome}")
        current.answer = None
        current.refused = False
        current.sources = []
        current.refusal_reason = failure["message"]
        await db.commit()
