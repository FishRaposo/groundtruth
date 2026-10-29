"""Pure contextual-v2 declared-source copy and consumer guard reconstruction.

An opaque whole-source copy proves literal preservation, never arbitrary action
semantics. Actual request/capture origins and authorized snapshots are supplied
by the caller. Numeric NLI replay does not attest actual model execution.
"""

import hashlib
import json
import math
import re
from copy import deepcopy

from app.evidence_policy import (
    ACTIVITY_INSTRUCTION_QUOTE_CONTRACT,
    ACTIVITY_PROCEDURE_QUOTE_CONTRACT,
    reading_version,
    recorded_evidence_policy,
    source_copy_version,
)
from app.services.contextual_procedures import (
    _envelope_declaration,
    _envelope_named_subject,
)
from app.services.linguistic_requirements import validate_request_plan
from app.services.linguistic_source_scope import _Graph, _windows, source_scope
from app.services.request_parser import _native, make_capture
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

PROFILE = "contextual_source_v2"
METHOD = "consumer_envelope"
REFERENCE_POLICY = "dependency-clause-reference-locality-v2"
_SEMANTIC_OPERAND_HYPOTHESIS = (
    "In the instruction «{clause}», the role of {argument} is an entity or data "
    "operand of the stated action."
)
_CONTAINERS = frozenset(
    "appendix annex manual handbook guide policy protocol specification "
    "instruction direction reference supplement attachment roster schedule".split()
)
_NORMATIVE = frozenset(
    "consult follow obey refer specify prescribe direct require rely".split()
)
_RELATIVE = frozenset({"as", "according", "per", "pursuant"})
_NOMINAL = frozenset({"compound", "amod", "det", "nmod", "nummod", "poss", "case"})
_COPY_CONTENT = frozenset(
    "condition prohibition prerequisite exception parameter instruction step "
    "governor rule limitation warning restriction".split()
)
_RECORD_FIELDS = {
    "requirement_id",
    "source_identity",
    "requested_subject",
    "source_windows",
    "envelope_inventory",
    "nli_assessments",
}
_ASSESSMENT = {
    "label",
    "logits",
    "entailment_margin",
    "supported",
    "pair_tokens",
}


class SourceGuardError(ValueError):
    """Actual retained source/request/model evidence does not reconstruct."""


class SourceGuardRefusal(SourceGuardError):
    """A required source/reference obligation is not discharged."""


class SourceReferenceUnresolved(SourceGuardRefusal):
    """A potential instruction-content use has no resolved immutable target."""

    def __init__(self, message, evidence):
        super().__init__(message)
        self.reference_evidence = deepcopy(evidence)


def build_envelope(
    body,
    identity,
    requested_subject,
    request_plan,
    source_windows,
    *,
    source_copy_policy=None,
):
    """Build exact-copy obligations; required external instructions still refuse.

    Old605admission is not widened: only its literal declaration grammar is
    reused. This new version reconstructs reference context and requires actual
    NLI for ambiguous physical/literal mentions. External required copies are
    unsupported until an authorized referenced-output closure is implemented.
    """
    try:
        return _build(
            body,
            identity,
            requested_subject,
            request_plan,
            source_windows,
            source_copy_version(source_copy_policy),
        )
    except SourceGuardError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise SourceGuardError("Source envelope inputs do not reconstruct") from exc


def reconstruct_source_guard(selection, requirement, snapshot, request_plan):
    """Replay every actual assessment, including genuine negative candidates."""
    try:
        return _reconstruct(selection, requirement, snapshot, request_plan)
    except SourceGuardError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise SourceGuardError("Source consumer guard does not reconstruct") from exc


def _json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _diff_path(actual, expected, path=""):
    if isinstance(actual, dict) and isinstance(expected, dict):
        return _diff_mapping(actual, expected, path)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return _diff_sequence(actual, expected, path)
    if type(actual) is not type(expected) or actual != expected:
        return (
            (path or "$")
            + f"({type(actual).__name__}:{actual!r}"
            + f" != {type(expected).__name__}:{expected!r})"
        )
    return None


def _diff_mapping(actual, expected, path):
    for key in sorted(set(actual) | set(expected)):
        if key not in actual or key not in expected:
            return (path + "/" + key) or "/"
        nested = _diff_path(actual[key], expected[key], path + "/" + key)
        if nested is not None:
            return nested
    return None


def _diff_sequence(actual, expected, path):
    if len(actual) != len(expected):
        return path + f"[len {len(actual)}!={len(expected)}]"
    for index, (left, right) in enumerate(zip(actual, expected, strict=False)):
        nested = _diff_path(left, right, f"{path}[{index}]")
        if nested is not None:
            return nested
    return None


def _same(actual, expected):
    if _json(actual) != _json(expected):
        raise SourceGuardError(
            "Canonical source proof mismatch: " + str(_diff_path(actual, expected))
        )


def _literal(body, start, end):
    return {"start": start, "end": end, "text": body[start:end]}


def _plan(request_plan, requested_subject):
    record = request_plan.record() if hasattr(request_plan, "record") else request_plan
    _native(record)
    if type(record) is not dict:
        raise SourceGuardError("Actual independently planned request required")
    capture = make_capture(json.loads(record["graph_json"]))
    _same(capture["annotation_sha256"], record["graph_sha256"])
    _same(capture["capture_sha256"], record["capture_sha256"])
    _same(capture["parser"], json.loads(record["model_identity_json"]))
    if not validate_request_plan(record, question=record["question"], capture=capture):
        raise SourceGuardError("Actual request plan does not replay")
    if record["resolved_request"] is not True or record["unresolved"]:
        raise SourceGuardRefusal("Whole request remains unresolved")
    requirements = [
        r
        for r in record["requirements"]
        if r["kind"] == "procedure" and r["topic"] == requested_subject
    ]
    if len(requirements) != 1:
        raise SourceGuardRefusal("One independently resolved procedure topic required")
    requirement = requirements[0]
    if requirement["depends_on"]:
        raise SourceGuardRefusal(
            "Dependent procedures require independently replayed effective bindings"
        )
    uses = [u for u in record["uses"] if u["requirement_id"] == requirement["id"]]
    if len(uses) != 1 or uses[0]["extent"] != "whole_requested":
        raise SourceGuardRefusal("Actual complete-copy request extent required")
    if uses[0]["conditions"]:
        raise SourceGuardRefusal(
            "Requested conditions require a faithful declarative applicability check"
        )
    return record, requirement, uses[0]


def _build(
    body, identity, requested_subject, request_plan, source_windows, copy_version
):
    _envelope_named_subject(requested_subject)
    plan, requirement, use = _plan(request_plan, requested_subject)
    return _build_from_bound_request(
        body,
        identity,
        requested_subject,
        plan,
        requirement,
        use,
        source_windows,
        copy_version,
        reading_profile=PROFILE,
    )


