export interface Document {
  id: string;
  title: string;
  source_type: "pdf" | "md" | "html" | "docx";
  source_url: string | null;
  status: "pending" | "processing" | "ready" | "error";
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentCreate {
  title: string;
  source_type: "pdf" | "md" | "html" | "docx";
  source_url?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  content_hash: string;
  created_at: string;
  change_summary: string | null;
  chunk_count: number;
}

export interface DocumentVersionDiff {
  line_diff: string;
  added_lines: number;
  removed_lines: number;
  total_changes: number;
  chunk_changes: Array<Record<string, unknown>>;
  similarity_ratio: number;
}

export interface DocumentRestoreResponse {
  document_id: string;
  restored_version: number;
  new_version: number;
  content_hash: string;
}

export interface QueryRequest {
  question: string;
  top_k?: number;
}

export interface SourceCitation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content_preview: string;
  relevance_score: number;
  citation_index: number;
}

export interface RetrievalTrace {
  query_embedding_dim: number;
  vector_results: number;
  keyword_results: number;
  reranked_results: number;
  final_context_chunks: number;
  confidence: number;
  latency_ms: number;
  scores: Record<string, unknown>[];
}

export interface QueryResponse {
  id: string;
  question: string;
  answer: string | null;
  sources: SourceCitation[];
  retrieval_trace: RetrievalTrace | null;
  refused: boolean;
  confidence: number | null;
  token_usage: Record<string, number> | null;
  created_at: string;
}

export interface QueryListItem {
  id: string;
  question: string;
  refused: boolean;
  confidence: number | null;
  created_at: string;
}

export interface QueryListResponse {
  queries: QueryListItem[];
  total: number;
}

export interface ChunkInfo {
  id: string;
  document_id: string;
  content: string;
  chunk_index: number;
  metadata: Record<string, unknown> | null;
  relevance_score: number;
}

export interface HealthCheck {
  status: string;
  database: string;
  document_count: number;
  version: string;
}

export interface ApiError {
  detail: string;
  status_code?: number;
}

export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "citations"; sources: SourceCitation[]; retrieval_trace?: RetrievalTrace }
  | { type: "refused"; reason: string; retrieval_trace?: RetrievalTrace }
  | { type: "done"; token_usage: Record<string, number> };

export interface WorkflowStepDefinition {
  name: string;
  description: string | null;
  approvers: string[];
  approver_role: string | null;
  is_parallel: boolean;
  min_approvals: number;
  sla_hours: number;
  approval_route: string | null;
  rejection_route: string | null;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string | null;
  steps_count: number;
  owner_id: string;
  organization_id: string | null;
  is_active: boolean;
  is_system: boolean;
  created_at: string | null;
}

export interface WorkflowStep {
  id: string;
  step_index: number;
  name: string;
  description: string | null;
  approver_ids: string[];
  approver_role: string | null;
  is_parallel: boolean;
  min_approvals: number;
  status: string;
  decisions: Record<string, any> | null;
  due_at: string | null;
  completed_at: string | null;
}

export interface WorkflowInstance {
  id: string;
  workflow_definition_id: string;
  document_id: string;
  status: string;
  current_step_index: number;
  triggered_by: string;
  trigger_type: string;
  metadata: Record<string, any> | null;
  created_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  steps?: WorkflowStep[];
}

export interface ApprovalActionRequest {
  step_id: string;
  action: "approve" | "reject" | "request_changes" | "delegate";
  comment: string | null;
}

export interface ApprovalResultResponse {
  success: boolean;
  workflow_id: string;
  step_id: string;
  action: string;
  new_status: string;
  next_step: string | null;
  notifications_sent: string[];
}

export interface WorkflowStatusEvent {
  id: number;
  event: "status" | string;
  workflow_id: string;
  status: string;
  step_id?: string | null;
  action?: string | null;
  message?: string | null;
  created_at?: string | null;
}

export interface AdminUsageSummary {
  total_requests: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  average_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  error_rate: number;
  cost_by_model: Record<string, number>;
  cost_by_prompt_version: Record<string, number>;
}

export interface AuditEvent {
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  workspace_id: string;
  request_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}
