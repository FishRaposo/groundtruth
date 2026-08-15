import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DocumentVersionPanel from "@/components/DocumentVersionPanel";
import { apiClient } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiClient: {
    fetchDocumentVersions: vi.fn(),
    diffDocumentVersions: vi.fn(),
    restoreDocumentVersion: vi.fn(),
  },
}));

const versions = [
  {
    id: "v2",
    document_id: "doc-1",
    version_number: 2,
    content_hash: "hash-2",
    created_at: "2026-08-15T12:00:00Z",
    change_summary: "Updated policy",
    chunk_count: 8,
  },
  {
    id: "v1",
    document_id: "doc-1",
    version_number: 1,
    content_hash: "hash-1",
    created_at: "2026-08-14T12:00:00Z",
    change_summary: "Initial upload",
    chunk_count: 6,
  },
];

describe("DocumentVersionPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.fetchDocumentVersions).mockResolvedValue(versions);
    vi.mocked(apiClient.diffDocumentVersions).mockResolvedValue({
      line_diff: "--- previous\n+++ current\n-old\n+new",
      added_lines: 1,
      removed_lines: 1,
      total_changes: 2,
      chunk_changes: [],
      similarity_ratio: 0.75,
    });
    vi.mocked(apiClient.restoreDocumentVersion).mockResolvedValue({
      document_id: "doc-1",
      restored_version: 1,
      new_version: 3,
      content_hash: "hash-3",
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("loads history and compares two selected versions", async () => {
    render(<DocumentVersionPanel documentId="doc-1" documentTitle="Policy" />);

    expect(await screen.findByText(/Updated policy/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("From version"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("To version"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Compare versions" }));

    expect(await screen.findByText("2 line changes")).toBeInTheDocument();
    expect(screen.getByLabelText("Version diff")).toHaveTextContent("+new");
  });

  it("restores a prior version and refreshes history", async () => {
    render(<DocumentVersionPanel documentId="doc-1" documentTitle="Policy" />);

    const restoreButtons = await screen.findAllByRole("button", {
      name: /restore version/i,
    });
    fireEvent.click(restoreButtons[1]);

    await waitFor(() => {
      expect(apiClient.restoreDocumentVersion).toHaveBeenCalledWith("doc-1", 1);
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Version 1 restored as version 3"
    );
    expect(apiClient.fetchDocumentVersions).toHaveBeenCalledTimes(2);
  });
});