def _build_from_bound_request(  # noqa: C901 - explicit versioned COPY branches
    body,
    identity,
    requested_subject,
    plan,
    requirement,
    use,
    source_windows,
    copy_version,
    *,
    reading_profile,
    source_ownership=None,
):
    """Pure body mechanics after a caller's version-specific request proof.

    This internal helper grants no request validity or publication authority.
    Legacy callers still pass through _plan; a new contract must independently
    replay its own whole plan before invoking these shared source mechanics.
    """
    _envelope_named_subject(requested_subject)
    version = reading_version(reading_profile)
    selected_copy = _selected_copy_mode(plan, reading_profile, source_ownership)
    cover = source_scope(body, identity, source_windows, asked_topic=requested_subject)
    if requirement["source_workspace"] is not None and requirement[
        "source_workspace"
    ] != cover["identity"].get("workspace_id"):
        raise SourceGuardRefusal("Actual requested source workspace does not match")
    try:
        declaration = _envelope_declaration(body)
        _envelope_named_subject(declaration["subject"])
    except ValueError as exc:
        raise SourceGuardRefusal(
            "No unambiguous first operative declared envelope"
        ) from exc
    first, last = declaration.span()
    full = {"start": 0, "end": len(body)}
    ordered = []
    if first:
        ordered.append({"kind": "literal_prefix", **_literal(body, 0, first)})
    ordered += [
        {"kind": "governing_declaration", **_literal(body, first, last)},
        {"kind": "opaque_payload", **_literal(body, last, len(body))},
    ]
    obligations = [
        {
            "name": name,
            "premise": body,
            "hypothesis": hypothesis,
            "source_range": dict(full),
        }
        for name, hypothesis in [
            ("namespace", f"This routine is for {requested_subject}."),
            ("applicability", f"This routine applies to {requested_subject}."),
        ]
    ]
    declared_relation = None
    governing_context = None
    applicability = _request_source_applicability(
        plan, requirement, use, reading_profile
    )
    if copy_version.instruction_arguments == "exact_source_copy":
        declared_relation = _request_declared_relation(
            body,
            declaration,
            source_windows,
            requested_subject,
            requirement,
            applicability,
            source_ownership,
            literal_declared_target=selected_copy,
        )
        references, locality, governing_context = _copy_reference_context(
            body,
            identity,
            cover,
            source_windows,
            (first, last),
            copy_version,
            declared_relation,
            source_ownership,
        )
        premise_range = (
            governing_context["source_range"] if governing_context else dict(full)
        )
        obligations = _requested_NI_obligations(
            body, declared_relation, premise_range, applicability
        )
    else:
        references, locality = _references(body, cover, source_windows, (first, last))
    obligations.extend(locality)
    instruction_boundary = None
    if copy_version.procedure_scope == "activity_quote_v2":
        if not selected_copy:
            raise SourceGuardRefusal("Instruction quote requires captured ownership")
        profile = recorded_evidence_policy(json.loads(plan["evidence_profile_json"]))
        if profile.procedure_scope_profile != "activity_quote_v2":
            raise SourceGuardError(
                "Instruction quote version differs from recorded policy"
            )
        instruction_boundary = _instruction_quote_boundary(body, source_ownership, last)
        full = dict(instruction_boundary["instruction_range"])
        ordered = [row for row in ordered if row["end"] <= last] + [
            {"kind": "opaque_payload", **_literal(body, last, full["end"])},
        ]
    request_obligations = _requested_copy_coverage(
        plan, requirement, use, full, reading_profile, applicability
    )
    inventory = {
        "contract": version.procedure,
        "reading_profile": reading_profile,
        "method": METHOD,
        "envelope_kind": "reference_aware_declared_source",
        "claim_semantics": "complete_literal_copy_of_declared_source_body",
        "source_identity": deepcopy(cover["identity"]),
        "source_body": body,
        "body_length": len(body),
        "envelope_range": full,
        "closure": {"kind": "immutable_eof", "offset": len(body)},
        "ordered_ranges": ordered,
        "requested_subject": requested_subject,
        "source_subject": declaration["subject"],
        "request_plan_sha256": _digest(plan),
        "requirement": requirement,
        "request_use": use,
        "request_obligation_inventory": request_obligations,
        "source_windows_sha256": _digest(source_windows),
        "source_scope": cover,
        "covered_units": [
            {
                "id": u["id"],
                **_literal(body, u["start"], u["end"]),
                "coverage": "covered_verbatim",
                "verification_method": "exact_source_interval_copy",
            }
            for u in cover["units"]
            if instruction_boundary is None or u["end"] <= full["end"]
        ],
        "literal_scope": {
            "source_subject": declaration["subject"],
            "requested_subject": requested_subject,
            "disclosure": f"Source-declared scope: {declaration['subject']}.",
            "claim": (
                "Literal source copy; original conditions and exceptions retained."
            ),
        },
        "reference_inventory": references,
        "nli_obligations": obligations,
        "guard_obligations": [
            {"kind": kind, "status": "pending_consumer_replay"}
            for kind in [
                "actual_request_and_source_binding",
                "full_literal_governing_material",
                "governing_context_namespace_and_applicability"
                if governing_context
                else "full_body_namespace_and_applicability",
                "bounded_required_reference_closure",
                "independent_factual_role_output_access_history",
            ]
        ],
    }
    if instruction_boundary is not None:
        inventory.update(
            instruction_boundary=instruction_boundary,
            claim_semantics="complete_contiguous_declared_instruction_quote",
            closure={"kind": "captured_instruction_interval", "offset": full["end"]},
        )
    if declared_relation is not None:
        inventory.update(
            source_copy_policy=copy_version.policy,
            declared_relation=declared_relation,
            nli_meaning={
                "method": copy_version.scope_proposition,
                "shared_proposition": True,
                "meaning": "two_named_gates_share_one_source_declared_relation",
                "independent_model_facts": False,
                "literal_argument_copy_is_not_nli_support": True,
            },
        )
    if governing_context is not None:
        inventory["governing_context"] = governing_context
    inventory.update(_selected_copy_scope(plan, cover["identity"], full, selected_copy))
    if instruction_boundary is not None:
        inventory["selected_source_scope"]["claim"] = (
            "complete_contiguous_declared_instruction_quote"
        )
        inventory["selected_source_scope"]["full_authority_scope"] = (
            instruction_boundary["authority_scope"]
        )
    inventory.update(_applicability_fields(applicability, inventory))
    if copy_version.argument_interpretation != "none":
        disclosure = (
            "Ordinary action arguments are copied literally. Explicit and "
            "identified instruction references require available content; "
            "implicit dependencies may remain unrecognized."
        )
        inventory["argument_interpretation"] = {
            "method": copy_version.argument_interpretation,
            "model_support": "NOT_ASSERTED",
            "implicit_reference_absence": "NOT_ESTABLISHED",
            "catalog": references["lexical_reference_catalog"],
            "disclosure": disclosure,
        }
        inventory["literal_scope"]["disclosure"] += " " + disclosure
    if copy_version.operand_semantics != "none":
        inventory["semantic_operand_inventory"] = deepcopy(
            references["semantic_operand_inventory"]
        )
        inventory["nli_meaning"]["operand_roles"] = {
            "method": copy_version.operand_semantics,
            "meaning": (
                "semantic_role_judgment_not_independent_fact_or_external_absence"
            ),
            "mandatory_contexts": ["complete_selected_clause", "whole_immutable_body"],
            "exact_copy_does_not_discharge": True,
        }
        inventory["guard_obligations"].append(
            {
                "kind": "source_bound_semantic_operand_roles",
                "status": "pending_consumer_replay",
            }
        )
    return inventory


def _instruction_quote_boundary(body, ownership, declaration_end):  # noqa: C901 - bounded fail-closed source cases
    """Select a literal instruction interval; retain full-source authority apart."""
    rows, instructions = [], []
    for unit in ownership["units"]:
        raw = unit["raw"]
        if raw["end"] <= declaration_end or not raw["text"].strip():
            continue
        groups = unit.get("captured_clauses", [])
        if not groups:
            raise SourceGuardRefusal("Instruction boundary has no captured clauses")
        kind = "unclassified_interior_copy"
        if _explicit_parallel_activity(groups):
            kind = "explicit_parallel_activity"
        else:
            roots, clauses = [], []
            for group in groups:
                clauses.extend(group["clauses"])
                roots.extend(
                    (token, group)
                    for token in group["tokens"]
                    if token["dep"] == "ROOT"
                )
            directives = [
                token
                for token, group in roots
                if token["pos"] == "VERB"
                and token["tag"] in {"VB", "VBP"}
                and not any(
                    t["head"] == token["i"]
                    and t["dep"]
                    in {"nsubj", "nsubjpass", "csubj", "csubjpass", "auxpass"}
                    for t in group["tokens"]
                )
            ]
            if directives:
                kind = "requested_instruction_with_all_attached_context"
                instructions.append(raw["end"])
            elif (
                roots
                and all(
                    any(
                        t["head"] == token["i"] and t["dep"] in {"nsubj", "nsubjpass"}
                        for t in group["tokens"]
                    )
                    and token["lemma"].casefold()
                    not in _NORMATIVE
                    | {"govern", "apply", "supply", "override", "permit", "prohibit"}
                    for token, group in roots
                )
                and not any(c["clause_marker"] or c["modality"] for c in clauses)
            ):
                kind = "independent_declarative_assertion"
        rows.append(
            {
                "unit_id": unit["unit_id"],
                "range": {"start": raw["start"], "end": raw["end"]},
                "disposition": kind,
            }
        )
    if not instructions:
        raise SourceGuardRefusal("No captured requested instruction boundary")
    end = max(instructions)
    for row in rows:
        kind = row["disposition"]
        if kind == "explicit_parallel_activity" and row["range"]["start"] < end:
            raise SourceGuardRefusal(
                "Interior parallel activity has ambiguous copy scope"
            )
        if row["range"]["start"] >= end and kind not in {
            "independent_declarative_assertion",
            "explicit_parallel_activity",
        }:
            raise SourceGuardRefusal("Unresolved trailing instruction governance")
    return {
        "method": "captured_contiguous_instruction_quote_v2",
        "instruction_range": {"start": 0, "end": end},
        "authority_scope": {"start": 0, "end": len(body)},
        "units": rows,
        "remaining_source_material": (
            "retained_in_full_authority_reference_and_conflict_checks"
        ),
        "action_or_independent_fact_truth": "NOT_ASSERTED",
    }


def _explicit_parallel_activity(groups):  # noqa: C901 - exact local scope binding
    """Bind an explicit separate activity to its local negative governor subject.

    This is a source-declared literal distinction, never a name-inequality rule.
    A combined factual/location sentence stays in this full retained tail.
    """
    if len(groups) != 1:
        return False
    group = groups[0]
    tokens = {t["i"]: t for t in group["tokens"]}
    semicolons = [t["source_start"] for t in tokens.values() if t["text"] == ";"]
    if len(semicolons) != 1:
        return False
    boundary = semicolons[0]
    separate = [
        t
        for t in tokens.values()
        if t["lemma"].casefold() == "separate"
        and t["dep"] == "amod"
        and t["source_end"] < boundary
    ]
    if len(separate) != 1 or separate[0]["head"] not in tokens:
        return False
    activity = tokens[separate[0]["head"]]
    if activity["pos"] not in {"NOUN", "PROPN"}:
        return False
    for clause in group["clauses"]:
        predicate = [
            t
            for t in tokens.values()
            if t["source_start"] == clause["predicate"]["start"]
        ]
        if len(predicate) != 1:
            continue
        lemma = predicate[0]["lemma"].casefold()
        governance = lemma in {"govern", "supply", "apply", "extend"}
        copula_part = lemma == "be" and any(
            a["attachment"] == "attr" and re.match(r"part\s+of\b", a["text"], re.I)
            for a in clause["arguments"]
        )
        if not (governance or copula_part):
            continue
        if predicate[0]["source_start"] <= boundary or not clause["negation"]:
            continue
        subjects = [
            a for a in clause["arguments"] if a["attachment"] in {"nsubj", "nsubjpass"}
        ]
        objects = [
            a
            for a in clause["arguments"]
            if a["attachment"] in {"dobj", "obj", "prep", "agent", "attr"}
        ]
        if len(subjects) != 1 or not objects:
            continue
        subject = [
            t
            for t in tokens.values()
            if subjects[0]["start"] <= t["source_start"] < subjects[0]["end"]
        ]
        anaphoric = (
            any(
                t["lemma"].casefold() in {"that", "this"} and t["dep"] == "det"
                for t in subject
            )
            or len(subject) == 1
            and subject[0]["pos"] == "PRON"
            and subject[0]["lemma"].casefold() == "it"
        )
        if not anaphoric:
            continue
        # Every later predicate must belong to this exact negative declaration.
        if any(
            c is not clause and c["predicate"]["start"] > boundary
            for c in group["clauses"]
        ):
            continue
        return True
    return False


