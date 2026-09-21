import type {
  AdminUsageSummary,
  AuditEvent,
  Document,
  DocumentListResponse,
  DocumentVersion,
  DocumentVersionDiff,
  QueryListItem,
  QueryListResponse,
  QueryResponse,
  WorkflowDefinition,
  WorkflowInstance,
  ApprovalResultResponse,
} from "@/types";

/** Stable timestamps for deterministic portfolio demos. */
const DEMO_CREATED = "2025-11-01T10:00:00.000Z";
const DEMO_UPDATED = "2025-11-15T14:30:00.000Z";

export const DEMO_DOC_REMOTE_ID = "demo-doc-remote";
export const DEMO_DOC_SECURITY_ID = "demo-doc-security";
export const DEMO_WORKFLOW_DEF_REVIEW_ID = "demo-wf-document-review";
export const DEMO_WORKFLOW_DEF_POLICY_ID = "demo-wf-policy-approval";
export const DEMO_WORKFLOW_INSTANCE_ID = "demo-wf-inst-001";

export const DEMO_DOCUMENTS: Document[] = [
  {
    id: DEMO_DOC_REMOTE_ID,
    title: "Remote Work Policy",
    source_type: "md",
    source_url: null,
    status: "ready",
    metadata: {
      file_type: "markdown",
      chunk_count: 12,
      active_workflow_id: DEMO_WORKFLOW_INSTANCE_ID,
    },
    created_at: DEMO_CREATED,
    updated_at: DEMO_UPDATED,
  },
  {
    id: DEMO_DOC_SECURITY_ID,
    title: "Security Handbook",
    source_type: "pdf",
    source_url: null,
    status: "ready",
    metadata: { file_type: "pdf", chunk_count: 24 },
    created_at: DEMO_CREATED,
    updated_at: DEMO_UPDATED,
  },
];

export const DEMO_DOCUMENT_LIST: DocumentListResponse = {
  documents: DEMO_DOCUMENTS,
  total: DEMO_DOCUMENTS.length,
  limit: 50,
  offset: 0,
};

export const DEMO_REMOTE_WORK_VERSIONS: DocumentVersion[] = [
  {
    id: "demo-ver-remote-3",
    document_id: DEMO_DOC_REMOTE_ID,
    version_number: 3,
    content_hash: "sha256:9f3a1c2b4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8",
    created_at: "2025-11-15T14:30:00.000Z",
    change_summary: "Clarified hybrid schedule and HR system recording requirement",
    chunk_count: 12,
  },
  {
    id: "demo-ver-remote-2",
    document_id: DEMO_DOC_REMOTE_ID,
    version_number: 2,
    content_hash: "sha256:8e2b0a1c3d4e5f60718293a4b5c6d7e8090a1b2c3d4e5f60718293a4b5c6d7e8",
    created_at: "2025-10-20T09:15:00.000Z",
    change_summary: "Raised remote allowance from two to three days per week",
    chunk_count: 11,
  },
  {
    id: "demo-ver-remote-1",
    document_id: DEMO_DOC_REMOTE_ID,
    version_number: 1,
    content_hash: "sha256:7d1a091b2c3d4e5f60718293a4b5c6d7e8090a1b2c3d4e5f60718293a4b5c6d7e8",
    created_at: DEMO_CREATED,
    change_summary: "Initial policy publication",
    chunk_count: 10,
  },
];

export const DEMO_SECURITY_VERSIONS: DocumentVersion[] = [
  {
    id: "demo-ver-security-1",
    document_id: DEMO_DOC_SECURITY_ID,
    version_number: 1,
    content_hash: "sha256:6c0a081a2b3c4d5e60718293a4b5c6d7e8090a1b2c3d4e5f60718293a4b5c6d7e8",
    created_at: DEMO_CREATED,
    change_summary: "Initial security handbook",
    chunk_count: 24,
  },
];

