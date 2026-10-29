"""Source-grounded coverage contracts, separate from the frozen version-one judge.

Literal facts are authored expectations, not a generative judge. Whitespace and
case are normalized; numbers, units, entities, negations and order stay literal.
Both comparison arms use this same quality contract. Candidate span validation
is an additional integrity gate and never an advantage in answer quality.
"""

import hashlib
import json
import re
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from app.evidence_policy import source_free_pattern_budget
from app.services.requirement_contract import KNOWN_CONTRACTS, procedure_completeness


def source_manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _canonical_chunks(observed_chunks, body, identifier, number, digest, workspace_id):
    if not isinstance(observed_chunks, list) or not observed_chunks:
        raise ValueError("Source snapshot canonical chunks are missing")
    chunks, ids, indices = [], set(), set()
    previous_start, previous_end = -1, -1
    for item in observed_chunks:
        if not isinstance(item, dict):
            raise ValueError("Invalid source snapshot chunk")
        chunk_id, index, text = (
            str(UUID(item["id"])),
            item["index"],
            item["content"],
        )
        if (
            chunk_id in ids
            or type(index) is not int
            or index != len(chunks)
            or index in indices
            or not isinstance(text, str)
            or not text
        ):
            raise ValueError("Source snapshot chunk identity/index differs")
        start = body.find(text, previous_start + 1)
        if start < 0 or start + len(text) <= previous_end:
            raise ValueError("Source snapshot chunk literal position/order differs")
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Source snapshot chunk metadata differs")
        for key, expected in (
            ("document_id", identifier),
            ("document_version", number),
            ("content_hash", digest),
            ("workspace_id", workspace_id),
        ):
            if key in metadata and (
                metadata[key] != expected
                or (key == "document_version" and type(metadata[key]) is not int)
            ):
                raise ValueError("Source snapshot chunk source identity differs")
        chunk = {"id": chunk_id, "index": index, "content": text}
        if "source_context" in metadata:
            chunk["metadata"] = {"source_context": metadata["source_context"]}
        chunks.append(chunk)
        ids.add(chunk_id)
        indices.add(index)
        previous_start, previous_end = start, start + len(text)
    return chunks


def canonical_source_snapshot(document_id, version, observation, workspace_id=None):
    """Bind observed IDs to oracle bytes; observations never establish source truth."""
    from app.services.document.source_context import validated_snapshot_context

    try:
        if not isinstance(observation, dict) or not isinstance(version, dict):
            raise ValueError("Invalid source snapshot observation")
        identifier = str(UUID(document_id))
        number, body, digest = (
            version["version_number"],
            version["content"],
            version["content_hash"],
        )
        observed_number = observation.get(
            "document_version", observation.get("version_number")
        )
        if (
            type(number) is not int
            or type(observed_number) is not int
            or observed_number != number
            or (
                "version_number" in observation
                and (
                    type(observation["version_number"]) is not int
                    or observation["version_number"] != number
                )
            )
            or number < 1
            or not isinstance(body, str)
            or hashlib.sha256(body.encode("utf-8")).hexdigest() != digest
            or observation.get("content_hash") != digest
            or observation.get("document_id", identifier) != identifier
            or observation.get("body", body) != body
            or observation.get("normalized_content", body) != body
            or observation.get("workspace_id", workspace_id) != workspace_id
        ):
            raise ValueError("Source snapshot observation identity/body differs")
        chunks = _canonical_chunks(
            observation.get("chunks"), body, identifier, number, digest, workspace_id
        )
        context = validated_snapshot_context(
            SimpleNamespace(
                document_id=identifier,
                version_number=number,
                workspace_id=workspace_id,
                normalized_content=body,
                content_hash=digest,
                chunks=chunks,
            )
        )
        if observation.get("captured_scope", context) != context:
            raise ValueError("Source snapshot captured source context differs")
        metadata = observation.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Source snapshot metadata differs")
        safe_metadata = {
            key: metadata[key]
            for key in ("condition", "conflict_group")
            if key in metadata
        }
        if any(
            value is not None and not isinstance(value, str)
            for value in safe_metadata.values()
        ):
            raise ValueError("Source snapshot curation metadata differs")
        result = {
            "document_id": identifier,
            "document_version": number,
            "content_hash": digest,
            "body": body,
            "chunks": chunks,
            "workspace_id": workspace_id,
        }
        if safe_metadata:
            result["metadata"] = safe_metadata
        if context is not None:
            result["captured_scope"] = context
        return result
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid source snapshot observation") from exc


