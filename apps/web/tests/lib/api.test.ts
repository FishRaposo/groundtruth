import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api";

describe("Task 4 API client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [],
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("requests document version history on the additive v1 route", async () => {
    await apiClient.fetchDocumentVersions("doc/1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/documents/doc%2F1/versions",
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });

  it("requests an ordered version diff", async () => {
    await apiClient.diffDocumentVersions("doc-1", 2, 5);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/documents/doc-1/versions/diff?from_version=2&to_version=5",
      expect.any(Object)
    );
  });

  it("restores an immutable version with POST", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        document_id: "doc-1",
        restored_version: 2,
        new_version: 6,
        content_hash: "abc",
      }),
    });

    await apiClient.restoreDocumentVersion("doc-1", 2);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/documents/doc-1/versions/2/restore",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("loads read-only usage and audit admin data", async () => {
    await apiClient.fetchAdminUsage();
    await apiClient.fetchAuditEvents();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/admin/usage",
      expect.any(Object)
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/admin/audit",
      expect.any(Object)
    );
  });
});
