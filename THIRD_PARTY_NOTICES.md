# Third-party notices

## Internally vendored operator core subset

GroundTruth contains a narrow, internally namespaced copy of the modules it
uses from `FishRaposo/operator-shared-core` v1.3.0. The source is pinned to
commit `dbf276a7708da65b55e1f10b35af634b300d1f07` and lives under
`apps/api/app/internal/vendor_core/`.

The vendored closure is limited to configuration, database helpers, document
parsing, deterministic embeddings and judges, errors, logging, LLM metrics and
pricing, Celery setup, and the HTTP client required by the embedding gateway.
Its imports are rewritten to the GroundTruth-owned namespace. The rest of
GroundTruth neither installs nor imports an external `shared_core` package.

Those modules remain under their original MIT license. The complete upstream
license text ships beside the vendored source at
[`apps/api/app/internal/vendor_core/LICENSE`](apps/api/app/internal/vendor_core/LICENSE),
including the `Copyright (c) 2026 Operator Systems` notice, grant, conditions,
and warranty disclaimer. GroundTruth itself is distributed under the MIT license
in [`LICENSE`](LICENSE).
