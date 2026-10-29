"""Rebind a property against its immutable body before accepting a chunk.

A true property fragment is not a complete property answer. This gate permits
only the same complete claim when independently rebuilt from the full body.
Cross-chunk copies that cannot fit the present witness contract refuse.
"""

import hashlib
import json
import re
from dataclasses import asdict

from app.evidence_policy import recorded_evidence_policy
from app.services.requirement_binding import SupportClaim, support_claim


class FactContextUnresolved(ValueError):
    """A valid source cannot express this complete bounded factual claim."""


def requirement_bound(policy):
    return policy is not None and (
        recorded_evidence_policy(policy.record()).source_governance_profile
        == "requirement_bound_v1"
    )


def _specialized_field_claim(requirement, context, start, end, policy, plan):
    if not requirement_bound(policy):
        return None
    if requirement.kind in {"owner", "deputy"}:
        from app.services.requirement_binding import activity_role_claim

        return activity_role_claim(requirement, context, start, end)
    if requirement.kind == "quantity" and plan is not None:
        from app.services.linguistic_quantities import scoped_quantity_claim

        return scoped_quantity_claim(
            requirement,
            context,
            start,
            end,
            evidence_profile=policy.record(),
            request_plan=plan,
        )
    return None


def factual_claim(requirement, context, start, end, *, policy, plan=None):
    """Existing binder first; new-mode typed scalar fallback retains literals."""
    field = _specialized_field_claim(requirement, context, start, end, policy, plan)
    if field is not None:
        return field
    claim = support_claim(
        requirement,
        context,
        start,
        end,
        reading_profile=policy.evidence_reading_profile,
    )
    if claim.rejection == "contextual_relation_unresolved":
        staged = _staged_field_claim(requirement, context, start, end, policy, plan)
        if staged is not None:
            return staged
    return claim


def _staged_field_claim(requirement, context, start, end, policy, plan):
    if (
        not requirement_bound(policy)
        or plan is None
        or requirement.kind not in {"duration", "location"}
    ):
        return None
    record = plan.record()
    uses = [u for u in plan.uses if u.requirement_id == requirement.id]
    if (
        record.get("contract") != "staged-request-plan-v2"
        or json.loads(record["evidence_profile_json"]) != policy.record()
        or requirement not in plan.requirements
        or len(uses) != 1
    ):
        return None
    use = uses[0]
    if requirement.depends_on or _use_blocked(requirement, use):
        return None
    features = json.loads(use.features_json)
    topic = requirement.topic or features.get("source_scope")
    attribute = requirement.attribute
    if attribute is None and requirement.kind == "location":
        attribute = "location"
    if (
        not topic
        or not attribute
        or (
            requirement.attribute is not None
            and features.get("attribute") != requirement.attribute
        )
    ):
        return None
    from app.services.contextual_binding import _TIME, _source_window

    window = _source_window(requirement, context, start, end)
    if window is None:
        return None
    _, _, left, right = window
    clause, value = context[left:right], context[start:end]
    # A source need not repeat the question's attribute wording. The complete
    # original attribute stays in the mandatory NLI hypothesis; literal topic
    # containment only bounds the candidate's named source context.
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in topic.split()) + r"\b"
    if not re.search(pattern, clause, re.I):
        return None
    if requirement.kind == "duration" and not re.fullmatch(
        rf"\d+(?:\.\d+)?\s+(?:[^\W\d_][\w-]*\s+){{0,3}}{_TIME}", value, re.I
    ):
        return None
    if requirement.kind == "location":
        return _location_claim(
            requirement,
            record,
            context,
            start,
            end,
            left,
            right,
            topic=topic,
            attribute=attribute,
        )
    return SupportClaim(
        f"The {attribute} for {topic} is {value}.",
        clause,
        value,
        start,
        end,
        None,
        left,
        right,
        premise_start=left,
        premise_end=right,
    )


def _use_blocked(requirement, use):
    references = use.references or []
    scope_resolved = (
        requirement.kind == "location"
        and len(use.scopes or []) == 1
        and all(
            (ref.get("text") or "").casefold() in _LOCATION_PRONOUNS
            for ref in references
        )
    )
    return (references and not scope_resolved) or any(
        getattr(use, key)
        for key in (
            "conditions",
            "condition_ast",
            "modality",
            "units",
            "governors",
            "quantifiers",
            "negation",
            "execution_dependencies",
        )
    )


