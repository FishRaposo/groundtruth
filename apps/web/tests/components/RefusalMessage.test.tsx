import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RefusalMessage from "@/components/RefusalMessage";

describe("RefusalMessage", () => {
  it("renders reason text", () => {
    render(<RefusalMessage reason="Insufficient context" />);
    expect(screen.getByText("Unable to Answer")).toBeInTheDocument();
    expect(screen.getByText("Insufficient context")).toBeInTheDocument();
  });

  it("renders confidence when provided", () => {
    render(<RefusalMessage reason="Low confidence" confidence={0.42} />);
    expect(screen.getByText("Confidence: 42%")).toBeInTheDocument();
  });

  it("renders suggestion when provided", () => {
    render(<RefusalMessage reason="No match" suggestion="Try rephrasing" />);
    expect(screen.getByText("Try rephrasing")).toBeInTheDocument();
  });
});