def _selected_copy_mode(plan, reading_profile, ownership):
    selected = False
    if reading_profile == "contextual_source_v4" and plan.get("evidence_profile_json"):
        profile = json.loads(plan["evidence_profile_json"])
        policy = recorded_evidence_policy(profile)
        _same(profile, policy.record())
        selected = policy.source_governance_profile == "requirement_bound_v1"
    if ownership is not None and not selected:
        raise SourceGuardError("Selected-source COPY needs its canonical recorded mode")
    if selected and ownership is None:
        raise SourceGuardRefusal(
            "Independently replayed selected-source ownership required"
        )
    return selected


def _replay_assumption_use(plan, requirement, use, pending, policy, frame):
    from app.services.role_scope_policy import (
        NativeGivenContextUnresolved,
        native_given_context,
        replay_native_request_use,
    )

    try:
        rebuilt_frame = replay_native_request_use(plan, requirement, use)
    except ValueError as exc:
        raise SourceGuardError(str(exc)) from exc
    _same(frame, rebuilt_frame)
    original = json.loads(plan["structure_json"])["historical_partial"]
    node = next(n for n in original["nodes"] if n["id"] == use["node_id"])
    _same(pending["original_features_json"], node["feature_json"])
    try:
        return native_given_context(plan, requirement, use, policy)
    except NativeGivenContextUnresolved as exc:
        raise SourceGuardRefusal(str(exc)) from exc


def _pending_applicability(plan, use):
    pending = [
        r
        for r in json.loads(plan["remaining_external_governing_json"])
        if r.get("reason") == "pending_source_applicability"
        and r.get("owner_id") == use["node_id"]
    ]
    if not pending:
        return None
    return pending


def _applicability_given(plan, requirement, use, pending, policy):
    if (
        len(pending) != 1
        or not policy.activity_roles
        or requirement["kind"] != "procedure"
    ):
        raise SourceGuardRefusal("Requested applicability has no known interpretation")
    frame = pending[0]["original_frame"]
    _same(frame["condition_ast"], use["condition_ast"])
    if policy.procedure_scope_profile in {
        "activity_quote_v1",
        "activity_quote_v2",
    } and any(
        clause["operator"] == "request_assumption" for clause in frame["condition_ast"]
    ):
        return _replay_assumption_use(plan, requirement, use, pending[0], policy, frame)
    _same(
        json.loads(pending[0]["original_features_json"])["condition_ast"],
        use["condition_ast"],
    )
    return None


def _applicability_activity(plan, requirement, use, policy):
    try:
        activity = _ordinary_activity_scope(requirement["topic"])
    except SourceGuardRefusal:
        if policy.procedure_scope_profile not in {
            "activity_quote_v1",
            "activity_quote_v2",
        }:
            raise
        source_scope = json.loads(use["features_json"])["source_scope"]
        if _session_shaped_topic(requirement["topic"]):
            # The request names a documented session mode: the activity is
            # recovered from the session-qualified requested scope while the
            # session applicability itself remains uncertified.
            try:
                first, last = _envelope_named_subject(source_scope)
            except ValueError as exc:
                raise SourceGuardRefusal(
                    "Unimplemented requested session scope"
                ) from exc
            activity = source_scope[first:last]
        else:
            # The request asks for the documented routine itself and names no
            # ordinary session: the quote keeps the source activity scope and
            # discloses that session applicability is not certified.
            activity = source_scope
        return activity, [], False
    role_requirements = _ordinary_inspection_requirements(
        plan, requirement, use, policy, activity
    )
    return activity, role_requirements, True


def _request_source_applicability(plan, requirement, use, reading_profile):
    if reading_profile != "contextual_source_v4":
        return None
    policy = recorded_evidence_policy(json.loads(plan["evidence_profile_json"]))
    if policy.source_governance_profile != "requirement_bound_v1":
        return None
    pending = _pending_applicability(plan, use)
    if not pending:
        return None
    frame = pending[0]["original_frame"]
    given = _applicability_given(plan, requirement, use, pending, policy)
    activity, role_requirements, scoped = _applicability_activity(
        plan, requirement, use, policy
    )
    graph = _Graph(
        plan["question"], 0, json.loads(plan["graph_json"]), 0, len(plan["question"])
    )
    condition = (
        given["premise"]
        if given is not None
        else _ordinary_assignment_condition(graph, use)
        if scoped and (use["conditions"] or use["condition_ast"])
        else None
    )
    _ordinary_procedure_attribute(graph, requirement, use)
    result = {
        "original_requirement": deepcopy(requirement),
        "original_use": deepcopy(use),
        "original_frame": deepcopy(frame),
        "original_features_json": pending[0]["original_features_json"],
        "activity_scope": activity,
        "ordinary_session_role_requirements": role_requirements,
        "requested_session_scope": requirement["topic"],
        "condition": condition,
        "condition_semantics": (
            "requested_hypothetical_context"
            if condition is not None
            else "no_requested_condition"
        ),
        "assignment_absence": "NOT_ESTABLISHED",
        "disclosure": (
            f"Source/activity scope: the source-declared routine for {activity} is "
            f"quoted for the requested session context {requirement['topic']!r}. "
            "The no-separate-assignment condition is requested context, not a "
            "finding that no session assignment exists."
        ),
    }
    if policy.procedure_scope_profile in {"activity_quote_v1", "activity_quote_v2"}:
        result.update(
            procedure_scope_profile=policy.procedure_scope_profile,
            procedure_scope_contract=(
                ACTIVITY_INSTRUCTION_QUOTE_CONTRACT
                if policy.procedure_scope_profile == "activity_quote_v2"
                else ACTIVITY_PROCEDURE_QUOTE_CONTRACT
            ),
            interpretation_method="exact_original_context_and_activity_quote_policy",
            session_applicability="NOT_CERTIFIED",
            disclosure=(
                "Documented activity procedure. This quote does not certify a "
                "session-specific procedure or that session conditions hold. "
                "Your no-assignment condition is retained as given context; it "
                "is not a source-verified absence fact. Apply the copied source "
                "conditions before acting."
            ),
        )
        if given is not None:
            result.update(
                given_context=given,
                condition_semantics="unverified_given_context",
                disclosure=(
                    "Documented activity procedure. This quote does not certify "
                    "a session-specific procedure or that session conditions hold. "
                    + given["disclosure"]
                    + " Apply the copied source conditions before acting."
                ),
            )
    return result


def _session_shaped_topic(topic):
    words = topic.casefold().split()
    if not words:
        return False
    if words[0] in {"the", "a", "an"}:
        words = words[1:]
    if not words:
        return False
    return (
        words[0] in {"ordinary", "normal", "standard"}
        or any(w in {"session", "sessions"} for w in words)
        or words[-1] in {"activity", "activities"}
    )


def _ordinary_activity_scope(topic):
    from app.services.role_scope_policy import canonical_role_scope

    try:
        first, last = _envelope_named_subject(topic)
    except ValueError as exc:
        raise SourceGuardRefusal("Unimplemented requested session scope") from exc
    trailing = topic[last:].strip().casefold()
    qualifier = topic[:first].strip().casefold().split()
    if (
        not qualifier or qualifier[-1] not in {"ordinary", "normal", "standard"}
    ) or trailing not in {"", "session", "sessions", "activity", "activities"}:
        raise SourceGuardRefusal("Unimplemented requested session mode")
    activity = topic[first:last]
    _same(
        canonical_role_scope(topic),
        canonical_role_scope(activity + " " + trailing),
    )
    return activity


def _ordinary_inspection_requirements(plan, requirement, use, policy, activity):
    from app.services.answer_requirements import Requirement
    from app.services.role_scope_policy import plan_activity_role

    linked = []
    for row in plan["requirements"]:
        if (
            row["kind"] not in {"owner", "deputy"}
            or row["topic"] != requirement["topic"]
            or row["source_workspace"] != requirement["source_workspace"]
        ):
            continue
        peer = next(
            item for item in plan["uses"] if item["requirement_id"] == row["id"]
        )
        if peer["condition_ast"] != use["condition_ast"]:
            continue
        actual = Requirement(
            **{
                **row,
                "anchors": tuple(row["anchors"]),
                "depends_on": tuple(row["depends_on"]),
            }
        )
        interpretation = plan_activity_role(actual, policy, request_plan=plan)
        if interpretation is not None and interpretation.activity_scope == activity:
            linked.append(row["id"])
    if not linked:
        raise SourceGuardRefusal(
            "Existing complete ordinary-session inspection is required"
        )
    return linked


def _ordinary_assignment_condition(graph, use):
    if (
        len(use["conditions"]) != 1
        or len(use["condition_ast"]) != 1
        or len(use["scopes"]) != 1
    ):
        raise SourceGuardRefusal("Unimplemented source applicability conditions")
    condition, ast = use["conditions"][0], use["condition_ast"][0]
    ids = ast["token_indices"]
    tokens = [graph.tokens[i] for i in ids]
    neg = [{"start": a, "end": b, "text": text} for a, b, text in ast["negation"]]
    expected = ("with", "no", "separate", "assignment")
    if (
        tuple(graph.lemma(i) for i in ids) != expected
        or tuple(t["dep"] for t in tokens) != ("prep", "det", "amod", "pobj")
        or tokens[1]["head"] != ids[3]
        or tokens[2]["head"] != ids[3]
        or tokens[3]["head"] != ids[0]
        or ast["operator"] != "with"
        or ast["complements"]
        or ast["modality"]
        or use["references"]
        or use["units"]
    ):
        raise SourceGuardRefusal("Unknown requested condition remains pending")
    _same(graph.span(set(ids)), condition)
    _same(ast["evidence"], [condition[k] for k in ("start", "end", "text")])
    _same(ast["subjects"], [[use["scopes"][0][k] for k in ("start", "end", "text")]])
    _same(use["negation"], neg)
    _same(use["modality"], neg)  # Here "no" is the captured negative determiner.
    return deepcopy(condition)