def bind_source_observations(document, observations):
    if not isinstance(observations, list):
        raise ValueError("Invalid source snapshot observations")
    snapshots = {}
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("Invalid source snapshot observation")
        # Old seed records did not retain chunk identities. Keep old scoring,
        # without upgrading their hash/body verification into v3 ID evidence.
        if "chunks" not in observation:
            continue
        number = observation.get("document_version", observation.get("version_number"))
        if (
            type(number) is not int
            or str(number) not in document["versions"]
            or str(number) in snapshots
        ):
            raise ValueError("Source snapshot observation version differs")
        snapshots[str(number)] = canonical_source_snapshot(
            document["document_id"],
            document["versions"][str(number)],
            observation,
            document.get("workspace_id"),
        )
    if snapshots:
        document["source_snapshots"] = snapshots


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def contains(answer: str, fragment: str) -> bool:
    # Avoid accepting 11 minutes inside 111 minutes, or a shorter entity token.
    return bool(
        re.search(r"(?<!\w)" + re.escape(normalized(fragment)) + r"(?!\w)", answer)
    )


def validate_coverage(
    documents: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    if manifest.get("score_contract") != "coverage-v2":
        raise ValueError("Version-two corpus requires coverage-v2 score contract")
    if manifest.get("corpus_role") not in ("development", "blind"):
        raise ValueError("Version-two corpus role must be development or blind")
    by_id = {document["id"]: document for document in documents}
    for document in documents:
        if document.get("current_version_number") != len(document["versions"]):
            raise ValueError("Current source version must be the latest snapshot")
        if document.get("owner") not in manifest["principals"]:
            raise ValueError("Document owner must be a declared principal")
        if document.get("visibility") not in ("public", "organization", "private"):
            raise ValueError("Document permission visibility is invalid")
    for case in cases:
        _validate_case(case, by_id)


def _validate_case(case: dict[str, Any], by_id: dict[str, Any]) -> None:
    if case.get("score_contract") != "coverage-v2":
        raise ValueError("Case requires coverage-v2 score contract")
    if case.get("expected_behavior") not in ("answer", "refuse", "review", "deny"):
        raise ValueError("Unknown expected behavior")
    answerable = case["expected_behavior"] == "answer"
    if answerable and (not case["expected_sources"] or not case.get("required_facts")):
        raise ValueError("Answerable case requires source and required facts")
    if not answerable and (
        case["expected_sources"]
        or case.get("required_facts")
        or case.get("ordered_steps")
    ):
        raise ValueError("Negative case cannot declare an answer contract")
    passages = _validate_expected_sources(case["expected_sources"], by_id)
    for name in ("required_facts", "ordered_steps"):
        _validate_grounded_groups(case.get(name, []), passages, name)


def _validate_expected_sources(
    sources: list[dict[str, Any]], by_id: dict[str, Any]
) -> list[str]:
    passages = []
    for source in sources:
        document = by_id[source["document_id"]]
        version = document["versions"][source["version_number"] - 1]
        if source.get("content_hash") != version["content_hash"]:
            raise ValueError("Expected source content hash mismatch")
        if source["version_number"] != document["current_version_number"]:
            raise ValueError("Expected answer must use current source version")
        alternatives = source.get("acceptable_answer_spans")
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or any(
                not isinstance(span, str)
                or not span
                or span not in source["quoted_text"]
                for span in alternatives
            )
        ):
            raise ValueError("Acceptable answer span must occur in expected quotation")
        passages.append(source["quoted_text"])
    return passages


