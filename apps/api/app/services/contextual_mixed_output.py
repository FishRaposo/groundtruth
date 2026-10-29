"""Pure mixed output reconstruction over actual sources and retained model input.

No inference or source authorization occurs here. The request planner and source
consumer are independently invoked, not replaced by producer success flags. Old
v3 factual certificates/serialization stay owned by contextual_output unchanged.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from app.evidence_policy import (
    ReadingVersion,
    reading_version,
    recorded_evidence_policy,
    staged_reading_profile,
)
from app.services import contextual_output as factual
from app.services.contextual_procedures import declared_envelope_inventory
from app.services.contextual_publication import stable_capture
from app.services.contextual_values import contextual_value_identity
from app.services.evidence_proposals import (
    make_proposal,
    qa_raw_candidates,
    validate_source,
)
from app.services.procedure_discovery import _bind_document_extent, build_plan
from app.services.procedure_output import (
    RENDERER,
    render_extractive,
    retained_selection,
)
from app.services.requirement_binding import condition_relation, support_claim
from app.services.requirement_contract import (
    _CONDITION_READER_FIELDS,
    condition_model_settings,
    valid_condition_model_settings,
)
from app.services.source_pattern_grammar import collect_source_proposals
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS

PROFILE = "contextual_source_v2"
CERTIFICATE_FIELD = "contextual_mixed_output_certificate"
_PRESENTATION = frozenset(
    {CERTIFICATE_FIELD, "contextual_output_certificate", "presentation_verification"}
)
_FACTS = factual._FACTUAL | {"owner", "deputy", "availability"}


class PendingConsumerProof(ValueError):
    """An independent request/source consumer has not discharged its gates."""


def _wire(value):
    return json.loads(factual._json(value))


def _same(actual, expected, reason):
    factual._same(actual, expected, reason)


def _version(reading_profile: str) -> ReadingVersion:
    if type(reading_profile) is not str or reading_profile not in {
        PROFILE,
        "contextual_source_v3",
        "contextual_source_v4",
    }:
        raise ValueError("Unsupported mixed output reading profile")
    return reading_version(reading_profile)


def _model_profile(settings):
    return _version(settings["evidence_profile"]["evidence_reading_profile"]).profile


def _settings(selection, query_context, *, reading_profile=PROFILE):
    version = _version(reading_profile)
    if (
        selection.get("contract") != version.requirement
        or selection.get("decision") != "answer"
    ):
        expected = "v4" if version.profile == PROFILE else version.requirement
        raise ValueError(f"Actual {expected} mixed selection required")
    profile = selection["evidence_profile"]
    _same(
        profile["evidence_reading_profile"],
        version.profile,
        "Mixed selected reading profile differs from captured settings",
    )
    expected = recorded_evidence_policy(profile).record()
    _same(profile, expected, "Mixed reading profile/settings mismatch")
    if type(selection.get("conflicts")) is not list:
        raise ValueError("Actual curated comparison inventory must be a list")
    for name in ("role_scope_interpretations", "role_scope_findings"):
        records = selection.get(name, [])
        if type(records) is not list:
            raise ValueError("Role scope records must be an explicit list")
        if any(type(r) is not dict or "requirement_id" not in r for r in records):
            raise PendingConsumerProof("Malformed independent role consumer input")
    from app.services.linguistic_role_consumer import stable_role_capture

    captured = retained_selection(query_context)
    if captured is None:
        raise ValueError("Independent retained execution capture required")
    stable = stable_capture(stable_role_capture(selection), _PRESENTATION)
    _same(
        stable,
        stable_capture(stable_role_capture(captured), _PRESENTATION),
        "Actual mixed inputs differ from retained execution",
    )
    settings = condition_model_settings(
        selection, selection["evidence_support"], selection, profile, "extractive"
    )
    if not valid_condition_model_settings(settings, selection):
        raise ValueError("Mixed reader/NLI model settings rejected")
    _same(
        settings["support"]["batch_size"],
        BATCH_SIZE,
        "NLI batch setting identity mismatch",
    )
    _same(
        settings["support"]["max_pair_tokens"],
        MAX_PAIR_TOKENS,
        "NLI token setting identity mismatch",
    )
    return settings, stable


def _request(selection, question, query_context, callback, *, reading_profile=PROFILE):
    version = _version(reading_profile)
    if version.profile != PROFILE and callback is None:
        raise PendingConsumerProof(
            "Independent staged request reconstructor is required"
        )
    if callback is None:
        from app.services.linguistic_requirements import (
            plan_request,
            validate_request_plan,
        )

        capture = selection.get("request_capture")
        if capture is None:
            raise PendingConsumerProof(
                "Actual independently retained request capture is missing"
            )
        plan = plan_request(question, capture)
        if not validate_request_plan(
            selection["request_plan"], question=question, capture=capture
        ):
            raise ValueError("Actual request plan reconstruction differs")
    else:
        plan = callback(question, query_context)
    record = _wire(plan.record())
    if (
        record.get("question") != question
        or record.get("contract") != version.request_plan
        or (
            version.profile != PROFILE
            and record.get("reading_profile") != version.profile
        )
        or type(record.get("unresolved")) is not list
        or record["unresolved"]
        or record.get("resolved_request") is not True
    ):
        raise PendingConsumerProof("Whole actual request remains unresolved")
    _same(selection["request_plan"], record, "Whole actual request plan differs")
    requirements = tuple(plan.requirements)
    if not requirements or len({r.id for r in requirements}) != len(requirements):
        raise ValueError("Actual requirement inventory missing/duplicated")
    _same(
        record["requirements"],
        [asdict(r) for r in requirements],
        "Actual plan requirements differ from full record",
    )
    for r in requirements:
        if r.kind not in _FACTS | {"procedure"} | (
            {"role_catalogue", "role_label", "role_assignment"}
            if staged_reading_profile(version.profile)
            else set()
        ):
            raise PendingConsumerProof("Special request binding is not implemented")
        if (
            type(r.input_start) is not int
            or type(r.input_end) is not int
            or not 0 <= r.input_start < r.input_end <= len(question)
            or question[r.input_start : r.input_end] != r.original_text
        ):
            raise ValueError("Actual original request ranges differ")
    return plan, record, requirements


def _sources(snapshots, selection, *, reading_profile=PROFILE, request_plan=None):
    chunks, inventory = factual._source_inventory(
        snapshots, max_documents=_version(reading_profile).scope_documents
    )
    inspected_snapshots = snapshots
    replay_inventory = inventory
    profile = selection.get("evidence_profile", {})
    if (
        reading_profile == "contextual_source_v4"
        and profile.get("source_governance_profile") == "requirement_bound_v1"
    ):
        policy = recorded_evidence_policy(profile)
        _same(profile, policy.record(), "Canonical captured source policy required")
        if request_plan is None:
            raise PendingConsumerProof(
                "Independently reconstructed source plan required"
            )
        _same(
            json.loads(request_plan.evidence_profile_json),
            profile,
            "Source inventory plan/profile differs",
        )
        original = json.loads(request_plan.source_productions_json)["original_inputs"]
        identities = [row["identity"] for row in original["snapshots"]]
        declared = original["manifest"]["publications"]
        _same(
            sorted(identities, key=lambda row: row["document_id"]),
            sorted(declared, key=lambda row: row["document_id"]),
            "Complete replayed source identity inventories differ",
        )
        expected = {row["document_id"]: row for row in identities}
        if len(expected) != len(identities) or set(snapshots) != set(expected):
            raise ValueError("Complete authoritative planning source domain differs")
        for identifier, identity in expected.items():
            _same(
                {
                    key: snapshots[identifier][key]
                    for key in (
                        "document_id",
                        "document_version",
                        "content_hash",
                        "workspace_id",
                        "snapshot_id",
                    )
                },
                identity,
                "Complete authoritative planning source identity differs",
            )
        # Full authority remains available to planning, source, curated and output
        # checks. Only the actual model-discovery view follows inspected sources.
        inspected_documents = {
            row["document_id"] for row in selection["inspected_sources"]
        }
        inspected_snapshots = {key: snapshots[key] for key in inspected_documents}
        replay_inventory = [
            row for row in inventory if row["document_id"] in inspected_documents
        ]
    factual._inspected_sources(selection, chunks, inspected_snapshots)
    replay_documents = {row["document_id"] for row in replay_inventory}
    sources = []
    for document in inventory:
        source = next(
            e["source"]
            for e in chunks.values()
            if e["identity"]["document_id"] == document["document_id"]
        )
        source.metadata = snapshots[document["document_id"]].get("metadata", {})
        source.captured_scope = snapshots[document["document_id"]].get("captured_scope")
        if "workspace_id" in snapshots[document["document_id"]]:
            source.identity["workspace_id"] = snapshots[document["document_id"]][
                "workspace_id"
            ]
        if document["document_id"] in replay_documents:
            sources.append(source)
    return chunks, inventory, sources


def _qa_inventory(selection, requirement, chunks):
    for record in selection["qa_observations"]:
        if record["requirement_id"] != requirement.id:
            continue
        content = chunks[record["chunk_id"]]["chunk"].content
        if record["question"] != requirement.question:
            raise ValueError("Retained QA input question differs")
        reader = record["reader"]
        shared = set(_CONDITION_READER_FIELDS) & reader.keys()
        if not {"mode", "model", "revision", "threshold"} <= shared:
            raise ValueError("Retained QA settings missing")
        _same(
            reader["contract"],
            selection["reader_contract"],
            "Retained QA reader contract differs",
        )
        _same(
            {k: reader[k] for k in shared},
            {k: selection[k] for k in shared},
            "Retained QA settings identity differs",
        )
        payload = json.dumps(
            {k: record[k] for k in ("span", "diagnostics", "question", "reader")},
            sort_keys=True,
            allow_nan=False,
        )
        _same(
            record["observation_id"],
            factual._hash(f"{requirement.id}:{record['chunk_id']}:{payload}"),
            "Retained QA observation identity differs",
        )
        if record["span"] is not None:
            factual._validated_qa_spans(record, content)
        for raw in qa_raw_candidates(record["diagnostics"]):
            a, b = factual._interval({k: raw[k] for k in ("start", "end")}, content)
            if "text" in raw:
                _same(raw["text"], content[a:b], "Retained raw QA source differs")
            margin = raw["null_margin"]
            if type(margin) not in (int, float) or not math.isfinite(margin):
                raise ValueError("Retained raw QA margin invalid")


def _proposals(selection, requirements, sources, chunks, *, reading_profile=PROFILE):
    reading_profile = _version(reading_profile).profile
    by_request = {r.id: r for r in requirements}
    for req in requirements:
        _qa_inventory(selection, req, chunks)
    canonical_patterns, observations = {}, []
    for req in requirements:
        batch = collect_source_proposals(req, sources, reading_profile=reading_profile)
        if not batch.complete:
            raise PendingConsumerProof(
                "Canonical pattern discovery incomplete/budget exceeded"
            )
        observations.extend(batch.observations)
        for p in batch.proposals:
            canonical_patterns[p.proposal_id] = p.record()
    _same(
        selection.get("pattern_observations"),
        observations,
        "Canonical pattern observations differ",
    )
    proposals, margins = {}, {}
    for proposal in selection["proposals"]:
        identifier = proposal["proposal_id"]
        if identifier in proposals:
            raise ValueError("Duplicate raw proposal ID")
        req, entry = (
            by_request[proposal["requirement_id"]],
            chunks[proposal["chunk_id"]],
        )
        left, right = factual._interval(proposal["chunk_range"], entry["chunk"].content)
        if proposal["origin"] == "qa_reader":
            observation, margin = factual._observation(
                proposal, req, selection, entry["chunk"].content
            )
            expected = make_proposal(
                req.id,
                entry["source"],
                entry["chunk"],
                left,
                right,
                origin="qa_reader",
                observation=observation,
            ).record()
            margins[identifier] = margin
        elif proposal["origin"] == "source_pattern":
            expected = canonical_patterns[identifier]
            margins[identifier] = None
        else:
            raise ValueError("Unknown proposal origin")
        _same(proposal, expected, "Actual raw proposal source/origin identity differs")
        proposals[identifier] = proposal
    _same(
        {
            p["proposal_id"]: p
            for p in proposals.values()
            if p["origin"] == "source_pattern"
        },
        canonical_patterns,
        "Whole canonical pattern proposal inventory differs",
    )
    return proposals, margins


def _body_fragments(source):
    cursor, parts = 0, []
    for item in source.chunks:
        if item.start > cursor or item.end <= cursor:
            raise ValueError("Immutable body cannot be copied through ordered chunks")
        right = min(item.end, len(source.body))
        parts.append(
            {
                "chunk_id": str(item.chunk.id),
                "chunk_start": cursor - item.start,
                "chunk_end": right - item.start,
                "document_start": cursor,
                "document_end": right,
            }
        )
        cursor = right
    if cursor != len(source.body):
        raise ValueError("Whole immutable source body has an uncovered tail")
    return parts


def procedure_obligations(  # noqa: C901 - explicit copy/NLI method separation
    requirement,
    source,
    proposal,
    *,
    method="declared_envelope",
    consumer_inventory=None,
    reading_profile=PROFILE,
) -> dict[str, Any]:
    """Canonical unassessed copy/model inputs for a producer; no success metadata."""
    version = _version(reading_profile)
    validate_source(source)
    if proposal["document_id"] != source.identity["document_id"]:
        raise ValueError("Procedure seed/source mismatch")
    first, last = factual._interval(proposal["document_range"], source.body)
    if source.body[first:last] != proposal["text"]:
        raise ValueError("Procedure raw seed differs from actual source")
    if method == "required_copy_v1" and version.profile == "contextual_source_v3":
        from app.services.required_copy_source import proof_from_envelope

        if type(consumer_inventory) is not dict:
            raise PendingConsumerProof(
                "Independent required-copy source guard required"
            )
        return proof_from_envelope(requirement, source, proposal, consumer_inventory)
    units = []
    if method == "declared_envelope":
        inventory = declared_envelope_inventory(
            source.body, source.identity, requested_subject=requirement.topic
        )
        for obligation in inventory["nli_obligations"]:
            units.append(
                {
                    "name": obligation["kind"],
                    "kind": obligation["kind"],
                    "source_range": obligation["source_range"],
                    "premise_range": obligation["source_range"],
                    "premise": obligation["premise"],
                    "hypothesis": obligation["hypothesis"],
                    "verification_method": "nli_entailment",
                }
            )
        for n, item in enumerate(inventory["ordered_ranges"]):
            units.append(
                {
                    "name": f"literal_copy_{n}",
                    "kind": item["kind"],
                    "source_range": {k: item[k] for k in ("start", "end")},
                    "verification_method": "exact_source_copy",
                }
            )
    elif method == "canonical_discovery":
        extent = _bind_document_extent(requirement, source, first, last)
        plan = build_plan(requirement, source, extent)
        inventory = plan.required_inventory(source)
        for unit in plan.units:
            semantic = unit.kind in {
                "namespace",
                "applicability",
                "request_scope",
                "bound_condition",
                "whole_method",
            }
            row = {
                "name": unit.name,
                "kind": unit.kind,
                "source_range": {"start": unit.start, "end": unit.end},
                "verification_method": "nli_entailment"
                if semantic
                else "exact_source_copy"
                if unit.kind in {"instruction", "prohibition"}
                else "exact_source_structure",
            }
            if semantic:
                row.update(
                    premise_range=unit.premise_range,
                    premise=source.body[
                        unit.premise_range["start"] : unit.premise_range["end"]
                    ],
                    hypothesis=unit.hypothesis,
                )
            units.append(row)
    elif method == "consumer_envelope":
        if type(consumer_inventory) is not dict:
            raise PendingConsumerProof(
                "Independent consumer envelope inventory required"
            )
        if reading_profile != PROFILE and (
            consumer_inventory.get("contract") != version.procedure
            or consumer_inventory.get("reading_profile") != version.profile
        ):
            raise ValueError("Independent consumer inventory version differs")
        inventory = deepcopy(consumer_inventory)
    else:
        raise ValueError("Unknown procedure reconstruction method")
    extent = {"start": 0, "end": len(source.body)}
    closure = {"kind": "immutable_eof", "offset": len(source.body)}
    fragments = _body_fragments(source)
    if inventory.get("source_copy_policy") == "ordinary_activity_quote_v2":
        extent = deepcopy(inventory["envelope_range"])
        first, last = factual._interval(extent, source.body)
        _same(
            extent,
            inventory["instruction_boundary"]["instruction_range"],
            "Instruction quote range differs",
        )
        _same(
            inventory["instruction_boundary"]["authority_scope"],
            {"start": 0, "end": len(source.body)},
            "Full instruction authority differs",
        )
        closure = deepcopy(inventory["closure"])
        _same(
            closure,
            {"kind": "captured_instruction_interval", "offset": last},
            "Instruction quote closure differs",
        )
        fragments = [
            {
                **row,
                "chunk_start": row["chunk_start"]
                + max(first - row["document_start"], 0),
                "chunk_end": row["chunk_end"] - max(row["document_end"] - last, 0),
                "document_start": max(row["document_start"], first),
                "document_end": min(row["document_end"], last),
            }
            for row in fragments
            if row["document_start"] < last and row["document_end"] > first
        ]
    return dict(
        contract=version.procedure,
        **source.identity,
        method=method,
        source_body=source.body,
        body_length=len(source.body),
        extent=extent,
        closure=closure,
        inventory=inventory,
        proof_units=units,
        raw_seed={
            k: deepcopy(proposal[k])
            for k in (
                "proposal_id",
                "origin",
                "chunk_id",
                "text",
                "chunk_range",
                "document_range",
            )
        },
        fragments=fragments,
    )


def _guard(callback, selection, requirement, snapshot, plan):
    if not callable(callback):
        raise PendingConsumerProof(
            "Independent source guard reconstructor is not wired"
        )
    result = _wire(
        callback(
            stable_capture(selection, _PRESENTATION),
            requirement,
            deepcopy(snapshot),
            plan,
        )
    )
    if type(result) is not dict or result.get("status") != "discharged":
        raise PendingConsumerProof(
            "Independent source/request/reference/governor guard remains pending"
        )
    return {
        "requirement_id": requirement.id,
        "source_identity": {
            k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
        },
        "request_plan_sha256": factual._hash(factual._json(plan.record())),
        "consumer_proof": result,
    }


def _fact(req, proposal, chunks, *, reading_profile=PROFILE, policy=None, plan=None):
    reading_profile = _version(reading_profile).profile
    entry = chunks[proposal["chunk_id"]]
    content = entry["chunk"].content
    left, right = factual._interval(proposal["chunk_range"], content)
    from app.services.linguistic_property_cover import factual_claim, requirement_bound

    claim = (
        factual_claim(req, content, left, right, policy=policy, plan=plan)
        if requirement_bound(policy)
        else support_claim(req, content, left, right, reading_profile=reading_profile)
    )
    if claim.rejection or not claim.hypothesis or claim.proof_edges:
        raise ValueError("Unsupported factual binding or special proof edge")
    from app.services.linguistic_property_cover import property_cover_error

    error = property_cover_error(
        req, entry["source"], entry["chunk"], {"start": left, "end": right}, claim
    )
    if error:
        raise ValueError(error)
    primary = factual._literal_range(
        claim.premise, content, claim.premise_start, claim.premise_end
    )
    checks = [
        factual._literal_range(c.premise, content, c.start, c.end) for c in claim.checks
    ]
    if not any(r["start"] <= left < right <= r["end"] for r in [primary, *checks]):
        raise ValueError("Raw factual proposal is outside actual support inputs")
    support = {"start": claim.support_start, "end": claim.support_end}
    a, b = factual._interval(support, content)
    descriptor = dict(
        **entry["identity"],
        value=claim.value,
        span={"start": a, "end": b, "text": content[a:b]},
        document_range={"start": entry["start"] + a, "end": entry["start"] + b},
        hypothesis=claim.hypothesis,
        primary_support_range=primary,
        support_checks=[
            {"name": c.name, "hypothesis": c.hypothesis, "source_range": r}
            for c, r in zip(claim.checks, checks, strict=True)
        ],
    )
    return claim, descriptor, primary, checks


def _fact_assessment(req, candidate, proposal, chunks, settings, plan=None):
    entry = chunks[proposal["chunk_id"]]
    policy = recorded_evidence_policy(settings["evidence_profile"])
    claim, descriptor, primary, checks = _fact(
        req,
        proposal,
        chunks,
        reading_profile=_model_profile(settings),
        policy=policy,
        plan=plan,
    )
    if policy.source_bound_counts and req.kind == "quantity":
        from app.services.count_runtime import reconstruct_count

        count_claim, count_record = reconstruct_count(
            candidate["quantity_binding"],
            req,
            entry["source"],
            entry["chunk"],
            proposal["chunk_range"],
            evidence_profile=policy.record(),
            request_plan=plan,
        )
        _same(asdict(count_claim), asdict(claim), "Source-bound count claim differs")
        descriptor["quantity_binding"] = count_record
    elif "quantity_binding" in candidate:
        raise ValueError("Count evidence cannot masquerade as a historical profile")
    from app.services.role_scope_policy import activity_role_candidate_scope

    activity_scope = activity_role_candidate_scope(
        req,
        entry["chunk"].content,
        proposal["chunk_range"]["start"],
        proposal["chunk_range"]["end"],
        entry["metadata"],
        policy=policy,
        request_plan=plan,
    )
    if activity_scope is not None and not activity_scope[1]:
        raise ValueError("Original activity-role scope remains unverified")
    expected = {
        "hypothesis": claim.hypothesis,
        "validated_answer_span": {
            "start": claim.start,
            "end": claim.end,
            "text": claim.value,
        },
        "condition": activity_scope[0]
        if activity_scope is not None
        else condition_relation(req, entry["chunk"].content, entry["metadata"]),
        "primary_support_range": primary,
        "proof_edges": [],
    }
    for key, value in expected.items():
        _same(candidate[key], value, "Actual factual candidate/model inputs differ")
    decision = factual._assessment(candidate["support"], settings, positive=False)
    pairs = factual._support_pairs(
        claim, candidate, settings, primary, checks, decision, allow_rejected=True
    )
    from app.services.linguistic_property_cover import factual_support_context

    context_key, whole_input = factual_support_context(
        req,
        entry["source"],
        entry["chunk"],
        proposal["chunk_range"],
        claim,
        policy=policy,
        plan=plan,
    )
    other_key = (
        "whole_source_support"
        if context_key == "fact_context_support"
        else "fact_context_support"
    )
    if other_key in candidate:
        raise ValueError("Factual support context policy differs")
    whole = candidate[context_key]
    if set(whole) != set(whole_input) | {"assessment"}:
        raise ValueError("Whole source NLI schema invalid")
    for key, expected in whole_input.items():
        _same(whole[key], expected, "Whole source NLI input/identity differs")
    whole_decision = factual._assessment(whole["assessment"], settings, positive=False)
    supported = (
        all(p["assessment"]["supported"] for p in pairs) and whole_decision["supported"]
    )
    _same(
        candidate["decision"],
        "supported" if supported else "support_rejected",
        "Local/whole factual support decision differs",
    )
    pairs.append({**whole_input, "assessment": whole_decision})
    descriptor = {
        k: v
        for k, v in descriptor.items()
        if k not in {"hypothesis", "primary_support_range", "support_checks"}
    }
    descriptor.update(proof_edges=[], nli_pairs=pairs)
    return descriptor, supported, decision["entailment_margin"], claim.value


def reconstruct_factual_source_guard(  # noqa: C901 - all retained inputs before filter
    selection, requirement, snapshot, request_plan, *, reading_profile=PROFILE
):
    """Replay all actual local/whole model inputs, including negative candidates.

    Discharged describes input/logit reconstruction; selected support still needs
    the outcome of every mandatory pair. This does not attest model execution.
    """
    version = _version(reading_profile)
    if (
        selection.get("contract") != version.requirement
        or selection["evidence_profile"].get("evidence_reading_profile")
        != version.profile
    ):
        raise ValueError("Factual guard selected reading profile differs")
    if requirement.kind not in _FACTS:
        raise PendingConsumerProof("Factual source guard kind unsupported")
    settings = condition_model_settings(
        selection,
        selection["evidence_support"],
        selection,
        selection["evidence_profile"],
        "extractive",
    )
    if not valid_condition_model_settings(settings, selection):
        raise ValueError("Factual guard settings invalid")
    _same(
        settings["support"]["batch_size"],
        BATCH_SIZE,
        "Factual guard batch setting differs",
    )
    _same(
        settings["support"]["max_pair_tokens"],
        MAX_PAIR_TOKENS,
        "Factual guard token setting differs",
    )
    chunks, inventory = factual._source_inventory({snapshot["document_id"]: snapshot})
    source = next(iter(chunks.values()))["source"]
    source.metadata = snapshot.get("metadata", {})
    source.captured_scope = snapshot.get("captured_scope")
    if "workspace_id" in snapshot:
        source.identity["workspace_id"] = snapshot["workspace_id"]
    batch = collect_source_proposals(
        requirement, [source], reading_profile=reading_profile
    )
    if not batch.complete:
        raise PendingConsumerProof("Factual guard pattern inventory incomplete")
    patterns = {p.proposal_id: p.record() for p in batch.proposals}
    proposals = {p["proposal_id"]: p for p in selection["proposals"]}
    rows = []
    seen = set()
    for candidate in selection["candidates"]:
        if (
            candidate.get("requirement_id") != requirement.id
            or candidate.get("document_id") != snapshot["document_id"]
        ):
            continue
        if "support" not in candidate and "whole_source_support" not in candidate:
            if candidate.get("decision") == "supported":
                raise ValueError("Factual positive has no actual assessments")
            continue
        proposal = proposals[candidate["proposal"]["proposal_id"]]
        _same(candidate["proposal"], proposal, "Factual guard raw proposal differs")
        origins = [proposal, *candidate.get("duplicate_proposals", [])]
        for raw in origins:
            _same(
                raw,
                proposals[raw["proposal_id"]],
                "Factual guard duplicate origin differs",
            )
            if raw["proposal_id"] in seen or raw["requirement_id"] != requirement.id:
                raise ValueError("Factual guard duplicate/retagged origin")
            seen.add(raw["proposal_id"])
            entry = chunks[raw["chunk_id"]]
            left, right = factual._interval(raw["chunk_range"], entry["chunk"].content)
            if raw["origin"] == "qa_reader":
                observed, margin = factual._observation(
                    raw, requirement, selection, entry["chunk"].content
                )
                expected = make_proposal(
                    requirement.id,
                    source,
                    entry["chunk"],
                    left,
                    right,
                    origin="qa_reader",
                    observation=observed,
                ).record()
            elif raw["origin"] == "source_pattern":
                expected = patterns[raw["proposal_id"]]
                margin = None
            else:
                raise ValueError("Unknown factual guard origin")
            _same(raw, expected, "Factual guard actual source/origin differs")
            if raw is proposal:
                for key, value in dict(
                    **entry["identity"], raw_span=raw["chunk_range"], null_margin=margin
                ).items():
                    _same(
                        candidate[key],
                        value,
                        "Factual guard actual identity/input differs",
                    )
            else:
                _same(
                    _fact(
                        requirement,
                        raw,
                        chunks,
                        reading_profile=_model_profile(settings),
                        policy=recorded_evidence_policy(settings["evidence_profile"]),
                        plan=request_plan,
                    )[1],
                    _fact(
                        requirement,
                        proposal,
                        chunks,
                        reading_profile=_model_profile(settings),
                        policy=recorded_evidence_policy(settings["evidence_profile"]),
                        plan=request_plan,
                    )[1],
                    "Factual guard shared model input differs",
                )
        descriptor, supported, margin, value = _fact_assessment(
            requirement,
            candidate,
            proposal,
            chunks,
            settings,
            request_plan,
        )
        rows.append(
            {
                "proposal_ids": [p["proposal_id"] for p in origins],
                "supported": supported,
                "margin": margin,
                "value": value,
                "descriptor": descriptor,
            }
        )
    if not rows:
        raise PendingConsumerProof("No assessed factual model input for source/request")
    return _wire(
        {
            "status": "discharged",
            "method": "source_bound_fact_support"
            if recorded_evidence_policy(
                selection["evidence_profile"]
            ).source_governance_profile
            == "requirement_bound_v1"
            else "whole_source_fact_support",
            "claim_semantics": "actual_recorded_model_inputs_replayed",
            "requirement_id": requirement.id,
            "source_identity": source.identity,
            "request_plan_sha256": factual._hash(factual._json(request_plan.record())),
            "observations": rows,
        }
    )


def _default_source_guard(
    selection, requirement, snapshot, request_plan, *, reading_profile=PROFILE
):
    if _version(reading_profile).profile != PROFILE:
        raise PendingConsumerProof("Independent staged source guard is required")
    if requirement.kind != "procedure":
        return reconstruct_factual_source_guard(
            selection,
            requirement,
            snapshot,
            request_plan,
            reading_profile=reading_profile,
        )
    try:
        from app.services.contextual_source_proof import reconstruct_source_guard
    except ImportError as exc:
        raise PendingConsumerProof("Procedure source consumer is not wired") from exc
    return reconstruct_source_guard(selection, requirement, snapshot, request_plan)


def _procedure_record(  # noqa: C901 - independent literal and semantic proof replay
    req, candidate, proposal, entry, guard, settings, selection, snapshots, plan
):
    recorded = candidate["procedure_completeness"]
    if (
        recorded["method"] == "required_copy_v1"
        and _model_profile(settings) == "contextual_source_v3"
    ):
        from app.services.required_copy_consumer import reconstruct_required_copy_group

        result = reconstruct_required_copy_group(
            selection, req, snapshots, plan, settings, guard=guard
        )
        _same(
            candidate["decision"],
            "supported" if result["supported"] else "support_rejected",
            "Required-copy support differs from retained execution",
        )
        return (
            result["descriptor"]["procedure_completeness"],
            result["supported"],
            result["margin"],
        )
    expected = procedure_obligations(
        req,
        entry["source"],
        proposal,
        method=recorded["method"],
        consumer_inventory=guard["consumer_proof"].get("envelope_inventory"),
        reading_profile=_model_profile(settings),
    )
    for key in set(expected) - {"proof_units"}:
        _same(
            recorded[key],
            expected[key],
            "Actual whole procedure inventory/source/seed/fragments differ",
        )
    if set(recorded) != set(expected) or len(recorded["proof_units"]) != len(
        expected["proof_units"]
    ):
        raise ValueError("Complete procedure obligation inventory differs")
    decisions = []
    for actual, unit in zip(
        recorded["proof_units"], expected["proof_units"], strict=True
    ):
        if unit["verification_method"] == "nli_entailment":
            if set(actual) != set(unit) | factual._ASSESSMENT:
                raise ValueError("Actual procedure NLI metadata missing or invented")
            for k, v in unit.items():
                _same(actual[k], v, "Actual procedure NLI input differs")
            decisions.append(
                factual._assessment(
                    {k: actual[k] for k in factual._ASSESSMENT},
                    settings,
                    positive=False,
                )
            )
        else:
            _same(
                actual,
                unit,
                "Exact copy/structure obligation contains altered or model metadata",
            )
    if (
        recorded["method"] == "consumer_envelope"
        or guard["consumer_proof"].get("method") == "consumer_envelope"
    ):
        rows = guard["consumer_proof"]["nli_assessments"]
        obligations = guard["consumer_proof"]["envelope_inventory"]["nli_obligations"]
        if type(rows) is not list or not rows or len(rows) != len(obligations):
            raise ValueError(
                "Consumer procedure semantic obligations missing or vacuous"
            )
        consumer_decisions = []
        for row, obligation in zip(rows, obligations, strict=True):
            if set(row) != set(obligation) | {"assessment"}:
                raise ValueError("Consumer NLI row schema differs")
            for key, value in obligation.items():
                _same(row[key], value, "Consumer actual NLI input differs")
            consumer_decisions.append(
                factual._assessment(row["assessment"], settings, positive=False)
            )
        _same(
            guard["consumer_proof"]["supported"],
            all(d["supported"] for d in consumer_decisions),
            "Consumer procedure NLI outcome differs",
        )
        _same(
            guard["consumer_proof"]["entailment_margin"],
            min(d["entailment_margin"] for d in consumer_decisions),
            "Consumer procedure NLI margin differs",
        )
        decisions.extend(consumer_decisions)
    if not decisions:
        raise ValueError("Procedure semantic assessments cannot be vacuous")
    supported = all(d["supported"] for d in decisions)
    _same(
        candidate["decision"],
        "supported" if supported else "support_rejected",
        "Procedure support decision differs from actual logits",
    )
    expected["proof_units"] = deepcopy(recorded["proof_units"])
    return (
        expected,
        supported,
        min((d["entailment_margin"] for d in decisions), default=None),
    )


def _groups(  # noqa: C901 - complete assessed inventory before filtering
    selection,
    requirements,
    proposals,
    margins,
    chunks,
    snapshots,
    plan,
    callback,
    settings,
    guard_selection=None,
):
    by_req = {r.id: r for r in requirements}
    groups = []
    owners = {}
    for candidate in selection["candidates"]:
        if (
            "support" not in candidate
            and "procedure_completeness" not in candidate
            and "whole_source_support" not in candidate
        ):
            if candidate.get("decision") == "supported":
                raise ValueError("Supported candidate has no actual proof")
            continue
        proposal = proposals[candidate["proposal"]["proposal_id"]]
        _same(
            candidate["proposal"], proposal, "Assessed candidate raw proposal differs"
        )
        req = by_req[candidate["requirement_id"]]
        if proposal["requirement_id"] != req.id:
            raise ValueError("Candidate retagged to another request")
        origins = [proposal, *candidate.get("duplicate_proposals", [])]
        if len({p["proposal_id"] for p in origins}) != len(origins):
            raise ValueError("Duplicate origin ID in shared proof")
        for p in origins:
            _same(p, proposals[p["proposal_id"]], "Shared proof origin missing/forged")
            if p["requirement_id"] != req.id or p["proposal_id"] in owners:
                raise ValueError("Raw origin assigned to multiple proof groups")
        entry = chunks[proposal["chunk_id"]]
        guard = _guard(
            callback,
            guard_selection if guard_selection is not None else selection,
            req,
            snapshots[proposal["document_id"]],
            plan,
        )
        expected_base = dict(
            **entry["identity"],
            raw_span=proposal["chunk_range"],
            null_margin=margins[proposal["proposal_id"]],
        )
        for key, value in expected_base.items():
            _same(candidate[key], value, "Actual candidate identity/raw input differs")
        if candidate.get("origin", proposal["origin"]) != proposal["origin"]:
            raise ValueError("Candidate origin method differs")
        if req.kind == "procedure":
            proof, supported, margin = _procedure_record(
                req,
                candidate,
                proposal,
                entry,
                guard,
                settings,
                selection,
                snapshots,
                plan,
            )
            for other in origins[1:]:
                other_entry = chunks[other["chunk_id"]]
                duplicate = procedure_obligations(
                    req,
                    other_entry["source"],
                    other,
                    method=proof["method"],
                    consumer_inventory=guard["consumer_proof"].get(
                        "envelope_inventory"
                    ),
                    reading_profile=_model_profile(settings),
                )
                for key in ("inventory", "proof_units", "source_body"):
                    _same(
                        duplicate[key],
                        {
                            **proof,
                            "proof_units": procedure_obligations(
                                req,
                                entry["source"],
                                proposal,
                                method=proof["method"],
                                consumer_inventory=guard["consumer_proof"].get(
                                    "envelope_inventory"
                                ),
                                reading_profile=_model_profile(settings),
                            )["proof_units"],
                        }[key],
                        "Deduplicated procedure model inputs differ",
                    )
            descriptor = dict(
                **entry["identity"],
                value=proof["required_copy"]["rendered_text"]
                if proof["method"] == "required_copy_v1"
                else (
                    entry["source"].body[
                        proof["extent"]["start"] : proof["extent"]["end"]
                    ]
                    if proof["inventory"].get("source_copy_policy")
                    == "ordinary_activity_quote_v2"
                    else entry["source"].body
                ),
                proof_edges=[],
                procedure_completeness=proof,
            )
            fragment = next(
                f for f in proof["fragments"] if f["chunk_id"] == proposal["chunk_id"]
            )
            descriptor.update(
                span={
                    "start": fragment["chunk_start"],
                    "end": fragment["chunk_end"],
                    "text": entry["chunk"].content[
                        fragment["chunk_start"] : fragment["chunk_end"]
                    ],
                },
                document_range={
                    "start": fragment["document_start"],
                    "end": fragment["document_end"],
                },
            )
            value = descriptor["value"]
        else:
            claim, descriptor, primary, checks = _fact(
                req,
                proposal,
                chunks,
                reading_profile=_model_profile(settings),
                policy=recorded_evidence_policy(settings["evidence_profile"]),
                plan=plan,
            )
            for other in origins[1:]:
                _same(
                    _fact(
                        req,
                        other,
                        chunks,
                        reading_profile=_model_profile(settings),
                        policy=recorded_evidence_policy(settings["evidence_profile"]),
                        plan=plan,
                    )[1],
                    descriptor,
                    "Deduplicated factual origins do not share actual model input",
                )
            descriptor, supported, margin, value = _fact_assessment(
                req,
                candidate,
                proposal,
                chunks,
                settings,
                plan,
            )
        group = {
            "requirement_id": req.id,
            "origins": deepcopy(origins),
            "descriptor": descriptor,
            "supported": supported,
            "margin": margin,
            "value": value,
            "source_guard": guard,
        }
        groups.append(group)
        for p in origins:
            owners[p["proposal_id"]] = group
    return groups, owners


def _selected(  # noqa: C901 - cross-link every selected origin and retained value
    selection, requirements, groups, owners
):
    selected = selection["selected_proposal_ids"]
    if (
        type(selected) is not list
        or not selected
        or len(selected) != len(set(selected))
    ):
        raise ValueError("Selected raw origin inventory invalid")
    rows = selection["requirements"]
    if len(rows) != len(requirements):
        raise ValueError("Whole actual requested requirements missing")
    chosen = []
    used = set()
    for row, req in zip(rows, requirements, strict=True):
        expected = {
            "id": req.id,
            "kind": req.kind,
            "original_text": req.original_text,
            "input_range": {"start": req.input_start, "end": req.input_end},
            "prepared_question": req.question,
            "source_workspace": req.source_workspace,
            "depends_on": list(req.depends_on),
            "status": "supported",
        }
        for k, v in expected.items():
            _same(row[k], v, "Actual requirement row differs from whole plan")
        accepted = [
            g for g in groups if g["requirement_id"] == req.id and g["supported"]
        ]
        values = {
            factual._hash(g["value"])
            if req.kind == "procedure"
            else factual._json(g["value"])
            if "typed_role_proof" in g["descriptor"]
            else g["descriptor"]["quantity_binding"]["binding"]["value_identity"]
            if "quantity_binding" in g["descriptor"]
            else contextual_value_identity(req, g["value"])
            for g in accepted
        }
        if len(values) > 1:
            raise ValueError(
                "Conflicting retained supported values require independent handling"
            )
        row_selected = []
        for witness in row["witnesses"]:
            origins = witness["proposals"]
            if not origins:
                raise ValueError("Witness has no actual raw origins")
            group = owners[origins[0]["proposal_id"]]
            if not group["supported"] or group["requirement_id"] != req.id:
                raise ValueError("Witness proof/request not supported")
            _same(
                origins, group["origins"], "Witness drops/reorders shared raw origins"
            )
            for k, v in group["descriptor"].items():
                if k != "nli_pairs":
                    _same(
                        witness[k], v, "Actual witness differs from reconstructed proof"
                    )
            if group["margin"] is not None:
                _same(
                    witness["entailment_margin"],
                    group["margin"],
                    "Witness NLI margin differs",
                )
            ids = {p["proposal_id"] for p in origins}
            if ids & set(selected):
                if not ids <= set(selected) or used & ids:
                    raise ValueError(
                        "Selected witness origin inventory incomplete/duplicated"
                    )
                row_selected.append(group)
                used |= ids
        if not row_selected:
            raise ValueError("Every actual requirement needs a selected proved witness")
        if req.kind == "procedure":
            _same(
                row["procedure_completeness"],
                row["witnesses"][0]["procedure_completeness"],
                "Procedure row inventory differs from its actual witness",
            )
        chosen.extend(row_selected)
    if used != set(selected):
        raise ValueError("Selected raw origin inventory is not exactly discharged")
    return chosen


def _answer_ranges(  # noqa: C901 - trace each versioned renderer emission exactly
    answer, citations, groups, fragments, disclosures
):
    # Trace the versioned renderer's literal emissions, then compare the entire
    # trace to its actual output. Offsets never come from a text-search match.
    prefix = render_extractive([], disclosures=disclosures)[0]
    if disclosures:
        suffix = "\n\n".join(disclosures)
        prefix = prefix[: -len(suffix)]
    cursor, extracts, segments = len(prefix), [], []
    indices = {c["chunk_id"]: c["citation_index"] for c in citations}
    for group in groups:
        extract = (
            group["text"]
            + " "
            + " ".join(f"[{indices[c]}]" for c in group["chunk_ids"])
        )
        group["answer_range"] = {"start": cursor, "end": cursor + len(group["text"])}
        extracts.append(extract)
        cursor += len(extract) + 2
    for citation in citations:
        identifier, passage = citation["chunk_id"], citation["quoted_text"]
        spans = citation["answer_spans"]
        if not groups:
            text = "\n".join(span["text"] for span in spans) if spans else passage
            local = cursor
            for span in spans:
                segments.append((identifier, span["start"], span["end"], local))
                local += len(span["text"]) + 1
            extract = f"{text} [{citation['citation_index']}]"
            extracts.append(extract)
            cursor += len(extract) + 2
            continue
        covered = sorted(
            (f["start"], f["end"])
            for group in groups
            for f in group["fragments"]
            if f["chunk_id"] == identifier
        )
        for span in spans:
            remaining = [(span["start"], span["end"])]
            for left, right in covered:
                remaining = [
                    (a, min(b, left)) for a, b in remaining if a < min(b, left)
                ] + [(max(a, right), b) for a, b in remaining if max(a, right) < b]
            for a, b in remaining:
                if passage[a:b].strip():
                    segments.append((identifier, a, b, cursor))
                    extract = f"{passage[a:b]} [{citation['citation_index']}]"
                    extracts.append(extract)
                    cursor += len(extract) + 2
    _same(
        answer,
        prefix + "\n\n".join([*extracts, *disclosures]),
        "Renderer literal emission trace differs",
    )
    for fragment in fragments:
        candidates = []
        for group in groups:
            same_source = group["document_id"] == fragment["document_id"]
            if same_source:
                start = (
                    group["answer_range"]["start"] + fragment["document_range"]["start"]
                )
                candidates.append(
                    {"start": start, "end": start + len(fragment["text"])}
                )
        left, right = fragment["chunk_range"]["start"], fragment["chunk_range"]["end"]
        candidates.extend(
            {"start": start + left - a, "end": start + right - a}
            for identifier, a, b, start in segments
            if identifier == fragment["chunk_id"] and a <= left < right <= b
        )
        if not candidates:
            raise ValueError(
                "Selected source fragment is absent from actual renderer emission"
            )
        offset = candidates[0]
        _same(
            answer[offset["start"] : offset["end"]],
            fragment["text"],
            "Selected fragment actual answer range differs",
        )
        fragment["answer_range"] = offset
    disclosure_ranges = []
    for text in disclosures:
        offset = {"start": cursor, "end": cursor + len(text)}
        _same(
            answer[offset["start"] : offset["end"]],
            text,
            "Disclosure answer range differs",
        )
        disclosure_ranges.append(offset)
        cursor += len(text) + 2
    return disclosure_ranges


def _verified_disclosures(chosen):
    records = []
    for group in chosen:
        guard = group["source_guard"]["consumer_proof"]
        if guard.get("method") not in {"consumer_envelope", "required_copy_v1"}:
            continue
        scope = guard["literal_scope"]
        _same(
            scope,
            guard["envelope_inventory"]["literal_scope"],
            "Consumer disclosure scope differs",
        )
        text = scope["disclosure"]
        if type(text) is not str or not text.strip():
            raise ValueError("Canonical source scope disclosure missing")
        records.append(
            {
                "kind": "source_declared_scope",
                "requirement_id": group["requirement_id"],
                "source_identity": guard["source_identity"],
                "text": text,
            }
        )
    return records


def _procedure_emissions(rid, proof, chunks):
    documents = (
        proof["required_copy"]["documents"]
        if proof["method"] == "required_copy_v1"
        else [
            {
                "identity": {"document_id": proof["document_id"]},
                "body": proof["source_body"],
                "fragments": proof["fragments"],
            }
        ]
    )
    fragments, groups = [], []
    for document in documents:
        parts = []
        for fragment in document["fragments"]:
            identity = chunks[fragment["chunk_id"]]["identity"]
            for key, value in document["identity"].items():
                if key in identity:
                    _same(
                        identity[key],
                        value,
                        "Required-copy fragment/document identity differs",
                    )
            fragments.append(
                {
                    "requirement_id": rid,
                    **identity,
                    "chunk_range": {
                        "start": fragment["chunk_start"],
                        "end": fragment["chunk_end"],
                    },
                    "document_range": {
                        "start": fragment["document_start"],
                        "end": fragment["document_end"],
                    },
                    "text": document["body"][
                        fragment["document_start"] : fragment["document_end"]
                    ],
                }
            )
            parts.append(
                {
                    "chunk_id": fragment["chunk_id"],
                    "start": fragment["chunk_start"],
                    "end": fragment["chunk_end"],
                }
            )
        groups.append(
            {
                "requirement_id": rid,
                "document_id": document["identity"]["document_id"],
                "text": document["body"][
                    proof["extent"]["start"] : proof["extent"]["end"]
                ]
                if proof["inventory"].get("source_copy_policy")
                == "ordinary_activity_quote_v2"
                else document["body"],
                "chunk_ids": [part["chunk_id"] for part in parts],
                "fragments": parts,
            }
        )
    return fragments, groups


def _presentation(chosen, chunks, role_scope=None):
    fragments = []
    groups = []
    for group in chosen:
        descriptor = group["descriptor"]
        rid = group["requirement_id"]
        if "procedure_completeness" in descriptor:
            proof = descriptor["procedure_completeness"]
            emitted, rendered = _procedure_emissions(rid, proof, chunks)
            fragments.extend(emitted)
            groups.extend(rendered)
        else:
            fragments.append(
                dict(
                    requirement_id=rid,
                    **{
                        k: descriptor[k]
                        for k in (
                            "chunk_id",
                            "document_id",
                            "document_version",
                            "content_hash",
                            "document_range",
                        )
                    },
                    chunk_range={k: descriptor["span"][k] for k in ("start", "end")},
                    text=descriptor["span"]["text"],
                )
            )
    if len({f["document_id"] for f in fragments}) > 8:
        raise ValueError("Eight-document citation budget exceeded")
    passages = factual._passages(fragments, chunks)
    citations = [
        dict(
            citation_index=n,
            **chunks[identifier]["identity"],
            quoted_text=chunks[identifier]["chunk"].content,
            answer_spans=spans,
        )
        for n, (identifier, spans) in enumerate(passages.items(), 1)
    ]
    disclosures = [
        *_verified_disclosures(chosen),
        *(deepcopy(role_scope["disclosures"]) if role_scope else []),
    ]
    texts = [d["text"] for d in disclosures]
    answer, ranges = render_extractive(citations, groups, texts)
    disclosure_ranges = _answer_ranges(answer, citations, groups, fragments, texts)
    for disclosure, offset in zip(disclosures, disclosure_ranges, strict=True):
        disclosure["answer_range"] = offset
    return answer, citations, fragments, groups, disclosures


def _replay_requirements(  # noqa: C901 - original order controls literal dependencies
    selection,
    requirements,
    sources,
    chunks,
    snapshots,
    plan,
    callback,
    settings,
    role_effective=None,
    role_scope=None,
    typed_role_evidence=None,
):
    from app.services.linguistic_dependencies import resolve_linguistic_requirement

    identifiers = {r.id for r in requirements}
    raw = selection["proposals"]
    if len({p["proposal_id"] for p in raw}) != len(raw):
        raise ValueError("Duplicate global raw proposal identity")
    if any(p["requirement_id"] not in identifiers for p in raw):
        raise ValueError("Raw proposal refers to unknown requested requirement")
    if any(c["requirement_id"] not in identifiers for c in selection["candidates"]):
        raise ValueError("Candidate refers to unknown requested requirement")
    observations = selection["qa_observations"]
    if type(observations) is not list or len(
        {o["observation_id"] for o in observations}
    ) != len(observations):
        raise ValueError("Retained QA observation inventory duplicated/invalid")
    if any(o["requirement_id"] not in identifiers for o in observations):
        raise ValueError("QA observation refers to unknown requirement")
    if any(
        o["requirement_id"] not in identifiers
        for o in selection["pattern_observations"]
    ):
        raise ValueError("Pattern observation refers to unknown requirement")
    selected = selection["selected_proposal_ids"]
    if (
        type(selected) is not list
        or not selected
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("Invalid selected raw inventory")
    if not set(selected) <= {p["proposal_id"] for p in raw}:
        raise ValueError("Selected raw proposal absent")
    rows = selection["requirements"]
    if len(rows) != len(requirements):
        raise ValueError("Requested rows missing/added")
    groups, chosen, effective, values = [], [], [], {}
    for original, row in zip(requirements, rows, strict=True):
        req, binding = resolve_linguistic_requirement(original, plan, values)
        req = (role_effective or {}).get(original.id, req)
        _same(
            row.get("dependency_binding", {}),
            binding,
            "Actual literal dependency binding differs",
        )
        view = {
            **selection,
            "requirements": [row],
            "candidates": [
                c for c in selection["candidates"] if c["requirement_id"] == req.id
            ],
            "proposals": [p for p in raw if p["requirement_id"] == req.id],
            "pattern_observations": [
                o
                for o in selection["pattern_observations"]
                if o["requirement_id"] == req.id
            ],
            "qa_observations": [
                o for o in observations if o["requirement_id"] == req.id
            ],
        }
        view["selected_proposal_ids"] = [
            p["proposal_id"] for p in view["proposals"] if p["proposal_id"] in selected
        ]
        role_documents = (role_scope or {}).get("allowed_documents", {}).get(req.id)
        scoped_sources = sources
        if role_documents is not None:
            scoped_sources = [
                s for s in sources if s.identity["document_id"] in role_documents
            ]
            for name in ("qa_observations", "proposals", "candidates"):
                for item in selection[name]:
                    if item["requirement_id"] == req.id:
                        document = chunks[item["chunk_id"]]["identity"]["document_id"]
                        if document not in role_documents:
                            raise ValueError(
                                "Role model input bypasses preferred session assignment"
                            )
        if typed_role_evidence is not None and req.id in typed_role_evidence:
            if _model_profile(settings) == "contextual_source_v4":
                from app.services import captured_role_consumer as staged_role_consumer
            else:
                from app.services import staged_role_consumer

            actual, owners = staged_role_consumer.groups(
                view, typed_role_evidence[req.id]
            )
        else:
            proposals, margins = _proposals(
                view,
                (req,),
                scoped_sources,
                chunks,
                reading_profile=_model_profile(settings),
            )
            actual, owners = _groups(
                view,
                (req,),
                proposals,
                margins,
                chunks,
                snapshots,
                plan,
                callback,
                settings,
                guard_selection=selection,
            )
        accepted = _selected(view, (req,), actual, owners)
        # Only selected independently replayed evidence supplies reference values.
        values[req.id] = accepted[0]["value"]
        effective.append({"requirement": asdict(req), "dependency_binding": binding})
        groups.extend(actual)
        chosen.extend(accepted)
    return groups, chosen, effective


def _guard_inventory(selection, groups):
    expected = {
        (group["requirement_id"], proof["document_id"])
        for group in groups
        if (proof := group["descriptor"].get("procedure_completeness"))
        and proof["method"] in {"consumer_envelope", "required_copy_v1"}
    }
    records = selection.get("source_guard_records", [])
    if type(records) is not list:
        raise ValueError("Retained assessed guard inventory must be a list")
    keys = []
    for record in records:
        if type(record) is not dict:
            raise ValueError("Retained assessed guard record must be an object")
        keys.append(
            (record["requirement_id"], record["source_identity"]["document_id"])
        )
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Retained assessed guards are duplicated, unbound or missing")


def _build(
    selection,
    *,
    question,
    source_snapshots,
    query_context,
    request_reconstructor=None,
    source_guard_reconstructor=None,
    reading_profile=PROFILE,
    typed_role_evidence=None,
):
    version = _version(reading_profile)
    if version.profile != PROFILE and (
        not callable(request_reconstructor) or not callable(source_guard_reconstructor)
    ):
        raise PendingConsumerProof(
            "Staged output requires independent request/source reconstructors"
        )
    settings, stable = _settings(
        selection, query_context, reading_profile=reading_profile
    )
    plan, plan_record, requirements = _request(
        selection,
        question,
        query_context,
        request_reconstructor,
        reading_profile=reading_profile,
    )
    if source_guard_reconstructor is None:
        source_guard_reconstructor = _default_source_guard
    chunks, inventory, sources = _sources(
        source_snapshots, selection, reading_profile=reading_profile, request_plan=plan
    )
    from app.services.linguistic_role_consumer import reconstruct_role_scope

    role_effective, role_scope = reconstruct_role_scope(
        selection, requirements, source_snapshots
    )
    groups, chosen, effective = _replay_requirements(
        selection,
        requirements,
        sources,
        chunks,
        source_snapshots,
        plan,
        source_guard_reconstructor,
        settings,
        role_effective,
        role_scope,
        typed_role_evidence,
    )
    _guard_inventory(selection, groups)
    from app.services.curated_conflict_proof import reconstruct_curated
    from app.services.linguistic_dependencies import resolve_linguistic_requirement

    bound_requirements, bound_values = [], {}
    for original in requirements:
        bound, _ = resolve_linguistic_requirement(original, plan, bound_values)
        bound = role_effective.get(original.id, bound)
        bound_requirements.append(bound)
        bound_values[bound.id] = next(
            g["value"] for g in chosen if g["requirement_id"] == bound.id
        )

    typed_ids = set(typed_role_evidence or {})
    curated = reconstruct_curated(
        {
            **selection,
            "conflicts": [
                row
                for row in selection["conflicts"]
                if row["requirement_id"] not in typed_ids
            ],
        },
        tuple(req for req in bound_requirements if req.id not in typed_ids),
        groups,
        source_snapshots,
        chunks,
        settings,
    )
    if typed_ids:
        if version.profile == "contextual_source_v4":
            from app.services import captured_typed_conflicts as staged_typed_conflicts
        else:
            from app.services import staged_typed_conflicts

        curated.extend(
            staged_typed_conflicts.reconstruct(
                selection,
                tuple(req for req in bound_requirements if req.id in typed_ids),
                typed_role_evidence,
                source_snapshots,
                chunks,
                plan,
            )
        )
    answer, citations, fragments, render_groups, disclosures = _presentation(
        chosen, chunks, role_scope
    )
    certificate = {
        "contract": recorded_evidence_policy(
            selection["evidence_profile"]
        ).output_contract,
        "reading_profile": version.profile,
        "renderer": RENDERER,
        "question_sha256": factual._hash(question),
        "answer_sha256": factual._hash(answer),
        "source_inventory": inventory,
        "request_plan": plan_record,
        **({"role_scope": role_scope} if role_scope else {}),
        "effective_requirements": effective,
        "model_settings": settings,
        "selected_proposal_ids": selection["selected_proposal_ids"],
        "selected_fragments": fragments,
        "procedure_groups": render_groups,
        "disclosures": disclosures,
        "assessed_inventory": groups,
        **({"curated_inspections": curated} if curated else {}),
        "retained_supported_inventory": [g for g in groups if g["supported"]],
        "source_guards": [g["source_guard"] for g in groups],
        "citations": citations,
        "retained_capture_sha256": factual._hash(factual._json(stable)),
    }
    return _wire({"answer": answer, "citations": citations, "certificate": certificate})


def build_output(selection, **context):
    """Produce only a fully reconstructed canonical presentation; no mutation."""
    try:
        return _build(selection, **context)
    except PendingConsumerProof:
        raise
    except (
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
        StopIteration,
        RecursionError,
        UnicodeError,
        OverflowError,
    ) as exc:
        raise ValueError(f"Mixed output rejected: {exc}") from exc


def reconstruct_certificate(selection, *, answer, citations, **context):
    """Replay actual output through canonical sources/model inputs and renderer."""
    result = build_output(selection, **context)
    _same(
        answer, result["answer"], "Actual answer differs from canonical mixed renderer"
    )
    canonical = result["citations"]
    if type(citations) is not list or len(citations) != len(canonical):
        raise ValueError("Actual citation inventory differs from canonical witnesses")
    for actual, expected in zip(citations, canonical, strict=True):
        if type(actual) is not dict or not set(expected) <= actual.keys():
            raise ValueError("Actual citation evidence record missing or invalid")
        for key, value in expected.items():
            _same(actual[key], value, "Actual citation order/source/spans differ")
    return result["certificate"]


def verify_output(selection, **context):
    """History must reproduce a recorded certificate, not its self-reported hash."""
    try:
        expected = reconstruct_certificate(selection, **context)
        return factual._json(selection.get(CERTIFICATE_FIELD)) == factual._json(
            expected
        )
    except (ValueError, TypeError, RecursionError):
        return False