def _strip_leading_article(text):
    lowered = text.casefold()
    for article in ("the ", "a ", "an "):
        if lowered.startswith(article):
            return text[len(article) :]
    return text


def _relation_head_matches(graph, index, relation):
    return (
        graph.lemma(index) == relation
        or graph.tokens[index]["text"].casefold() == relation.casefold()
    )


def _ordinary_procedure_attribute(graph, requirement, use):
    heads = [
        i
        for i in use["head_token_indices"]
        if _relation_head_matches(graph, i, requirement["relation"])
    ]
    if len(heads) != 1:
        raise SourceGuardRefusal("Requested procedure method remains unbound")
    nominal = graph.nominal(heads[0])
    # Hyphenated and adverbial pieces inside the requested nominal (e.g.
    # "lower-bound") attach below the nominal dependencies collected above.
    frontier = list(nominal)
    while frontier:
        parent = frontier.pop()
        for child in graph.children(parent):
            token = graph.tokens[child]
            if child in nominal:
                continue
            if (
                token["dep"] in {"advmod", "npadvmod"}
                or token["dep"] == "punct"
                and token["text"] in {"-", "–", "—"}
                or token["dep"] in {"cc", "conj"}
                and child > 0
                and child + 1 < len(graph.tokens)
                and (
                    graph.tokens[child - 1]["text"] == "-"
                    or graph.tokens[child + 1]["text"] == "-"
                )
            ):
                nominal.add(child)
                frontier.append(child)
    span = graph.span(nominal)
    leading = min(nominal, key=lambda i: graph.tokens[i]["start"])
    body = (
        nominal - {leading}
        if graph.tokens[leading]["dep"] == "det"
        and graph.lemma(leading) in {"the", "a", "an"}
        else nominal
    )
    _same(
        graph.span(body)["text"],
        _strip_leading_article(requirement["attribute"]),
    )
    topic_words = {
        word.casefold() for word in re.findall(r"[^\W_]+", requirement["topic"])
    }
    if (
        any(
            not (
                i == heads[0]
                or graph.tokens[i]["dep"] == "det"
                and graph.lemma(i) in {"the", "a", "an", "all", "every"}
                or graph.tokens[i]["dep"] == "amod"
                and graph.lemma(i)
                in {"full", "complete", "entire", "govern", "whole", "order"}
                or graph.tokens[i]["dep"] == "poss"
                and graph.lemma(i) in {"its", "their"}
                or graph.tokens[i]["dep"] in {"compound", "flat", "fixed"}
                or graph.tokens[i]["dep"] == "punct"
                and graph.tokens[i]["text"] in {"-", "–", "—"}
                or graph.lemma(i) in topic_words
                or graph.tokens[i]["text"].casefold() in topic_words
            )
            for i in nominal
        )
        or {
            i
            for i in graph.indices
            if span["start"]
            <= graph.tokens[i]["start"]
            < graph.tokens[i]["end"]
            <= span["end"]
        }
        != nominal
    ):
        raise SourceGuardRefusal("Unknown requested procedure modifier remains pending")


def _request_declared_relation(
    body,
    declaration,
    windows,
    subject,
    requirement,
    applicability,
    ownership,
    *,
    literal_declared_target=False,
):
    if applicability is None:
        return _declared_relation(
            body,
            declaration,
            windows,
            subject,
            requirement,
            literal_declared_target=literal_declared_target,
        )
    if ownership is None or ownership.get("status") != "copy_domain_structurally_owned":
        raise SourceGuardRefusal(
            "Selected source has unresolved instruction governance"
        )
    _same(ownership["definition"], _literal(body, *declaration.span()))
    first, last = _envelope_named_subject(declaration["subject"])
    if declaration["subject"][:first].strip().casefold() not in {
        "ordinary",
        "normal",
        "standard",
    }:
        raise SourceGuardRefusal(
            "Selected source has no approved ordinary activity mode"
        )
    _same(
        declaration["subject"][first:last].casefold(),
        applicability["activity_scope"].casefold(),
    )
    relation = ownership["definition_relation"]
    quoted = applicability.get("procedure_scope_profile") in {
        "activity_quote_v1",
        "activity_quote_v2",
    }
    return {
        "method": "literal_activity_identity_and_activity_quote_policy"
        if quoted
        else "literal_activity_identity_and_original_conditional_NI",
        "proposition": _literal(body, *declaration.span()),
        "requested_subject": requirement["topic"],
        "requested_method": requirement["relation"],
        "predicate": deepcopy(relation["predicate"]),
        "subject": deepcopy(relation["subject"]),
        "target": deepcopy(relation["literal_scope"]),
        "declared_subject": _literal(
            body, declaration.start("subject"), declaration.end("subject")
        ),
        "whole_declaration_retained": True,
        "meaning": "source_activity_NI_given_session_context_not_certified"
        if quoted
        else "source_activity_identity_requested_conditional_scope_requires_NI",
    }


def _requested_NI_obligations(body, relation, source_range, applicability):
    hypotheses = dict.fromkeys(
        ("namespace", "applicability"), relation["proposition"]["text"]
    )
    if applicability is not None:
        requested = applicability["original_requirement"]
        # Exact canonical-body/EOF coverage proves COPY completeness separately.
        # Keep the entire conditional governed relation in the mandatory NI gate.
        ni_attribute = " ".join(
            word
            for word in requested["attribute"].split(" ")
            if word.casefold() != "complete"
        )
        source = relation["declared_subject"]["text"]
        scope = applicability["original_use"]["scopes"][0]["text"]
        condition = applicability["condition"]
        hypotheses = {
            "namespace": (
                f"The source-declared {source} is a {requested['relation']} "
                f"for {applicability['activity_scope']}."
            ),
            "applicability": (
                f"For {scope} {condition['text']}, "
                f"the source-declared {source} is {ni_attribute}."
                if condition is not None
                else (
                    f"The source-declared {source} is {ni_attribute} "
                    f"for {applicability['activity_scope']}."
                )
            ),
        }
        if applicability.get("procedure_scope_profile") in {
            "activity_quote_v1",
            "activity_quote_v2",
        }:
            hypotheses["applicability"] = (
                f"The source-declared {source} applies to "
                f"{applicability['activity_scope']}."
            )
    return [
        {
            "name": name,
            "premise": body[source_range["start"] : source_range["end"]],
            "hypothesis": hypothesis,
            "source_range": dict(source_range),
        }
        for name, hypothesis in hypotheses.items()
    ]


def _requested_copy_coverage(
    plan, requirement, use, full, reading_profile, applicability
):
    if applicability is None:
        return _bound_request_obligations(
            plan, requirement, use, full, reading_profile=reading_profile
        )
    return [
        {
            "kind": "source_bound_requested_applicability",
            "source_range": dict(full),
            "original_requirement": deepcopy(requirement),
            "original_use": deepcopy(use),
            "original_frame": applicability["original_frame"],
            "method": "exact_original_frame_activity_quote_policy_and_source_NI"
            if applicability.get("procedure_scope_profile")
            in {"activity_quote_v1", "activity_quote_v2"}
            else "original_typed_frame_and_two_mandatory_source_NI_gates",
            "coverage": "this_procedure_use_only_other_requirements_pending",
        }
    ]


def _applicability_fields(applicability, inventory):
    if applicability is None:
        return {}
    return {
        "request_applicability": {
            **deepcopy(applicability),
            "source_identity": deepcopy(inventory["source_identity"]),
            "source_declared_subject": inventory["source_subject"],
        },
        "literal_scope": {
            **inventory["literal_scope"],
            "disclosure": inventory["literal_scope"]["disclosure"]
            + " "
            + applicability["disclosure"],
        },
        "nli_meaning": {
            **inventory["nli_meaning"],
            "shared_proposition": False,
            "meaning": "source_activity_only_given_session_context_not_certified"
            if applicability.get("procedure_scope_profile")
            in {"activity_quote_v1", "activity_quote_v2"}
            else "source_activity_and_entire_requested_conditional_context",
        },
        "pending_external_checks": {
            **inventory["pending_external_checks"],
            "ordinary_session_assignments": "required_separately",
        },
    }


def _copy_reference_context(
    body, identity, cover, windows, declaration, version, relation, ownership
):
    if ownership is not None:
        references, locality = _owned_copy_references(body, identity, ownership)
        first, last = declaration
        context = {
            "contract": "complete-governing-context-v1",
            "method": "complete_first_source_declaration_for_quoted_scope",
            "source_range": {"start": first, "end": last},
            "source_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "governing_clauses": [dict(relation["proposition"])],
            "whole_source_structure_sha256": _digest(references),
            "selection": "fixed_structurally_before_model_results",
            "meaning": "selected_source_relation_not_action_or_other_source_truth",
            "quoted_conditions_prohibitions_contingencies": {
                "start": 0,
                "end": len(body),
            },
            "other_governing_material": (
                "retained_in_complete_COPY_and_external_checks"
            ),
        }
        return references, locality, context
    references, locality = _copy_references(body, cover, windows, declaration, version)
    context = (
        _complete_governing_context(body, relation, references)
        if version.governing_context == "complete_governing_context_v1"
        else None
    )
    return references, locality, context


