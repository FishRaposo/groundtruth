"""Generate GroundTruth's deterministic, credential-free portfolio evidence bundle."""

# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.db.session import Base  # noqa: E402
from app.internal.provider_contracts import OfflineEmbeddingProvider  # noqa: E402
from app.middleware.rate_limit import RateLimitBuckets  # noqa: E402
from app.models.document import Document, DocumentStatus, SourceType  # noqa: E402
from app.models.document.workflow import ApprovalAction, WorkflowStep  # noqa: E402
from app.models.query import SourceCitation  # noqa: E402
from app.services.audit import AuditTrail  # noqa: E402
from app.services.citation import CitationService  # noqa: E402
from app.services.conversation.memory import select_bounded_history  # noqa: E402
from app.services.cost_tracking import CostTracker  # noqa: E402
from app.services.document.processing.approval import (  # noqa: E402
    ApprovalWorkflowEngine,
    WorkflowStatus,
)
from app.services.document.versioning import DocumentVersionManager  # noqa: E402
from app.services.document_intelligence import (  # noqa: E402
    content_hash,
    deduplicate_chunks,
    normalize_content,
)
from app.services.notifications import (  # noqa: E402
    InMemoryNotificationSink,
    NotificationOutbox,
)
from app.services.refusal import REFUSAL_MESSAGES, RefusalService  # noqa: E402
from app.services.reranking.colbert import CrossEncoderReranker  # noqa: E402
from app.services.retrieval.bm25 import HybridRetriever  # noqa: E402
from app.services.workflow_events import WorkflowEventBroker  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "portfolio" / "groundtruth-evidence"
NORMALIZED_TIMESTAMP = "<normalized-timestamp>"
NORMALIZED_ID = "<normalized-id>"
SECRET_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "cookie",
    "openai_api_key",
    "password",
    "secret",
    "token",
}