def _validate_grounded_groups(groups: Any, passages: list[str], name: str) -> None:
    if not isinstance(groups, list):
        raise ValueError(f"Invalid {name} contract")
    for alternatives in groups:
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or any(
                not isinstance(fact, str)
                or not fact
                or not any(contains(normalized(p), fact) for p in passages)
                for fact in alternatives
            )
        ):
            raise ValueError(f"Unfounded required fact or step: {name}")


def _spans_valid(citations: list[dict[str, Any]], required: bool) -> bool:
    found = False
    for citation in citations:
        quote = citation.get("quoted_text")
        spans = citation.get("answer_spans", [])
        if not isinstance(spans, list) or (required and not spans):
            return False
        for span in spans:
            if not isinstance(span, dict) or not isinstance(quote, str):
                return False
            start, end, text = span.get("start"), span.get("end"), span.get("text")
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(quote)
                or not isinstance(text, str)
                or quote[start:end] != text
            ):
                return False
            found = True
    return found or not required


def _source_authorized(document: dict[str, Any], principal_alias: str | None) -> bool:
    """Match the seeded workspace/owner/visibility contract, failing closed.

    Corpus v2 seeds no collection shares. Group names in prose or metadata are
    not grants. Organization collections are seeded with the source workspace
    as organization, and seeded principals use that same organization identity.
    """
    principal = document.get("principals", {}).get(principal_alias, {})
    workspace = document.get("workspace_id")
    if not workspace or principal.get("workspace_id") != workspace:
        return False
    visibility = document.get("visibility")
    if visibility not in ("public", "organization", "private"):
        return False
    return (
        document.get("owner") == principal_alias
        or principal.get("role") == "admin"
        or visibility in ("public", "organization")
    )


def _requirement_evidence_sources(response: dict[str, Any]) -> list[dict[str, Any]]:
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    if selection.get("contract") not in KNOWN_CONTRACTS:
        return []
    # New evidence can disclose identities even when no answer is emitted.
    # Historical reader records use ranks; do not fabricate unknown provenance.
    sources = [
        *selection.get("inspected_sources", []),
        *selection.get("candidates", []),
        *selection.get("proposals", []),
        *selection.get("pattern_observations", []),
    ]
    role_read_set = selection.get("role_scope_read_set") or {}
    if not isinstance(role_read_set, dict):
        raise ValueError("Role scope inspection metadata is malformed")
    sources.extend(role_read_set.get("documents", []))
    sources.extend(
        source
        for row in selection.get("followup_retrieval", [])
        for source in row.get("sources", [])
    )
    sources.extend(
        source
        for row in selection.get("procedure_contexts", [])
        for source in row.get("sources", [])
    )
    sources.extend(
        source
        for row in selection.get("requirements", [])
        for source in row.get("witnesses", [])
    )
    return [source for source in sources if not source_free_pattern_budget(source)]


def _unauthorized_exposures(
    case: dict[str, Any], response: dict[str, Any], documents: dict[str, Any]
) -> int:
    """Judge every exposed identity, including ranks beyond metric top-five."""
    reverse = {str(value["document_id"]): key for key, value in documents.items()}
    forbidden = {
        (source["document_id"], str(source["version_number"]))
        for source in case["forbidden_sources"]
    }
    ranks = (response.get("retrieval_trace") or {}).get("scores") or []
    exposed = {
        (
            str(item.get("document_id")),
            str(item.get("document_version", item.get("version_number"))),
        )
        for item in [
            *(response.get("sources") or []),
            *ranks,
            *_requirement_evidence_sources(response),
        ]
    }
    unauthorized = 0
    for identifier, version in exposed:
        logical = reverse.get(identifier)
        document = documents.get(logical, {}) if logical is not None else {}
        if (
            not document
            or not _source_authorized(document, case.get("principal"))
            or version not in document.get("versions", {})
            or (logical, version) in forbidden
        ):
            unauthorized += 1
    return unauthorized


