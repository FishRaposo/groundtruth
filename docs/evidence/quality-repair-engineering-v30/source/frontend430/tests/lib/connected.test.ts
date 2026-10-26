import { describe, expect, it, vi, afterEach } from "vitest";
import { ConnectedClient } from "@/lib/connected";

afterEach(() => vi.unstubAllGlobals());

async function readEvents(chunks: Uint8Array[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    body: new ReadableStream<Uint8Array>({ start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    } }),
  }));
  const client = new ConnectedClient("http://unit.invalid", "unit-only");
  const events = [];
  for await (const event of client.events("/events")) events.push(event);
  client.close();
  return events;
}

describe("connected boundary", () => {
  it("preserves a CRLF-framed event at every possible byte boundary", async () => {
    const bytes = new TextEncoder().encode('event: done\r\nid: result-1\r\ndata: {"type":"done","text":"✅ café"}\r\n\r\n');
    const expected = [{ event: "done", id: "result-1", data: { type: "done", text: "✅ café" } }];
    for (let split = 1; split < bytes.length; split += 1) {
      expect(await readEvents([bytes.slice(0, split), bytes.slice(split)]), `split ${split}`).toEqual(expected);
    }
  });
  it("decodes UTF-8 and consecutive LF/CRLF events one byte at a time", async () => {
    const bytes = new TextEncoder().encode('data: {"type":"token","content":"🧭"}\r\n\r\nevent: done\ndata: {"type":"done","id":"saved"}\n\n');
    expect(await readEvents(Array.from(bytes, (byte) => new Uint8Array([byte])))).toEqual([
      { event: "message", id: "", data: { type: "token", content: "🧭" } },
      { event: "done", id: "", data: { type: "done", id: "saved" } },
    ]);
  });
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