export const DEMO_VERSION_DIFF: DocumentVersionDiff = {
  line_diff:
    "- Employees may work remotely up to two days per week.\n" +
    "+ Employees may work remotely up to three days per week with manager approval.\n" +
    "+ Remote arrangements must be documented in the HR system before they begin.",
  added_lines: 2,
  removed_lines: 1,
  total_changes: 3,
  chunk_changes: [
    { chunk_index: 2, change: "updated", summary: "Hybrid schedule allowance" },
    { chunk_index: 5, change: "added", summary: "HR system recording requirement" },
  ],
  similarity_ratio: 0.87,
};

export const DEMO_WORKFLOW_DEFINITIONS: WorkflowDefinition[] = [
  {
    id: DEMO_WORKFLOW_DEF_REVIEW_ID,
    name: "Document Review",
    description:
      "Two-step review for policy documents: content review, then compliance sign-off.",
    steps_count: 2,
    owner_id: "admin",
    organization_id: "demo-org",
    is_active: true,
    is_system: true,
    created_at: DEMO_CREATED,
  },
  {
    id: DEMO_WORKFLOW_DEF_POLICY_ID,
    name: "Policy Approval",
    description:
      "Formal approval chain for HR and security policy updates before publication.",
    steps_count: 3,
    owner_id: "admin",
    organization_id: "demo-org",
    is_active: true,
    is_system: false,
    created_at: DEMO_CREATED,
  },
];

export const DEMO_WORKFLOW_INSTANCE: WorkflowInstance = {
  id: DEMO_WORKFLOW_INSTANCE_ID,
  workflow_definition_id: DEMO_WORKFLOW_DEF_REVIEW_ID,
  document_id: DEMO_DOC_REMOTE_ID,
  status: "in_progress",
  current_step_index: 1,
  triggered_by: "admin",
  trigger_type: "manual",
  metadata: { document_title: "Remote Work Policy" },
  created_at: "2025-11-16T08:00:00.000Z",
  completed_at: null,
  expires_at: "2025-11-17T08:00:00.000Z",
  steps: [
    {
      id: "demo-step-1",
      step_index: 0,
      name: "Content Review",
      description: "Verify policy language and scope",
      approver_ids: ["reviewer@company.com"],
      approver_role: "content_reviewer",
      is_parallel: false,
      min_approvals: 1,
      status: "completed",
      decisions: {
        "reviewer@company.com": { action: "approve", comment: "Language is clear and accurate." },
      },
      due_at: "2025-11-16T12:00:00.000Z",
      completed_at: "2025-11-16T10:30:00.000Z",
    },
    {
      id: "demo-step-2",
      step_index: 1,
      name: "Compliance Sign-off",
      description: "Confirm HR and legal compliance requirements are met",
      approver_ids: ["compliance@company.com"],
      approver_role: "compliance_officer",
      is_parallel: false,
      min_approvals: 1,
      status: "pending",
      decisions: null,
      due_at: "2025-11-17T08:00:00.000Z",
      completed_at: null,
    },
  ],
};

export const DEMO_ADMIN_USAGE: AdminUsageSummary = {
  total_requests: 1847,
  total_tokens: 412_350,
  input_tokens: 298_120,
  output_tokens: 114_230,
  estimated_cost: 12.47,
  average_latency_ms: 342,
  p50_latency_ms: 280,
  p95_latency_ms: 890,
  p99_latency_ms: 1240,
  error_rate: 0.018,
  cost_by_model: {
    "gpt-4o-mini": 8.92,
    "text-embedding-3-small": 3.55,
  },
  cost_by_prompt_version: {
    "grounded-v2": 10.12,
    "refusal-v1": 2.35,
  },
};

export const DEMO_AUDIT_EVENTS: AuditEvent[] = [
  {
    actor_id: "admin",
    action: "document.upload",
    resource_type: "document",
    resource_id: DEMO_DOC_REMOTE_ID,
    workspace_id: "demo-workspace",
    request_id: "req-demo-001",
    metadata: { title: "Remote Work Policy", source_type: "md" },
    created_at: DEMO_CREATED,
  },
  {
    actor_id: "admin",
    action: "query.execute",
    resource_type: "query",
    resource_id: "demo-query-remote",
    workspace_id: "demo-workspace",
    request_id: "req-demo-002",
    metadata: { question: "What is our remote work policy?", refused: false },
    created_at: "2025-11-16T09:00:00.000Z",
  },
  {
    actor_id: "compliance@company.com",
    action: "workflow.approve",
    resource_type: "workflow",
    resource_id: DEMO_WORKFLOW_INSTANCE_ID,
    workspace_id: "demo-workspace",
    request_id: "req-demo-003",
    metadata: { step: "Content Review", action: "approve" },
    created_at: "2025-11-16T10:30:00.000Z",
  },
];

