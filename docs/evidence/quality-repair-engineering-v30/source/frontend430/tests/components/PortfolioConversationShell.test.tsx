import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import PortfolioProvider, { usePortfolio } from "@/components/PortfolioProvider";
import PortfolioShell from "@/components/PortfolioShell";
import PortfolioChat from "@/components/PortfolioChat";

vi.mock("next/navigation", () => ({
  usePathname: () => "/chat", useRouter: () => ({ push: vi.fn() }),
}));
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  localStorage.setItem("groundtruth.source.v1", "connected");
  sessionStorage.setItem("groundtruth.api-key.v1", "unit-only");
  window.history.replaceState(null, "", "/chat");
});
afterEach(() => vi.unstubAllGlobals());

function ContextControls() {
  const p = usePortfolio();
  return <>
    <button onClick={() => p.setConversation("another-conversation")}>Switch conversation</button>
    <button onClick={() => p.connect("different-unit-key")}>Switch identity</button>
    <button onClick={() => p.setSource("sample")}>Switch to preview</button>
  </>;
}
function LocalDraft() {
  const [draft, setDraft] = useState("");
  return <input aria-label="Page-local draft" value={draft} onChange={event => setDraft(event.target.value)} />;
}

it("retains page-local state for conversation changes and clears it for identity, source and reset", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ documents: [], queries: [], conversations: [], status: "ok" }) }));
  render(<PortfolioProvider><ContextControls /><PortfolioShell><LocalDraft /></PortfolioShell></PortfolioProvider>);
  await screen.findByText("Connected local application", { exact: true });
  const typeDraft = () => fireEvent.change(screen.getByLabelText("Page-local draft"), { target: { value: "Private draft" } });
  typeDraft();
  fireEvent.click(screen.getByText("Switch conversation"));
  expect(screen.getByLabelText("Page-local draft")).toHaveValue("Private draft");
  fireEvent.click(screen.getByText("Switch identity"));
  expect(screen.getByLabelText("Page-local draft")).toHaveValue("");
  typeDraft();
  fireEvent.click(screen.getByText("Switch to preview"));
  expect(screen.getByLabelText("Page-local draft")).toHaveValue("");
  typeDraft();
  fireEvent.click(screen.getByRole("button", { name: "Reset demo" }));
  expect(screen.getByLabelText("Page-local draft")).toHaveValue("");
});

it("preserves a draft typed during conversation creation through the real shell", async () => {
  const response = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload });
  let finishCreation: ((value: ReturnType<typeof response>) => void) | undefined;
  const submitted: Record<string, unknown>[] = [];
  vi.stubGlobal("fetch", vi.fn((input: string, options: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/conversations") && options.method === "POST")
      return new Promise<ReturnType<typeof response>>(resolve => { finishCreation = resolve; });
    if (url.endsWith("/api/queries") && options.method === "POST") {
      const body = JSON.parse(String(options.body)); submitted.push(body);
      return Promise.resolve(response({ id: "saved", ...body, answer: "The saved answer", sources: [], refused: false, outcome: "completed", created_at: "2026-10-24T00:00:00Z" }));
    }
    return Promise.resolve(response(url.includes("/documents") ? { documents: [] }
      : url.includes("/queries?") ? { queries: [] }
        : url.includes("/conversations") ? [{ id: "new-conversation", title: "Operational investigation" }]
          : url.includes("/identity") ? { name: "Operator", workspace_id: "ops", is_admin: false }
            : { status: "ok" }));
  }));
  render(<PortfolioProvider><PortfolioShell><PortfolioChat /></PortfolioShell></PortfolioProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "New conversation" }));
  fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: "Who owns the review?" } });
  expect(screen.getByRole("button", { name: /^Ask question$/ })).toBeDisabled();
  await waitFor(() => expect(finishCreation).toBeDefined());
  await act(async () => finishCreation!(response({ id: "new-conversation", title: "Operational investigation" })));
  expect(screen.getByLabelText("What do you need to know?")).toHaveValue("Who owns the review?");
  await waitFor(() => expect(screen.getByRole("button", { name: /^Ask question$/ })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: /^Ask question$/ }));
  await screen.findByText("The saved answer");
  expect(submitted).toEqual([expect.objectContaining({ conversation_id: "new-conversation", question: "Who owns the review?" })]);
});
