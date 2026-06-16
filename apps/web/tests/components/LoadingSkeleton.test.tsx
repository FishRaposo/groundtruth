import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MessageSkeleton, CardSkeleton } from "@/components/LoadingSkeleton";

describe("LoadingSkeleton", () => {
  it("renders message skeleton without crashing", () => {
    const { container } = render(<MessageSkeleton />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("renders card skeleton without crashing", () => {
    const { container } = render(<CardSkeleton />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });
});
