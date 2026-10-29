"""Runtime curated inspection; pure proof authorities have no service imports."""

from __future__ import annotations

import json
from dataclasses import asdict

from app.services.curated_conflict_proof import (
    PROCEDURE_CONTRACT as CONTRACT,
)
from app.services.curated_conflict_proof import (
    SelectedQuoteScopeUnresolved,
    canonical_claims,
    fact_claim,
    fact_inputs,
    fact_outcome,
    inspection_identity,
    quote_procedure_outcome,
    quote_scope_input,
    quote_scope_row,
    scope_input,
    selected_quote_scope,
)
from app.services.curated_conflict_proof import (
    procedure_outcome as _outcome,
)
from app.services.curated_conflict_proof import (
    reconstruct_procedure_group as reconstruct_group,
)
from app.services.curated_conflict_proof import (
    scope_row as _row,
)

__all__ = [
    "CONTRACT",
    "reconstruct_group",
    "scope_input",
    "inspect_group",
    "inspect_fact_group",
]


async def _resolve_sources(
    db, request, principal, members, inspected, contexts, origin
):
    from app.services.procedure_evidence import resolve_version
    from app.services.requirement_answers import source_identity

    by_document = {}
    for member in sorted(
        members, key=lambda c: (str(c.document_id), c.chunk_index, str(c.id))
    ):
        by_document.setdefault(str(member.document_id), member)
    sources = []
    for member in by_document.values():
        source = await resolve_version(db, principal, request, member, inspected)
        for item in source.chunks:
            inspected[item.chunk.id] = item.chunk
        contexts.append(
            dict(
                **source.identity,
                origin=origin,
                sources=[source_identity(i.chunk) for i in source.chunks],
            )
        )
        sources.append(source)
    identities = sorted(
        [
            inspection_identity(part.chunk)
            for source in sources
            for part in source.chunks
        ],
        key=lambda row: row["chunk_id"],
    )
    return sources, identities


async def inspect_group(
    db,
    request,
    principal,
    current,
    config,
    members,
    truncated,
    witnesses,
    inspected,
    contexts,
):
    from app.evidence_policy import resolve_evidence_policy
    from app.services.answer_support import (
        SupportInputBudgetExceeded,
        SupportPair,
        support_service,
    )
    from app.services.procedure_evidence import ProcedureRejected

    if witnesses and resolve_evidence_policy(config).procedure_scope_profile in {
        "activity_quote_v1",
        "activity_quote_v2",
    }:
        return await _inspect_quote_group(
            db,
            request,
            principal,
            current,
            config,
            members,
            truncated,
            witnesses,
            inspected,
            contexts,
        )

    settings = {"support": support_service.metadata(config)}
    rows = []
    identities = sorted(
        [inspection_identity(m) for m in members], key=lambda r: r["chunk_id"]
    )
    try:
        sources, identities = await _resolve_sources(
            db,
            request,
            principal,
            members,
            inspected,
            contexts,
            "curated-procedure-inspection",
        )
        for source in sources:
            inputs = scope_input(current, source.identity, source.body)
            decisions = await support_service.assess(
                [
                    SupportPair(
                        inputs["premise"],
                        inputs["hypothesis"],
                        current.id,
                        source.identity["document_id"],
                    )
                ],
                config=config,
            )
            if len(decisions) != 1:
                raise RuntimeError(
                    "Curated scope classifier returned incomplete decisions"
                )
            rows.append(
                _row(inputs, json.loads(json.dumps(asdict(decisions[0]))), settings)
            )
    except (ProcedureRejected, SupportInputBudgetExceeded) as exc:
        rows.append(
            {
                "scope_excluded": False,
                "reason": str(exc),
                "unresolved_sources": identities,
            }
        )
    return _outcome(current, rows, identities, truncated, bool(witnesses))