class EvidenceError(RuntimeError):
    """Raised when a portfolio evidence capability check fails."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reproducibility_hash(payloads: dict[str, bytes]) -> str:
    """Hash the canonical machine and human reports with domain separation."""
    digest = hashlib.sha256()
    for name in ("report.json", "report.md"):
        data = payloads[name]
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _normalized_path(value: str) -> str:
    try:
        relative = Path(value).resolve().relative_to(REPO_ROOT.resolve())
    except (OSError, ValueError):
        return "<normalized-path>"
    return "<repo>/" + relative.as_posix()


def _is_secret_key(key: str) -> bool:
    segments = set(key.split("_"))
    return (
        key in SECRET_KEYS
        or bool(segments & {"password", "secret", "token"})
        or key.endswith("_api_key")
        or key.startswith("api_key_")
    )


def _is_generated_id_key(key: str) -> bool:
    return key == "id" or key.endswith(("_id", "_uuid"))


def normalize_evidence(value: Any, key: str | None = None) -> Any:  # noqa: C901
    """Recursively replace volatile, machine-specific, and sensitive evidence."""
    normalized_key = (key or "").lower().replace("-", "_")
    if _is_secret_key(normalized_key):
        return "[REDACTED]"
    if normalized_key.startswith("provider_") and normalized_key.endswith(
        ("output", "response", "result")
    ):
        return "<normalized-provider-output>"
    if normalized_key == "timestamp" or normalized_key.endswith("_at"):
        return NORMALIZED_TIMESTAMP
    if normalized_key.endswith("duration_ms") or normalized_key == "latency_ms":
        return 0
    if _is_generated_id_key(normalized_key):
        return NORMALIZED_ID
    if normalized_key == "output_path" and isinstance(value, str):
        return "<normalized-path>"
    if (normalized_key == "path" or normalized_key.endswith("_path")) and isinstance(
        value, str
    ):
        return _normalized_path(value)
    if normalized_key == "environment" and isinstance(value, dict):
        return {
            str(child_key): (
                "[REDACTED]"
                if _is_secret_key(str(child_key).lower())
                else "<normalized-env>"
            )
            for child_key in sorted(value)
        }
    if isinstance(value, dict):
        is_named_check = {"id", "status", "evidence"}.issubset(value)
        return {
            str(child_key): (
                child
                if is_named_check and str(child_key) == "id"
                else normalize_evidence(child, str(child_key))
            )
            for child_key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_evidence(item) for item in value]
    if isinstance(value, Path):
        return _normalized_path(str(value))
    return value


def _check(check_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "evidence": evidence}


async def _exercise_approval_workflow() -> dict[str, Any]:
    """Run one real approval transition with local SQLite and memory notifications."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            document = Document(
                # SQLite gives its PostgreSQL ``UUID`` spelling numeric affinity;
                # include hex letters so the fixed fixture remains text-backed.
                id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                title="Portfolio policy",
                source_type=SourceType.TEXT,
                status=DocumentStatus.READY,
                workspace_id="portfolio",
            )
            session.add(document)
            await session.commit()

            sink = InMemoryNotificationSink()
            workflow_engine = ApprovalWorkflowEngine(
                session,
                outbox=NotificationOutbox([sink]),
                event_broker=WorkflowEventBroker(),
            )
            definition = await workflow_engine.create_workflow_definition(
                name="Portfolio approval",
                description="Offline evidence",
                steps=[
                    {
                        "name": "review",
                        "approvers": ["reviewer"],
                        "approval_route": "end",
                    }
                ],
                owner_id="portfolio-owner",
                workspace_id="portfolio",
            )
            workflow = await workflow_engine.start_workflow(
                str(definition.id),
                str(document.id),
                "portfolio-owner",
                workspace_id="portfolio",
            )
            step_result = await session.execute(
                select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)
            )
            step = step_result.scalar_one()
            result = await workflow_engine.process_approval(
                str(workflow.id),
                str(step.id),
                "reviewer",
                ApprovalAction.APPROVE,
                workspace_id="portfolio",
            )
            if (
                not result.success
                or result.new_status != WorkflowStatus.APPROVED.value
                or result.notifications_sent != ["owner:portfolio-owner"]
                or len(sink.delivered) != 2
            ):
                raise EvidenceError("approval workflow check failed")
            return {
                "action": ApprovalAction.APPROVE.value,
                "engine": "ApprovalWorkflowEngine.process_approval",
                "new_status": result.new_status,
                "notifications_sent": len(result.notifications_sent),
                "success": result.success,
            }
    finally:
        await engine.dispose()