def _selected_copy_scope(plan, identity, full, selected):
    if not selected:
        return {}
    return {
        "source_governance_profile": "requirement_bound_v1",
        "selected_source_scope": {
            "source_identity": deepcopy(identity),
            "source_range": dict(full),
            "claim": "complete_literal_copy_of_this_declared_source_only",
            "other_source_governance": "NOT_DISCHARGED",
            "action_semantics_and_independent_facts": "NOT_ASSERTED",
        },
        "pending_external_checks": {
            "source_operation_inventory": {
                "location": "request_plan.remaining_external_governing_json",
                "sha256": _digest(
                    json.loads(plan["remaining_external_governing_json"])
                ),
                "status": "PENDING_independent_outer_consumer",
            },
            "curated_group_inspection": "required_separately",
            "independent_factual_support": "required_separately",
            "SQL_authorization_currentness": "required_separately",
            "output_and_history": "required_separately",
        },
    }


def _owned_copy_references(body, identity, ownership):
    """Use the independently reconstructed source owner, not action grammar.

    The public staged ingress supplies this record from raw input2 replay.
    Literal COPY grants no action meaning or external-universe acceptance.
    """
    from app.semantic_reference_catalog import catalog_metadata

    if (
        type(ownership) is not dict
        or ownership.get("status") != "copy_domain_structurally_owned"
    ):
        raise SourceGuardRefusal(
            "Selected source has unresolved instruction governance"
        )
    _same(ownership["source_identity"], identity)
    entries, cursor = [], 0
    for row in ownership["units"]:
        raw = row["raw"]
        if (
            raw["start"] != cursor
            or not cursor < raw["end"] <= len(body)
            or raw["text"] != body[cursor : raw["end"]]
            or row["owner"]
            not in {
                "syntax_separator",
                "local_declared_instruction_definition",
                "captured_root_directive",
                "captured_declared_source_payload",
            }
        ):
            raise SourceGuardError(
                "Complete immutable selected-source ownership differs"
            )
        cursor = raw["end"]
        entries.append(
            {
                "unit_id": row["unit_id"],
                "clause": deepcopy(raw),
                "classification": row["owner"],
                "verification_method": "exact_source_interval_copy",
                "authority_closure": "selected_source_ownership_not_external_universe",
            }
        )
    if cursor != len(body):
        raise SourceGuardError("Selected-source COPY has an uncovered tail")
    return {
        "policy": source_copy_version(reading_profile="contextual_source_v4").reference,
        "entries": entries,
        "directive_ast": [],
        "captured_source_ownership": deepcopy(ownership),
        "lexical_reference_catalog": catalog_metadata(),
        "lexical_reference_inspections": [],
        "inspection_scope": (
            "captured_owned_opaque_source_not_action_sense_classification"
        ),
        "closure_claim": (
            "Selected-source explicit authority checks; "
            "implicit reference absence is not established."
        ),
        "semantic_authority_support": "NOT_ESTABLISHED_BY_COPY",
    }, []


def _complete_governing_context(body, relation, references):
    """Choose context before inference, retaining every governing clause.

    Directive conditions remain in their complete copied instruction graph.
    Any other governing clause extends the contiguous scope premise; it cannot
    be removed because a shorter model input would score more favorably.
    """
    ast = references["directive_ast"]
    if not ast:
        raise SourceGuardRefusal("No complete instruction payload was declared")
    governing = [dict(relation["proposition"])]
    for clause in ast:
        if clause["kind"] == "literal_governing_clause":
            governing.append(dict(clause["clause"]))
        elif clause["kind"] != "root_directive":
            raise SourceGuardRefusal("Unresolved governing source clause")
    end = max(row["end"] for row in governing)
    return {
        "contract": "complete-governing-context-v1",
        "method": "contiguous_prefix_through_all_governing_clauses",
        "source_range": {"start": 0, "end": end},
        "source_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "governing_clauses": governing,
        "whole_source_structure_sha256": _digest(references),
        "selection": "fixed_structurally_before_model_results",
        "meaning": (
            "source_declared_relation_not_condition_satisfaction_or_action_truth"
        ),
    }


def _unit_graph(body, windows, start, end):
    window = next(w for w in windows if w[0] <= start < end <= w[1])
    return _Graph(body, window[0], window[2], start, end)


def _one_root(g):
    roots = [i for i in g.indices if g.tokens[i]["dep"] == "ROOT"]
    if len(roots) != 1 or g.subtree(roots[0]) != g.indices:
        raise SourceGuardRefusal("Source clause has unresolved dependency attachment")
    return roots[0]


def _declared_relation(
    body,
    declaration,
    source_windows,
    requested_subject,
    requirement,
    *,
    literal_declared_target=False,
):
    if literal_declared_target is not False:
        if literal_declared_target is not True:
            raise SourceGuardError("Literal declared-target mode must be a native bool")
        return _literal_declared_relation(
            body, declaration, source_windows, requested_subject, requirement
        )
    first, last = declaration.span()
    g = _unit_graph(body, _windows(body, source_windows), first, last)
    root = _one_root(g)
    subjects = g.children(root, {"nsubj", "nsubjpass"})
    if len(subjects) != 1 or any(
        g.tokens[i]["dep"] == "neg" or g.tokens[i]["tag"] == "MD" for i in g.indices
    ):
        raise SourceGuardRefusal("Source-declared governing relation is not positive")
    subject = subjects[0]
    targets = []
    if g.lemma(root) == "govern":
        targets = g.children(root, {"dobj"})
    elif g.lemma(root) in {"apply", "be"}:
        targets = [obj for _, obj in g.pp(root, {"to", "for"})]
    if len(targets) != 1:
        raise SourceGuardRefusal("Source-declared target relation is unresolved")
    target = targets[0]
    left, right = _envelope_named_subject(declaration["subject"])
    literal_name = declaration["subject"][left:right]
    # This bridge binds the actual requested method/name, not just a substring
    # or a successful copy. Additional requested qualifiers still refuse.
    if literal_name.casefold() != requested_subject.casefold():
        raise SourceGuardRefusal(
            "Requested scope has no literal declared-target bridge"
        )
    relation = requirement["relation"]
    if not (
        _relation_head_matches(g, target, relation)
        or _relation_head_matches(g, subject, relation)
    ):
        raise SourceGuardRefusal("Requested method head has no declared-method bridge")
    nominal = g.nominal(target)
    source_start = declaration.start("subject")
    source_end = declaration.end("subject")
    declared_tokens = {
        i
        for i in g.indices
        if source_start <= g.offset + g.tokens[i]["start"]
        and g.offset + g.tokens[i]["end"] <= source_end
    }
    if not declared_tokens or not declared_tokens <= nominal:
        raise SourceGuardRefusal("Whole qualified declaration target is not attached")
    return {
        "method": "literal_requested_name_and_method_to_qualified_declared_target",
        "proposition": _literal(body, first, last),
        "requested_subject": requested_subject,
        "requested_method": relation,
        "predicate": g.span({root}),
        "subject": g.span(g.nominal(subject)),
        "target": g.span(nominal),
        "declared_subject": _literal(body, source_start, source_end),
        "declared_name": _literal(body, source_start + left, source_start + right),
        "whole_declaration_retained": True,
        "meaning": "source_qualified_scope_only_not_all_activity_variants",
    }


def _literal_declared_relation(
    body, declaration, source_windows, requested_subject, requirement
):
    from app.services.contextual_procedures import _ENVELOPE_GOVERNING_DECLARATION

    actual = _envelope_declaration(body)
    if actual.span() != declaration.span() or actual.group() != declaration.group():
        raise SourceGuardRefusal(
            "One complete first positive governing declaration required"
        )
    if _ENVELOPE_GOVERNING_DECLARATION.fullmatch(actual.group()) is None:
        # Recognized older declaration grammar keeps its original strict bridge;
        # a failed modern target is never retried through this format dispatch.
        return _declared_relation(
            body, actual, source_windows, requested_subject, requirement
        )
    first, last = actual.span()
    graph = _unit_graph(body, _windows(body, source_windows), first, last)
    root = _one_root(graph)
    subjects = graph.children(root, {"nsubj", "nsubjpass"})
    if (
        graph.lemma(root) != "govern"
        or graph.tokens[root]["pos"] != "VERB"
        or len(subjects) != 1
        or graph.lemma(subjects[0]) != "instruction"
        or any(
            graph.tokens[i]["dep"] == "neg" or graph.tokens[i]["tag"] == "MD"
            for i in graph.indices
        )
    ):
        raise SourceGuardRefusal("Source-declared governing relation is not positive")
    left, right = _envelope_named_subject(actual["subject"])
    literal_name = actual["subject"][left:right]
    if literal_name.casefold() != requested_subject.casefold():
        raise SourceGuardRefusal(
            "Requested scope has no literal declared-target bridge"
        )
    method = actual["subject"].split()[-1].casefold()
    if requirement["relation"].casefold() not in {
        method,
        graph.lemma(subjects[0]),
        graph.tokens[subjects[0]]["text"].casefold(),
    }:
        raise SourceGuardRefusal(
            "Requested method has no literal declared-method bridge"
        )
    start, end = actual.start("subject"), actual.end("subject")
    ids = {
        i
        for i in graph.indices
        if start
        <= graph.offset + graph.tokens[i]["start"]
        < graph.offset + graph.tokens[i]["end"]
        <= end
    }
    if not ids or graph.span(ids) != _literal(body, start, end):
        raise SourceGuardRefusal(
            "Complete literal declaration target has no capture cover"
        )
    return {
        "method": "literal_requested_name_and_method_to_whole_declared_target",
        "proposition": _literal(body, first, last),
        "requested_subject": requested_subject,
        "requested_method": requirement["relation"],
        "predicate": graph.span({root}),
        "subject": graph.span(graph.nominal(subjects[0])),
        "target": _literal(body, start, end),
        "declared_subject": _literal(body, start, end),
        "declared_name": _literal(body, start + left, start + right),
        "whole_declaration_retained": True,
        "meaning": "source_qualified_scope_only_not_all_activity_variants",
        "statistical_target_attachment": "NOT_ASSERTED",
        "captured_tokens": [deepcopy(graph.tokens[i]) for i in sorted(graph.indices)],
    }


