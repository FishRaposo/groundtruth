import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PortfolioAdmin } from "@/components/PortfolioOperations";

const { request, sample } = vi.hoisted(() => ({
  request: vi.fn(),
  sample: { audit: [], queries: [] },
}));
const client = { request };
vi.mock("@/components/PortfolioProvider", () => ({
  usePortfolio: () => ({
    source: "connected",
    identity: { is_admin: true },
    runtime: null,
    sample,
    client,
  }),
}));
describe("connected admin evidence", () => {
  beforeEach(() => {
    request.mockReset().mockImplementation(() => new Promise(() => undefined));
  });
  it("distinguishes loading from an observed empty audit", () => {
    render(<PortfolioAdmin />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading durable usage and audit history",
    );
    expect(
      screen.queryByText("No recorded events for this view yet."),
    ).not.toBeInTheDocument();
  });
  it("renders actual strict usage with unknown pricing rather than crashing or inventing zero", async () => {
    request.mockImplementation(async (url: string) =>
      url.endsWith("/usage")
        ? {
            total_requests: 7,
            total_tokens: 211,
            total_cost: null,
            estimated: true,
            pricing_provenance:
              "unknown; local extractive generation has no provider charge",
            average_latency_ms: 42,
            outcomes: { completed: 7 },
          }
        : [
            {
              actor_id: "operator",
              action: "query.completed",
              resource_type: "query",
              resource_id: "query-1",
              workspace_id: "ops",
              request_id: null,
              metadata: {},
              created_at: "2026-10-24T03:00:00Z",
            },
          ],
    );
    render(<PortfolioAdmin />);
    expect(await screen.findByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("query.completed")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