async def _inspect_quote_group(
    db,
    request,
    principal,
    current,
    config,
    members,
    truncated,
    witnesses,
    inspected,
    contexts,
):
    from app.services.answer_support import (
        SupportInputBudgetExceeded,
        SupportPair,
        support_service,
    )
    from app.services.procedure_evidence import ProcedureRejected, resolve_version

    settings = {"support": support_service.metadata(config)}
    rows, basis = [], None
    identities = sorted(
        [inspection_identity(m) for m in members], key=lambda r: r["chunk_id"]
    )
    try:
        sources, identities = await _resolve_sources(
            db,
            request,
            principal,
            members,
            inspected,
            contexts,
            "curated-procedure-inspection",
        )
        snapshots, inventories = {}, []
        for witness in witnesses:
            source = await resolve_version(
                db, principal, request, witness.chunk, inspected
            )
            snapshots[source.identity["document_id"]] = dict(
                source.identity, body=source.body
            )
            inventories.append(witness.completeness["inventory"])
        from app.evidence_policy import resolve_evidence_policy

        basis = selected_quote_scope(
            current,
            inventories,
            snapshots,
            evidence_profile=resolve_evidence_policy(config).record(),
        )
        for source in sources:
            inputs = quote_scope_input(current, source.identity, source.body, basis)
            decisions = await support_service.assess(
                [
                    SupportPair(
                        inputs["premise"],
                        inputs["hypothesis"],
                        current.id,
                        source.identity["document_id"],
                    )
                ],
                config=config,
            )
            if len(decisions) != 1:
                raise RuntimeError(
                    "Curated scope classifier returned incomplete decisions"
                )
            rows.append(quote_scope_row(inputs, asdict(decisions[0]), settings))
    except (
        ProcedureRejected,
        SupportInputBudgetExceeded,
        SelectedQuoteScopeUnresolved,
    ) as exc:
        rows.append(
            {
                "scope_excluded": False,
                "reason": str(exc),
                "unresolved_sources": identities,
            }
        )
    if basis is not None:
        basis = dict(
            basis, body=snapshots[basis["source_identity"]["document_id"]]["body"]
        )
    return quote_procedure_outcome(current, rows, identities, truncated, basis)


async def capture_fact_source_windows(body, config, cache):
    """Actual configured parser boundary; pure replay never imports this path."""
    from app.services.linguistic_procedure_runtime import _windows

    return await _windows(body, config, cache)


async def inspect_fact_group(
    db,
    request,
    principal,
    current,
    config,
    members,
    truncated,
    witnesses,
    inspected,
    contexts,
    *,
    source_window_cache=None,
):
    from app.services.answer_support import (
        SupportInputBudgetExceeded,
        SupportPair,
        support_service,
    )
    from app.services.curated_conflict_proof import FACT_CONTRACT
    from app.services.linguistic_procedure_runtime import SourceWindowRejected
    from app.services.procedure_evidence import ProcedureRejected
    from app.services.requirement_answers import source_identity

    claims = canonical_claims(
        [
            fact_claim(
                source_identity(w.chunk), w.span.model_dump(), w.value, w.hypothesis
            )
            for w in witnesses
        ]
    )
    try:
        sources, identities = await _resolve_sources(
            db,
            request,
            principal,
            members,
            inspected,
            contexts,
            "curated-factual-inspection",
        )
        snapshots = {
            s.identity["document_id"]: dict(
                **s.identity, body=s.body, metadata=s.metadata
            )
            for s in sources
        }
        cache = {} if source_window_cache is None else source_window_cache
        captures = {
            identifier: await capture_fact_source_windows(
                snapshot["body"], config, cache
            )
            for identifier, snapshot in snapshots.items()
        }
        scopes, claims, inputs = fact_inputs(
            current, snapshots, identities, claims, captures
        )
        decisions = (
            await support_service.assess(
                [
                    SupportPair(
                        row["premise"],
                        row["hypothesis"],
                        current.id,
                        row["source_identity"]["document_id"],
                    )
                    for row in inputs
                ],
                config=config,
            )
            if inputs
            else []
        )
        if len(decisions) != len(inputs):
            raise RuntimeError("Curated fact classifier returned incomplete decisions")
        rows = [
            {**row, "assessment": json.loads(json.dumps(asdict(d)))}
            for row, d in zip(inputs, decisions, strict=True)
        ]
        return fact_outcome(current, identities, scopes, claims, rows, truncated)
    except (ProcedureRejected, SupportInputBudgetExceeded, SourceWindowRejected) as exc:
        return {
            "requirement_id": current.id,
            "inspection_method": FACT_CONTRACT,
            "inspection_sources": sorted(
                [inspection_identity(m) for m in members], key=lambda r: r["chunk_id"]
            ),
            "inspection_complete": False,
            "truncated": truncated,
            "relevant": bool(witnesses),
            "outcome": "comparison_unconfirmed",
            "reason": str(exc),
        }
