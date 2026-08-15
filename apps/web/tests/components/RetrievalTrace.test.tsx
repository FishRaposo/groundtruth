import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RetrievalTrace from "@/components/RetrievalTrace";

describe("RetrievalTrace", () => {
  it("keeps score details collapsed until explicitly expanded", () => {
    render(
      <RetrievalTrace
        trace={{
          query_embedding_dim: 1536,
          vector_results: 8,
          keyword_results: 4,
          reranked_results: 2,
          final_context_chunks: 2,
          confidence: 0.83,
          latency_ms: 91,
          scores: [
            { chunk_id: "chunk-123456", document_id: "doc-123456", score: 0.88 },
          ],
        }}
      />
    );

    expect(screen.queryByText(/chunk-123/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand score details" }));
    expect(screen.getByText(/chunk-123/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse score details" })).toBeInTheDocument();
  });
});
