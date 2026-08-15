# Design decisions

## Self-contain the compatibility closure

GroundTruth previously imported a sibling/Git-installed `shared_core` package. The
required v1.3.0 closure is now pinned at commit
`dbf276a7708da65b55e1f10b35af634b300d1f07`, vendored under
`app.internal.vendor_core`, and included in the wheel with its MIT license. Imports
were rewritten only for the internal namespace.

This removes installation-order and sibling-checkout risk while preserving upstream
provenance. The forbidden scan, wheel-content check, and isolated-wheel import test
enforce the decision. See [vendoring provenance](migrations/2026-08-15-operator-shared-core-v1.3.0-vendoring.md).

## Keep GroundTruth's domain contracts

The compatibility layer supplies infrastructure and narrow deterministic primitives;
GroundTruth remains authoritative for routes, response keys, status codes, SSE event
vocabulary, retrieval/refusal/citation semantics, parser registry, models, migrations,
and `groundtruth_*` metrics.

GroundTruth keeps its own `DeclarativeBase` because the models and Alembic history are
authored against that metadata. Migration 003 does not add or drop
`documents.content_hash`, which already belongs to migration 001.

## Preserve score-sensitive behavior

New provider and evaluation capabilities are additive. Existing retrieval score
formulae and citation assembly stay golden-pinned. Optional cross-encoder ranking uses
only local cached weights and falls back to deterministic lexical Jaccard ranking.
No model download occurs in default demo/tests/CI.

## Keep legacy interfaces while adding typed providers

Generation and embedding provider protocols expose structured provider/model/usage/
fallback metadata. Existing service return shapes, offline behavior, query response
fields, and SSE event types remain compatible. Provider-backed OpenAI paths are
bounded and optional.

## Make conversation memory explicit

Memory is disabled by default. A request must include a `conversation_id` and select
the `recent` policy; bounded newest-complete-turn selection then feeds the same context
to normal and streaming generation. This prevents implicit cross-request state from
changing legacy behavior.

## Extend ingestion through the existing pipeline

CSV/TSV and optional XLSX/PPTX adapters join the existing parser registry and reuse
normalization, hash/dedup, entity metadata, chunking, quarantine, and reindex behavior.
OCR remains opt-in. There is no second ingestion gateway, quarantine service, or
KnowledgeOps service topology.

## Treat versions and workflow state as auditable records

Document snapshots are immutable; restore creates a new version. Workflow state is
workspace/owner scoped, approval/rejection routing is explicit, and status events are
ordered. The notification outbox redacts payloads and defaults to memory/log sinks;
SMTP and webhooks are adapters, not hosted services.

## Separate default and integration gates

Default CI is credential-free and sibling-free. It runs API tests, Ruff, Pyright,
package/evidence checks, locked frontend tests/lint/build, Chromium Playwright, and
Docker builds. PostgreSQL/Redis tests are manual opt-in because a green offline gate
must not imply live-infrastructure verification.

## Explicit non-goals

SAML/SSO, hosted/team workflows, hosted notification services, mandatory
infrastructure, cloud object storage, hosted scheduling, database row-level security,
and a hosted tenancy control plane are deferred.
