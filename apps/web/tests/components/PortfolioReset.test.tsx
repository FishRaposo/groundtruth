import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import PortfolioProvider from "@/components/PortfolioProvider";
import PortfolioShell from "@/components/PortfolioShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/workflows",
  useRouter: () => ({ push: vi.fn() }),
}));
function SelectedWorkflow() {
  const [selected, setSelected] = useState(false);
  return (
    <div>
      <p>
        {selected
          ? "Previously selected completed workflow"
          : "No workflow selected"}
      </p>
      <button onClick={() => setSelected(true)}>
        Select recorded workflow
      </button>
    </div>
  );
}
describe("complete sample reset", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  it("resets page-local investigation state together with shared sample records", async () => {
    render(
      <PortfolioProvider>
        <PortfolioShell>
          <SelectedWorkflow />
        </PortfolioShell>
      </PortfolioProvider>,
    );
    fireEvent.click(await screen.findByText("Select recorded workflow"));
    expect(
      screen.getByText("Previously selected completed workflow"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset demo" }));
    expect(screen.getByText("No workflow selected")).toBeInTheDocument();
  });
});
