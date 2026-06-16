import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ChatInterface from "@/components/ChatInterface";
import { apiClient } from "@/lib/api";
import type { StreamEvent } from "@/types";

vi.mock("@/lib/api", () => ({
  apiClient: {
    streamQuestion: vi.fn(),
  },
}));

const mockedStream = apiClient.streamQuestion as unknown as ReturnType<typeof vi.fn>;

async function* fromEvents(events: StreamEvent[]): AsyncGenerator<StreamEvent> {
  for (const e of events) yield e;
}

function submitQuestion(text: string): void {
  const input = screen.getByPlaceholderText(/ask a question/i);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatInterface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom lacks scrollIntoView
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it("shows the empty state initially", () => {
    render(<ChatInterface />);
    expect(
      screen.getByText(/ask a question about your uploaded documents/i)
    ).toBeInTheDocument();
  });

  it("streams a grounded answer with highlighted citations", async () => {
    mockedStream.mockReturnValue(
      fromEvents([
        { type: "token", content: "Answer [1] " },
        {
          type: "citations",
          sources: [
            {
              chunk_id: "c1",
              document_id: "d1",
              document_title: "Doc",
              content_preview: "p",
              relevance_score: 0.9,
              citation_index: 1,
            },
          ],
        },
        { type: "done", token_usage: { total_tokens: 2 } },
      ])
    );

    render(<ChatInterface />);
    submitQuestion("hello");

    await waitFor(() => {
      expect(screen.getByTestId("citation-marker-1")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("falls back to demo mode on a network error", async () => {
    mockedStream.mockImplementation(() => {
      throw new TypeError("Failed to fetch");
    });

    render(<ChatInterface />);
    submitQuestion("What is the remote work policy?");

    await waitFor(() => {
      expect(screen.getByTestId("demo-banner")).toBeInTheDocument();
    });
    // Demo answer for remote work resolves citation [1].
    await waitFor(() => {
      expect(screen.getByTestId("citation-marker-1")).toBeInTheDocument();
    });
  });

  it("shows a refusal message on a non-network application error", async () => {
    mockedStream.mockImplementation(() => {
      throw new Error("Query not found");
    });

    render(<ChatInterface />);
    submitQuestion("anything");

    await waitFor(() => {
      expect(screen.getByText(/unable to answer/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("renders a backend refusal event", async () => {
    mockedStream.mockReturnValue(
      fromEvents([
        { type: "refused", reason: "Not enough evidence." },
        { type: "done", token_usage: { total_tokens: 0 } },
      ])
    );

    render(<ChatInterface />);
    submitQuestion("obscure question");

    await waitFor(() => {
      expect(screen.getByText(/unable to answer/i)).toBeInTheDocument();
    });
  });
});
