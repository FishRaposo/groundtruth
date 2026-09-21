import type {
  Document,
  DocumentListResponse,
  QueryRequest,
  QueryResponse,
  QueryListResponse,
  HealthCheck,
  StreamEvent,
  WorkflowDefinition,
  WorkflowInstance,
  ApprovalResultResponse,
  AdminUsageSummary,
  AuditEvent,
  DocumentRestoreResponse,
  DocumentVersion,
  DocumentVersionDiff,
  WorkflowStatusEvent,
} from "@/types";
import { buildDemoQueryResponse, streamDemoResponse } from "@/lib/demoMode";
import {
  DEMO_ADMIN_USAGE,
  DEMO_AUDIT_EVENTS,
  DEMO_DOCUMENT_LIST,
  DEMO_QUERY_LIST,
  DEMO_VERSION_DIFF,
  DEMO_WORKFLOW_DEFINITIONS,
  DEMO_WORKFLOW_INSTANCE,
  getDemoApprovalResult,
  getDemoDocumentVersions,
  getDemoQueryDetail,
} from "@/lib/demoFixtures";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  }

  async fetchDocuments(
    limit: number = 50,
    offset: number = 0,
    status?: string
  ): Promise<DocumentListResponse> {
    if (DEMO_MODE) {
      let documents = DEMO_DOCUMENT_LIST.documents;
      if (status) {
        documents = documents.filter((doc) => doc.status === status);
      }
      return {
        documents: documents.slice(offset, offset + limit),
        total: documents.length,
        limit,
        offset,
      };
    }
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (status) params.set("status", status);
    return this.request<DocumentListResponse>(`/api/documents?${params}`);
  }

  async uploadDocument(files: File[]): Promise<{ documents: Document[] }> {
    if (DEMO_MODE) {
      return { documents: DEMO_DOCUMENT_LIST.documents };
    }
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    const response = await fetch(`${this.baseUrl}/api/documents/upload`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Upload failed: ${response.status}`);
    }

    return response.json();
  }

  async deleteDocument(documentId: string): Promise<void> {
    if (DEMO_MODE) return;
    await this.request<void>(`/api/documents/${documentId}`, {
      method: "DELETE",
    });
  }

  async getDocument(documentId: string): Promise<Document> {
    if (DEMO_MODE) {
      const doc = DEMO_DOCUMENT_LIST.documents.find((item) => item.id === documentId);
      if (!doc) throw new Error("Document not found");
      return doc;
    }
    return this.request<Document>(`/api/documents/${encodeURIComponent(documentId)}`);
  }

  async fetchDocumentVersions(documentId: string): Promise<DocumentVersion[]> {
    if (DEMO_MODE) {
      return getDemoDocumentVersions(documentId);
    }
    return this.request<DocumentVersion[]>(
      `/api/v1/documents/${encodeURIComponent(documentId)}/versions`
    );
  }

  async diffDocumentVersions(
    documentId: string,
    fromVersion: number,
    toVersion: number
  ): Promise<DocumentVersionDiff> {
    if (DEMO_MODE) {
      return DEMO_VERSION_DIFF;
    }
    const params = new URLSearchParams({
      from_version: String(fromVersion),
      to_version: String(toVersion),
    });
    return this.request<DocumentVersionDiff>(
      `/api/v1/documents/${encodeURIComponent(documentId)}/versions/diff?${params}`
    );
  }

  async restoreDocumentVersion(
    documentId: string,
    version: number
  ): Promise<DocumentRestoreResponse> {
    if (DEMO_MODE) {
      return {
        document_id: documentId,
        restored_version: version,
        new_version: version + 1,
        content_hash: "sha256:demo-restored",
      };
    }
    return this.request<DocumentRestoreResponse>(
      `/api/v1/documents/${encodeURIComponent(documentId)}/versions/${version}/restore`,
      { method: "POST" }
    );
  }

  async askQuestion(request: QueryRequest): Promise<QueryResponse> {
    if (DEMO_MODE) {
      return buildDemoQueryResponse(request.question);
    }
    return this.request<QueryResponse>("/api/queries", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getQueryHistory(
    limit: number = 20,
    offset: number = 0
  ): Promise<QueryListResponse> {
    if (DEMO_MODE) {
      return {
        queries: DEMO_QUERY_LIST.queries.slice(offset, offset + limit),
        total: DEMO_QUERY_LIST.total,
      };
    }
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    return this.request<QueryListResponse>(`/api/queries?${params}`);
  }

  async getQueryDetail(queryId: string): Promise<QueryResponse> {
    if (DEMO_MODE) {
      const query = getDemoQueryDetail(queryId);
      if (!query) throw new Error("Query not found");
      return query;
    }
    return this.request<QueryResponse>(`/api/queries/${queryId}`);
  }

  async processOcr(documentId: string): Promise<{ document_id: string; text: string; total_pages: number; confidence: number; blocks_count: number }> {
    if (DEMO_MODE) {
      return {
        document_id: documentId,
        text: "Demo OCR text extraction is not available in portfolio mode.",
        total_pages: 1,
        confidence: 0.95,
        blocks_count: 1,
      };
    }
    return this.request<{ document_id: string; text: string; total_pages: number; confidence: number; blocks_count: number }>(`/api/v1/documents/${documentId}/ocr`, {
      method: "POST",
    });
  }

  async detectTemplate(documentId: string): Promise<{ document_id: string; template: string | null; confidence: number; fields: Record<string, unknown>[]; matched_keywords?: string[]; message?: string }> {
    if (DEMO_MODE) {
      return {
        document_id: documentId,
        template: "policy_document",
        confidence: 0.88,
        fields: [{ name: "effective_date", value: "2025-11-01" }],
        matched_keywords: ["policy", "remote", "work"],
      };
    }
    return this.request<{ document_id: string; template: string | null; confidence: number; fields: Record<string, unknown>[]; matched_keywords?: string[]; message?: string }>(`/api/v1/documents/${documentId}/detect-template`, {
      method: "POST",
    });
  }

  async healthCheck(): Promise<HealthCheck> {
    if (DEMO_MODE) {
      return {
        status: "ok",
        database: "demo",
        document_count: DEMO_DOCUMENT_LIST.total,
        version: "demo",
      };
    }
    return this.request<HealthCheck>("/api/health");
  }

  async *streamQuestion(request: QueryRequest): AsyncGenerator<StreamEvent> {
    if (DEMO_MODE) {
      yield* streamDemoResponse(request.question);
      return;
    }
    const url = `${this.baseUrl}/api/queries/stream`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const jsonStr = trimmed.slice(6);
        if (!jsonStr) continue;

        const event: StreamEvent = JSON.parse(jsonStr);
        yield event;
      }
    }

    if (buffer.trim().startsWith("data: ")) {
      const jsonStr = buffer.trim().slice(6);
      if (jsonStr) {
        const event: StreamEvent = JSON.parse(jsonStr);
        yield event;
      }
    }
  }

  async fetchWorkflowDefinitions(): Promise<WorkflowDefinition[]> {
    if (DEMO_MODE) {
      return DEMO_WORKFLOW_DEFINITIONS;
    }
    return this.request<WorkflowDefinition[]>("/api/v1/workflows/definitions");
  }

  async startWorkflow(
    workflowDefinitionId: string,
    documentId: string,
    triggerType: string = "manual"
  ): Promise<WorkflowInstance> {
    if (DEMO_MODE) {
      return {
        ...DEMO_WORKFLOW_INSTANCE,
        id: `demo-wf-inst-${Date.now()}`,
        workflow_definition_id: workflowDefinitionId,
        document_id: documentId,
        trigger_type: triggerType,
      };
    }
    return this.request<WorkflowInstance>("/api/v1/workflows/instances", {
      method: "POST",
      body: JSON.stringify({
        workflow_definition_id: workflowDefinitionId,
        document_id: documentId,
        trigger_type: triggerType,
      }),
    });
  }

  async fetchWorkflowInstance(workflowId: string): Promise<WorkflowInstance> {
    if (DEMO_MODE) {
      if (workflowId === DEMO_WORKFLOW_INSTANCE.id) {
        return DEMO_WORKFLOW_INSTANCE;
      }
      return { ...DEMO_WORKFLOW_INSTANCE, id: workflowId };
    }
    return this.request<WorkflowInstance>(`/api/v1/workflows/instances/${workflowId}`);
  }

  async processApproval(
    workflowId: string,
    stepId: string,
    action: "approve" | "reject" | "request_changes" | "delegate",
    comment: string | null = null
  ): Promise<ApprovalResultResponse> {
    if (DEMO_MODE) {
      return getDemoApprovalResult(workflowId, stepId, action);
    }
    return this.request<ApprovalResultResponse>(`/api/v1/workflows/${workflowId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        step_id: stepId,
        action,
        comment,
      }),
    });
  }

  async cancelWorkflow(workflowId: string, reason?: string): Promise<{ success: boolean; message: string }> {
    if (DEMO_MODE) {
      return { success: true, message: reason || "Workflow cancelled" };
    }
    const query = reason ? `?reason=${encodeURIComponent(reason)}` : "";
    return this.request<{ success: boolean; message: string }>(`/api/v1/workflows/instances/${workflowId}/cancel${query}`, {
      method: "POST",
    });
  }

  async fetchDocumentWorkflowHistory(documentId: string): Promise<any[]> {
    if (DEMO_MODE) {
      return [DEMO_WORKFLOW_INSTANCE];
    }
    return this.request<any[]>(`/api/v1/workflows/documents/${documentId}/history`);
  }

  subscribeWorkflowEvents(
    workflowId: string,
    onEvent: (event: WorkflowStatusEvent) => void,
    onError?: () => void,
    afterEventId: number = 0
  ): () => void {
    if (DEMO_MODE) {
      onEvent({
        id: afterEventId + 1,
        event: "status",
        workflow_id: workflowId,
        status: "in_progress",
        step_id: "demo-step-2",
        action: null,
        message: "Compliance sign-off pending",
        created_at: "2025-11-16T10:30:00.000Z",
      });
      return () => undefined;
    }
    const params = new URLSearchParams({ after_event_id: String(afterEventId) });
    const source = new EventSource(
      `${this.baseUrl}/api/v1/workflows/instances/${encodeURIComponent(workflowId)}/events?${params}`
    );
    const listener = (rawEvent: Event): void => {
      const event = rawEvent as MessageEvent<string>;
      const payload = JSON.parse(event.data) as Pick<
        WorkflowStatusEvent,
        "status" | "step_id" | "action" | "message" | "created_at"
      >;
      onEvent({
        ...payload,
        id: Number(event.lastEventId || 0),
        event: event.type,
        workflow_id: workflowId,
      });
    };
    source.addEventListener("status", listener);
    source.onerror = () => onError?.();
    return () => source.close();
  }

  async fetchAdminUsage(): Promise<AdminUsageSummary> {
    if (DEMO_MODE) {
      return DEMO_ADMIN_USAGE;
    }
    return this.request<AdminUsageSummary>("/api/v1/admin/usage");
  }

  async fetchAuditEvents(): Promise<AuditEvent[]> {
    if (DEMO_MODE) {
      return DEMO_AUDIT_EVENTS;
    }
    return this.request<AuditEvent[]>("/api/v1/admin/audit");
  }
}

export const apiClient = new ApiClient(API_BASE);
