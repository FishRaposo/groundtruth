import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminConsole from "@/components/AdminConsole";
import { apiClient } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiClient: {
    fetchAdminUsage: vi.fn(),
    fetchAuditEvents: vi.fn(),
  },
}));

describe("AdminConsole", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.fetchAdminUsage).mockResolvedValue({
      total_requests: 12,
      total_tokens: 3200,
      input_tokens: 2100,
      output_tokens: 1100,
      estimated_cost: 0.42,
      average_latency_ms: 180,
      p50_latency_ms: 170,
      p95_latency_ms: 240,
      p99_latency_ms: 300,
      error_rate: 0,
      cost_by_model: { "gpt-4o-mini": 0.42 },
      cost_by_prompt_version: { unversioned: 0.42 },
    });
    vi.mocked(apiClient.fetchAuditEvents).mockResolvedValue([
      {
        actor_id: "operator",
        action: "restore",
        resource_type: "document",
        resource_id: "doc-1",
        workspace_id: "workspace-1",
        request_id: "request-1",
        metadata: { restored_version: 2 },
        created_at: "2026-08-15T12:00:00Z",
      },
    ]);
  });

  it("renders usage totals and audit events as read-only evidence", async () => {
    render(<AdminConsole />);

    expect(await screen.findByText("3,200")).toBeInTheDocument();
    expect(screen.getByText("$0.42")).toBeInTheDocument();
    expect(screen.getByText("restore")).toBeInTheDocument();
    expect(screen.getByText("document · doc-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete|edit/i })).not.toBeInTheDocument();
  });
});
