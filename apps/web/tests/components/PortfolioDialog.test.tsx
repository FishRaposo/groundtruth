import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Dialog } from "@/components/PortfolioShell";

describe("evidence drawer keyboard boundary", () => {
  it("traps Tab at expandable technical details and supports Escape", () => {
    const close = vi.fn();
    render(
      <Dialog title="Captured source" close={close}>
        <details>
          <summary>Immutable source identity</summary>
          <p>Version 2</p>
        </details>
      </Dialog>,
    );
    const summary = screen.getByText("Immutable source identity");
    summary.focus();
    fireEvent.keyDown(summary, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("button", { name: "Close dialog" }), {
      key: "Tab",
      shiftKey: true,
    });
    expect(summary).toHaveFocus();
    fireEvent.keyDown(summary, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  });
});
