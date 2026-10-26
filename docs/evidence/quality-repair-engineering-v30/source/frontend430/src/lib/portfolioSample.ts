import type {
  Document,
  QueryResponse,
  SourceCitation,
  AuditEvent,
  WorkflowInstance,
} from "@/types";

export const CURRENT_PASSAGE =
  "For a staging rollback, stop the deployment, select the last verified release, restore the staging snapshot, and verify the health checks before reopening traffic. Record the release and approval in the incident log.";
export const OLD_PASSAGE =
  "For a staging rollback, deploy the previous release and reopen traffic immediately. This historical procedure was superseded: it did not require snapshot restoration or health verification.";
// SHA-256 of the exact sample passages; these are synthetic source snapshots.
export const CURRENT_HASH =
  "0fdd2a9ae80f42f315a084f43dc89bc6c36be87cbb9def450250a768c6f1972c";
export const OLD_HASH =
  "db0632f2473e1761161c5826c2fbafe8b84230c98e6c110f5d0a7afaa6a0dc20";
const timestamp = "2026-10-23T12:00:00Z";
export interface SampleState {
  documents: Document[];
  queries: QueryResponse[];
  audit: AuditEvent[];
  workflows: WorkflowInstance[];
  recovered: boolean;
}
const titles = [
  "Staging rollback runbook",
  "Database recovery — procedure A",
  "Database recovery — procedure B",
  "Quarantined attachment",
  "Deployment health checks",
  "Incident communication",
  "Secret rotation",
  "Queue recovery",
  "Cache invalidation",
  "Access review",
  "Backup verification",
  "Release sign-off",
];
export function createSampleState(): SampleState {
  const documents: Document[] = titles.map((title, index) => ({
    id: index === 0 ? "sample-rollback" : `sample-doc-${index}`,
    title,
    source_type: "md",
    source_url: null,
    status: index === 3 ? "error" : "ready",
    metadata: {
      sample: true,
      visibility: index === 9 ? "private" : "public",
      ...(index === 3
        ? {
            quarantine_reason:
              "Parser could not read the attachment. The published collection is unaffected.",
          }
        : {}),
    },
    created_at: timestamp,
    updated_at: timestamp,
    version_number: index === 0 ? 2 : 1,
    content_hash: index === 0 ? CURRENT_HASH : null,
    permissions: { read: true, write: true, admin: true },
  }));
  const state: SampleState = {
    documents,
    queries: [],
    audit: [],
    workflows: [],
    recovered: false,
  };
  state.queries = [sampleQuestion("How do I roll back staging safely?", state)];
  return state;
}
export function recoverSample(state: SampleState): SampleState {
  return {
    ...state,
    recovered: true,
    documents: state.documents.map((d) =>
      d.id === "sample-doc-3" ? { ...d, status: "ready" } : d,
    ),
    audit: [...state.audit, sampleAudit("ingestion.retry", "sample-doc-3")],
  };
}
export function restoreSample(
  state: SampleState,
  id: string,
  version: number,
): SampleState {
  return {
    ...state,
    documents: state.documents.map((d) =>
      d.id === id
        ? {
            ...d,
            version_number: (d.version_number || 1) + 1,
            content_hash: version === 1 ? OLD_HASH : CURRENT_HASH,
          }
        : d,
    ),
    audit: [...state.audit, sampleAudit("document.restore", id)],
  };
}
export function sampleAudit(action: string, id: string): AuditEvent {
  return {
    actor_id: "sample-operator",
    action,
    resource_type: "document",
    resource_id: id,
    workspace_id: "sample-engineering",
    request_id: null,
    metadata: { simulated: true },
    created_at: timestamp,
  };
}
export function sampleQuestion(
  question: string,
  state: SampleState,
): QueryResponse {
  const nextId =
    state.queries.reduce(
      (largest, query) =>
        Math.max(
          largest,
          Number(/^sample-query-(\d+)$/.exec(query.id)?.[1] || 0),
        ),
      0,
    ) + 1;
  const conflict = /conflict|database.*procedure/i.test(question);
  const matched =
    /rollback|roll back|staging|health|release/i.test(question) && !conflict;
  const doc = state.documents[0];
  const old = doc.content_hash === OLD_HASH;
  const source: SourceCitation = {
    chunk_id: `sample-chunk-v${doc.version_number}`,
    document_id: doc.id,
    document_title: doc.title,
    content_preview: old ? OLD_PASSAGE : CURRENT_PASSAGE,
    quoted_text: old ? OLD_PASSAGE : CURRENT_PASSAGE,
    relevance_score: 0.89,
    citation_index: 1,
    document_version: doc.version_number,
    content_hash: old ? OLD_HASH : CURRENT_HASH,
    source_status: "current",
  };
  const reason = conflict
    ? "Two current database procedures disagree. A human must resolve the conflicting procedure group before an answer can be trusted."
    : "The authorized runbooks contain no evidence for this question. No answer has been invented.";
  return {
    id: `sample-query-${nextId}`,
    conversation_id: "sample-conversation",
    question,
    answer: matched ? `${old ? OLD_PASSAGE : CURRENT_PASSAGE} [1]` : null,
    sources: matched ? [source] : [],
    retrieval_trace: {
      query_embedding_dim: 384,
      vector_results: matched ? 4 : 0,
      keyword_results: matched ? 3 : 0,
      reranked_results: matched ? 2 : 0,
      final_context_chunks: matched ? 1 : 0,
      confidence: matched ? 0.89 : 0,
      latency_ms: 42,
      scores: [],
    },
    refused: !matched,
    confidence: matched ? 0.89 : 0,
    refusal_reason: matched ? null : reason,
    outcome: matched ? "completed" : "refused",
    execution_mode: "interactive-sample",
    evidence_access: "available",
    provenance: {
      generation_method: "simulated source extraction",
      embedding_mode: "sample",
      retrieval_method: "reranked",
      sample_timings: true,
    },
    token_usage: null,
    created_at: timestamp,
  };
}