def _copy_references(body, cover, source_windows, declaration, copy_version):
    windows = _windows(body, source_windows)
    entries, ast, semantic, obligations = [], [], [], []
    lexical = []
    for unit in cover["units"]:
        if unit["kind"] == "separator":
            continue
        if "capture_boundary" in unit["unresolved"]:
            raise SourceGuardRefusal("Source-copy AST crosses a capture boundary")
        g = _unit_graph(body, windows, unit["start"], unit["end"])
        clause = _literal(body, unit["start"], unit["end"])
        entry = {
            "id": f"ref{len(entries) + 1}",
            "unit_id": unit["id"],
            "clause": clause,
            "targets": _dependency_targets(g),
            "verification_method": "exact_source_interval_copy",
            "authority_closure": "not_inferred_from_literal_copy",
        }
        if declaration[0] <= unit["start"] < unit["end"] <= declaration[1]:
            entry["classification"] = "local_declared_source_definition"
        elif unit["kind"] == "nonoperative_region":
            entry["classification"] = "literal_nonoperative_material"
        else:
            parsed = _copy_clause(g, clause)
            ast.append(parsed)
            entry.update(
                classification="copied_directive_arguments",
                predicate_ranges=[c["predicate"] for c in parsed["clauses"]],
            )
            if copy_version.reference_catalog != "none":
                inspected = _ordinary_reference_inspections(
                    g, parsed, cover["identity"], clause, unit["id"]
                )
                lexical.extend(inspected)
                entry["lexical_reference_inspections"] = inspected
            if copy_version.operand_semantics != "none":
                bound, rows = _semantic_operand_rows(
                    g, parsed, unit["id"], cover["identity"], copy_version
                )
                semantic.extend(bound)
                obligations.extend(rows)
                entry["semantic_obligations"] = [r["name"] for r in rows]
        entries.append(entry)
    return _copy_reference_inventory(
        copy_version, entries, ast, semantic, lexical, obligations
    )


def _copy_reference_inventory(
    copy_version, entries, ast, semantic, lexical, obligations
):
    inventory = {
        "policy": copy_version.reference,
        "entries": entries,
        "directive_ast": ast,
        "closure_claim": (
            "Explicit or unresolved instruction-authority edges refuse; literal "
            "operands are copied without a physicality or universal absence claim."
        ),
        "semantic_authority_support": "NOT_ESTABLISHED_BY_COPY",
    }
    if copy_version.operand_semantics != "none":
        inventory["semantic_operand_inventory"] = semantic
    if copy_version.reference_catalog != "none":
        from app.semantic_reference_catalog import catalog_metadata

        inventory["lexical_reference_catalog"] = catalog_metadata()
        inventory["lexical_reference_inspections"] = lexical
        inventory["closure_claim"] = (
            "Bounded explicit and lexical reference checks under the disclosed "
            "ordinary-argument interpretation; not proof that every implicit "
            "dependency or real-world prerequisite is documented."
        )
    if copy_version.require_unique_semantic_inputs:
        inventory["semantic_input_binding"] = _unique_semantic_inputs(
            semantic, obligations
        )
    return inventory, obligations


def _ordinary_reference_inspections(graph, parsed, identity, clause, unit_id):
    from app.semantic_reference_catalog import (
        ReferenceCandidateLimit,
        inspect_predicate,
    )

    try:
        inspected = [
            inspect_predicate(
                graph,
                item["token"],
                source_identity=identity,
                clause_range=clause,
            )
            for item in parsed["clauses"]
        ]
    except ReferenceCandidateLimit as exc:
        raise SourceGuardRefusal(
            "Bounded instruction-reference inventory is incomplete"
        ) from exc
    if any(
        type(row) is not dict
        or type(row.get("potential_instruction_content")) is not bool
        or type(row.get("unresolved_risk")) is not bool
        for row in inspected
    ):
        raise RuntimeError("Malformed lexical reference inspection")
    if any(
        row["potential_instruction_content"] or row["unresolved_risk"]
        for row in inspected
    ):
        raise SourceReferenceUnresolved(
            "Possible instruction-content reference has no resolved immutable "
            "instruction body",
            {
                "source_identity": deepcopy(identity),
                "unit_id": unit_id,
                "inspections": inspected,
                "meaning": "possible_sense_veto_not_actual_sense_or_fact",
            },
        )
    return inspected


def _unique_semantic_inputs(bindings, rows):
    """Refuse unresolved occurrence grammar; never drop a copied step or row.

    Different labels/digests do not disambiguate the text seen by the model.
    This is a compiler invariant, not classifier support or an invalidity claim
    about coordination. Historical policy versions preserve their old inputs.
    """
    by_name = {row["name"]: row for row in rows}
    seen, manifest = {}, []
    for binding in bindings:
        occurrence = _digest(
            {
                key: binding[key]
                for key in (
                    "source_identity",
                    "clause",
                    "predicate",
                    "predicate_token",
                    "argument",
                    "argument_token",
                    "grammatical_attachment",
                    "preposition",
                )
            }
        )
        for name in (binding["clause_nli_name"], binding["nli_name"]):
            row = by_name[name]
            model_input = (row["premise"], row["hypothesis"])
            if model_input in seen and seen[model_input] != occurrence:
                raise SourceGuardRefusal(
                    "Ambiguous semantic input for distinct predicate/argument "
                    "occurrences; "
                    "this source grammar remains unresolved"
                )
            seen[model_input] = occurrence
            manifest.append(
                {
                    "nli_name": name,
                    "occurrence_sha256": occurrence,
                    "model_input_sha256": _digest(model_input),
                }
            )
    return {"method": "distinct_occurrence_input_injectivity_v1", "inputs": manifest}


def _semantic_argument_heads(g, predicate):
    heads = [
        (i, None)
        for i in g.children(
            predicate,
            {
                "dobj",
                "obj",
                "iobj",
                "dative",
                "nsubj",
                "nsubjpass",
                "attr",
                "oprd",
            },
        )
    ]
    for prep in g.children(predicate, {"prep", "agent"}):
        objects = g.children(prep, {"pobj"})
        if not objects:
            raise SourceGuardRefusal("Unresolved semantic prepositional operand")
        heads.extend((obj, prep) for obj in objects)
    if not heads:
        raise SourceGuardRefusal("No bound semantic operand-role proposition available")
    return heads


def _semantic_operand_rows(g, parsed, unit_id, identity, copy_version):
    inventory, rows = [], []
    for clause in parsed["clauses"]:
        predicate = clause["token"]
        for argument_head, prep in _semantic_argument_heads(g, predicate):
            argument = g.span(g.subtree(argument_head))
            name = f"semantic_operand:{unit_id}:p{predicate}:a{argument_head}"
            hypothesis = _SEMANTIC_OPERAND_HYPOTHESIS.format(
                clause=parsed["clause"]["text"], argument=argument["text"]
            )
            inputs = [
                {
                    "name": name + ":clause",
                    "premise": parsed["clause"]["text"],
                    "hypothesis": hypothesis,
                    "source_range": {k: parsed["clause"][k] for k in ("start", "end")},
                },
                {
                    "name": name + ":body",
                    "premise": g.body,
                    "hypothesis": hypothesis,
                    "source_range": {"start": 0, "end": len(g.body)},
                },
            ]
            binding = {
                "nli_name": name + ":body",
                "clause_nli_name": name + ":clause",
                "method": copy_version.operand_semantics,
                "source_identity": deepcopy(identity),
                "unit_id": unit_id,
                "clause": deepcopy(parsed["clause"]),
                "predicate": g.span({predicate}),
                "predicate_token": predicate,
                "predicate_clause": deepcopy(clause["literal_subtree"]),
                "argument": argument,
                "argument_token": argument_head,
                "grammatical_attachment": g.tokens[argument_head]["dep"],
                "preposition": None if prep is None else g.span({prep}),
                "status": "pending_actual_semantic_nli",
                "meaning": "semantic_operand_role_not_physicality_or_external_absence",
            }
            binding["input_sha256"] = _digest(
                {"binding": binding, "nli_inputs": inputs}
            )
            inventory.append(binding)
            rows.extend(inputs)
    return inventory, rows


def _copy_clause(g, clause):
    root = _one_root(g)
    if g.tokens[root]["pos"] not in {"VERB", "AUX"}:
        raise SourceGuardRefusal("Source operative predicate role is unresolved")
    predicates = _copy_predicates(g)
    _copy_authority_edges(g, predicates)
    clauses = [_copy_ast_clause(g, i) for i in sorted(predicates)]
    return {
        "clause": clause,
        "root_token": root,
        "kind": "root_directive"
        if not g.children(root, {"nsubj", "nsubjpass"})
        else "literal_governing_clause",
        "clauses": clauses,
        "subordinate_clauses": [c for c in clauses if c["token"] != root],
        "tokens": [_copy_ast_token(g, i, predicates) for i in sorted(g.indices)],
        "argument_meaning": "literal_directive_operands_not_independent_factual_claims",
        "verification_method": "exact_source_interval_copy",
        "action_semantics": "NOT_ASSERTED",
    }


def _copy_predicates(g):
    # Enumerate the complete predicate graph before any authority check. Only
    # attached auxiliaries and amod participles have explicit non-predicate
    # roles; an unrecognized content-verb attachment cannot become opaque text.
    predicates = set()
    for i in g.indices:
        token = g.tokens[i]
        if token["pos"] not in {"VERB", "AUX"}:
            continue
        if token["dep"] in {"aux", "auxpass", "amod"}:
            continue
        if token["dep"] not in {
            "ROOT",
            "conj",
            "advcl",
            "csubj",
            "csubjpass",
            "ccomp",
            "xcomp",
            "pcomp",
            "acl",
            "relcl",
        }:
            raise SourceGuardRefusal("Unresolved source content-predicate attachment")
        predicates.add(i)
    return predicates