def _procedure_output_context(case, response, documents):
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    query_context = response.get("retrieval_trace")
    retained = (
        query_context.get("provenance") if isinstance(query_context, dict) else None
    )
    retained_selection = (
        retained.get("answer_selection") if isinstance(retained, dict) else None
    )
    if not any(
        (row.get("procedure_completeness") or {}).get("contract")
        == "complete-immutable-procedure-v3"
        for candidate in (selection, retained_selection)
        if isinstance(candidate, dict)
        for row in candidate.get("requirements", [])
    ):
        return {}
    snapshots = {}
    for document in documents.values():
        current = str(max(map(int, document["versions"]), default=0))
        snapshot = document.get("source_snapshots", {}).get(current)
        if snapshot is not None:
            snapshots[str(document["document_id"])] = snapshot
    return {
        "question": case["question"],
        "answer": response.get("answer") or "",
        "citations": response.get("sources") or [],
        "source_snapshots": snapshots,
        "query_context": query_context,
    }


def score_coverage(
    case: dict[str, Any],
    response: dict[str, Any],
    documents: dict[str, Any],
    result: dict[str, Any],
    *,
    require_answer_spans: bool,
) -> dict[str, Any]:
    answer = normalized(response.get("answer") or "")
    citations = response.get("sources") or []
    expected = case["expected_behavior"] == "answer"
    facts_correct = all(
        any(contains(answer, fact) for fact in alternatives)
        for alternatives in case.get("required_facts", [])
    )
    cursor = 0
    order_correct = True
    for alternatives in case.get("ordered_steps", []):
        matches = [
            match
            for step in alternatives
            if (
                match := re.search(
                    r"(?<!\w)" + re.escape(normalized(step)) + r"(?!\w)",
                    answer[cursor:],
                )
            )
            is not None
        ]
        if not matches:
            order_correct = False
            break
        cursor += min(matches, key=lambda match: match.start()).end()
    spans_supported = all(
        any(contains(answer, span) for span in source["acceptable_answer_spans"])
        for source in case["expected_sources"]
    )
    answer_correct = (
        facts_correct and order_correct and spans_supported if expected else None
    )
    completeness = procedure_completeness(
        (response.get("provenance") or {}).get("answer_selection") or {},
        **_procedure_output_context(case, response, documents),
    )
    if expected and completeness is False:
        answer_correct = False
    reverse = {str(value["document_id"]): key for key, value in documents.items()}
    citation_integrity = True
    for citation in citations:
        logical = reverse.get(str(citation.get("document_id")))
        versions = documents[logical].get("versions", {}) if logical is not None else {}
        version = str(citation.get("document_version"))
        snapshot = versions.get(version, {})
        quote = citation.get("quoted_text")
        if (
            not snapshot
            or not isinstance(quote, str)
            or not quote
            or quote not in snapshot.get("content", "")
            or citation.get("content_hash") != snapshot.get("content_hash")
            or version != str(max(map(int, versions), default=0))
        ):
            citation_integrity = False
    emitted = bool(answer) and not result["refused"]
    span_integrity = _spans_valid(citations, require_answer_spans and emitted)
    execution_error = result["execution_error"] or response.get("outcome") in (
        "error",
        "interrupted",
        "running",
        "pending",
    )
    source_correct = result["source_version_correct"]
    if expected:
        source_correct = bool(source_correct) and citation_integrity
    # Refusals must not carry an answer body (even when the refused flag is set).
    negative_clean = expected or not answer
    unauthorized = _unauthorized_exposures(case, response, documents)
    quality_passed = (
        result["behavior_correct"]
        and not execution_error
        and not unauthorized
        and citation_integrity
        and negative_clean
        and (not expected or (source_correct and answer_correct))
    )
    return {
        **result,
        "passed": bool(quality_passed and span_integrity),
        "score_contract": "coverage-v2",
        "answer_quality_passed": bool(quality_passed),
        "unauthorized_source_exposures": unauthorized,
        "execution_error": execution_error,
        "answer_contract_correct": answer_correct,
        "procedure_completeness_correct": completeness,
        "required_facts_correct": facts_correct if expected else None,
        "ordered_steps_correct": order_correct if expected else None,
        "source_version_correct": source_correct,
        "citation_integrity_correct": citation_integrity,
        "span_integrity_correct": span_integrity,
        "span_integrity_required": require_answer_spans,
    }
