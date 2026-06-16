import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import SourceCitation from "@/components/SourceCitation";

describe("SourceCitation", () => {
  it("renders citation index and title", () => {
    const citation = {
      chunk_id: "uuid-1",
      document_id: "uuid-2",
      document_title: "Remote Work Policy",
      content_preview: "Employees may work remotely up to 3 days per week.",
      relevance_score: 0.92,
      citation_index: 1,
    };

    render(<SourceCitation citation={citation} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Remote Work Policy")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("shows green badge for high scores", () => {
    const citation = {
      chunk_id: "uuid-1",
      document_id: "uuid-2",
      document_title: "High Score Doc",
      content_preview: "content",
      relevance_score: 0.85,
      citation_index: 2,
    };

    const { container } = render(<SourceCitation citation={citation} />);
    const badge = container.querySelector(".text-green-600");
    expect(badge).toBeInTheDocument();
  });

  it("shows red badge for low scores", () => {
    const citation = {
      chunk_id: "uuid-1",
      document_id: "uuid-2",
      document_title: "Low Score Doc",
      content_preview: "content",
      relevance_score: 0.3,
      citation_index: 3,
    };

    const { container } = render(<SourceCitation citation={citation} />);
    const badge = container.querySelector(".text-red-600");
    expect(badge).toBeInTheDocument();
  });
});
