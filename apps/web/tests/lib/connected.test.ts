import { describe, expect, it, vi, afterEach } from "vitest";
import { ConnectedClient } from "@/lib/connected";

afterEach(() => vi.unstubAllGlobals());
describe("connected boundary", () => {
  it("sends identity in headers for JSON and multipart, never URLs", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetcher);
    const client = new ConnectedClient(
      "http://127.0.0.1:8400",
      "private-test-key",
    );
    await client.request("/api/identity");
    await client.request("/api/documents/upload", {
      method: "POST",
      body: new FormData(),
    });
    expect(
      fetcher.mock.calls.every(([url]) => !url.includes("private-test-key")),
    ).toBe(true);
    expect(new Headers(fetcher.mock.calls[0][1].headers).get("X-API-Key")).toBe(
      "private-test-key",
    );
    expect(
      new Headers(fetcher.mock.calls[1][1].headers).has("Content-Type"),
    ).toBe(false);
  });
  it("retains HTTP errors and aborts obsolete work", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ detail: "Not authorized" }),
      });
    vi.stubGlobal("fetch", fetcher);
    const client = new ConnectedClient("http://127.0.0.1:8400", "key");
    await expect(client.request("/api/queries")).rejects.toThrow(
      "Not authorized",
    );
    client.close();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
    await expect(client.request("/api/queries")).rejects.toThrow();
  });
});