async def build_report(  # noqa: C901
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Exercise the portfolio-critical contracts and return normalized evidence."""
    checks: list[dict[str, Any]] = []

    raw_lines = [
        "  Remote work is allowed three days.  ",
        "Security keys rotate quarterly.\n",
    ]
    normalized_lines = [normalize_content(line) for line in raw_lines]
    chunks = deduplicate_chunks(
        [normalized_lines[0], normalized_lines[1], raw_lines[0]]
    )
    digest = content_hash("\n".join(normalized_lines))
    if len(chunks) != 2 or len(digest) != 64:
        raise EvidenceError("ingestion/deduplication check failed")
    checks.append(
        _check(
            "ingestion-deduplication",
            {
                "content_hash_algorithm": "sha256",
                "input_chunks": 3,
                "normalized_lines": len(normalized_lines),
                "unique_chunks": len(chunks),
            },
        )
    )

    hybrid = HybridRetriever(bm25_weight=0.3, vector_weight=0.7)
    fused = hybrid.fuse_scores(
        [("remote-work-policy", 1.0), ("security-handbook", 0.5)],
        [("remote-work-policy", 0.9), ("security-handbook", 0.8)],
        top_k=2,
    )
    if fused[0][0] != "remote-work-policy":
        raise EvidenceError("hybrid retrieval check failed")
    checks.append(
        _check(
            "hybrid-retrieval",
            {
                "fusion": "weighted-bm25-vector",
                "top_document": fused[0][0],
                "top_score": round(fused[0][1], 6),
            },
        )
    )

    refused, refusal_message = RefusalService().should_refuse(
        "What is the parental leave policy?", [], confidence=0.0
    )
    if not refused or refusal_message != REFUSAL_MESSAGES["no_results"]:
        raise EvidenceError("refusal check failed")
    checks.append(
        _check("graceful-refusal", {"reason": "no-results", "refused": refused})
    )

    citation = SourceCitation(
        chunk_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        document_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        document_title="Remote Work Policy",
        content_preview="Remote work is allowed three days.",
        relevance_score=1.0,
        citation_index=1,
    )
    citations_valid = CitationService().validate_citations(
        "Remote work is allowed three days [1].", [citation]
    )
    if not citations_valid:
        raise EvidenceError("citation check failed")
    checks.append(
        _check(
            "citations",
            {"citation_indices": [citation.citation_index], "valid": citations_valid},
        )
    )

    tracker = CostTracker()
    tracker.record(
        model="offline-portfolio",
        prompt_tokens=50,
        completion_tokens=25,
        latency_ms=123.4,
        workspace="portfolio",
        cost_usd=0.000042,
    )
    cost = tracker.summary("portfolio")
    if cost["total_requests"] != 1 or cost["total_tokens"] != 75:
        raise EvidenceError("cost tracking check failed")
    checks.append(
        _check(
            "workspace-cost-tracking",
            {
                "estimated_cost_usd": cost["estimated_cost"],
                "total_requests": cost["total_requests"],
                "total_tokens": cost["total_tokens"],
                "workspace": "portfolio",
            },
        )
    )

    history = [
        {"role": "user", "content": "old question with four words"},
        {"role": "assistant", "content": "old answer with four words"},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "new answer"},
    ]
    selected = select_bounded_history(history, max_tokens=4)
    if selected != history[-2:]:
        raise EvidenceError("conversation memory check failed")
    checks.append(
        _check(
            "bounded-conversation-memory",
            {
                "max_tokens": 4,
                "roles": [message["role"] for message in selected],
                "selected_messages": len(selected),
            },
        )
    )

    version_manager = DocumentVersionManager(None)  # type: ignore[arg-type]
    diff = version_manager.compute_diff("policy\nold", "policy\nnew")
    if diff["total_changes"] != 2:
        raise EvidenceError("document versioning check failed")
    checks.append(
        _check(
            "document-versioning",
            {
                "added_lines": diff["added_lines"],
                "removed_lines": diff["removed_lines"],
                "total_changes": diff["total_changes"],
            },
        )
    )

    checks.append(_check("approval-workflow", await _exercise_approval_workflow()))

    audit = await AuditTrail().record(
        actor_id="portfolio-owner",
        action="create",
        resource_type="api_key",
        workspace_id="portfolio",
        metadata={"secret": "portfolio-secret"},
    )
    if audit.metadata["secret"] != "[REDACTED]":
        raise EvidenceError("audit redaction check failed")
    checks.append(
        _check(
            "redacted-audit",
            {
                "created_at": audit.created_at.isoformat(),
                "secret": audit.metadata["secret"],
                "workspace": audit.workspace_id,
            },
        )
    )

    buckets = RateLimitBuckets(window_seconds=60)
    first = buckets.check("portfolio", "key-a", limit=1, now=0)
    second = buckets.check("portfolio", "key-a", limit=1, now=1)
    isolated = buckets.check("other", "key-a", limit=1, now=1)
    if not first.allowed or second.allowed or not isolated.allowed:
        raise EvidenceError("rate limit check failed")
    checks.append(
        _check(
            "workspace-rate-limits",
            {
                "first_allowed": first.allowed,
                "retry_after": second.retry_after,
                "second_allowed": second.allowed,
                "workspace_isolated": isolated.allowed,
            },
        )
    )

    embedding = await OfflineEmbeddingProvider(dimensions=8).embed(["stable evidence"])
    reranker = CrossEncoderReranker(enabled=False)
    reranked = await reranker.rerank(
        "remote work policy",
        [("office catering", "catering"), ("remote work policy", "policy")],
    )
    if embedding.fallback_path != "hash" or reranked[0][0] != "policy":
        raise EvidenceError("offline fallback check failed")
    checks.append(
        _check(
            "optional-offline-fallbacks",
            {
                "embedding_fallback": embedding.fallback_path,
                "embedding_provider": embedding.provider,
                "reranker_method": reranker.last_method,
                "top_document": reranked[0][0],
            },
        )
    )

    frontend_fixtures = {
        "admin-audit": REPO_ROOT / "apps/web/tests/components/AdminConsole.test.tsx",
        "citations": REPO_ROOT / "apps/web/tests/components/SourceCitation.test.tsx",
        "document-versioning": REPO_ROOT
        / "apps/web/tests/components/DocumentVersionPanel.test.tsx",
        "offline-demo": REPO_ROOT / "apps/web/tests/lib/demoMode.test.ts",
        "retrieval-trace": REPO_ROOT
        / "apps/web/tests/components/RetrievalTrace.test.tsx",
        "workflow-stream": REPO_ROOT
        / "apps/web/tests/components/WorkflowStatusStream.test.tsx",
    }
    missing = [name for name, path in frontend_fixtures.items() if not path.is_file()]
    if missing:
        raise EvidenceError(f"frontend fixture check failed: {', '.join(missing)}")
    checks.append(
        _check(
            "frontend-fixture-summary",
            {
                "fixture_files": len(frontend_fixtures),
                "surfaces": sorted(frontend_fixtures),
            },
        )
    )

    raw_report = {
        "schema_version": 1,
        "project": {"name": "GroundTruth", "proof": "offline-portfolio-evidence"},
        "execution": {
            "credentials": "not-required",
            "duration_ms": 1.0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "deterministic-offline",
            "network": "disabled",
            "output_path": str(output_dir),
        },
        "normalization": {
            "environment": "stable-markers",
            "generated_ids": "stable-markers",
            "paths": "repo-relative",
            "provider_outputs": "stable-markers",
            "secrets": "redacted",
            "timestamps_and_durations": "stable-markers",
        },
        "summary": {"failed": 0, "passed": len(checks), "total": len(checks)},
        "checks": checks,
    }
    return normalize_evidence(raw_report)


def render_markdown(report: dict[str, Any]) -> str:
    """Render a stable human-readable companion to the JSON report."""
    lines = [
        "# GroundTruth portfolio evidence",
        "",
        (
            "Deterministic offline proof. No network, credentials, "
            "or live services required."
        ),
        "",
        (
            f"Result: {report['summary']['passed']}/{report['summary']['total']} "
            "checks passed."
        ),
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    lines.extend(f"| {check['id']} | {check['status']} |" for check in report["checks"])
    lines.extend(
        [
            "",
            "Volatile timestamps, generated IDs, paths, durations, environment values,",
            "secrets, and provider outputs are normalized before hashing.",
            "",
        ]
    )
    return "\n".join(lines)


async def generate_bundle(output_dir: Path) -> str:
    """Generate all evidence files and return the reproducibility hash."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report = await build_report(output_dir)
    report_bytes = _json_bytes(report)
    report_md_bytes = render_markdown(report).encode("utf-8")
    payloads = {"report.json": report_bytes, "report.md": report_md_bytes}
    bundle_hash = reproducibility_hash(payloads)
    manifest = {
        "artifact": "groundtruth-evidence",
        "files": {
            name: {"bytes": len(data), "sha256": _sha256(data)}
            for name, data in sorted(payloads.items())
        },
        "reproducibility_hash": bundle_hash,
        "schema_version": 1,
    }
    manifest_bytes = _json_bytes(manifest)
    payloads["manifest.json"] = manifest_bytes

    for name, data in payloads.items():
        (output_dir / name).write_bytes(data)
    checksum_names = sorted(payloads)
    checksum_text = "".join(
        f"{_sha256(payloads[name])}  {name}\n" for name in checksum_names
    )
    (output_dir / "checksums.sha256").write_bytes(checksum_text.encode("utf-8"))
    return bundle_hash


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic offline GroundTruth portfolio evidence."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        digest = asyncio.run(generate_bundle(args.output_dir.resolve()))
    except (EvidenceError, OSError, ValueError) as exc:
        print(f"evidence generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"generated GroundTruth evidence: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