def _copy_authority_edges(g, predicates):
    words = {g.lemma(i) for i in g.indices}
    lemmas = {g.lemma(i) for i in predicates}
    if lemmas & _NORMATIVE or _external_direction(g, lemmas, words):
        raise SourceGuardRefusal(
            "Instruction-authority edge needs actual copied closure"
        )
    # Instruction-bearing material is a semantic type, not an action alias.
    # Ambiguous materials (including attachments) conservatively remain refused.
    instruction_material = _CONTAINERS | {
        "step",
        "procedure",
        "routine",
        "method",
        "rule",
        "guidance",
    }
    if words & instruction_material:
        raise SourceGuardRefusal(
            "Instruction-material target needs actual copied closure"
        )
    if any(
        g.tokens[i]["dep"]
        in {
            "csubj",
            "csubjpass",
            "ccomp",
            "xcomp",
            "pcomp",
            "acl",
            "relcl",
        }
        or g.tokens[i]["tag"] in {"WP", "WP$", "WDT", "WRB"}
        for i in g.indices
    ):
        raise SourceGuardRefusal("Unknown referential/control complement needs closure")
    if words & {"elsewhere", "external", "outside", "above", "below", "omitted"}:
        raise SourceGuardRefusal("Unbound external/deictic material needs closure")
    if any(g.tokens[i]["pos"] == "PRON" for i in g.indices):
        raise SourceGuardRefusal("Unbound pronominal source argument needs closure")
    if any(
        g.tokens[i]["dep"] in {"dep", "meta", "intj", "parataxis"} for i in g.indices
    ):
        raise SourceGuardRefusal("Unresolved source token/parallel clause attachment")
    for i in predicates:
        if g.tokens[i]["dep"] == "advcl":
            markers = g.children(i, {"mark"})
            if len(markers) != 1 or g.lemma(markers[0]) not in {
                "if",
                "unless",
                "when",
                "while",
                "before",
                "after",
                "until",
                "once",
                "because",
                "provided",
                "without",
                "except",
                "whether",
            }:
                raise SourceGuardRefusal(
                    "Unknown subordinate/control clause attachment"
                )


def _copy_ast_clause(g, i):
    markers = g.children(i, {"mark"})
    arguments = g.children(
        i,
        {
            "dobj",
            "obj",
            "iobj",
            "dative",
            "nsubj",
            "nsubjpass",
            "attr",
            "oprd",
            "prep",
            "agent",
        },
    )
    return {
        "token": i,
        "predicate": g.span({i}),
        "attachment": g.tokens[i]["dep"],
        "clause_marker": " ".join(g.tokens[m]["text"] for m in markers),
        "arguments": [
            {"attachment": g.tokens[j]["dep"], **g.span(g.subtree(j))}
            for j in arguments
        ],
        "negation": [g.span({j}) for j in g.children(i, {"neg"})],
        "modality": [g.span({j}) for j in g.children(i, {"aux", "auxpass"})],
        "literal_subtree": g.span(g.subtree(i)),
    }


def _copy_ast_token(g, i, predicates):
    at = i
    while at not in predicates:
        parent = g.tokens[at]["head"]
        if parent == at:
            raise SourceGuardRefusal("Unconsumed source token attachment")
        at = parent
    token = g.tokens[i]
    return {
        "token": i,
        **g.span({i}),
        "head": token["head"],
        "dep": token["dep"],
        "role": "operative_predicate"
        if i in predicates
        else "literal_modifier"
        if token["dep"] in _NOMINAL
        else "literal_attached_context",
        "governing_clause": at,
    }


def _request_obligations(plan, use, full):
    # These are requests to retain source material, not assertions that the
    # source contains an emergency override, a measurement, or a named value.
    # Unknown semantic arguments cannot be discharged by merely copying/hash-
    # binding the request, nor by inventing an entailment hypothesis.
    for field in ("modality", "units", "references", "condition_ast"):
        if use[field]:
            raise SourceGuardRefusal(
                f"Requested {field} require independent semantic proof"
            )
    tokens = json.loads(plan["graph_json"])["tokens"]
    proofs = []
    for governor in use["governors"]:
        selected = [
            t
            for t in tokens
            if governor["start"] <= t["start"] < t["end"] <= governor["end"]
        ]
        if not _copy_governor(selected):
            raise SourceGuardRefusal(
                "Requested governor has no independently discharged meaning"
            )
        proofs.append(
            {
                "kind": "governors",
                "request_range": deepcopy(governor),
                "method": "whole_literal_source_retention",
                "source_range": dict(full),
                "meaning": (
                    "retain_all_source_declared_content_without_asserting_existence"
                ),
            }
        )
    return proofs


def _bound_request_obligations(plan, requirement, use, full, *, reading_profile):
    """Keep old records exact; v3 alone can replay actual owned copy selectors."""
    try:
        return _request_obligations(plan, use, full)
    except SourceGuardRefusal:
        if reading_profile not in {"contextual_source_v3", "contextual_source_v4"}:
            raise
        from app.services.staged_copy_facets import reconstruct_copy_facets

        try:
            return reconstruct_copy_facets(
                plan, requirement, use, full, reading_profile=reading_profile
            )
        except ValueError as exc:
            raise SourceGuardRefusal(str(exc)) from exc


def _copy_governor(tokens):
    if len(tokens) < 2 or tokens[0]["lemma"].casefold() not in {"include", "with"}:
        return False
    # Closed dependency production: include/with + [all] content nouns joined
    # by 'and'/commas. Every token must belong; no arbitrary modifiers/units.
    lead = tokens[0]["i"]
    nouns = {
        t["i"]
        for t in tokens[1:]
        if t["pos"] == "NOUN" and t["lemma"].casefold() in _COPY_CONTENT
    }
    if not nouns:
        return False
    for t in tokens[1:]:
        if t["i"] in nouns:
            if not (
                (t["dep"] in {"pobj", "dobj", "obj"} and t["head"] == lead)
                or (t["dep"] == "conj" and t["head"] in nouns)
            ):
                return False
        elif not (
            (
                t["lemma"].casefold() == "all"
                and t["dep"] == "det"
                and t["head"] in nouns
            )
            or (t["lemma"] == "and" and t["dep"] == "cc" and t["head"] in nouns)
            or (t["text"] == "," and t["dep"] == "punct" and t["head"] in nouns)
        ):
            return False
    return True


def _references(body, cover, source_windows, declaration):
    windows = _windows(body, source_windows)
    entries, obligations = [], []
    for unit in cover["units"]:
        if unit["kind"] == "separator":
            continue
        if "capture_boundary" in unit["unresolved"]:
            raise SourceGuardRefusal(
                "Reference analysis crosses an unresolved capture edge"
            )
        start, end = unit["start"], unit["end"]
        window = next(w for w in windows if w[0] <= start < end <= w[1])
        graph = _Graph(body, window[0], window[2], start, end)
        entry, obligation = _reference_clause(
            graph, unit, declaration, len(entries) + 1
        )
        entries.append(entry)
        if obligation is not None:
            obligations.append(obligation)
    return {
        "policy": REFERENCE_POLICY,
        "entries": entries,
        "closure_claim": (
            "No unresolved required dependencies under this bounded source-copy "
            "policy; not universal workflow closure."
        ),
    }, obligations


def _reference_clause(g, unit, declaration, number):
    first, last = unit["start"], unit["end"]
    entry = {
        "id": f"ref{number}",
        "unit_id": unit["id"],
        "clause": _literal(g.body, first, last),
        "predicate_ranges": [
            g.span({i})
            for i in sorted(g.indices)
            if g.tokens[i]["pos"] in {"VERB", "AUX"}
        ],
        "targets": [],
        "classification": "unclassified",
    }
    if declaration[0] <= first < last <= declaration[1]:
        entry["classification"] = "local_declared_source_definition"
        return entry, None
    if unit["kind"] == "nonoperative_region":
        entry["classification"] = "literal_nonoperative_material"
        return entry, None
    containers = [i for i in sorted(g.indices) if g.lemma(i) in _CONTAINERS]
    predicates = {
        g.lemma(i) for i in g.indices if g.tokens[i]["pos"] in {"VERB", "AUX"}
    }
    words = {g.lemma(i) for i in g.indices}
    if _external_direction(g, predicates, words):
        raise SourceGuardRefusal(
            "Required external instruction relationship has no authorized copy closure"
        )
    entry["targets"].extend(_container_targets(g, containers))
    dependency_targets = _dependency_targets(g)
    relative_targets = _relative_targets(g)
    entry["targets"].extend(dependency_targets + relative_targets)
    if dependency_targets and predicates & _NORMATIVE:
        raise SourceGuardRefusal(
            "Normative dependency target has no actual copied instruction closure"
        )
    if not containers and not relative_targets and not dependency_targets:
        entry["classification"] = "no_explicit_dependency_target_under_bounded_policy"
        return entry, None
    entry["classification"] = "physical_or_literal_candidate_requires_nli"
    name = f"reference_locality:{entry['id']}"
    entry["nli_obligation"] = name
    return entry, {
        "name": name,
        "premise": unit["text"],
        "hypothesis": (
            "This clause concerns a physical object or literal mention and does "
            "not direct consulting another source for mandatory instructions."
        ),
        "source_range": {"start": first, "end": last},
    }


def _container_targets(g, containers):
    targets = []
    for i in containers:
        at, nominal = i, {i}
        while g.tokens[at]["dep"] in _NOMINAL and g.tokens[at]["head"] in g.indices:
            at = g.tokens[at]["head"]
            nominal.add(at)
        nominal |= g.nominal(at)
        targets.append(g.span(nominal))
        ancestors, head = set(), i
        while head in g.indices and head not in ancestors:
            ancestors.add(head)
            if g.tokens[head]["head"] == head:
                break
            head = g.tokens[head]["head"]
        verbs = {g.lemma(j) for j in ancestors if g.tokens[j]["pos"] in {"VERB", "AUX"}}
        if verbs & _NORMATIVE or _instruction_object(g, at):
            raise SourceGuardRefusal(
                "External instruction target has no actual copied closure"
            )
    return targets


