import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowStatusStream from "@/components/WorkflowStatusStream";
import { apiClient } from "@/lib/api";
import type { WorkflowStatusEvent } from "@/types";

vi.mock("@/lib/api", () => ({
  apiClient: {
    subscribeWorkflowEvents: vi.fn(),
  },
}));

describe("WorkflowStatusStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders local status events received over the workflow stream", () => {
    let emit: ((event: WorkflowStatusEvent) => void) | undefined;
    const unsubscribe = vi.fn();
    vi.mocked(apiClient.subscribeWorkflowEvents).mockImplementation(
      (_id, onEvent) => {
        emit = onEvent;
        return unsubscribe;
      }
    );

    const { unmount } = render(<WorkflowStatusStream workflowId="wf-1" />);

    act(() => {
      emit?.({
        id: 4,
        event: "status",
        workflow_id: "wf-1",
        status: "approved",
        step_id: "step-1",
        message: "Review approved",
        created_at: "2026-08-15T12:00:00Z",
      });
    });

    expect(screen.getByText("Review approved")).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
    unmount();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
