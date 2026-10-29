"""New-only captured role facts; values bind only after fixed factual NI.

Original candidates, all source units and raw numeric receipts remain retained.
SQL authority/currentness and complete publication remain caller obligations.
"""

import asyncio
import json
from dataclasses import asdict, dataclass, fields

from app.services import captured_fact_support as factual
from app.services import captured_plan_binding as binding
from app.services import planning_declarations as source
from app.services import planning_support as support
from app.services import staged_role_evidence as legacy
from app.services.captured_plan_inputs import decode_inputs_v2
from app.services.effective_request import MemberBinding

CONTRACT = "captured-role-evidence-v1"
PATTERN = "captured-role-declaration-v1"
KINDS = frozenset({"role_catalogue", "role_label", "role_assignment"})
canonical, digest = source.canonical, source.digest
BoundRequirement = legacy.BoundRequirement
RoleFact = legacy.RoleFact
CatalogueSetProof = legacy.CatalogueSetProof
RoleSourceUnrepresentable = legacy.RoleSourceUnrepresentable
_require = legacy._require
_proposal = legacy._proposal


@dataclass(frozen=True)
class RoleEvidencePlan(legacy.RoleEvidencePlan):
    fact_batches_json: str = "[]"

    def record(self):
        return json.loads(
            canonical({"contract": CONTRACT + ":prepared", **asdict(self)})
        )


@dataclass(frozen=True)
class RoleEvidence(legacy.RoleEvidence):
    def record(self):
        return json.loads(canonical({"contract": CONTRACT, **asdict(self)}))


def _context(inputs):
    plan = binding.reconstruct_request(
        inputs["planning_inputs"],
        question=inputs["question"],
        authoritative_snapshots=inputs["authoritative_snapshots"],
        retained_inputs=inputs["retained_inputs"],
        require_runtime=inputs.get("require_runtime", True),
    )
    _require(plan.resolved_request, "Whole captured request remains unresolved")
    decoded = decode_inputs_v2(
        inputs["planning_inputs"],
        question=inputs["question"],
        authoritative_snapshots=inputs["authoritative_snapshots"],
        retained_inputs=inputs["retained_inputs"],
    )
    args = decoded.arguments
    _require(
        args["manifest"].selection_mode == "bounded_authorized_scan",
        "Complete selected captured publication inventory required",
    )
    inventory = source.declaration_inventory(
        args["manifest"], args["snapshots"], args["source_captures"]
    )
    return plan, args, inventory, decoded.source_productions


def _bound(plan, identifier, kinds: set[str] | frozenset[str] = KINDS):
    rows = [r for r in plan.requirements if r.id == identifier]
    uses = [u for u in plan.uses if u.requirement_id == identifier]
    _require(len(rows) == len(uses) == 1, "One captured requirement/use required")
    requirement, use = rows[0], uses[0]
    _require(requirement.kind in kinds, "Wrong captured factual requirement kind")
    features = json.loads(use.features_json)
    _require(
        not any(
            features.get(k)
            for k in (
                "condition_ast",
                "modality",
                "negation",
                "units",
                "governors",
                "order",
                "quantifiers",
            )
        ),
        "Qualified factual request remains unresolved",
    )
    return BoundRequirement(
        **asdict(requirement),
        use_json=canonical(asdict(use)),
        plan_sha256=digest(plan.record()),
        member_binding_id=use.member_binding_id,
        value_slot_id=use.value_slot_id,
        source_uses_json=use.source_uses_json,
    ), use


def _catalogue(plan, use, inventory):
    root_id = use.parent_id or use.requirement_id
    roots = [u for u in plan.uses if u.requirement_id == root_id]
    _require(len(roots) == 1, "One captured catalogue parent required")
    members = tuple(
        MemberBinding(**{**r, "literal": source.RawRange(**r["literal"])})
        for r in json.loads(plan.members_json)
        if r["group_id"] == root_id
    )
    _require(
        members and len({m.declaration_id for m in members}) == 1,
        "One exact immutable role catalogue required",
    )
    rows = [r for r in inventory.declarations if r.id == members[0].declaration_id]
    _require(
        len(rows) == 1 and rows[0].kind == "role_catalogue", "Catalogue source missing"
    )
    catalogue = rows[0]
    _require(
        tuple(m.literal for m in members) == catalogue.members
        and len(catalogue.scope) == 1,
        "Full literal catalogue membership differs",
    )
    ledger = json.loads(plan.source_productions_json)
    relevant = [
        candidate
        for source_row in ledger["sources"]
        for candidate in source_row["relation_candidates"]
        if [r["text"] for r in candidate["scope_candidates"]]
        == [r.text for r in catalogue.scope]
    ]
    labels = {member.literal.text for member in members}
    _require(
        all(candidate["role_label"]["text"] in labels for candidate in relevant)
        and all(
            sum(candidate["role_label"]["text"] == label for candidate in relevant) <= 1
            for label in labels
        ),
        "Unlisted or ambiguous captured role relationships remain unresolved",
    )
    children = tuple(u.requirement_id for u in plan.uses if u.parent_id == root_id)
    _require(len(children) == len(members), "Every captured catalogue child required")
    return catalogue, members, children