_LOCATION_PRONOUNS = {
    "it",
    "its",
    "they",
    "their",
    "them",
    "this",
    "that",
    "these",
    "those",
}


def _location_claim(
    requirement, record, context, start, end, left, right, *, topic, attribute
):
    interval = _captured_location_range(record, context, start, end, left, right)
    if interval is None:
        return SupportClaim(
            None,
            context[left:right],
            context[start:end],
            start,
            end,
            "captured_location_argument_unresolved",
        )
    start, end = interval
    value = context[start:end]
    return SupportClaim(
        f"The {attribute} for {topic} is {value}.",
        context[left:right],
        value,
        start,
        end,
        None,
        left,
        right,
        premise_start=left,
        premise_end=right,
    )


def _location_capture(record, context):
    from app.services.dependency_frames import Graph
    from app.services.request_parser import validate_capture

    original = json.loads(record["source_productions_json"])["original_inputs"]
    snapshots = [
        s
        for s in original["snapshots"]
        if s["body"] == context
        or any(c["literal"]["text"] == context for c in s["chunks"])
    ]
    if len(snapshots) != 1:
        return None
    snapshot = snapshots[0]
    body = snapshot["body"]
    offset = body.find(context)
    if offset < 0 or body.find(context, offset + 1) >= 0:
        return None
    if (
        hashlib.sha256(body.encode()).hexdigest()
        != snapshot["identity"]["content_hash"]
    ):
        raise ValueError("Location source identity differs from retained body")
    captures = [
        c for c in original["source_captures"] if c["identity"] == snapshot["identity"]
    ]
    if len(captures) != 1 or len(captures[0]["windows"]) != 1:
        return None
    window = captures[0]["windows"][0]
    if window["start"] != 0 or window["end"] != len(body):
        return None
    return Graph(
        body, validate_capture(body, json.loads(window["capture_json"]))
    ), offset


def _captured_location_range(record, context, start, end, left, right):
    """Reconstruct one complete captured field, never equate raw strings."""
    captured = _location_capture(record, context)
    if captured is None:
        return None
    graph, offset = captured
    body = graph.raw
    candidates = []
    for token in graph.ts:
        parent = graph.ts[token["head"]]
        if (
            token["dep"] != "pobj"
            or parent["dep"] != "prep"
            or parent["text"].casefold() not in {"in", "at"}
        ):
            continue
        nominal = set(graph.nominal(token["i"]))
        nominal.update(
            child for child in token["children"] if graph.ts[child]["dep"] == "appos"
        )
        span = graph.span(nominal)
        if (
            not left + offset
            <= parent["start"]
            < span.start
            <= start + offset
            < end + offset
            <= span.end
            <= right + offset
        ):
            continue
        if not _closed_location_nominal(graph, nominal, span):
            continue
        value_end = span.end
        # The captured label may include the sentence delimiter (e.g. P.).
        # Only the proven clause boundary excludes it from the field value.
        if value_end == right + offset and body[value_end - 1] in ".!?":
            value_end -= 1
        if span.start < value_end:
            candidates.append((span.start - offset, value_end - offset))
    return candidates[0] if len(candidates) == 1 else None


def _closed_location_nominal(graph, nominal, span):
    inside = {
        t["i"] for t in graph.ts if span.start <= t["start"] and t["end"] <= span.end
    }
    if inside != nominal:
        return False
    for index in nominal:
        token = graph.ts[index]
        if token["pos"] == "PRON" or token["dep"] in {"poss", "case"}:
            return False
        if token["dep"] == "det" and token["text"].casefold() not in {"a", "an", "the"}:
            return False
        if any(child not in nominal for child in token["children"]):
            return False
    return True