def _dependency_targets(g):
    # A noun catalogue cannot establish reference absence: an unknown object
    # may itself denote mandatory instructions. Retain full argument subtrees,
    # including object-attached locations, and require actual clause locality.
    indices = [
        i
        for i in sorted(g.indices)
        if g.tokens[i]["dep"]
        in {
            "dobj",
            "obj",
            "iobj",
            "pobj",
            "obl",
            "attr",
            "oprd",
            "nsubj",
            "nsubjpass",
            "csubj",
            "csubjpass",
            "ccomp",
            "xcomp",
        }
    ]
    return [g.span(g.subtree(i)) for i in indices]


def _snapshot_identity(snapshot):
    keys = ["document_id", "document_version", "content_hash"]
    result = {key: snapshot[key] for key in keys}
    for key in ["workspace_id", "snapshot_id"]:
        if snapshot.get(key) is not None:
            result[key] = snapshot[key]
    return result


def _external_direction(g, predicates, words):
    if predicates & {"consult", "refer"}:
        return True
    if predicates & _NORMATIVE and words & {
        "elsewhere",
        "external",
        "outside",
        "omitted",
    }:
        return True
    reporting = {"tell", "instruct", "order", "describe", "prescribe", "specify"}
    for i in g.indices:
        if (
            g.lemma(i) in reporting
            and g.tokens[i]["dep"] in {"advcl", "acl", "relcl", "ccomp"}
            and any(g.lemma(j) in _RELATIVE for j in g.children(i, {"mark", "advmod"}))
        ):
            return True
        if g.lemma(i) in {"per", "according", "pursuant"} and any(
            g.lemma(j) in _CONTAINERS or g.tokens[j]["pos"] == "PROPN"
            for j in g.subtree(i) - {i}
        ):
            return True
    return False


def _relative_targets(g):
    return [
        g.span(g.subtree(i))
        for i in sorted(g.indices)
        if g.tokens[i]["dep"] in {"advcl", "acl", "relcl", "ccomp", "xcomp"}
        and any(
            g.tokens[j]["tag"] in {"WP", "WP$", "WDT", "WRB"}
            or g.lemma(j) in {"whatever", "wherever", "what", "where", "as"}
            for j in g.subtree(i)
        )
    ]


def _instruction_object(g, head):
    parent = g.tokens[head]["head"]
    return (
        parent in g.indices
        and g.tokens[head]["dep"] == "dobj"
        and g.lemma(parent) in {"read", "use"}
        and g.lemma(head)
        in {
            "manual",
            "handbook",
            "appendix",
            "annex",
            "specification",
            "instruction",
            "direction",
            "policy",
            "protocol",
        }
    )


def _support(selection):
    support = selection["evidence_support"]
    expected = {
        "mode": "local_nli",
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "device": "cpu",
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "batch_size": BATCH_SIZE,
        "score_semantics": "raw contradiction/entailment/neutral logits; uncalibrated",
    }
    for key, value in expected.items():
        _same(support[key], value)
    margin = support["minimum_entailment_margin"]
    if (
        type(margin) not in (int, float)
        or not math.isfinite(margin)
        or not 0 <= margin <= 4
    ):
        raise SourceGuardError(
            "Captured source guard entailment margin must be finite0..4"
        )
    return {**expected, "minimum_entailment_margin": margin}


def _assessment(record, support):
    if type(record) is not dict or set(record) != _ASSESSMENT:
        raise SourceGuardError("Actual NLI assessment schema mismatch")
    logits = record["logits"]
    if (
        type(logits) is not list
        or len(logits) != 3
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in logits)
    ):
        raise SourceGuardError("Actual finite NLI logits required")
    margin = logits[1] - max(logits[0], logits[2])
    expected = margin > 0 and margin >= support["minimum_entailment_margin"]
    if (
        type(record["entailment_margin"]) not in (int, float)
        or not math.isfinite(record["entailment_margin"])
        or record["entailment_margin"] != margin
        or record["label"] != NLI.labels[max(range(3), key=lambda i: logits[i])]
        or record["supported"] is not expected
        or type(record["pair_tokens"]) is not int
        or not 0 < record["pair_tokens"] <= support["max_pair_tokens"]
    ):
        raise SourceGuardError("Actual NLI numeric decision/token contract mismatch")
    return deepcopy(record)


def _reconstruct(selection, requirement, snapshot, request_plan):
    _native(selection)
    version = reading_version(PROFILE)
    _same(selection["contract"], version.requirement)
    profile = selection["evidence_profile"]
    profile_contract = version.evidence_profile
    if "quantity_verification_profile" in profile:
        # A count-enabled request still needs the same procedure proof. Bind
        # its complete recorded policy instead of assuming the legacy marker.
        recorded = recorded_evidence_policy(profile).record()
        _same(profile, recorded)
        profile_contract = recorded["contract"]
    for key, expected in {
        "contract": profile_contract,
        "evidence_reading_profile": PROFILE,
        "procedure_contract": version.procedure,
    }.items():
        _same(profile[key], expected)
    if isinstance(requirement, dict):
        identifier, topic, kind = (
            requirement["id"],
            requirement["topic"],
            requirement["kind"],
        )
    else:
        identifier, topic, kind = requirement.id, requirement.topic, requirement.kind
    if kind != "procedure":
        raise SourceGuardRefusal(
            "An exact procedure copy cannot prove a separate factual or role request"
        )
    identity = _snapshot_identity(snapshot)
    support = _support(selection)
    record, retained = _source_record(
        selection, identifier, identity, request_plan, support
    )
    _same(record["source_identity"], identity)
    _same(record["requested_subject"], topic)
    envelope = build_envelope(
        snapshot["body"],
        identity,
        topic,
        request_plan,
        record["source_windows"],
        source_copy_policy=_record_policy(record),
    )
    _same(envelope["requirement"]["id"], identifier)
    supplied_requirement = (
        requirement
        if type(requirement) is dict
        else {key: getattr(requirement, key) for key in envelope["requirement"]}
    )
    _same(supplied_requirement, envelope["requirement"])
    _same(record["envelope_inventory"], envelope)
    assessments = _assessments(record, envelope, support)
    supported = all(row["assessment"]["supported"] for row in assessments)
    return {
        "contract": version.procedure,
        "status": "discharged",
        "method": METHOD,
        "source_identity": identity,
        "requirement_id": identifier,
        "request_plan_sha256": envelope["request_plan_sha256"],
        "envelope_inventory": envelope,
        "literal_scope": envelope["literal_scope"],
        "nli_assessments": assessments,
        "retained_record_inventory": retained,
        "retained_record_authority": (
            "each_identity_requires_independent_caller_snapshot_replay"
        ),
        "supported": supported,
        "entailment_margin": min(
            row["assessment"]["entailment_margin"] for row in assessments
        ),
        "minimum_entailment_margin": support["minimum_entailment_margin"],
        "support_settings": support,
        "governing_material": "covered_verbatim_without_action_semantics",
        "reference_closure": (
            "disclosed_ordinary_argument_bounded_reference_inventory"
            if envelope.get("argument_interpretation")
            else "supported_bounded_inventory"
        )
        if supported
        else "not_supported",
        "independent_factual_role_output_access_history": "required_separately",
    }


def _assessments(record, envelope, support):
    actual = record["nli_assessments"]
    expected = envelope["nli_obligations"]
    if type(actual) is not list or len(actual) != len(expected) or len(expected) < 2:
        raise SourceGuardError("Complete actual mandatory NLI inventory required")
    assessments = []
    for row, obligation in zip(actual, expected, strict=True):
        if type(row) is not dict or set(row) != set(obligation) | {"assessment"}:
            raise SourceGuardError("Actual NLI input schema mismatch")
        _same({k: row[k] for k in obligation}, obligation)
        assessments.append(
            {**obligation, "assessment": _assessment(row["assessment"], support)}
        )
    return assessments


def _source_record(selection, identifier, identity, request_plan, support):
    records = selection["source_guard_records"]
    if type(records) is not list:
        raise SourceGuardError("Actual retained source guard records required")
    retained, seen = [], set()
    for row in records:
        if type(row) is not dict or set(row) != _RECORD_FIELDS:
            raise SourceGuardError("Actual source guard record schema mismatch")
        envelope = build_envelope(
            row["envelope_inventory"]["source_body"],
            row["source_identity"],
            row["requested_subject"],
            request_plan,
            row["source_windows"],
            source_copy_policy=_record_policy(row),
        )
        _same(row["requirement_id"], envelope["requirement"]["id"])
        _same(row["envelope_inventory"], envelope)
        _assessments(row, envelope, support)
        key = (row["requirement_id"], _json(row["source_identity"]))
        if key in seen:
            raise SourceGuardError("Duplicate actual assessed source/request record")
        seen.add(key)
        retained.append(
            {
                "requirement_id": row["requirement_id"],
                "source_identity": deepcopy(row["source_identity"]),
                "record_sha256": _digest(row),
            }
        )
    matches = [
        row
        for row in records
        if row["requirement_id"] == identifier
        and row["source_identity"]["document_id"] == identity["document_id"]
    ]
    if len(matches) != 1:
        raise SourceGuardError("One actual assessed source/request record required")
    return matches[0], retained


def _record_policy(record):
    inventory = record["envelope_inventory"]
    policy = inventory.get("source_copy_policy")
    version = source_copy_version(policy)
    _same(inventory["reference_inventory"]["policy"], version.reference)
    return version.policy
