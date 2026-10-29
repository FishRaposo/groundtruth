"""Versioned literal rendering and independent immutable source/output replay.

No classifier, tokenizer, retrieval or producer success flag is an authority here.
Callers supply actual request/output and separately resolved immutable snapshots.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy

from app.services.requirement_contract import PROCEDURE_COPY_CONTRACT as COPY_CONTRACT

RENDERER = "extractive-answer-v1"
OUTPUT_CONTRACT = "procedure-output-cover-v1"
CONDITIONAL_OUTPUT_CONTRACT = "procedure-output-cover-v2"


def query_capture_signature(selection):
    """Normalize retained execution inputs, excluding derived presentation stamps.

    The caller owns the separately retained trace. This function never obtains
    authority from the mutable certificate or a producer's absence marker.
    """
    from app.services.requirement_contract import (
        _CONDITION_READER_FIELDS,
        _CONDITION_SUPPORT_FIELDS,
    )

    def ordered(items):
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))

    def sources(items):
        return ordered(
            [
                {
                    key: item[key]
                    for key in (
                        "chunk_id",
                        "document_id",
                        "document_version",
                        "content_hash",
                    )
                }
                for item in items
            ]
        )

    read_set = selection.get("procedure_read_set") or {}
    signature = {
        "requirements": [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "kind",
                    "original_text",
                    "input_range",
                    "source_workspace",
                    "depends_on",
                    "prepared_question",
                )
            }
            for row in selection["requirements"]
        ],
        "evidence_profile": selection["evidence_profile"],
        "reader": {
            key: selection.get(key)
            for key in (*_CONDITION_READER_FIELDS, "reader_contract")
        },
        "support": {
            key: selection.get("evidence_support", {}).get(key)
            for key in _CONDITION_SUPPORT_FIELDS
        },
        "inspected_sources": sources(selection["inspected_sources"]),
        "procedure_contexts": ordered(
            [
                {
                    **{
                        key: context[key]
                        for key in (
                            "document_id",
                            "document_version",
                            "content_hash",
                            "workspace_id",
                            "origin",
                        )
                    },
                    "sources": sources(context["sources"]),
                }
                for context in selection.get("procedure_contexts", [])
            ]
        ),
        "procedure_read_set": {
            **{
                key: read_set.get(key)
                for key in ("contract", "document_ids", "collection_ids")
            },
            "sources": ordered(read_set.get("sources", [])),
            "groups": ordered(
                [
                    {"group": group["group"], "sources": ordered(group["sources"])}
                    for group in read_set.get("groups", [])
                ]
            ),
        },
    }
    if selection.get("evidence_profile", {}).get("source_context_policy") in (
        "scoped_note_context_v1",
        "scoped_note_context_v2",
    ):
        signature["contextual_semantics"] = {
            "conflicts": deepcopy(selection.get("conflicts", [])),
            "proofs": [
                {
                    key: deepcopy(row.get("procedure_completeness", {}).get(key))
                    for key in (
                        "proof_units",
                        "required_inventory",
                        "request_binding",
                        "extent",
                        "source_body",
                    )
                }
                for row in selection["requirements"]
                if row.get("kind") == "procedure"
            ],
        }
    return signature


def retained_selection(query_context):
    """Return a real capture, or None for a metadata-only legacy trace.

    An explicitly recorded but malformed capture is not legacy absence.
    """
    if not isinstance(query_context, dict):
        raise ValueError("Malformed retained query context")
    provenance = query_context.get("provenance")
    if provenance is None:
        return None
    if not isinstance(provenance, dict):
        raise ValueError("Malformed retained provenance")
    if "answer_selection" not in provenance:
        return None
    capture = provenance["answer_selection"]
    if not isinstance(capture, dict):
        raise ValueError("Malformed retained selection")
    return capture


def _legacy_trace_members(selection, query_context):
    """A missing full capture cannot erase independently retained score members."""
    known = selection["inspected_sources"]
    scores = query_context.get("scores", [])
    if not isinstance(scores, list):
        raise ValueError("Malformed legacy retrieved-source capture")
    for score in scores:
        version = score.get("document_version")
        if version is not None and (type(version) is not int or version <= 0):
            raise ValueError("Malformed legacy source version")
        if not any(
            member["document_id"] == score["document_id"]
            and (version is None or member["document_version"] == version)
            and (
                score.get("chunk_id") is None or member["chunk_id"] == score["chunk_id"]
            )
            for member in known
        ):
            raise ValueError("Presentation omits a retained retrieved source")


def render_extractive(citations, groups=(), disclosures=()):
    """One renderer shared by publication and saved-answer verification."""
    indices = {str(c["chunk_id"]): c["citation_index"] for c in citations}
    extracts = []
    segments = {}
    for group in groups:
        extracts.append(
            group["text"]
            + " "
            + " ".join(f"[{indices[identifier]}]" for identifier in group["chunk_ids"])
        )
    for citation in citations:
        identifier, passage = str(citation["chunk_id"]), citation["quoted_text"]
        spans = citation.get("answer_spans") or []
        if not groups:
            extract = "\n".join(s["text"] for s in spans) if spans else passage
            extracts.append(f"{extract} [{citation['citation_index']}]")
            continue
        covered = sorted(
            (f["start"], f["end"])
            for g in groups
            for f in g["fragments"]
            if f["chunk_id"] == identifier
        )
        for span in spans:
            remaining = [(span["start"], span["end"])]
            for left, right in covered:
                remaining = [
                    (a, min(b, left)) for a, b in remaining if a < min(b, left)
                ] + [(max(a, right), b) for a, b in remaining if max(a, right) < b]
            extracts.extend(
                f"{passage[a:b]} [{citation['citation_index']}]"
                for a, b in remaining
                if passage[a:b].strip()
            )
    prefix = (
        "Source extracts with declared activity-scope interpretation:\n\n"
        if disclosures
        else "Source extracts (not model-generated):\n\n"
    )
    cursor = len(prefix)
    for group, extract in zip(groups, extracts, strict=False):
        segments[group["requirement_id"]] = {
            "start": cursor,
            "end": cursor + len(group["text"]),
        }
        cursor += len(extract) + 2
    return prefix + "\n\n".join([*extracts, *disclosures]), segments


def _source(proof, snapshots):
    from app.models.chunk import ChunkWithScore
    from app.services.procedure_evidence import (
        MAX_BODY_BYTES,
        MAX_CHUNKS,
        LocatedChunk,
        ProcedureSource,
    )

    snapshot = snapshots[proof["document_id"]]
    identity = {
        k: proof[k] for k in ("document_id", "document_version", "content_hash")
    }
    if "workspace_id" in proof:
        identity["workspace_id"] = proof["workspace_id"]
    if any(snapshot.get(k) != v for k, v in identity.items()):
        raise ValueError("Immutable identity mismatch")
    body = snapshot["body"]
    if (
        not isinstance(body, str)
        or body != proof["source_body"]
        or len(body) != proof["body_length"]
        or len(body.encode()) > MAX_BODY_BYTES
        or hashlib.sha256(body.encode()).hexdigest() != identity["content_hash"]
    ):
        raise ValueError("Immutable body mismatch")
    manifest = snapshot["chunks"]
    if not isinstance(manifest, list) or not 1 <= len(manifest) <= MAX_CHUNKS:
        raise ValueError("Immutable chunk budget")
    located, ids, indices = [], set(), set()
    for item in manifest:
        identifier, index, text = uuid.UUID(item["id"]), item["index"], item["content"]
        if (
            identifier in ids
            or type(index) is not int
            or index < 0
            or index in indices
            or not isinstance(text, str)
            or not text
        ):
            raise ValueError("Immutable chunk identity mismatch")
        start = body.find(text)
        if start < 0 or body.find(text, start + 1) >= 0:
            raise ValueError("Ambiguous immutable chunk mapping")
        chunk = ChunkWithScore(
            id=identifier,
            document_id=uuid.UUID(identity["document_id"]),
            content=text,
            chunk_index=index,
            relevance_score=0.0,
            metadata={**snapshot.get("metadata", {}), **identity},
        )
        located.append(LocatedChunk(chunk, start, start + len(text)))
        ids.add(identifier)
        indices.add(index)
    located.sort(key=lambda c: c.chunk.chunk_index)
    if any(
        a.start >= b.start or a.end >= b.end
        for a, b in zip(located, located[1:], strict=False)
    ):
        raise ValueError("Immutable chunk ordering mismatch")
    return ProcedureSource(
        body,
        tuple(located),
        identity,
        snapshot.get("metadata", {}),
        snapshot.get("captured_scope"),
    )


def _canonical_group(proof, requirement, question, citations, snapshots):  # noqa: C901 - bounded canonical source and certificate replay
    from app.services.procedure_evidence import bind_extent, project_cover
    from app.services.procedure_support import (
        COPY_PROFILE,
        build_plan,
        copy_request_binding,
        verification_method,
    )
    from app.services.requirement_contract import _units_valid

    if (
        proof["contract"] != COPY_CONTRACT
        or proof["status"] != "supported"
        or proof["coverage_complete"] is not True
        or proof["procedure_verification_profile"] != COPY_PROFILE
        or proof["request_binding"] != copy_request_binding(requirement, question)
    ):
        raise ValueError("Procedure request binding mismatch")
    source = _source(proof, snapshots)
    raw = proof["raw_seed"]
    seed = next(c.chunk for c in source.chunks if str(c.chunk.id) == raw["chunk_id"])
    extent = bind_extent(
        requirement, source, seed, {**raw["chunk_range"], "text": raw["text"]}
    )
    if raw["document_range"] != {"start": extent.raw_start, "end": extent.raw_end}:
        raise ValueError("Raw source position mismatch")
    plan = build_plan(requirement, source, extent)
    copy_request_binding(requirement, question, plan=plan, source=source)
    if not {"namespace", "applicability"}.issubset({u.kind for u in plan.units}):
        raise ValueError("Source declaration required")
    closure = {"kind": extent.closure, "end": extent.claim.end}
    if extent.boundary:
        closure["boundary_range"] = {
            "start": extent.boundary[0],
            "end": extent.boundary[1],
        }
    expected = {
        "extent": {"start": plan.start, "end": plan.end},
        "closure": closure,
        "structure": plan.structure,
        "step_count": len(plan.steps) if plan.structure == "numbered" else None,
        "mandatory_proof_count": len(plan.units),
        "step_ranges": [{"ordinal": n, "start": a, "end": b} for n, a, b in plan.steps],
        "required_inventory": plan.required_inventory(source),
        "structure_edges": list(plan.edges),
    }
    if any(proof[k] != v for k, v in expected.items()) or len(
        proof["proof_units"]
    ) != len(plan.units):
        raise ValueError("Canonical inventory mismatch")
    for unit, record in zip(plan.units, proof["proof_units"], strict=True):
        method = verification_method(unit)
        fields = {
            "name": unit.name,
            "kind": unit.kind,
            "source_range": {"start": unit.start, "end": unit.end},
            "premise_range": unit.premise_range,
            "hypothesis": unit.hypothesis,
            "verification_method": method,
            "supported": True,
        }
        if any(record.get(k) != v for k, v in fields.items()):
            raise ValueError("Canonical obligation mismatch")
        if method == "nli_entailment":
            if not _units_valid(
                {"mandatory_proof_count": 1, "proof_units": [record]}, len(source.body)
            ):
                raise ValueError("NLI obligation rejected")
        elif set(record) != set(fields):
            raise ValueError("Non-NLI obligation contains classifier fields")
    fragments = project_cover(source, plan.start, plan.end, plan.steps)
    expected_parts = [
        {
            "chunk_id": str(c.id),
            "chunk_start": s.start,
            "chunk_end": s.end,
            "document_start": a,
            "document_end": b,
        }
        for c, s, a, b in fragments
    ]
    if proof["fragments"] != expected_parts:
        raise ValueError("Canonical fragment mismatch")
    mapping = []
    for chunk, span, _left, _right in fragments:
        matches = [c for c in citations if str(c["chunk_id"]) == str(chunk.id)]
        if len(matches) != 1:
            raise ValueError("Missing unique procedure citation")
        citation = matches[0]
        if any(
            citation.get(k) != source.identity[k]
            for k in ("document_id", "document_version", "content_hash")
        ):
            raise ValueError("Citation immutable identity mismatch")
        if citation["quoted_text"] != chunk.content or not any(
            s["start"] <= span.start < span.end <= s["end"]
            for s in citation["answer_spans"]
        ):
            raise ValueError("Citation does not cover procedure")
        mapping.append(
            {
                **expected_parts[len(mapping)],
                "citation_index": citation["citation_index"],
            }
        )
    return {
        "requirement_id": requirement.id,
        "text": source.body[plan.start : plan.end],
        "chunk_ids": [str(c.id) for c, *_ in fragments],
        "fragments": [
            {"chunk_id": str(c.id), "start": s.start, "end": s.end}
            for c, s, *_ in fragments
        ],
    }, mapping


def _inspection_source(identity, snapshots):
    snapshot = snapshots[identity["document_id"]]
    if (
        type(identity["document_version"]) is not int
        or identity["document_version"] <= 0
    ):
        raise ValueError("Invalid inspection version")
    return _source(
        {
            **{
                key: identity[key]
                for key in (
                    "document_id",
                    "document_version",
                    "content_hash",
                    "workspace_id",
                )
            },
            "source_body": snapshot["body"],
            "body_length": len(snapshot["body"]),
        },
        snapshots,
    )


def _condition_context(selection, snapshots):  # noqa: C901 - full immutable inspection manifest replay
    """Bind all captured members before interpreting any excluded condition."""
    from app.services.requirement_contract import PROCEDURE_READ_SET_CONTRACT

    read_set = selection["procedure_read_set"]
    if (
        read_set["contract"] != PROCEDURE_READ_SET_CONTRACT
        or read_set["after_proofs"]["consistent"] is not True
    ):
        raise ValueError("Incomplete condition inspection read set")
    if read_set.get("before_publication", {}).get("consistent", True) is not True:
        raise ValueError("Stale condition inspection read set")
    for field in ("document_ids", "collection_ids"):
        values = read_set[field]
        if values is not None and (
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(str(uuid.UUID(value)) != value for value in values)
        ):
            raise ValueError("Invalid captured query scope")
    known, sources, documents, groups = {}, [], {}, {}
    for entry in read_set["sources"]:
        if entry["chunk_id"] in known:
            raise ValueError("Duplicate inspected member")
        source = _inspection_source(entry, snapshots)
        chunk = next(
            c.chunk for c in source.chunks if str(c.chunk.id) == entry["chunk_id"]
        )
        expected = {
            "chunk_id": str(chunk.id),
            **source.identity,
            "condition": entry["condition"],
            "conflict_group": entry["conflict_group"],
            "chunk_hash": hashlib.sha256(chunk.content.encode()).hexdigest(),
        }
        if entry != expected:
            raise ValueError("Inspected immutable member mismatch")
        if (
            read_set["document_ids"] is not None
            and entry["document_id"] not in read_set["document_ids"]
        ):
            raise ValueError("Inspected member outside captured request")
        metadata = snapshots[entry["document_id"]].get("metadata", {})
        if any(
            key in metadata and metadata[key] != entry[key]
            for key in ("condition", "conflict_group")
        ):
            raise ValueError("Independent source context mismatch")
        previous = documents.get(entry["document_id"])
        if previous is not None and any(
            previous[key] != entry[key]
            for key in (
                "document_version",
                "content_hash",
                "workspace_id",
                "condition",
                "conflict_group",
            )
        ):
            raise ValueError("Inconsistent document inspection context")
        documents[entry["document_id"]] = entry
        known[entry["chunk_id"]] = entry
        sources.append(expected)
        group = entry["conflict_group"]
        if group is not None:
            if not isinstance(group, str) or not group:
                raise ValueError("Invalid curated group")
            groups.setdefault(group, []).append(expected)
    minimal = ("chunk_id", "document_id", "document_version", "content_hash")
    inspected = selection["inspected_sources"]
    if len(inspected) != len(known) or {
        item["chunk_id"]: {key: item[key] for key in minimal} for item in inspected
    } != {
        identifier: {key: item[key] for key in minimal}
        for identifier, item in known.items()
    }:
        raise ValueError("Complete inspected source inventory mismatch")
    normalized = {
        group: sorted(members, key=lambda item: item["chunk_id"])
        for group, members in groups.items()
    }
    captured = {}
    for group in read_set["groups"]:
        members = sorted(group["sources"], key=lambda item: item["chunk_id"])
        if members != normalized[group["group"]] or (
            group["group"] in captured and captured[group["group"]] != members
        ):
            raise ValueError("Complete curated membership mismatch")
        captured[group["group"]] = members
    if captured != normalized:
        raise ValueError("Omitted curated inspection group")
    for identifier, entry in documents.items():
        if entry["conflict_group"] is None:
            continue
        source = _inspection_source(entry, snapshots)
        expected_ids = {
            str(c.chunk.id): {key: source.identity[key] for key in minimal[1:]}
            for c in source.chunks
        }
        if set(expected_ids) != {
            chunk_id
            for chunk_id, member in known.items()
            if member["document_id"] == identifier
        }:
            raise ValueError("Incomplete immutable curated chunk membership")
        contexts = [
            context
            for context in selection["procedure_contexts"]
            if context.get("document_id") == identifier
            and context.get("origin") == "curated-procedure-inspection"
        ]
        if not contexts or any(
            any(context[key] != source.identity[key] for key in source.identity)
            or {
                item["chunk_id"]: {key: item[key] for key in minimal[1:]}
                for item in context["sources"]
            }
            != expected_ids
            or len(context["sources"]) != len(expected_ids)
            for context in contexts
        ):
            raise ValueError("Missing complete immutable procedure context")
    return {
        "document_ids": read_set["document_ids"],
        "collection_ids": read_set["collection_ids"],
        "sources": sorted(sources, key=lambda item: item["chunk_id"]),
        "groups": [
            {"group": name, "sources": normalized[name]} for name in sorted(normalized)
        ],
    }, documents


def _condition_inventory(proof, requirement, question, selection, snapshots):  # noqa: C901 - reconstruct mandatory exclusions independently of recorded discharge
    from app.services.procedure_evidence import discover_procedure_candidates
    from app.services.procedure_support import (
        build_plan,
        copy_request_binding,
        verification_method,
    )
    from app.services.requirement_binding import condition_relation
    from app.services.requirement_conflict_scope import procedure_condition_exclusion
    from app.services.requirement_contract import (
        CONDITION_INVENTORY_CONTRACT,
        valid_condition_assessment,
        valid_condition_model_settings,
    )

    conflicts = [
        c
        for c in selection.get("conflicts", [])
        if c.get("requirement_id") == requirement.id
    ]
    hint = (
        "condition_exclusion_inventory" in proof
        or any(
            "condition_scope" in check
            for conflict in conflicts
            for check in conflict.get("source_extent_checks", [])
        )
        or proof.get("output_certificate", {}).get("contract")
        in (
            CONDITIONAL_OUTPUT_CONTRACT,
            "procedure-output-cover-v3",
            "procedure-output-cover-v4",
        )
    )
    captured_sources = selection.get("procedure_read_set", {}).get("sources", [])
    if captured_sources and (
        len(captured_sources) != len(selection["inspected_sources"])
        or {entry["chunk_id"] for entry in captured_sources}
        != {entry["chunk_id"] for entry in selection["inspected_sources"]}
    ):
        raise ValueError("Omitted complete inspection manifest")
    required = {}
    for entry in captured_sources:
        if not entry.get("conflict_group"):
            continue
        source = _inspection_source(entry, snapshots)
        metadata = {key: entry[key] for key in ("condition", "conflict_group")}
        candidate = procedure_condition_exclusion(
            requirement,
            source.body,
            metadata,
            [proof],
            context_policy=selection.get("evidence_profile", {}).get(
                "source_context_policy", "explicit_target_v1"
            ),
        )
        if (
            candidate is not None
            and condition_relation(requirement, source.body, metadata) != "irrelevant"
        ):
            required[(entry["conflict_group"], entry["document_id"])] = candidate
    for context in selection.get("procedure_contexts", []):
        if context.get("origin") != "curated-procedure-inspection":
            continue
        source = _inspection_source(context, snapshots)
        captured = next(
            (
                entry
                for entry in captured_sources
                if entry["document_id"] == context["document_id"]
            ),
            None,
        )
        if captured is None:
            raise ValueError("Curated context absent from inspection manifest")
        metadata = {key: captured[key] for key in ("condition", "conflict_group")}
        candidate = procedure_condition_exclusion(
            requirement,
            source.body,
            metadata,
            [proof],
            context_policy=selection.get("evidence_profile", {}).get(
                "source_context_policy", "explicit_target_v1"
            ),
        )
        if (
            candidate is not None
            and condition_relation(requirement, source.body, metadata) != "irrelevant"
            and (captured["conflict_group"], context["document_id"]) not in required
        ):
            raise ValueError("Omitted required curated condition inventory")
    if not required:
        if hint:
            raise ValueError("Forged or unbound condition exclusion inventory")
        return None
    if len(required) > 64:
        raise ValueError("Conditional obligation budget exceeded")
    manifest, documents = _condition_context(selection, snapshots)
    groups, exclusions, settings, opponent_nli = [], [], None, []
    for group_name in sorted({key[0] for key in required}):
        members = next(
            group["sources"]
            for group in manifest["groups"]
            if group["group"] == group_name
        )
        matching = [
            conflict for conflict in conflicts if conflict.get("group") == group_name
        ]
        if len(matching) != 1:
            raise ValueError("Missing unique curated condition comparison")
        conflict = matching[0]
        if sorted(
            conflict["inspection_sources"], key=lambda item: item["chunk_id"]
        ) != members or (
            conflict["inspection_method"] != COPY_CONTRACT
            or conflict["inspection_complete"] is not True
            or conflict["relevant"] is not False
        ):
            raise ValueError("Invalid condition comparison context")
        excluded, applicable, checked = [], [], set()
        member_ids = sorted({entry["document_id"] for entry in members})
        for identifier in member_ids:
            source = _inspection_source(documents[identifier], snapshots)
            metadata = {
                key: documents[identifier][key]
                for key in ("condition", "conflict_group")
            }
            if condition_relation(requirement, source.body, metadata) == "irrelevant":
                excluded.append(identifier)
                continue
            checks = [
                check
                for check in conflict["source_extent_checks"]
                if check.get("document_id") == identifier
            ]
            if len(checks) != 1:
                raise ValueError("Missing mandatory source condition discharge")
            check = checks[0]
            checked.add(identifier)
            representative = source.chunks[0].chunk
            expected_identity = {
                "chunk_id": str(representative.id),
                **{
                    key: source.identity[key]
                    for key in ("document_id", "document_version", "content_hash")
                },
            }
            if any(
                check.get(key) != value for key, value in expected_identity.items()
            ) or (
                check.get("proposal_origin") != "structural-opponent-inspection"
                or check.get("answer_witness") is not False
            ):
                raise ValueError("Conditional source identity mismatch")
            candidate = required.get((group_name, identifier))
            if candidate is not None:
                scope = check["condition_scope"]
                current_settings = scope["model_settings"]
                if not valid_condition_model_settings(current_settings, selection) or (
                    settings is not None and settings != current_settings
                ):
                    raise ValueError("Invalid recorded condition inference settings")
                settings = current_settings
                if candidate["contract"] in (
                    "procedure-condition-scope-v2",
                    "procedure-condition-scope-v3",
                ):
                    from app.services.source_context_scope import replay_context_scope

                    expected = replay_context_scope(
                        candidate, scope, source, requirement, current_settings
                    )
                else:
                    expected = {
                        **candidate,
                        "model_settings": current_settings,
                        "pair": {
                            "premise": source.body,
                            "hypothesis": candidate["hypothesis"],
                            "requirement_id": requirement.id,
                            "reference_id": f"{identifier}:condition-scope",
                        },
                        "assessment": scope["assessment"],
                        "verification_method": "nli_entailment",
                        "reason": "verified_excluded_source_condition",
                    }
                if (
                    scope != expected
                    or (
                        candidate["contract"] == "procedure-condition-scope-v1"
                        and not valid_condition_assessment(
                            scope["assessment"], settings
                        )
                    )
                    or (
                        check["status"] != "irrelevant"
                        or check["reason"] != expected["reason"]
                    )
                ):
                    raise ValueError("Invalid mandatory condition scope proof")
                exclusions.append(
                    {
                        "group": group_name,
                        "source_identity": source.identity,
                        "condition_scope": deepcopy(expected),
                    }
                )
                excluded.append(identifier)
            else:
                # An ordinary/mixed member cannot disappear behind excluded peers.
                extents = discover_procedure_candidates(requirement, source)
                if len(extents) != 1 or check["status"] != "supported":
                    raise ValueError("Unverified applicable procedure opponent")
                plan = build_plan(requirement, source, extents[0])
                copy_request_binding(requirement, question, plan=plan, source=source)
                if (
                    check["required_inventory"] != plan.required_inventory(source)
                    or source.body[plan.start : plan.end]
                    != proof["source_body"][
                        proof["extent"]["start"] : proof["extent"]["end"]
                    ]
                ):
                    raise ValueError("Applicable procedure opponent differs")
                records = check["proof_units"]
                expected_step_count = (
                    None
                    if check.get("contract") == COPY_CONTRACT
                    and plan.structure != "numbered"
                    else len(plan.steps)
                )
                if len(records) != len(plan.units) or (
                    check["extent"] != {"start": plan.start, "end": plan.end}
                    or check["mandatory_proof_count"] != len(plan.units)
                    or check["step_count"] != expected_step_count
                ):
                    raise ValueError("Incomplete applicable opponent inventory")
                for unit, record in zip(plan.units, records, strict=True):
                    if any(
                        record.get(key) != value
                        for key, value in {
                            "name": unit.name,
                            "kind": unit.kind,
                            "source_range": {"start": unit.start, "end": unit.end},
                            "premise_range": unit.premise_range,
                            "hypothesis": unit.hypothesis,
                            "verification_method": verification_method(unit),
                            "supported": True,
                        }.items()
                    ):
                        raise ValueError("Applicable opponent obligation mismatch")
                    if verification_method(unit) == "nli_entailment":
                        opponent_nli.append(record)
                applicable.append(identifier)
        if len(conflict["source_extent_checks"]) != len(checked) or (
            sorted(conflict["subject_scope_excluded_documents"]) != excluded
            or sorted(conflict["applicable_documents"]) != applicable
            or conflict["requested_fact_agreement"] is not bool(applicable)
            or conflict["outcome"] != ("agreement" if applicable else "not_relevant")
        ):
            raise ValueError("Incomplete curated condition disposition inventory")
        groups.append(
            {
                "group": group_name,
                "sources": members,
                "excluded_documents": excluded,
                "applicable_documents": applicable,
            }
        )
    assert settings is not None
    # The declaration relied on by each exclusion is itself mandatory NLI.
    for record in [*proof["proof_units"], *opponent_nli]:
        if record[
            "verification_method"
        ] == "nli_entailment" and not valid_condition_assessment(record, settings):
            raise ValueError("Invalid source applicability supporting an exclusion")
    for conflict in conflicts:
        for check in conflict.get("source_extent_checks", []):
            if (
                "condition_scope" in check
                and (conflict["group"], check["document_id"]) not in required
            ):
                raise ValueError("Unexpected condition exclusion discharge")
    source_contexts = []
    for _identifier, entry in sorted(documents.items()):
        if entry["conflict_group"] is None:
            continue
        source = _inspection_source(entry, snapshots)
        source_contexts.append(
            {
                "source_identity": source.identity,
                "source_body": source.body,
                "metadata": {
                    key: entry[key] for key in ("condition", "conflict_group")
                },
                "chunks": [
                    {
                        "chunk_id": str(part.chunk.id),
                        "index": part.chunk.chunk_index,
                        "content": part.chunk.content,
                        "document_range": {"start": part.start, "end": part.end},
                        "chunk_hash": hashlib.sha256(
                            part.chunk.content.encode()
                        ).hexdigest(),
                    }
                    for part in source.chunks
                ],
            }
        )
    return {
        "contract": (
            "procedure-condition-exclusion-inventory-v3"
            if selection.get("evidence_profile", {}).get("source_context_policy")
            == "scoped_note_context_v2"
            else "procedure-condition-exclusion-inventory-v2"
        )
        if selection.get("evidence_profile", {}).get("source_context_policy")
        in ("scoped_note_context_v1", "scoped_note_context_v2")
        else CONDITION_INVENTORY_CONTRACT,
        "request_binding": copy_request_binding(requirement, question),
        "model_settings": deepcopy(settings),
        "inspection_manifest": manifest,
        "source_contexts": source_contexts,
        "groups": groups,
        "exclusions": exclusions,
    }


def _unbound_condition_absence(proof, requirement, selection, snapshots):
    """No retained capture: independently known scoped candidates make absence unknown.

    This does not declare oracle documents inspected or invent obligations from
    the whole corpus. A retained capture can establish a narrower inspected set;
    without it, a missing conditional branch cannot prove its own absence.
    """
    from app.services.requirement_binding import condition_relation
    from app.services.requirement_conflict_scope import procedure_condition_exclusion

    scope = selection.get("procedure_read_set", {}).get("document_ids")
    for identifier, snapshot in snapshots.items():
        if scope is not None and identifier not in scope:
            continue
        metadata = snapshot.get("metadata") or {}
        source = _inspection_source(snapshot, snapshots)
        if (
            procedure_condition_exclusion(
                requirement,
                source.body,
                metadata,
                [proof],
                context_policy=selection.get("evidence_profile", {}).get(
                    "source_context_policy", "explicit_target_v1"
                ),
            )
            is not None
            and condition_relation(requirement, source.body, metadata) != "irrelevant"
        ):
            raise ValueError(
                "Independent retained query context is required "
                "to establish condition absence"
            )


def _replay(  # noqa: C901 - complete request/output cross-contract replay
    selection, *, question, answer, citations, source_snapshots, query_context=None
):
    from app.services.answer_requirements import plan_requirements
    from app.services.requirement_contract import (
        validate_discovery_lineage,
        validate_role_scope_evidence,
    )

    if (
        selection.get("evidence_profile", {}).get("procedure_verification_profile")
        != "source_declared_procedure_copy_v1"
        or validate_discovery_lineage(selection).get("valid") is not True
        or validate_role_scope_evidence(selection).get("valid") is False
    ):
        raise ValueError("Invalid recorded evidence lineage")

    if (
        not isinstance(question, str)
        or not isinstance(answer, str)
        or not isinstance(citations, list)
    ):
        raise ValueError("Actual presentation context required")
    captured = retained_selection(query_context) if query_context is not None else None
    if (
        selection.get("evidence_profile", {}).get("source_context_policy")
        in ("scoped_note_context_v1", "scoped_note_context_v2")
        and captured is None
    ):
        raise ValueError(
            "Contextual reading requires independently retained execution evidence"
        )
    if (
        captured is not None
        and selection.get("evidence_profile", {}).get("source_context_policy")
        == "scoped_note_context_v2"
    ):
        if json.dumps(
            query_capture_signature(selection), sort_keys=True, allow_nan=False
        ) != json.dumps(
            query_capture_signature(captured), sort_keys=True, allow_nan=False
        ):
            raise ValueError("Typed contextual evidence differs from retained capture")
    if captured is not None and query_capture_signature(
        selection
    ) != query_capture_signature(captured):
        raise ValueError(
            "Presentation differs from independently retained query capture"
        )
    if query_context is not None and captured is None:
        _legacy_trace_members(selection, query_context)
    planned = plan_requirements(question)
    requirements = selection["requirements"]
    if len(requirements) != len(planned):
        raise ValueError("Entire request inventory mismatch")
    groups, pending, seen = [], [], set()
    for row, requirement in zip(requirements, planned, strict=True):
        if (
            row.get("id") != requirement.id
            or row.get("kind") != requirement.kind
            or row.get("original_text") != requirement.original_text
            or row.get("input_range")
            != {"start": requirement.input_start, "end": requirement.input_end}
            or row.get("status") != "supported"
        ):
            raise ValueError("Actual request plan mismatch")
        if requirement.kind != "procedure":
            continue
        proof = row["procedure_completeness"]
        group, mapping = _canonical_group(
            proof, requirement, question, citations, source_snapshots
        )
        groups.append(group)
        inventory = _condition_inventory(
            proof, requirement, question, selection, source_snapshots
        )
        if inventory is not None and query_context is not None and captured is None:
            raise ValueError("Conditional output requires a retained execution capture")
        if inventory is None and captured is None:
            _unbound_condition_absence(proof, requirement, selection, source_snapshots)
        pending.append((proof, mapping, requirement, inventory))
    if not pending:
        raise ValueError("No v3 procedure")
    _validate_selected_passages(selection, citations, groups, source_snapshots)
    for index, citation in enumerate(citations, 1):
        identifier = str(citation["chunk_id"])
        if citation["citation_index"] != index or identifier in seen:
            raise ValueError("Citation order mismatch")
        seen.add(identifier)
        passage = citation["quoted_text"]
        for span in citation["answer_spans"]:
            a, b = span["start"], span["end"]
            if (
                type(a) is not int
                or type(b) is not int
                or not 0 <= a < b <= len(passage)
                or passage[a:b] != span["text"]
            ):
                raise ValueError("Nonliteral answer span")
    disclosures = [
        item["disclosure"]
        for item in selection.get("role_scope_interpretations", [])
        if item.get("activity_fallback")
    ]
    disclosures.extend(
        sorted(
            {
                exclusion["condition_scope"]["context_reading"]["disclosure"]
                for _, _, _, inventory in pending
                if inventory
                for exclusion in inventory["exclusions"]
                if exclusion["condition_scope"]["contract"]
                in ("procedure-condition-scope-v2", "procedure-condition-scope-v3")
            }
        )
    )
    expected_answer, segments = render_extractive(citations, groups, disclosures)
    if answer != expected_answer:
        raise ValueError("Actual answer differs from canonical renderer")
    certificates = []
    for proof, mapping, requirement, inventory in pending:
        certificates.append(
            (
                proof,
                {
                    "contract": (
                        (
                            "procedure-output-cover-v4"
                            if inventory["contract"]
                            == "procedure-condition-exclusion-inventory-v3"
                            else "procedure-output-cover-v3"
                        )
                        if inventory
                        and inventory["contract"]
                        in (
                            "procedure-condition-exclusion-inventory-v2",
                            "procedure-condition-exclusion-inventory-v3",
                        )
                        else CONDITIONAL_OUTPUT_CONTRACT
                    )
                    if inventory
                    else OUTPUT_CONTRACT,
                    "renderer": RENDERER,
                    "request_binding": proof["request_binding"],
                    "source_identity": {
                        k: proof[k]
                        for k in ("document_id", "document_version", "content_hash")
                    },
                    "required_inventory": proof["required_inventory"],
                    "instruction_range": proof["extent"],
                    "answer_range": segments[requirement.id],
                    "citation_mapping": mapping,
                    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                    **(
                        {"condition_exclusion_inventory": inventory}
                        if inventory
                        else {}
                    ),
                },
            )
        )
    return certificates


def _validate_selected_passages(selection, citations, groups, snapshots):  # noqa: C901 - replay the existing witness-span union
    """Replay the existing selected-witness span union, including other facts."""
    from app.models.query import AnswerSpan
    from app.services.requirement_answers import Witness, _selected_passages

    chunks = {}
    for citation in citations:
        snapshot = snapshots[citation["document_id"]]
        source = _source(
            {
                **{
                    k: citation[k]
                    for k in ("document_id", "document_version", "content_hash")
                },
                "workspace_id": snapshot["workspace_id"],
                "source_body": snapshot["body"],
                "body_length": len(snapshot["body"]),
            },
            snapshots,
        )
        chunk = next(
            c.chunk
            for c in source.chunks
            if str(c.chunk.id) == str(citation["chunk_id"])
        )
        if chunk.content != citation["quoted_text"]:
            raise ValueError("Citation differs from immutable chunk")
        chunks[str(chunk.id)] = chunk
    selected = []
    for group in groups:
        for part in group["fragments"]:
            chunk = chunks[part["chunk_id"]]
            span = AnswerSpan(
                start=part["start"],
                end=part["end"],
                text=chunk.content[part["start"] : part["end"]],
            )
            selected.append(
                Witness(group["requirement_id"], chunk, span, "", "", 0, None)
            )
    identifiers = set(selection["selected_proposal_ids"])
    for row in selection["requirements"]:
        if row["kind"] == "procedure":
            continue
        matching = [
            w
            for w in row["witnesses"]
            if any(p["proposal_id"] in identifiers for p in w["proposals"])
        ]
        if not matching:
            raise ValueError("No selected factual witness")
        for witness in matching:
            chunk = chunks[witness["chunk_id"]]
            span = AnswerSpan.model_validate(witness["span"])
            if chunk.content[span.start : span.end] != span.text:
                raise ValueError("Factual witness is not literal")
            selected.append(Witness(row["id"], chunk, span, "", "", 0, None))
    expected = _selected_passages(selected)
    for citation in citations:
        spans = expected.get(uuid.UUID(str(citation["chunk_id"])), ())
        if citation["answer_spans"] != [s.model_dump(mode="json") for s in spans]:
            raise ValueError(
                "Actual extracts differ from selected factual/procedure witnesses"
            )


def certify_output(selection, **context):
    """Stage -> certified only after reconstructing actual full canonical output."""
    for proof, certificate in _replay(selection, **context):
        inventory = certificate.get("condition_exclusion_inventory")
        if inventory is not None:
            if (
                "condition_exclusion_inventory" in proof
                and proof["condition_exclusion_inventory"] != inventory
            ):
                raise ValueError(
                    "Staged condition inventory differs from canonical obligations"
                )
            proof["condition_exclusion_inventory"] = deepcopy(inventory)
        proof["output_certificate"] = deepcopy(certificate)


def verify_output(selection, **context) -> bool:
    try:
        return all(
            proof.get("output_certificate") == certificate
            and proof.get("condition_exclusion_inventory")
            == certificate.get("condition_exclusion_inventory")
            for proof, certificate in _replay(selection, **context)
        )
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, StopIteration):
        return False


def has_v3(selection, query_context=None):
    if query_context is not None:
        try:
            if has_v3(retained_selection(query_context)):
                return True
        except (KeyError, TypeError, AttributeError, ValueError):
            pass
    if not isinstance(selection, dict):
        return False
    profile = selection.get("evidence_profile")
    profile = profile if isinstance(profile, dict) else {}
    rows = selection.get("requirements", [])
    copy_profile = (
        profile.get("procedure_verification_profile")
        == "source_declared_procedure_copy_v1"
    )
    if not isinstance(rows, list):
        return copy_profile
    return (
        any(
            isinstance(row, dict)
            and row.get("kind") == "procedure"
            and row.get("status") == "supported"
            for row in rows
        )
        and copy_profile
    ) or any(
        isinstance(row, dict)
        and isinstance(row.get("procedure_completeness"), dict)
        and row["procedure_completeness"].get("contract") == COPY_CONTRACT
        for row in rows
    )


async def load_snapshots(db, selection, *, query_context=None):  # noqa: C901 - legacy versions plus opt-in role receipts
    """Historical versions are independently loaded, never copied from certificates."""
    from app.services.output_dispatch import _requires_staged

    if _requires_staged(selection, query_context):
        from app.services.staged_snapshot_store import load_staged_snapshots

        return await load_staged_snapshots(db, selection, query_context=query_context)
    from sqlalchemy import select

    from app.db.cancellation import complete_read
    from app.models.document import DocumentVersion
    from app.services.document.source_context import validated_snapshot_context

    snapshots = {}
    profile = selection.get("evidence_profile", {}).get("evidence_reading_profile")
    # This expansion is opt-in only. Legacy historical snapshot shape is stable.
    role_documents = {}
    if profile == "contextual_source_v2":
        for document in selection.get("role_scope_read_set", {}).get("documents", []):
            identifier = document["document_id"]
            if identifier in role_documents:
                raise ValueError("Duplicate role snapshot identity")
            role_documents[identifier] = document

    identities = [
        row.get("procedure_completeness") or {}
        for row in selection.get("requirements", [])
    ]
    identities.extend(selection.get("inspected_sources", []))
    identities.extend(role_documents.values())
    captured_metadata = {}
    captured = retained_selection(query_context) if query_context is not None else None
    if captured is not None:
        identities = [*captured.get("inspected_sources", []), *identities]
        for source in captured.get("procedure_read_set", {}).get("sources", []):
            metadata = {key: source[key] for key in ("condition", "conflict_group")}
            identifier = source["document_id"]
            if (
                identifier in captured_metadata
                and captured_metadata[identifier] != metadata
            ):
                raise ValueError("Inconsistent retained source context")
            captured_metadata[identifier] = metadata
    if profile == "contextual_source_v2" and captured is not None:
        for document in captured.get("role_scope_read_set", {}).get("documents", []):
            identifier = document["document_id"]
            existing = role_documents.get(identifier)
            if existing is not None and existing != document:
                raise ValueError("Role snapshot differs from retained execution")
            role_documents[identifier] = document
        identities.extend(role_documents.values())
    for proof in identities:
        if not proof:
            continue
        if proof["document_id"] in snapshots:
            if any(
                snapshots[proof["document_id"]][key] != proof[key]
                for key in ("document_version", "content_hash")
            ):
                raise ValueError(
                    "Presentation source differs from retained source version"
                )
            continue
        with db.no_autoflush:
            snapshot = await complete_read(
                db.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == uuid.UUID(proof["document_id"]),
                        DocumentVersion.version_number == proof["document_version"],
                        DocumentVersion.content_hash == proof["content_hash"],
                    )
                )
            )
        if snapshot is None:
            raise ValueError("Missing immutable snapshot")
        snapshots[proof["document_id"]] = {
            "document_id": proof["document_id"],
            "document_version": snapshot.version_number,
            "content_hash": snapshot.content_hash,
            "workspace_id": snapshot.workspace_id,
            "body": snapshot.normalized_content,
            "chunks": snapshot.chunks,
            "captured_scope": validated_snapshot_context(snapshot),
            "metadata": captured_metadata.get(proof["document_id"], {}),
        }
        if proof["document_id"] in role_documents:
            snapshots[proof["document_id"]]["snapshot_id"] = str(snapshot.id)
    if role_documents:
        from app.models.chunk import Chunk
        from app.models.document import Document
        from app.services.linguistic_role_consumer import _record, _same
        from app.services.role_scope_inspection import MAX_ROLE_CHUNKS

        for identifier in role_documents:
            resolved = snapshots[identifier]
            document = await complete_read(
                db.scalar(
                    select(Document)
                    .where(
                        Document.id == uuid.UUID(identifier),
                        Document.workspace_id == resolved["workspace_id"],
                        Document.version_number == resolved["document_version"],
                        Document.content_hash == resolved["content_hash"],
                    )
                    .execution_options(populate_existing=True)
                )
            )
            if document is None:
                raise ValueError("Role metadata publication is no longer available")
            rows = list(
                (
                    await complete_read(
                        db.scalars(
                            select(Chunk)
                            .where(
                                Chunk.document_id == document.id,
                            )
                            .order_by(Chunk.chunk_index)
                            .limit(MAX_ROLE_CHUNKS + 1)
                            .execution_options(populate_existing=True)
                        )
                    )
                ).all()
            )
            resolved.update(
                owner_id=document.owner_id,
                status=document.status.value,
                metadata=deepcopy(document.metadata_ or {}),
                role_live_chunks=[
                    {
                        "id": str(row.id),
                        "index": row.chunk_index,
                        "content": row.content,
                        "metadata": deepcopy(row.metadata_),
                    }
                    for row in rows
                ],
            )
            _same(role_documents[identifier], _record(resolved))
    return snapshots
