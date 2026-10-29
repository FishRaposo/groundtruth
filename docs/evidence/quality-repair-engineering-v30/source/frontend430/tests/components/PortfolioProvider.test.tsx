import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioProvider, {
  usePortfolio,
} from "@/components/PortfolioProvider";

function Inspector() {
  const p = usePortfolio();
  return (
    <div>
      <span>{p.ready ? "Ready" : "Waiting"}</span>
      <span>{p.source}</span>
      <span>{p.identity?.name || "No identity"}</span>
      <span>{p.history.map((item) => item.question).join(",")}</span>
      <button onClick={() => p.connect("alpha-key")}>Connect alpha</button>
      <button onClick={() => p.connect("beta-key")}>Connect beta</button>
      <button onClick={() => p.setSource("sample")}>Sample</button>
      <button onClick={() => p.setConversation("conversation-b")}>
        Change conversation
      </button>
      <span>{p.conversation}</span>
    </div>
  );
}
describe("shared private application state", () => {
  it("clears stale saved-query URLs when conversation or identity changes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => new Promise(() => undefined)),
    );
    render(
      <PortfolioProvider>
        <Inspector />
      </PortfolioProvider>,
    );
    await screen.findByText("Ready");
    window.history.replaceState(null, "", "/chat?query=old-conversation-query");
    fireEvent.click(screen.getByText("Change conversation"));
    expect(window.location.search).not.toContain("query=");
    window.history.replaceState(null, "", "/chat?query=old-identity-query");
    fireEvent.click(screen.getByText("Connect alpha"));
    expect(window.location.search).not.toContain("query=");
  });
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());
  it("keeps the sample independent and clears private views on identity/source/session changes", async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(async (url: string, options: RequestInit) => {
        const key = new Headers(options.headers).get("X-API-Key");
        const result = url.includes("/identity")
          ? {
              id: key,
              name: key === "alpha-key" ? "Alpha operator" : "Beta operator",
              workspace_id: "ops",
              is_admin: false,
            }
          : url.includes("/documents")
            ? { documents: [] }
            : url.includes("/queries")
              ? {
                  queries: [
                    {
                      id: key,
                      question: `${key} private history`,
                      refused: false,
                      confidence: null,
                      created_at: "2026-10-23",
                    },
                  ],
                }
              : url.includes("/conversations")
                ? []
                : { status: "ok", database: "sqlite" };
        return { ok: true, status: 200, json: async () => result };
      });
    vi.stubGlobal("fetch", fetcher);
    render(
      <PortfolioProvider>
        <Inspector />
      </PortfolioProvider>,
    );
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
    expect(fetcher).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Connect alpha"));
    await screen.findByText("Alpha operator");
    expect(screen.getByText("alpha-key private history")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Connect beta"));
    await screen.findByText("Beta operator");
    expect(
      screen.queryByText("alpha-key private history"),
    ).not.toBeInTheDocument();
    expect(sessionStorage.getItem("groundtruth.api-key.v1")).toBe("beta-key");
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
    fireEvent.click(screen.getByText("Change conversation"));
    await screen.findByText("conversation-b");
    expect(sessionStorage.getItem("groundtruth.conversation.v1")).toBe(
      "conversation-b",
    );
    fireEvent.click(screen.getByText("Sample"));
    await screen.findByText("No identity");
    expect(
      screen.queryByText("beta-key private history"),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem("groundtruth.source.v1")).toBe("sample");
  });
});