def factual_support_context(
    requirement, source, member, raw, claim, *, policy, plan=None
):
    """Fix mandatory context from independently rebound claim/check ranges."""
    record = {
        "contract": "whole-source-fact-support-v1",
        "verification_method": "nli_entailment",
        "requirement_id": requirement.id,
        "source_identity": source.identity,
        "source_range": {"start": 0, "end": len(source.body)},
        "premise": source.body,
        "hypothesis": claim.hypothesis,
    }
    if not requirement_bound(policy):
        return "whole_source_support", record
    from app.services.contextual_output import _literal_range
    from app.services.evidence_proposals import validate_source

    validate_source(source)
    immutable_metadata = _immutable_fact_metadata(source, policy, plan)
    located = [p for p in source.chunks if p.chunk.id == member.id]
    if len(located) != 1 or located[0].chunk.content != member.content:
        raise ValueError("fact_context_chunk_mapping_invalid")
    offset = located[0].start
    full = factual_claim(
        requirement,
        source.body,
        raw["start"] + offset,
        raw["end"] + offset,
        policy=policy,
        plan=plan,
    )
    if (
        full.rejection
        or full.proof_edges
        or asdict(full) != _document_claim(claim, offset)
    ):
        raise FactContextUnresolved("fact_context_full_claim_unresolved_or_differs")
    ranges = [
        _literal_range(full.premise, source.body, full.premise_start, full.premise_end)
    ]
    ranges.extend(
        _literal_range(c.premise, source.body, c.start, c.end) for c in full.checks
    )
    left, right = min(r["start"] for r in ranges), max(r["end"] for r in ranges)
    record.update(
        contract=policy.record()["source_governance_contract"],
        source_range={"start": left, "end": right},
        premise=source.body[left:right],
        source_metadata=immutable_metadata,
        mandatory_ranges=ranges,
    )
    return "fact_context_support", record


def _immutable_fact_metadata(source, policy, plan):
    """One metadata authority for new producer and independently replayed receipt."""
    try:
        if plan is None or policy.evidence_reading_profile != "contextual_source_v4":
            raise ValueError("Captured source plan required")
        record = plan.record()
        if (
            record["contract"] != "staged-request-plan-v2"
            or record["reading_profile"] != "contextual_source_v4"
            or recorded_evidence_policy(json.loads(record["evidence_profile_json"]))
            != policy
        ):
            raise ValueError("Captured source policy differs")
        original = json.loads(record["source_productions_json"])["original_inputs"]
        snapshots = [
            row
            for row in original["snapshots"]
            if row["identity"]["document_id"] == source.identity["document_id"]
        ]
        if len(snapshots) != 1:
            raise ValueError("One immutable source metadata record required")
        snapshot = snapshots[0]
        for key in ("document_id", "document_version", "content_hash", "workspace_id"):
            expected, actual = snapshot["identity"][key], source.identity[key]
            if type(actual) is not type(expected) or actual != expected:
                raise ValueError("Immutable source metadata identity differs")
        if (
            snapshot["body"] != source.body
            or hashlib.sha256(source.body.encode()).hexdigest()
            != snapshot["identity"]["content_hash"]
            or type(snapshot["metadata_json"]) is not str
        ):
            raise ValueError("Immutable source metadata body differs")
        metadata = json.loads(snapshot["metadata_json"])
        if type(metadata) is not dict:
            raise ValueError("Immutable source metadata must be an object")
        json.dumps(metadata, allow_nan=False)
        return metadata
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise FactContextUnresolved(
            "fact_context_immutable_source_metadata_unresolved"
        ) from exc


def _document_claim(claim, offset):
    actual = asdict(claim)
    for name in (
        "start",
        "end",
        "support_start",
        "support_end",
        "premise_start",
        "premise_end",
    ):
        if actual[name] is not None:
            actual[name] += offset
    for check in actual["checks"]:
        for name in ("start", "end"):
            if check[name] is not None:
                check[name] += offset
    return actual


def property_cover_error(requirement, source, member, raw, claim):
    if requirement.kind != "availability":
        return None
    located = [part for part in source.chunks if part.chunk.id == member.id]
    if (
        len(located) != 1
        or source.body[located[0].start : located[0].end] != member.content
    ):
        return "property_chunk_mapping_invalid"
    offset = located[0].start
    full = support_claim(
        requirement,
        source.body,
        raw["start"] + offset,
        raw["end"] + offset,
        reading_profile="contextual_source_v2",
    )
    if full.rejection:
        return "whole_property_unresolved"
    expected = asdict(full)
    actual = asdict(claim)
    for name in (
        "start",
        "end",
        "support_start",
        "support_end",
        "premise_start",
        "premise_end",
    ):
        if actual[name] is not None:
            actual[name] += offset
    for check in actual["checks"]:
        for name in ("start", "end"):
            if check[name] is not None:
                check[name] += offset
    if expected != actual:
        return "whole_property_not_covered_by_witness"
    return None