def _candidate_row(plan, bound, use, catalogue, members, ledger):
    if bound.kind == "role_catalogue":
        return catalogue, None, None
    member = next((m for m in members if m.id == use.member_binding_id), None)
    if member is None:
        raise ValueError("Exact catalogue member binding required")
    if bound.kind == "role_label":
        return catalogue, member.literal, member.literal
    slots = [
        s
        for s in json.loads(plan.value_slots_json)
        if (
            s["id"] == use.value_slot_id
            and s["requirement_id"] == bound.id
            and s["member_binding_id"] == member.id
        )
    ]
    _require(
        len(slots) == 1 and slots[0]["status"] == "UNBOUND_ACTOR_VALUE",
        "Actual unbound value slot required",
    )
    candidates = json.loads(slots[0]["candidates_json"])
    _require(len(candidates) == 1, "One unambiguous captured role value required")
    candidate = candidates[0]
    actual = [
        r
        for s in ledger["sources"]
        for r in s["relation_candidates"]
        if canonical(r) == canonical(candidate)
    ]
    _require(
        len(actual) == 1
        and candidate["actor_value"] == "UNBOUND"
        and candidate["accepted"] is False,
        "Original unbound role candidate required",
    )
    _require(
        candidate["role_label"] == asdict(member.literal)
        or candidate["role_label"]["text"] == member.literal.text,
        "Role candidate literal member differs",
    )
    _require(
        [r["text"] for r in candidate["scope_candidates"]]
        == [r.text for r in catalogue.scope]
        and member.declaration_id == catalogue.id,
        "Role candidate catalogue/scope ancestry differs",
    )
    units = [
        u
        for u in ledger["source_inventory"]["units"]
        if u["source"] == candidate["source"] and u["raw"] == candidate["raw"]
    ]
    _require(len(units) == 1, "One complete captured role source unit required")
    value = source.RawRange(**candidate["literal_value_candidate"])
    row = source.Declaration(
        candidate["id"],
        "captured_role_relation_candidate",
        units[0]["id"],
        source.SourceIdentity(**candidate["source"]),
        source.RawRange(**candidate["raw"]),
        source.RawRange(**candidate["role_label"]),
        tuple(source.RawRange(**r) for r in candidate["scope_candidates"]),
        (),
        canonical(candidate["original_features"]),
        canonical({"original_candidate": candidate, "value": asdict(value)}),
        "CAPTURED_UNBOUND_CANDIDATE",
    )
    return row, value, row.literal


def _fact_kwargs(inputs, row, claims, metadata):
    return {
        "record": inputs["planning_inputs"],
        "question": inputs["question"],
        "authoritative_snapshots": inputs["authoritative_snapshots"],
        "retained_inputs": inputs["retained_inputs"],
        "source_identity": row.source,
        "selected_clause": row.raw,
        "claims": tuple(claims),
        "expected_support_metadata": metadata,
    }


def _claims(bound, proposal, catalogue, members, label=None, value=None):
    scope = catalogue.scope[0].text
    chosen = (
        members
        if bound.kind == "role_catalogue"
        else tuple(m for m in members if m.id == bound.member_binding_id)
    )
    hypotheses = [
        "The roles stated here are for " + scope + ".",
        "The stated role labels for "
        + scope
        + " are "
        + support._join([m.literal.text for m in members])
        + ".",
        *(m.literal.text + " is a role for " + scope + "." for m in chosen),
    ]
    catalogue_claims = tuple(
        factual.FactSupportClaim(
            bound.id, proposal.proposal_id + ":catalogue:" + str(i), hypothesis
        )
        for i, hypothesis in enumerate(hypotheses)
    )
    if bound.kind != "role_assignment":
        return catalogue_claims, ()
    if label is None or value is None:
        raise ValueError("Actual literal role label and candidate value required")
    value_claims = (
        factual.FactSupportClaim(
            bound.id,
            proposal.proposal_id + ":role-value",
            f"For {scope}, {value.text} holds the {label.text} role.",
        ),
    )
    return catalogue_claims, value_claims


