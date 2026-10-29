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
from app.services import output_dispatch
from app.services.requirement_contract import KNOWN_CONTRACTS, procedure_completeness


def source_manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _canonical_chunks(
    observed_chunks,
    body,
    identifier,
    number,
    digest,
    workspace_id,
    *,
    full_metadata=False,
):
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
        captured_metadata = _observed_chunk_metadata(item, metadata, full_metadata)
        if captured_metadata is not None:
            chunk["metadata"] = captured_metadata
        chunks.append(chunk)
        ids.add(chunk_id)
        indices.add(index)
        previous_start, previous_end = start, start + len(text)
    return chunks


def _native_copy(value):
    from app.services.request_parser import _native

    _native(value)
    return json.loads(json.dumps(value, allow_nan=False))


def _observed_chunk_metadata(item, metadata, full):
    if full:
        if "metadata" not in item or type(item["metadata"]) is not dict:
            raise ValueError("Full source snapshot chunk metadata is missing")
        return _native_copy(item["metadata"])
    if "source_context" in metadata:
        return {"source_context": metadata["source_context"]}
    return None


def _full_snapshot_fields(observation):
    snapshot_id = observation.get("snapshot_id", observation.get("id"))
    if (
        type(snapshot_id) is not str
        or type(observation["title"]) is not str
        or type(observation["metadata"]) is not dict
        or ("id" in observation and observation["id"] != snapshot_id)
    ):
        raise ValueError("Full source snapshot identity/title/metadata differs")
    return {
        "snapshot_id": str(UUID(snapshot_id)),
        "title": observation["title"],
        "metadata": _native_copy(observation["metadata"]),
    }


def _observation_matches_version(
    observation, identifier, number, body, digest, workspace_id
):
    observed_number = observation.get(
        "document_version", observation.get("version_number")
    )
    return not (
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
    )


