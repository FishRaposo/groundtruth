# Operator shared-core v1.3.0 vendoring provenance

Date: 2026-08-15

## Source

| Field | Value |
|---|---|
| Repository | `FishRaposo/operator-shared-core` |
| Release | `v1.3.0` |
| Commit | `dbf276a7708da65b55e1f10b35af634b300d1f07` |
| License | MIT, copyright 2026 Operator Systems |
| Destination | `apps/api/app/internal/vendor_core/` |

The exact upstream license is shipped at
`apps/api/app/internal/vendor_core/LICENSE` and summarized in
`THIRD_PARTY_NOTICES.md`.

## Vendored closure

The retained modules are `clients`, `config`, `database`, `docparse`, `embeddings`,
`errors`, `evaljudge`, `llmmetrics`, `logging`, `pricing`, and `tasks`, plus package
metadata and license. This is the proven transitive closure GroundTruth uses for
configuration, DB/session helpers, parsing primitives, deterministic evaluation and
embeddings, errors/logging, task setup, and metrics/pricing support.

## Allowed modifications

- Rewrite imports from the upstream package namespace to
  `app.internal.vendor_core`.
- Add provenance docstrings/comments that do not alter behavior.

No external `shared_core` package is installed or imported by the default project.
GroundTruth's own routes, schemas, status codes, SSE vocabulary, models/Alembic base,
retrieval/refusal/citation rules, parser registry, and metrics remain authoritative.

## Verification gates

- `scripts/check_forbidden_dependencies.py` rejects actionable external package/Git/
  sibling references.
- `python -m build apps/api` builds from repository-local sources.
- `scripts/check_wheel_contents.py` verifies the vendored closure and license ship.
- `scripts/verify_isolated_wheel.py` installs/imports the wheel without a sibling
  checkout or external package.

Task 1 verified the source checkout and license against the pinned commit, recorded a
54-test focused pass, built `groundtruth-0.1.0-py3-none-any.whl`, verified its contents,
and imported it in a fresh virtual environment. PostgreSQL/Redis and Docker remained
explicit integration boundaries rather than implied by those package checks.
