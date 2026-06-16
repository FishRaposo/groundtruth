import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import CitationText from "@/components/CitationText";
import type { SourceCitation } from "@/types";

const sources: SourceCitation[] = [
  {
    chunk_id: "c1",
    document_id: "d1",
    document_title: "Doc 1",
    content_preview: "preview",
    relevance_score: 0.9,
    citation_index: 1,
  },
  {
    chunk_id: "c2",
    document_id: "d1",
    document_title: "Doc 1",
    content_preview: "preview",
    relevance_score: 0.8,
    citation_index: 2,
  },
];

describe("CitationText", () => {
  it("renders plain text without markers", () => {
    render(<CitationText text="No markers here." sources={sources} />);
    expect(screen.getByText("No markers here.")).toBeInTheDocument();
  });

  it("renders resolved markers as clickable badges", () => {
    render(<CitationText text="Grounded claim [1]." sources={sources} />);
    expect(screen.getByTestId("citation-marker-1")).toBeInTheDocument();
  });

  it("renders both resolved markers when multiple sources exist", () => {
    render(<CitationText text="See [1] and [2]." sources={sources} />);
    expect(screen.getByTestId("citation-marker-1")).toBeInTheDocument();
    expect(screen.getByTestId("citation-marker-2")).toBeInTheDocument();
  });

  it("renders dangling markers muted when no source matches", () => {
    render(<CitationText text="Claim [9]." sources={sources} />);
    expect(screen.getByTestId("citation-dangling-9")).toBeInTheDocument();
    expect(screen.queryByTestId("citation-marker-9")).not.toBeInTheDocument();
  });

  it("invokes onCitationClick with the marker number", () => {
    const onClick = vi.fn();
    render(
      <CitationText text="Claim [2]." sources={sources} onCitationClick={onClick} />
    );
    fireEvent.click(screen.getByTestId("citation-marker-2"));
    expect(onClick).toHaveBeenCalledWith(2);
  });

  it("preserves surrounding text around markers", () => {
    const { container } = render(
      <CitationText text="Before [1] after." sources={sources} />
    );
    expect(container.textContent).toContain("Before");
    expect(container.textContent).toContain("after.");
  });

  it("treats all markers as dangling when sources is empty", () => {
    render(<CitationText text="Claim [1]." sources={[]} />);
    expect(screen.getByTestId("citation-dangling-1")).toBeInTheDocument();
  });
});
