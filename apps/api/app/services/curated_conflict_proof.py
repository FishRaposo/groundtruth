"""Pure bounded curated comparisons over independently supplied source records.

Membership/currentness is captured by the caller and bound to authoritative
snapshots here. Recorded flags, rankings and QA abstentions grant no exclusion.
This is not universal contradiction detection or model execution attestation.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace

from app.services.contextual_output import _assessment, _same
from app.services.requirement_binding import (
    _DURATION_UNIT,
    _WEEKDAY,
    support_claim,
)
from app.services.requirement_conflict_scope import source_relation_scope
from app.services.requirement_contract import PROCEDURE_READ_SET_CONTRACT

PROCEDURE_CONTRACT = "curated-whole-source-scope-v1"
QUOTE_PROCEDURE_CONTRACT = "curated-selected-declaration-scope-v2"
LEGACY_FACT_CONTRACT = "curated-full-source-fact-comparison-v2"
FACT_CONTRACT = "curated-captured-source-fact-comparison-v3"
_IDENTITY = ("document_id", "document_version", "content_hash", "workspace_id")
_MINIMAL = ("chunk_id", "document_id", "document_version", "content_hash")


def _wire(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def subject_scope(current, applicable, witnesses):
    """The existing legacy bounded subject rule, shared without new semantics."""
    identifiers = {member.id for member in applicable}
    group_witnesses = [w for w in witnesses if w.chunk.id in identifiers]
    grammar = set(
        "the a an of for in on at with its it that this to is are "
        "standard ordinary normal".split()
    )
    subject = set(re.findall(r"\w[\w-]*", current.topic.casefold())) - grammar
    subject |= set(current.anchors)
    scoped = []
    for member in applicable:
        relation_scope = source_relation_scope(current, member.content)
        inherited = relation_scope == "unknown" and bool(group_witnesses)
        legacy_scope = (
            relation_scope == "unknown"
            and current.kind not in {"owner", "deputy", "procedure"}
            and subject
            and subject.issubset(
                set(re.findall(r"\w[\w-]*", member.content.casefold()))
            )
        )
        if relation_scope == "applies" or inherited or legacy_scope:
            scoped.append(member)
    kept = {member.id for member in scoped}
    excluded = [str(m.document_id) for m in applicable if m.id not in kept]
    return scoped, group_witnesses or witnesses, excluded


def complete_fact_agreement(members, witnesses):
    """Existing rule: the same validated value on every inspected member."""
    identifiers = {member.id for member in members}
    matching = [w for w in witnesses if w.chunk.id in identifiers]
    values = {w.value for w in matching}
    return (
        len({m.document_id for m in members}) >= 2
        and len(values) == 1
        and bool(next(iter(values), ""))
        and {w.chunk.id for w in matching} == identifiers
    )


def snapshot_identity(snapshot):
    return {key: snapshot.get(key) for key in _IDENTITY}


def inspection_identity(chunk, metadata=None):
    context = chunk.metadata if metadata is None else metadata
    context = context or {}
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "document_version": context.get("document_version"),
        "content_hash": context.get("content_hash"),
        "workspace_id": context.get("workspace_id"),
        "condition": deepcopy(context.get("condition")),
        "conflict_group": deepcopy(context.get("conflict_group")),
        "chunk_hash": hashlib.sha256(chunk.content.encode()).hexdigest(),
    }


def reconstruct_membership(selection, snapshots, chunks):  # noqa: C901 - complete independent read-set membership before semantic filtering
    """Bind the complete captured group/source universe before interpreting it."""
    expected = []
    for identifier, entry in sorted(chunks.items()):
        snapshot = snapshots[entry["identity"]["document_id"]]
        metadata = snapshot.get("metadata", {})
        if type(metadata) is not dict:
            raise ValueError("Authoritative curated metadata must be an object")
        group = metadata.get("conflict_group")
        if group is not None and (type(group) is not str or not group):
            raise ValueError("Authoritative curated group is invalid")
        expected.append(
            dict(
                **snapshot_identity(snapshot),
                chunk_id=identifier,
                condition=deepcopy(metadata.get("condition")),
                conflict_group=group,
                chunk_hash=hashlib.sha256(entry["chunk"].content.encode()).hexdigest(),
            )
        )
    groups = {}
    for entry in expected:
        if entry["conflict_group"] is not None:
            groups.setdefault(entry["conflict_group"], []).append(entry)
    records = selection.get("conflicts")
    if type(records) is not list:
        raise ValueError("Actual curated comparison list required")
    read_set = selection.get("procedure_read_set") or {}
    if not groups and not records and not read_set.get("groups"):
        return {}
    if (
        type(read_set) is not dict
        or read_set.get("contract") != PROCEDURE_READ_SET_CONTRACT
        or read_set.get("after_proofs", {}).get("consistent") is not True
        or read_set.get("before_publication", {}).get("consistent", True) is not True
    ):
        raise ValueError("Complete current curated read set required")
    for field in ("document_ids", "collection_ids"):
        values = read_set[field]
        if values is not None and (
            type(values) is not list
            or any(type(v) is not str or not v for v in values)
            or values != sorted(set(values))
            or any(str(uuid.UUID(v)) != v for v in values)
            or (not values and bool(expected))
        ):
            raise ValueError("Captured curated request scope is invalid")
    if read_set["document_ids"] is not None and any(
        e["document_id"] not in read_set["document_ids"] for e in expected
    ):
        raise ValueError("Curated member outside actual request scope")
    for snapshot in snapshots.values():
        captured_scope = snapshot.get("captured_scope")
        if captured_scope is not None:
            for field in ("document_ids", "collection_ids"):
                if field in captured_scope:
                    _same(
                        captured_scope[field],
                        read_set[field],
                        "Actual curated query scope differs",
                    )
    _same(
        read_set["sources"],
        expected,
        "Complete authoritative curated source inventory differs",
    )
    _same(
        sorted(selection["inspected_sources"], key=lambda row: row["chunk_id"]),
        [{k: entry[k] for k in _MINIMAL} for entry in expected],
        "Curated inspected member inventory differs",
    )
    _same(
        read_set["groups"],
        [{"group": name, "sources": groups[name]} for name in sorted(groups)],
        "Complete authoritative curated group membership differs",
    )
    return groups


def scope_input(requirement, identity, body):
    if requirement.kind != "procedure":
        raise ValueError("Procedure scope cannot replace factual support")
    return {
        "source_identity": dict(identity),
        "requirement_id": requirement.id,
        "source_range": {"start": 0, "end": len(body)},
        "premise": body,
        "hypothesis": f"The procedure described here applies to {requirement.topic}.",
        "verification_method": "nli_applicability_scope",
    }


class SelectedQuoteScopeUnresolved(ValueError):
    """The selected quote has no unique, independently bound declaration."""


def quote_policy(profile):
    from app.evidence_policy import recorded_evidence_policy

    policy = recorded_evidence_policy(profile)
    _same(profile, policy.record(), "Canonical curated quote policy required")
    return policy.procedure_scope_profile in {"activity_quote_v1", "activity_quote_v2"}


def selected_quote_scope(requirement, inventories, snapshots, *, evidence_profile=None):
    """Rebind a replayed quote inventory to its authoritative literal header.

    The caller supplies independently replayed inventories, not producer scope
    targets. This only selects the classifier target; it grants no exclusion.
    """
    from app.services.contextual_procedures import (
        RoutineRejected,
        _envelope_declaration,
    )

    expected_copy = "ordinary_activity_quote_v1"
    if evidence_profile is not None:
        from app.evidence_policy import recorded_evidence_policy

        if not quote_policy(evidence_profile):
            raise SelectedQuoteScopeUnresolved(
                "Canonical activity quote policy required"
            )
        if (
            recorded_evidence_policy(evidence_profile).procedure_scope_profile
            == "activity_quote_v2"
        ):
            expected_copy = "ordinary_activity_quote_v2"
    bases = []
    for inventory in inventories:
        _same(inventory["requirement"], asdict(requirement), "Quote request differs")
        if inventory["source_copy_policy"] != expected_copy:
            raise SelectedQuoteScopeUnresolved(
                "Selected source is not an activity quote"
            )
        identity = inventory["source_identity"]
        snapshot = snapshots[identity["document_id"]]
        _same(
            {k: identity.get(k) for k in _IDENTITY},
            {k: snapshot.get(k) for k in _IDENTITY},
            "Selected quote source identity differs",
        )
        body = snapshot["body"]
        if hashlib.sha256(body.encode()).hexdigest() != identity["content_hash"]:
            raise ValueError("Selected quote body hash differs")
        _same(inventory["source_body"], body, "Selected quote body differs")
        try:
            declaration = _envelope_declaration(body)
        except RoutineRejected as exc:
            raise SelectedQuoteScopeUnresolved(str(exc)) from exc
        proposition = {
            "start": declaration.start(),
            "end": declaration.end(),
            "text": declaration.group(),
        }
        target = {
            "start": declaration.start("subject"),
            "end": declaration.end("subject"),
            "text": declaration["subject"],
        }
        relation = inventory["declared_relation"]
        _same(relation["proposition"], proposition, "Selected declaration differs")
        _same(relation["declared_subject"], target, "Selected declared scope differs")
        basis = {
            "source_identity": {k: identity[k] for k in _IDENTITY if k in identity},
            "requirement": asdict(requirement),
            "request_use": deepcopy(inventory["request_use"]),
            "proposition": proposition,
            "target": target,
        }
        if basis not in bases:
            bases.append(basis)
    if len(bases) != 1:
        raise SelectedQuoteScopeUnresolved("One selected declared quote scope required")
    return bases[0]


def quote_scope_input(requirement, identity, body, basis):
    result = scope_input(requirement, identity, body)
    result.update(
        hypothesis=(
            f"The procedure described here applies to {basis['target']['text']}."
        ),
        verification_method="nli_selected_declaration_applicability_scope",
        selected_declaration=deepcopy(basis),
    )
    return result


def quote_scope_row(inputs, assessment, settings):
    actual = _assessment(assessment, settings, positive=False)
    row = scope_row(inputs, assessment, settings)
    row["scope_status"] = (
        "excluded"
        if row["scope_excluded"]
        else "applicable"
        if actual["supported"]
        else "unconfirmed"
    )
    return row


def quote_procedure_outcome(requirement, rows, identities, truncated, basis):
    unconfirmed = basis is None or any(
        r.get("scope_status") not in {"excluded", "applicable"} for r in rows
    )
    retained = [r for r in rows if r.get("scope_status") == "applicable"]
    # Any applicable opponent remains a conflict unless it is the exact copy.
    agreement = all(r["premise"] == basis["body"] for r in retained) if basis else False
    relevant = truncated or unconfirmed or not agreement
    result = procedure_outcome(requirement, rows, identities, truncated, True)
    result.update(
        inspection_method=QUOTE_PROCEDURE_CONTRACT,
        inspection_complete=not truncated and not unconfirmed,
        requested_fact_agreement=agreement,
        relevant=relevant,
        outcome="comparison_unconfirmed"
        if truncated or unconfirmed
        else "curated_conflict"
        if relevant
        else "not_relevant",
    )
    return result


def reconstruct_quote_group(record, requirement, snapshots, settings, inventories):
    if not quote_policy(settings["evidence_profile"]):
        raise ValueError("Selected declaration scope requires the quote policy")
    if type(record["truncated"]) is not bool:
        raise ValueError("Curated truncation state differs")
    basis = selected_quote_scope(
        requirement,
        inventories,
        snapshots,
        evidence_profile=settings["evidence_profile"],
    )
    documents = sorted({i["document_id"] for i in record["inspection_sources"]})
    if len(record["source_extent_checks"]) != len(documents):
        raise ValueError("Complete curated quote source rows required")
    rows = []
    for identifier, observed in zip(
        documents, record["source_extent_checks"], strict=True
    ):
        snapshot = snapshots[identifier]
        identity = {k: snapshot[k] for k in _IDENTITY if snapshot.get(k) is not None}
        row = quote_scope_row(
            quote_scope_input(requirement, identity, snapshot["body"], basis),
            observed["assessment"],
            settings,
        )
        _same(observed, row, "Curated selected-scope inputs/assessment differ")
        rows.append(row)
    expected = quote_procedure_outcome(
        requirement,
        rows,
        record["inspection_sources"],
        record["truncated"],
        dict(basis, body=snapshots[basis["source_identity"]["document_id"]]["body"]),
    )
    expected["group"] = record["group"]
    _same(record, expected, "Curated selected-scope outcome differs")
    return expected


def scope_row(inputs, assessment, settings):
    actual = _assessment(assessment, settings, positive=False)
    logits = actual["logits"]
    margin = logits[0] - max(logits[1:])
    excluded = (
        actual["label"] == "contradiction"
        and margin > 0
        and margin >= settings["support"]["minimum_entailment_margin"]
    )
    return dict(
        **inputs,
        assessment=actual,
        scope_contradiction_margin=margin,
        scope_excluded=excluded,
        reason="full_source_contradicts_requested_applicability"
        if excluded
        else "applicability_not_excluded",
    )


def procedure_outcome(requirement, rows, identities, truncated, supported_group):
    retained = [r for r in rows if not r.get("scope_excluded", False)]
    unconfirmed = any("assessment" not in r for r in rows)
    bodies = [r["premise"] for r in retained if "assessment" in r]
    agreement = len(bodies) >= 2 and all(body == bodies[0] for body in bodies)
    relevant = supported_group and (
        truncated or unconfirmed or (len(retained) >= 2 and not agreement)
    )
    return {
        "requirement_id": requirement.id,
        "inspection_method": PROCEDURE_CONTRACT,
        "inspection_sources": identities,
        "inspection_complete": not truncated and not unconfirmed,
        "truncated": truncated,
        "source_extent_checks": rows,
        "excluded_documents": sorted(
            r["source_identity"]["document_id"] for r in rows if r.get("scope_excluded")
        ),
        "requested_fact_agreement": agreement,
        "relevant": relevant,
        "outcome": "comparison_unconfirmed"
        if relevant and (truncated or unconfirmed)
        else "curated_conflict"
        if relevant
        else "not_relevant",
    }


def reconstruct_procedure_group(
    record, requirement, snapshots, settings, *, supported_group
):
    if (
        record["inspection_method"] != PROCEDURE_CONTRACT
        or type(record["truncated"]) is not bool
    ):
        raise ValueError("Unknown curated procedure inspection contract")
    documents = sorted({i["document_id"] for i in record["inspection_sources"]})
    rows = []
    if len(record["source_extent_checks"]) != len(documents):
        raise ValueError("Complete curated procedure source rows required")
    for identifier, observed in zip(
        documents, record["source_extent_checks"], strict=True
    ):
        snapshot = snapshots[identifier]
        # ProcedureSource identities omit absent workspace fields; preserve the
        # actual independently captured identity schema, never copy an extra key.
        identity = {k: snapshot[k] for k in _IDENTITY if k in snapshot}
        if identity.get("workspace_id") is None:
            identity.pop("workspace_id", None)
        actual = scope_row(
            scope_input(requirement, identity, snapshot["body"]),
            observed["assessment"],
            settings,
        )
        _same(
            observed,
            actual,
            "Curated procedure full-source model inputs/outcome differ",
        )
        rows.append(actual)
    expected = procedure_outcome(
        requirement,
        rows,
        record["inspection_sources"],
        record["truncated"],
        supported_group,
    )
    expected["group"] = record["group"]
    _same(record, expected, "Curated procedure comparison outcome differs")
    return expected


def fact_claim(chunk_identity, span, value, hypothesis):
    return {
        "source_identity": {k: chunk_identity[k] for k in _MINIMAL},
        "span": dict(span),
        "value": value,
        "hypothesis": hypothesis,
    }


def canonical_claims(claims):
    unique = {json.dumps(c, sort_keys=True, allow_nan=False): _wire(c) for c in claims}
    return [unique[k] for k in sorted(unique)]


def _other_relation_proof(requirement, fragment):
    """A complete, positive different-field parse; absence signals are not proof.

    This bounded exclusion recognizes simple temporal declaratives only for a
    role request. Its entire subject, predicate and value must be consumed and
    the canonical binding authority must reproduce the typed proposition. Other
    syntax, subordinate instructions and referrals remain for full-source NLI.
    It establishes a different field in the text, never factual entailment.
    """
    if requirement.kind not in {"owner", "deputy"}:
        return None
    for kind, predicate, value in (
        ("duration", r"lasts?(?:\s+for)?|takes?", rf"\d+\s+{_DURATION_UNIT}"),
        ("start_time", r"starts?(?:\s+at)?|begins?(?:\s+at)?", r"\d{1,2}:\d{2}"),
        ("weekday", r"starts?\s+on|begins?\s+on", _WEEKDAY),
    ):
        match = re.fullmatch(
            rf"\s*(?P<subject>(?:the|a|an)\s+[\w'’-]+(?:\s+[\w'’-]+)*)"
            rf"\s+(?P<predicate>{predicate})\s+(?P<value>{value})\s*[.!?;]?\s*",
            fragment,
            re.I,
        )
        if match is None:
            continue
        typed = replace(
            requirement,
            original_text=(
                f"How long does {match.group('subject')} last?"
                if kind == "duration"
                else f"{'Which day' if kind == 'weekday' else 'What time'} "
                f"does {match.group('subject')} start?"
            ),
            kind=kind,
            topic=match.group("subject"),
            anchors=(),
            depends_on=(),
            relation="lasts" if kind == "duration" else "starts",
            attribute=kind,
        )
        typed = replace(
            typed,
            question=typed.original_text,
            input_start=0,
            input_end=len(typed.original_text),
        )
        claim = support_claim(typed, fragment, match.start("value"), match.end("value"))
        if claim.rejection is not None or claim.hypothesis is None:
            continue
        return {
            "contract": "complete-other-field-declarative-v1",
            "kind": kind,
            "subject": match.group("subject"),
            "predicate": match.group("predicate"),
            "value_range": {"start": claim.start, "end": claim.end},
            "value": claim.value,
            "hypothesis": claim.hypothesis,
        }
    return None


def fact_scope(requirement, snapshot, source_windows=None):
    from app.services.curated_source_closure import closed_source_scope

    if source_windows is None:
        source_windows = snapshot.get("source_windows")
    if source_windows is None:
        raise ValueError("Actual complete curated source parser captures required")
    return closed_source_scope(
        requirement, snapshot, source_windows, _other_relation_proof
    )


def fact_inputs(requirement, snapshots, identities, claims, source_captures=None):
    documents = sorted({entry["document_id"] for entry in identities})
    claims = canonical_claims(claims)
    scopes = [
        fact_scope(
            requirement,
            snapshots[i],
            None if source_captures is None else source_captures[i],
        )
        for i in documents
    ]
    pairs = [
        {
            "requirement_id": requirement.id,
            "source_identity": row["source_identity"],
            "source_range": row["source_range"],
            "premise": row["premise"],
            "witness": claim,
            "hypothesis": claim["hypothesis"],
            "verification_method": "whole_source_requested_fact_nli",
        }
        for row in scopes
        if row["included"]
        for claim in claims
    ]
    return scopes, claims, pairs


def fact_outcome(requirement, identities, scopes, claims, comparisons, truncated):
    included = {r["source_identity"]["document_id"] for r in scopes if r["included"]}
    members = [
        SimpleNamespace(id=i["chunk_id"], document_id=i["document_id"])
        for i in identities
        if i["document_id"] in included
    ]
    witnesses = [
        SimpleNamespace(
            chunk=SimpleNamespace(id=c["source_identity"]["chunk_id"]), value=c["value"]
        )
        for c in claims
    ]
    complete = (
        not truncated
        and bool(comparisons)
        and all("assessment" in r for r in comparisons)
    )
    agreement = (
        complete
        and all(r["assessment"]["supported"] for r in comparisons)
        and complete_fact_agreement(members, witnesses)
    )
    all_excluded = not included
    sole_supported = (
        len(included) == 1
        and complete
        and all(r["assessment"]["supported"] for r in comparisons)
        and any(c["source_identity"]["document_id"] in included for c in claims)
    )
    unconfirmed = (
        truncated
        or (not all_excluded and not complete)
        or any(r.get("assessment", {}).get("label") == "neutral" for r in comparisons)
    )
    relevant = bool(claims) and (
        truncated or not (all_excluded or sole_supported or agreement)
    )
    return {
        "requirement_id": requirement.id,
        "inspection_method": FACT_CONTRACT,
        "inspection_sources": identities,
        "source_scope_decisions": scopes,
        "witness_claims": claims,
        "comparisons": comparisons,
        "truncated": truncated,
        "applicable_documents": sorted(included),
        "subject_scope_excluded_documents": sorted(
            r["source_identity"]["document_id"] for r in scopes if not r["included"]
        ),
        "inspection_complete": not truncated and (all_excluded or complete),
        "requested_fact_agreement": agreement,
        "agreement_method": "identical-validated-member-witnesses-v1"
        if agreement
        else None,
        "relevant": relevant,
        "outcome": "comparison_unconfirmed"
        if relevant and unconfirmed
        else "curated_conflict"
        if relevant
        else "not_relevant",
    }


def reconstruct_fact_group(record, requirement, snapshots, settings, claims):
    if (
        record.get("inspection_method") != FACT_CONTRACT
        or type(record.get("truncated")) is not bool
    ):
        raise ValueError(
            "Captured-source v3 curated factual inspection required; "
            "old uncaptured v2 is not certified"
        )
    from app.services.curated_source_closure import capture_inventory

    captures = capture_inventory(record, snapshots)
    scopes, claims, inputs = fact_inputs(
        requirement, snapshots, record["inspection_sources"], claims, captures
    )
    actual = record["comparisons"]
    if type(actual) is not list or len(actual) != len(inputs):
        raise ValueError("Complete curated factual model input inventory required")
    rows = []
    for observed, expected in zip(actual, inputs, strict=True):
        row = {
            **expected,
            "assessment": _assessment(observed["assessment"], settings, positive=False),
        }
        _same(observed, row, "Curated factual full-source/witness/model input differs")
        rows.append(row)
    result = fact_outcome(
        requirement,
        record["inspection_sources"],
        scopes,
        claims,
        rows,
        record["truncated"],
    )
    result["group"] = record["group"]
    _same(record, result, "Curated factual scope/agreement/outcome differs")
    return result


def reconstruct_curated(selection, requirements, groups, snapshots, chunks, settings):
    memberships = reconstruct_membership(selection, snapshots, chunks)
    expected_keys = {(name, req.id) for name in memberships for req in requirements}
    records = selection["conflicts"]
    keys = [(r["group"], r["requirement_id"]) for r in records]
    if len(keys) != len(set(keys)) or set(keys) != expected_keys:
        raise ValueError(
            "Complete unique request/curated comparison inventory required"
        )
    by_req = {r.id: r for r in requirements}
    # Replay every full source capture, including excluded and negative members,
    # and reject inconsistent copies across requirements before filtering.
    from app.services.curated_source_closure import recorded_capture_inventory

    recorded_capture_inventory(records, by_req, snapshots, FACT_CONTRACT)
    results = []
    for record in records:
        req = by_req[record["requirement_id"]]
        _same(
            record["inspection_sources"],
            memberships[record["group"]],
            "Actual curated comparison membership differs",
        )
        supported = [
            g for g in groups if g["requirement_id"] == req.id and g["supported"]
        ]
        if req.kind == "procedure":
            if record["inspection_method"] == QUOTE_PROCEDURE_CONTRACT:
                inventories = [
                    g["source_guard"]["consumer_proof"]["envelope_inventory"]
                    for g in supported
                ]
                result = reconstruct_quote_group(
                    record, req, snapshots, settings, inventories
                )
            else:
                result = reconstruct_procedure_group(
                    record, req, snapshots, settings, supported_group=bool(supported)
                )
            retained = [
                r["premise"]
                for r in result["source_extent_checks"]
                if not r["scope_excluded"]
            ]
            if any(body != g["value"] for body in retained for g in supported):
                raise ValueError(
                    "Curated retained procedure differs from actual supported copy"
                )
        else:
            claims = [
                fact_claim(
                    g["descriptor"],
                    g["descriptor"]["span"],
                    g["value"],
                    g["descriptor"]["nli_pairs"][0]["hypothesis"],
                )
                for g in supported
            ]
            result = reconstruct_fact_group(record, req, snapshots, settings, claims)
        if result["inspection_complete"] is not True or result["relevant"] is not False:
            raise ValueError("Curated opposition remains relevant or unconfirmed")
        results.append(result)
    return results
