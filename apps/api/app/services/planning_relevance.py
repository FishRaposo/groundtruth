"""Candidate-only relevance with complete immutable source/blocker ledgers.

No SQL/source/capture/read-set filtering. An explicit bridge is replayed from
actual inputs; its closed other-namespace sources may defer candidate blockers,
never resolve them or authorize source access/currentness/factual support.
"""

import json
from dataclasses import asdict, dataclass

from . import planning_declarations as source
from .planning_scope_bridge import reconstruct_scope_bridge
from .request_obligations import PartialRequest

canonical = source.canonical


@dataclass(frozen=True)
class BlockerOrigin:
    reason: str
    source: source.SourceIdentity | None
    origin: str
    unit_id: str | None = None
    declaration_id: str | None = None


@dataclass(frozen=True)
class CandidateSelection:
    inventory_sha256: str
    read_set_json: str
    scope_bridge_json: str | None
    excluded_source_ids: tuple[str, ...]
    candidate_declaration_ids: tuple[str, ...]
    candidate_unit_ids: tuple[str, ...]
    blocker_origins: tuple[BlockerOrigin, ...]
    active_blockers: tuple[BlockerOrigin, ...]
    deferred_blockers: tuple[BlockerOrigin, ...]
    procedure_obligations_json: str = "[]"

    @property
    def used(self):
        return bool(self.excluded_source_ids) or self.procedure_obligations_json != "[]"

    def record(self):
        result = json.loads(
            canonical(
                {
                    "contract": "planning-candidate-relevance-v1",
                    **asdict(self),
                    "scope": "candidate_obligation_selection_only",
                    "excluded_material": "RETAINED_UNRESOLVED_IN_FULL_INVENTORY",
                    "authority_currentness_support": "NOT_ASSESSED",
                }
            )
        )
        if self.procedure_obligations_json == "[]":
            result.pop("procedure_obligations_json")
        return result


def _window_origins(snapshot, identity, window, capture, annotation):
    units, _, blockers = source._window_inventory(
        snapshot, identity, window, capture, annotation
    )
    result = [
        BlockerOrigin(reason, identity, "source_unit", unit.id)
        for unit in units
        for reason in unit.unknowns
    ]
    owned = {row.reason for row in result}
    # New parser reasons without unit ownership remain global.
    result.extend(
        BlockerOrigin(reason, None, "unowned_window_blocker")
        for reason in blockers
        if reason not in owned
    )
    return result


def _origins(inventory, manifest, snapshots, captures):
    # Reuse actual validated parser windows; never attribute a deduplicated
    # reason to just one source by string lookup or fabricate a small universe.
    by_id, validated = source._inputs(manifest, snapshots, captures)
    result = [
        BlockerOrigin(reason, None, "outer_authority")
        for reason in (
            "planning_universe_requires_independent_authorization_and_currentness",
            "source_authority_and_evidence_not_assessed",
        )
    ]
    if manifest.selection_mode != "bounded_authorized_scan":
        result.append(
            BlockerOrigin(
                "ranked_or_unknown_universe_cannot_establish_closure", None, "universe"
            )
        )
    for identity in inventory.read_set.missing_publications:
        result.append(
            BlockerOrigin(
                "uninspectable_selected_publication", identity, "missing_publication"
            )
        )
    for identity in manifest.publications:
        sid = identity.document_id
        if sid not in by_id:
            continue
        windows = validated[sid]
        if len(windows) > 1:
            result.append(
                BlockerOrigin(
                    "cross_window_semantics_not_established",
                    identity,
                    "capture_windows",
                )
            )
        for window, capture, annotation in windows:
            result.extend(
                _window_origins(by_id[sid], identity, window, capture, annotation)
            )
    for row in inventory.declarations:
        if row.kind == "external_instruction_target":
            result.append(
                BlockerOrigin(
                    "external_instruction_targets_initially_unresolved",
                    row.source,
                    "external_reference",
                    row.unit_id,
                    row.id,
                )
            )
    represented = {row.reason for row in result}
    result.extend(
        BlockerOrigin(reason, None, "unowned_inventory_blocker")
        for reason in inventory.blockers
        if reason not in represented
    )
    return tuple(result)


def reconstruct_candidate_selection(
    partial: PartialRequest, manifest, snapshots, captures, *, scope_bridge_record=None
):
    if type(partial) is not PartialRequest:
        raise ValueError("Typed actual partial request required")
    inventory = source.declaration_inventory(manifest, snapshots, captures)
    excluded = ()
    bridge_json = None
    if scope_bridge_record is not None:
        actual = reconstruct_scope_bridge(
            partial,
            manifest,
            snapshots,
            captures,
            procedure_productions="procedure_production_obligations"
            in scope_bridge_record,
        )
        if type(scope_bridge_record) is not dict or canonical(
            scope_bridge_record
        ) != canonical(actual):
            raise ValueError(
                "Candidate relevance bridge differs from actual full inputs"
            )
        if canonical(actual["read_set"]) != canonical(inventory.read_set.record()):
            raise ValueError("Candidate relevance/full declaration read sets differ")
        excluded = tuple(actual["excluded"])
        bridge_json = canonical(actual)
    origins = _origins(inventory, manifest, snapshots, captures)
    from .staged_production_obligations import source_ownership

    obligations = (
        source_ownership(partial, manifest, snapshots, captures, inventory)
        if scope_bridge_record is not None
        and "procedure_production_obligations" in scope_bridge_record
        else ()
    )
    owned = {row["unit_id"] for row in obligations}

    def retained(row):
        return (
            row.source is None or row.source.document_id not in excluded
        ) and row.unit_id not in owned

    return CandidateSelection(
        source.digest(inventory.record()),
        canonical(inventory.read_set.record()),
        bridge_json,
        excluded,
        tuple(
            row.id
            for row in inventory.declarations
            if row.source.document_id not in excluded
        ),
        tuple(
            unit.id
            for unit in inventory.units
            if unit.source.document_id not in excluded and unit.id not in owned
        ),
        origins,
        tuple(row for row in origins if retained(row)),
        tuple(row for row in origins if not retained(row)),
        canonical(obligations),
    )


def validate_candidate_selection(
    record, partial, manifest, snapshots, captures, *, scope_bridge_record=None
):
    try:
        source._native(record)
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_candidate_selection(
                partial,
                manifest,
                snapshots,
                captures,
                scope_bridge_record=scope_bridge_record,
            ).record()
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        RecursionError,
    ):
        return False
