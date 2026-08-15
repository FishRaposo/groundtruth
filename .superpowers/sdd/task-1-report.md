# Task 1 report — baseline contracts, vendored core, and package alignment

Status: **DONE_WITH_CONCERNS**

## Delivered

- Vendored the GroundTruth closure from `FishRaposo/operator-shared-core` 1.3.0,
  commit `dbf276a7708da65b55e1f10b35af634b300d1f07`, under
  `apps/api/app/internal/vendor_core/`.
- Verified each vendored module against that commit. Differences are limited to
  the required internal-namespace import rewrites and explanatory docstrings;
  the implementation remains the pinned upstream code.
- Rewrote active application/demo imports to the internal namespace while
  preserving route, schema, status-code, SSE, retrieval, refusal, citation, and
  offline-fallback contracts.
- Removed the Git/sibling `shared_core` install path from package metadata,
  Docker, Makefile, and CI.
- Split parser, PostgreSQL/pgvector, Redis, and model-backed embedding
  dependencies into explicit extras. The default wheel imports in SQLite mode
  without those integrations; NumPy is loaded only when model reranking runs.
- Added root and wheel-distributed MIT licensing, the full upstream MIT license
  beside the vendored source, and `THIRD_PARTY_NOTICES.md` with source/version/
  commit attribution.
- Added forbidden-dependency, wheel-content, and isolated-wheel import checks.
  Default CI runs those checks; PostgreSQL/Redis integration CI is an explicit
  `workflow_dispatch` opt-in.

## Verification evidence

- Red contract run: `5 failed` before the remaining package fixes.
- Green package-contract run: `5 passed`.
- Focused vendor/import/package suite:
  `54 passed in 1.50s`.
- Focused Ruff lint + format: `All checks passed`; `31 files already formatted`.
- Forbidden dependency scan:
  `No actionable external shared-core dependencies found.`
- Wheel build: `Successfully built groundtruth-0.1.0-py3-none-any.whl`.
- Wheel contents:
  `Wheel vendor closure verified: groundtruth-0.1.0-py3-none-any.whl`.
- Fresh virtualenv install/import:
  `Isolated wheel imports verified without an external shared_core package.`
- Upstream source checkout resolved exactly to
  `dbf276a7708da65b55e1f10b35af634b300d1f07`; upstream package metadata reports
  version `1.3.0` and the copied MIT license matches its `LICENSE`.

## Concerns / environment limits

- Local verification used Python 3.14.6; CI remains pinned to Python 3.11.
- PostgreSQL/Redis integration tests and Docker builds were not run locally.
  Those integrations are intentionally opt-in and retain dedicated CI coverage.
- The repository-wide `ruff format --check` surfaces pre-existing formatting/
  line-ending drift in files outside this slice. The Task 1 surface itself is
  format-clean, and repository-wide `ruff check` is clean.
