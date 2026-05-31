import type {
  Document,
  DocumentListResponse,
  QueryRequest,
  QueryResponse,
  QueryListResponse,
  HealthCheck,
  StreamEvent,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (status) params.set("status", status);
    return this.request<DocumentListResponse>(`/api/documents?${params}`);
  }

  async uploadDocument(files: File[]): Promise<{ documents: Document[] }> {
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
    await this.request<void>(`/api/documents/${documentId}`, {
      method: "DELETE",
    });
  }

  async getDocument(documentId: string): Promise<Document> {
    return this.request<Document>(`/api/documents/${documentId}`);
  }

  async askQuestion(request: QueryRequest): Promise<QueryResponse> {
    return this.request<QueryResponse>("/api/queries", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getQueryHistory(
    limit: number = 20,
    offset: number = 0
  ): Promise<QueryListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    return this.request<QueryListResponse>(`/api/queries?${params}`);
  }

  async getQueryDetail(queryId: string): Promise<QueryResponse> {
    return this.request<QueryResponse>(`/api/queries/${queryId}`);
  }

  async processOcr(documentId: string): Promise<{ document_id: string; text: string; total_pages: number; confidence: number; blocks_count: number }> {
    return this.request<{ document_id: string; text: string; total_pages: number; confidence: number; blocks_count: number }>(`/api/v1/documents/${documentId}/ocr`, {
      method: "POST",
    });
  }

  async detectTemplate(documentId: string): Promise<{ document_id: string; template: string | null; confidence: number; fields: Record<string, unknown>[]; matched_keywords?: string[]; message?: string }> {
    return this.request<{ document_id: string; template: string | null; confidence: number; fields: Record<string, unknown>[]; matched_keywords?: string[]; message?: string }>(`/api/v1/documents/${documentId}/detect-template`, {
      method: "POST",
    });
  }

  async healthCheck(): Promise<HealthCheck> {
    return this.request<HealthCheck>("/api/health");
  }

  async *streamQuestion(request: QueryRequest): AsyncGenerator<StreamEvent> {
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
}

export const apiClient = new ApiClient(API_BASE);