export const DEMO_QUERY_HISTORY: QueryListItem[] = [
  {
    id: "demo-query-remote",
    question: "What is our remote work policy?",
    refused: false,
    confidence: 0.91,
    created_at: "2025-11-16T09:00:00.000Z",
  },
  {
    id: "demo-query-salary",
    question: "What are the salary bands?",
    refused: true,
    confidence: 0.2,
    created_at: "2025-11-16T09:05:00.000Z",
  },
];

export const DEMO_QUERY_LIST: QueryListResponse = {
  queries: DEMO_QUERY_HISTORY,
  total: DEMO_QUERY_HISTORY.length,
};

export function getDemoDocumentVersions(documentId: string): DocumentVersion[] {
  if (documentId === DEMO_DOC_REMOTE_ID) return DEMO_REMOTE_WORK_VERSIONS;
  if (documentId === DEMO_DOC_SECURITY_ID) return DEMO_SECURITY_VERSIONS;
  return [];
}

export function getDemoQueryDetail(queryId: string): QueryResponse | null {
  if (queryId === "demo-query-remote") {
    return {
      id: "demo-query-remote",
      question: "What is our remote work policy?",
      answer:
        "Employees may work remotely up to three days per week with manager " +
        "approval [1]. The arrangement must be recorded in the HR system before " +
        "it begins [2].",
      sources: [
        {
          chunk_id: "demo-chunk-1",
          document_id: DEMO_DOC_REMOTE_ID,
          document_title: "Remote Work Policy",
          content_preview:
            "Employees may work remotely up to three days per week with manager approval.",
          relevance_score: 0.94,
          citation_index: 1,
        },
        {
          chunk_id: "demo-chunk-2",
          document_id: DEMO_DOC_REMOTE_ID,
          document_title: "Remote Work Policy",
          content_preview:
            "Remote arrangements must be documented in the HR system before they begin.",
          relevance_score: 0.88,
          citation_index: 2,
        },
      ],
      retrieval_trace: {
        query_embedding_dim: 384,
        vector_results: 8,
        keyword_results: 5,
        reranked_results: 4,
        final_context_chunks: 2,
        confidence: 0.91,
        latency_ms: 142,
        scores: [
          { chunk_id: "demo-chunk-1", score: 0.94 },
          { chunk_id: "demo-chunk-2", score: 0.88 },
        ],
      },
      refused: false,
      confidence: 0.91,
      token_usage: { total_tokens: 48 },
      created_at: "2025-11-16T09:00:00.000Z",
    };
  }
  if (queryId === "demo-query-salary") {
    return {
      id: "demo-query-salary",
      question: "What are the salary bands?",
      answer:
        "I couldn't find relevant information in the demo documents for that question. " +
        "Try asking about the remote work policy or security access.",
      sources: [],
      retrieval_trace: {
        query_embedding_dim: 384,
        vector_results: 3,
        keyword_results: 1,
        reranked_results: 0,
        final_context_chunks: 0,
        confidence: 0.2,
        latency_ms: 98,
        scores: [],
      },
      refused: true,
      confidence: 0.2,
      token_usage: { total_tokens: 0 },
      created_at: "2025-11-16T09:05:00.000Z",
    };
  }
  return null;
}

export function getDemoApprovalResult(
  workflowId: string,
  stepId: string,
  action: string
): ApprovalResultResponse {
  return {
    success: true,
    workflow_id: workflowId,
    step_id: stepId,
    action,
    new_status: action === "approve" ? "completed" : "rejected",
    next_step: action === "approve" ? null : null,
    notifications_sent: ["compliance@company.com"],
  };
}