def prepare_role_evidence(*, requirement_id, **inputs):
    plan, args, inventory, ledger = _context(inputs)
    bound, use = _bound(plan, requirement_id)
    catalogue, members, children = _catalogue(plan, use, inventory)
    row, value, label = _candidate_row(plan, bound, use, catalogue, members, ledger)
    snapshot = next(s for s in args["snapshots"] if s.identity == row.source)
    proposal = _proposal(bound, snapshot, row, value, pattern_id=PATTERN)
    catalogue_claims, value_claims = _claims(
        bound, proposal, catalogue, members, label, value
    )
    batches, checks = [], []
    for actual, claims in ((catalogue, catalogue_claims), (row, value_claims)):
        if not claims:
            continue
        prepared = factual.prepare_fact_support(
            **_fact_kwargs(inputs, actual, claims, args["support_metadata"])
        )
        _require(
            prepared.ready_for_assessment,
            "Captured factual/governing context remains unresolved",
        )
        batches.append(
            {
                "source": asdict(actual.source),
                "raw": asdict(actual.raw),
                "claims": [asdict(c) for c in claims],
            }
        )
        checks.extend(prepared.assertions)
    _require(checks, "Mandatory role factual NI cannot be empty")
    return RoleEvidencePlan(
        bound,
        canonical(plan.record()),
        canonical(inventory.record()),
        plan.read_set_json,
        canonical(inputs["planning_inputs"]),
        canonical(inputs["retained_inputs"]),
        canonical(inputs["authoritative_snapshots"]),
        canonical(support._metadata(args["support_metadata"])),
        catalogue,
        members,
        children,
        row,
        value,
        label,
        (proposal,),
        tuple(checks),
        canonical(batches),
    )


def _batches(prepared, inputs):
    for batch in json.loads(prepared.fact_batches_json):
        yield {
            "record": inputs["planning_inputs"],
            "question": inputs["question"],
            "authoritative_snapshots": inputs["authoritative_snapshots"],
            "retained_inputs": inputs["retained_inputs"],
            "source_identity": source.SourceIdentity(**batch["source"]),
            "selected_clause": source.RawRange(**batch["raw"]),
            "claims": tuple(factual.FactSupportClaim(**r) for r in batch["claims"]),
            "expected_support_metadata": json.loads(prepared.support_metadata_json),
        }


def _replay(
    prepared,
    inputs,
    observations: tuple[support.NliObservation, ...],
    actual_executions: tuple[support.NliExecution, ...],
):
    _require(
        type(observations) is tuple and type(actual_executions) is tuple,
        "Immutable role observations and retained executions required",
    )
    _require(
        all(type(r) is support.NliObservation for r in observations)
        and all(type(r) is support.NliExecution for r in actual_executions),
        "Typed actual captured factual receipts required",
    )
    expected = {c.id for c in prepared.checks}
    _require(
        len(expected) == len(observations) == len(actual_executions)
        and {r.assertion_id for r in observations} == expected
        and {r.assertion_id for r in actual_executions} == expected
        and len({r.execution_id for r in actual_executions}) == len(expected),
        "Complete unique captured role execution inventory required",
    )
    assessments = []
    for kwargs in _batches(prepared, inputs):
        batch = factual.prepare_fact_support(**kwargs)
        ids = {c.id for c in batch.assertions}
        result = factual.reconstruct_fact_support(
            **kwargs,
            observations=tuple(r for r in observations if r.assertion_id in ids),
            actual_executions=tuple(
                r for r in actual_executions if r.assertion_id in ids
            ),
            require_runtime=inputs.get("require_runtime", True),
        )
        assessments.extend(result.assessments)
    _require(
        {r.assertion_id for r in assessments} == expected,
        "Full factual NI replay differs",
    )
    return tuple(assessments)


def reconstruct_role_evidence(
    *, requirement_id, proposal_id, observations, actual_executions, **inputs
):
    prepared = prepare_role_evidence(requirement_id=requirement_id, **inputs)
    _require(
        proposal_id == prepared.proposals[0].proposal_id,
        "Actual captured role proposal differs",
    )
    assessments = _replay(prepared, inputs, observations, actual_executions)
    result = legacy._bound_result(
        prepared, assessments, observations, actual_executions
    )
    return RoleEvidence(
        **{f.name: getattr(result, f.name) for f in fields(legacy.RoleEvidence)}
    )


async def assess_role_evidence(
    config, *, requirement_id, execution_capture_kind="runtime_capture", **inputs
):
    _require(
        execution_capture_kind in {"runtime_capture", "UNITONLY"}
        and (
            not inputs.get("require_runtime", True)
            or execution_capture_kind == "runtime_capture"
        ),
        "Explicit compatible captured role execution kind required",
    )
    prepared = prepare_role_evidence(requirement_id=requirement_id, **inputs)
    selected = config.model_copy(deep=True)
    observations, executions = [], []
    try:
        for kwargs in _batches(prepared, inputs):
            kwargs.pop("expected_support_metadata")
            result = await factual.assess_fact_support(
                config=selected, execution_capture_kind=execution_capture_kind, **kwargs
            )
            observations.extend(result.observations)
            executions.extend(result.actual_executions)
        return reconstruct_role_evidence(
            requirement_id=requirement_id,
            proposal_id=prepared.proposals[0].proposal_id,
            observations=tuple(observations),
            actual_executions=tuple(executions),
            **inputs,
        )
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["role_evidence_json"] = canonical(
            {
                "contract": CONTRACT + ":failure",
                "requirement_id": requirement_id,
                "prepared": prepared.record(),
                "exception_type": type(exc).__name__,
                "observations": [asdict(r) for r in observations],
                "actual_executions": [asdict(r) for r in executions],
                "current_fact_failure": exc.__dict__.get("fact_support_evidence_json"),
            }
        )
        raise