def _snapshot_optional_fields(observation, chunks, full, context):
    metadata = observation.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Source snapshot metadata differs")
    safe_metadata = {
        key: metadata[key] for key in ("condition", "conflict_group") if key in metadata
    }
    if any(
        value is not None and not isinstance(value, str)
        for value in safe_metadata.values()
    ):
        raise ValueError("Source snapshot curation metadata differs")
    result = {}
    if safe_metadata:
        result["metadata"] = safe_metadata
    if full:
        result.update(_full_snapshot_fields(observation))
    marker = (
        (observation["chunks"][0].get("metadata") or {}).get(
            "staged_publication_context"
        )
        if observation.get("chunks")
        else None
    )
    if isinstance(marker, dict):
        from app.services.staged_publication_context import _json as _live_json

        result["owner_id"] = marker.get("owner_id")
        result["status"] = marker.get("status")
        result["role_live_chunks"] = [
            {
                "id": str(UUID(item["id"])),
                "index": item["index"],
                "content": item["content"],
                "metadata": _live_json(item.get("metadata")),
            }
            for item in observation["chunks"]
        ]
    if context is not None:
        result["captured_scope"] = context
    return result


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
        if not _observation_matches_version(
            observation, identifier, number, body, digest, workspace_id
        ):
            raise ValueError("Source snapshot observation identity/body differs")
        full = {"title", "metadata"} <= observation.keys() and (
            "snapshot_id" in observation or "id" in observation
        )
        chunks = _canonical_chunks(
            observation.get("chunks"),
            body,
            identifier,
            number,
            digest,
            workspace_id,
            full_metadata=full,
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
        result = {
            "document_id": identifier,
            "document_version": number,
            "content_hash": digest,
            "body": body,
            "chunks": chunks,
            "workspace_id": workspace_id,
        }
        result.update(_snapshot_optional_fields(observation, chunks, full, context))
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
    if output_dispatch._requires_staged(selection, response.get("retrieval_trace")):
        return _staged_exposure_sources(response)[0]
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


_STAGED_SOURCE_CHANNELS = {
    "inspected_sources": list,
    "candidates": list,
    "proposals": list,
    "qa_observations": list,
    "pattern_observations": list,
    "followup_retrieval": list,
    "procedure_contexts": list,
    "procedure_read_set": dict,
    "role_scope_read_set": dict,
    "role_scope_interpretations": list,
    "role_scope_findings": list,
    "requirements": list,
    "conflicts": list,
    "request_plan": dict,
    "source_guard_records": list,
    "staged_request_inputs": dict,
    "staged_output_certificate": dict,
    "citation_selection": dict,
}
# Only declared source-bearing transports are decoded. Literal body, metadata,
# parser captures and arbitrary strings are never searched or parsed for IDs.
_SOURCE_JSON_CONTRACTS = {
    "read_set_json": "request-planning-read-set-v1",
    "scope_bridge_json": "staged-planning-scope-bridge-v2",
    "effective_candidate_json": "staged-effective-request-proposal-v1",
    "effective_plan_json": "staged-effective-request-proposal-v1",
    "planning_support_json": "planning-support-observations-v2",
    "sql_read_set_json": "request-planning-publications-v1",
    "inventory_json": "request-declaration-inventory-proposal-v2",
    "candidate_selection_json": "planning-candidate-relevance-v1",
    "planning_inputs_json": "staged-request-inputs-v1",
    "retained_inputs_json": "staged-request-inputs-v1",
    "plan_json": "staged-request-plan-v1",
}
# New contracts are selected only by the canonical new reading profile.
_CAPTURED_JSON_CONTRACTS = {
    **_SOURCE_JSON_CONTRACTS,
    "effective_plan_json": "captured-plan-candidates-v1",
    "planning_support_json": "captured-planning-support-v1",
    "planning_inputs_json": "staged-request-inputs-v2",
    "retained_inputs_json": "staged-request-inputs-v2",
    "plan_json": "staged-request-plan-v2",
    "structure_json": "captured-request-structure-v1",
    "partial_json": "captured-request-structure-v1",
    "source_productions_json": "captured-source-productions-v1",
}
_CAPTURED_JSON_LISTS = frozenset(
    {
        "operation_ledger_json",
        "remaining_external_governing_json",
        "unresolved_json",
        "fact_batches_json",
    }
)
_CAPTURED_JSON_OBJECTS = frozenset({"request_relation_json", "evidence_profile_json"})


_SOURCE_JSON_LISTS = frozenset(
    {
        "source_uses_json",
        "members_json",
        "value_slots_json",
        "candidates_json",
        "observations_json",
        "procedure_obligations_json",
        "chunks_json",
        "typed_prior_executions_json",
    }
)
_SOURCE_JSON_OBJECTS = frozenset(
    {
        "authoritative_snapshots_json",
        "identity_json",
        "input_json",
        "retained_trace_json",
        "retained_json",
        "use_json",
        "snapshots_json",
        "inputs_json",
        "role_evidence_json",
        "dependent_field_execution_json",
    }
)
_OPAQUE_SOURCE_FIELDS = frozenset({"metadata", "metadata_json"})
_EXPOSURE_JSON_BYTES = 256 * 1024 * 1024
_STAGED_CERTIFICATE_FIELDS = frozenset(
    {
        "contract",
        "reading_profile",
        "renderer",
        "question_sha256",
        "answer_sha256",
        "source_inventory",
        "request_plan",
        "effective_requirements",
        "model_settings",
        "selected_proposal_ids",
        "selected_fragments",
        "procedure_groups",
        "disclosures",
        "assessed_inventory",
        "retained_supported_inventory",
        "source_guards",
        "citations",
        "retained_capture_sha256",
    }
)


def _exposure_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate source transport JSON key")
        result[key] = value
    return result


def _exposure_json(field, value, budget, *, captured=False):
    from app.services.request_parser import _native

    if type(value) is not str or len(value) > budget[0]:
        raise ValueError("Source transport JSON exceeds type/byte budget")
    try:
        budget[0] -= len(value.encode("utf-8"))
        if budget[0] < 0:
            raise ValueError("Source transport JSON byte budget exceeded")
        decoded = json.loads(value, object_pairs_hook=_exposure_pairs)
        _native(decoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid source transport JSON") from exc
    lists = _SOURCE_JSON_LISTS | (_CAPTURED_JSON_LISTS if captured else frozenset())
    contracts = _CAPTURED_JSON_CONTRACTS if captured else _SOURCE_JSON_CONTRACTS
    expected = list if field in lists else dict
    if type(decoded) is not expected:
        raise ValueError("Source transport JSON schema differs")
    if captured and field == "evidence_profile_json":
        from app.services.captured_plan_inputs import _profile

        _profile(decoded)
    elif field in contracts and (
        type(decoded) is not dict or decoded.get("contract") != contracts[field]
    ):
        raise ValueError("Unknown source transport contract")
    _source_json_schema(field, decoded, captured=captured)
    return decoded


def _source_json_schema(field, value, *, captured=False):
    channel = {
        "planning_inputs_json": "staged_request_inputs",
        "retained_inputs_json": "staged_request_inputs",
        "plan_json": "request_plan",
    }.get(field)
    if channel is not None:
        _staged_exposure_schema(channel, value, captured=captured)
    if captured and field == "source_productions_json":
        _captured_source_parts(value)
    required = {
        "read_set_json": {
            "universe",
            "snapshot_reads",
            "capture_reads",
            "missing_publications",
        },
        "scope_bridge_json": {
            "universe",
            "snapshots",
            "captures",
            "read_set",
            "source_decisions",
            "name_candidates",
        },
    }.get(field, set())
    if required and (type(value) is not dict or not required <= value.keys()):
        raise ValueError("Incomplete source transport JSON")


def _exposure_identity(value):
    if type(value) is not dict:
        raise ValueError("Malformed staged source identity")
    version = value.get("document_version", value.get("version_number"))
    if (
        type(value.get("document_id")) is not str
        or not value["document_id"]
        or type(version) is not int
        or version < 1
    ):
        raise ValueError("Malformed staged source identity")
    for key in ("document_version", "version_number"):
        if key in value and (
            type(value[key]) is not int or value[key] < 1 or value[key] != version
        ):
            raise ValueError("Staged source version aliases differ")
    return value


def _proof_exposure_sources(value, sources, budget, depth=0, *, captured=False):
    if depth > 32:
        budget[1] = False
        return
    if type(value) is list:
        for row in value:
            _proof_exposure_sources(row, sources, budget, depth + 1, captured=captured)
    elif type(value) is dict and not source_free_pattern_budget(value):
        if "document_id" in value:
            try:
                _append_exposure_identity(value, sources)
            except (TypeError, ValueError):
                budget[1] = False
        for field, child in value.items():
            try:
                _proof_exposure_field(
                    field, child, sources, budget, depth, captured=captured
                )
            except (TypeError, ValueError, RecursionError):
                budget[1] = False


def _append_exposure_identity(value, sources):
    if "document_version" in value or "version_number" in value:
        sources.append(_exposure_identity(value))
    elif type(value["document_id"]) is str and value["document_id"]:
        # Render groups omit a repeated version. Unbound projections retain
        # their unknown-version pair, never a corpus/current-version default.
        sources.append({"document_id": value["document_id"]})
    else:
        raise ValueError("Malformed projected source identity")


def _proof_exposure_field(field, child, sources, budget, depth, *, captured=False):
    if field in _OPAQUE_SOURCE_FIELDS:
        return
    if (
        captured
        and field
        in (
            _CAPTURED_JSON_CONTRACTS.keys()
            | _CAPTURED_JSON_LISTS
            | _CAPTURED_JSON_OBJECTS
        )
        or field in _SOURCE_JSON_CONTRACTS
        or field in _SOURCE_JSON_LISTS
        or field in _SOURCE_JSON_OBJECTS
    ):
        child = _exposure_json(field, child, budget, captured=captured)
    if field in {"identity", "source_identity"}:
        _exposure_identity(child)
    if field in {"publications", "missing_publications"}:
        if type(child) is not list:
            raise ValueError("Source publication inventory is malformed")
        for row in child:
            _exposure_identity(row)
    if field in {
        "snapshots",
        "source_captures",
        "snapshot_reads",
        "capture_reads",
        "captures",
    }:
        if type(child) is not list or any(
            type(row) is not dict or "identity" not in row for row in child
        ):
            raise ValueError("Source snapshot/capture inventory is malformed")
    if type(child) in (dict, list):
        _proof_exposure_sources(child, sources, budget, depth + 1, captured=captured)


def _staged_exposure_sources(response):
    from app.services.procedure_output import retained_selection

    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    trace = response.get("retrieval_trace")
    sources, budget = [], [_EXPOSURE_JSON_BYTES, True]
    try:
        retained = retained_selection(trace) if trace is not None else None
    except (TypeError, ValueError, RecursionError):
        retained, budget[1] = None, False
    for channel in (selection, retained):
        if channel is None:
            continue
        if type(channel) is not dict:
            budget[1] = False
            continue
        captured_profile = _captured_exposure_policy(channel)
        if not _staged_exposure_native(channel) or (
            captured_profile and not _captured_observation_links(channel)
        ):
            budget[1] = False
        channels = {
            **_STAGED_SOURCE_CHANNELS,
            **({"captured_output_certificate": dict} if captured_profile else {}),
        }
        for field, expected in channels.items():
            if field not in channel:
                continue
            value = channel[field]
            if type(value) is not expected:
                budget[1] = False
                continue
            try:
                _staged_exposure_schema(field, value, captured=captured_profile)
            except (TypeError, ValueError, RecursionError):
                budget[1] = False
            _proof_exposure_sources(value, sources, budget, captured=captured_profile)
    complete = {
        row["document_id"]
        for row in sources
        if "document_version" in row or "version_number" in row
    }
    return [
        row
        for row in sources
        if "document_version" in row
        or "version_number" in row
        or row["document_id"] not in complete
    ], budget[1]


def _staged_exposure_policy(channel):
    from app.evidence_policy import reading_version
    from app.portfolio.comparison import evidence_profile_matches

    return channel.get("contract") == reading_version(
        "contextual_source_v3"
    ).requirement and evidence_profile_matches(
        channel,
        {
            "procedure_verification_profile": "source_declared_procedure_copy_v1",
            "source_context_policy": "scoped_note_context_v2",
        },
    )


def _captured_exposure_policy(channel):
    from app.evidence_policy import reading_version

    try:
        return (
            reading_version(
                channel["evidence_profile"]["evidence_reading_profile"]
            ).request_inputs
            == "staged-request-inputs-v2"
        )
    except (KeyError, TypeError, ValueError):
        return False


def _captured_observation(row):
    return (
        type(row) is dict
        and set(row)
        == {
            "contract",
            "requirement_id",
            "origin",
            "pattern_id",
            "proposal_ids",
            "source_declaration_id",
        }
        and row["contract"] == "captured-role-declaration-observation-v1"
        and row["origin"] == "source_pattern"
        and all(
            type(row[key]) is str and bool(row[key])
            for key in ("requirement_id", "pattern_id", "source_declaration_id")
        )
        and type(row["proposal_ids"]) is list
        and bool(row["proposal_ids"])
        and all(
            type(identifier) is str and bool(identifier)
            for identifier in row["proposal_ids"]
        )
    )


def _captured_observation_links(channel):
    proposals = channel.get("proposals", [])
    observations = channel.get("pattern_observations", [])
    if type(proposals) is not list or type(observations) is not list:
        return False
    identifiers = {
        r["proposal_id"]
        for r in proposals
        if type(r) is dict and type(r.get("proposal_id")) is str and "document_id" in r
    }
    return all(
        set(row["proposal_ids"]) <= identifiers
        for row in observations
        if _captured_observation(row)
    )


def _staged_exposure_native(channel):
    from app.services.request_parser import _native

    try:
        _native(channel)
        return type(channel) is dict and _staged_exposure_policy(channel)
    except (TypeError, ValueError, RecursionError):
        return False


def _staged_exposure_schema(field, value, *, captured=False):
    from dataclasses import fields

    from app.services.contextual_source_proof import _RECORD_FIELDS
    from app.services.staged_plan_binding import StagedRequestPlan
    from app.services.staged_plan_replay import _FIELDS

    if captured and field in {
        "staged_request_inputs",
        "request_plan",
        "captured_output_certificate",
    }:
        _captured_channel_schema(field, value)
        return
    contracts = {
        "staged_request_inputs": "staged-request-inputs-v1",
        "request_plan": "staged-request-plan-v1",
        "staged_output_certificate": "procedure-output-cover-v8",
    }
    if field in contracts and value.get("contract") != contracts[field]:
        raise ValueError("Unknown staged source channel contract")
    if field == "staged_request_inputs" and set(value) != _FIELDS:
        raise ValueError("Incomplete staged source inputs")
    if field == "request_plan" and set(value) != {
        "contract",
        "reading_profile",
        "resolved_request",
        *(row.name for row in fields(StagedRequestPlan)),
    }:
        raise ValueError("Incomplete staged source plan")
    if field == "staged_output_certificate" and (
        not _STAGED_CERTIFICATE_FIELDS <= value.keys()
        or not value.keys()
        <= _STAGED_CERTIFICATE_FIELDS | {"role_scope", "curated_inspections"}
    ):
        raise ValueError("Incomplete staged output source inventory")
    if field == "source_guard_records" and any(
        type(row) is not dict
        or set(row)
        not in (_RECORD_FIELDS, _RECORD_FIELDS | {"required_copy_execution"})
        for row in value
    ):
        raise ValueError("Incomplete staged source guard record")
    if field in {
        "inspected_sources",
        "candidates",
        "proposals",
        "pattern_observations",
    }:
        for row in value:
            if not (
                captured
                and field == "pattern_observations"
                and _captured_observation(row)
            ) and not source_free_pattern_budget(row):
                _exposure_identity(row)


def _captured_source_parts(value):
    required = {
        "contract",
        "request_productions",
        "original_inputs",
        "source_inventory",
        "read_set",
        "sources",
        "sql_read_set_json",
    }
    if type(value) is not dict or not required <= value.keys():
        raise ValueError("Incomplete captured source production input")
    original = value["original_inputs"]
    if type(original) is not dict or set(original) != {
        "question",
        "capture",
        "manifest",
        "snapshots",
        "source_captures",
    }:
        raise ValueError("Incomplete captured original source input")


def _captured_channel_schema(field, value):
    from dataclasses import fields

    from app.evidence_policy import reading_version, recorded_evidence_policy
    from app.services.captured_plan_binding import CapturedRequestPlan
    from app.services.captured_plan_inputs import _FIELDS, _profile

    version = reading_version("contextual_source_v4")
    contracts = {
        "staged_request_inputs": version.request_inputs,
        "request_plan": version.request_plan,
        "captured_output_certificate": version.output,
    }
    if field == "captured_output_certificate":
        policy = recorded_evidence_policy(value["model_settings"]["evidence_profile"])
        if policy.source_governance_profile == "requirement_bound_v1":
            contracts[field] = policy.output_contract
    if value.get("contract") != contracts[field]:
        raise ValueError("Unknown captured source channel contract")
    if field == "staged_request_inputs":
        if set(value) != _FIELDS:
            raise ValueError("Incomplete captured source inputs")
        _profile(value["evidence_profile"])
        expected = {
            "request_productions": "captured-request-productions-v1",
            "source_productions": version.source_productions,
        }
        if any(
            type(value[k]) is not dict or value[k].get("contract") != c
            for k, c in expected.items()
        ):
            raise ValueError("Unknown captured production input contract")
        _captured_source_parts(value["source_productions"])
    if field == "request_plan" and set(value) != {
        "contract",
        "reading_profile",
        "resolved_request",
        "unresolved",
        *(r.name for r in fields(CapturedRequestPlan)),
    }:
        raise ValueError("Incomplete captured source plan")
    if field == "captured_output_certificate" and (
        not _STAGED_CERTIFICATE_FIELDS <= value.keys()
        or not value.keys()
        <= _STAGED_CERTIFICATE_FIELDS | {"role_scope", "curated_inspections"}
    ):
        raise ValueError("Incomplete captured output source inventory")


def _unauthorized_exposures(
    case: dict[str, Any],
    response: dict[str, Any],
    documents: dict[str, Any],
    *,
    evidence_sources=None,
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
            *(
                _requirement_evidence_sources(response)
                if evidence_sources is None
                else evidence_sources
            ),
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


def _exposure_inspection(case, response, documents):
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    if output_dispatch._requires_staged(selection, response.get("retrieval_trace")):
        sources, complete = _staged_exposure_sources(response)
        return _unauthorized_exposures(
            case, response, documents, evidence_sources=sources
        ), complete
    return _unauthorized_exposures(case, response, documents), True


def _procedure_output_context(case, response, documents):
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    query_context = response.get("retrieval_trace")
    if not output_dispatch.has_output_contract(selection, query_context):
        return {}
    authorized = None
    plan = selection.get("request_plan") or {}
    try:
        original = (
            json.loads(plan.get("source_productions_json") or "{}").get(
                "original_inputs"
            )
            or {}
        )
    except (TypeError, ValueError):
        original = {}
    if original.get("snapshots"):
        authorized = {
            str((row.get("identity") or {}).get("document_id"))
            for row in original["snapshots"]
        }
    snapshots = {}
    for document in documents.values():
        if authorized is not None and str(document["document_id"]) not in authorized:
            continue
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
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    output_context = _procedure_output_context(case, response, documents)
    if expected and output_dispatch.is_contextual(
        selection, response.get("retrieval_trace")
    ):
        completeness = output_dispatch.verify_output(selection, **output_context)
    else:
        completeness = procedure_completeness(selection, **output_context)
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
    unauthorized, exposure_complete = _exposure_inspection(case, response, documents)
    execution_error = execution_error or not exposure_complete
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
        **(
            {"source_exposure_inspection_complete": exposure_complete}
            if output_dispatch._requires_staged(
                selection, response.get("retrieval_trace")
            )
            else {}
        ),
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
