import type { Page } from "@playwright/test";
import { describe, expect, it } from "vitest";
import { installOfflineNetworkGuard, offlineRequestViolation, offlineWebSocketViolation } from "../../e2e/offlineNetworkGuard";

const baseURL = "http://127.0.0.1:3506";

describe("offline frontend origin guard", () => {
  it.each(["/", "/chat", "/documents?sort=name", "/_next/static/chunks/app.js", "/icon.svg", "/apiary"])("allows configured firstparty GET/HEAD %s", (path) => {
    expect(offlineRequestViolation(baseURL + path, "GET", baseURL)).toBeNull();
    expect(offlineRequestViolation(baseURL + path, "HEAD", baseURL)).toBeNull();
  });
  it("uses the supplied viewport server origin rather than a hardcoded port", () => {
    const configured = "http://localhost:61234/test-root";
    expect(offlineRequestViolation("http://localhost:61234/chat", "GET", configured)).toBeNull();
    expect(offlineRequestViolation(baseURL + "/chat", "GET", configured)).toMatchObject({ reason: "different-origin" });
  });
  it.each([
    "http://127.0.0.1:11434/v1/chat/completions",
    "http://localhost:11434/v1/chat/completions",
    "http://127.0.0.1:8402/health",
    "http://localhost:3506/chat",
    "http://[::1]:3506/chat",
    "https://127.0.0.1:3506/chat",
    "https://api.openai.com/v1/responses",
    "http://127.0.0.1:3505/chat",
  ])("reports every different origin: %s", (url) => {
    expect(offlineRequestViolation(url, "GET", baseURL)).toMatchObject({ reason: "different-origin" });
  });
  it.each([
    "/api", "/api/", "/api/queries", "/API/queries", "/%61pi", "/%61pi/queries", "/api%2fqueries",
    "/%2fapi/queries", "/%2561pi/queries", "/api%252fqueries", "/prefix/%252e%252e/api/queries",
    "/%5capi/queries", "/api%3fprivate=value", "/api%23fragment",
  ])("reports API roots and encoded namespaces: %s", (path) => {
    expect(offlineRequestViolation(baseURL + path, "GET", baseURL)).toMatchObject({ reason: "api-namespace" });
  });
  it.each(["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT"])("reports firstparty %s writes", (method) => {
    expect(offlineRequestViolation(baseURL + "/chat", method, baseURL)).toMatchObject({ reason: "write-method" });
  });
  it.each(["ws://127.0.0.1:3506/events", "wss://127.0.0.1:3506/events", "ws://127.0.0.1:11434/events"])("reports every WebSocket: %s", (url) => {
    expect(offlineWebSocketViolation(url).reason).toBe("websocket");
  });
  it.each(["data:text/plain,local", "blob:http://127.0.0.1:3506/local", "about:blank"])("ignores browser-local non-network resources: %s", (url) => {
    expect(offlineRequestViolation(url, "GET", baseURL)).toBeNull();
    expect(offlineRequestViolation("http://127.0.0.1:8402/health", "GET", baseURL)).not.toBeNull();
  });
  it("fails closed on unsupported protocols, malformed URLs and malformed path encoding", () => {
    expect(offlineRequestViolation("file:///private/path", "GET", baseURL)).toMatchObject({ reason: "unsupported-protocol" });
    expect(offlineRequestViolation("invalid URL", "GET", baseURL)).toEqual({ reason: "invalid-request-url", origin: "unavailable" });
    expect(offlineRequestViolation(baseURL + "/%GG", "GET", baseURL)).toMatchObject({ reason: "invalid-path-encoding" });
  });
  it.each([undefined, "invalid base", "file:///tmp/site", "http://user:password@127.0.0.1:3506"])("requires an explicit valid credential-free HTTP frontend baseURL: %s", (configured) => {
    expect(() => offlineRequestViolation(baseURL, "GET", configured)).toThrow(/Offline guard requires/);
  });
  it("captures both actual event types and logs only reason/origin without credentials, query, path or fragment", () => {
    const handlers = new Map<string, (event: { url(): string; method(): string }) => void>();
    const page = { on(event: string, listener: (event: { url(): string; method(): string }) => void) { handlers.set(event, listener); } } as unknown as Page;
    const unexpected: string[] = [];
    installOfflineNetworkGuard(page, baseURL, unexpected);
    expect(Array.from(handlers.keys())).toEqual(["request", "websocket"]);
    handlers.get("request")!({ url: () => "http://user:password@127.0.0.1:8402/private-name?api_key=private-key#private-fragment", method: () => "POST" });
    handlers.get("websocket")!({ url: () => "ws://user:password@127.0.0.1:3506/private-name?token=private-key#private-fragment", method: () => "GET" });
    expect(unexpected).toEqual([
      "reason=different-origin; origin=http://127.0.0.1:8402",
      "reason=websocket; origin=ws://127.0.0.1:3506",
    ]);
    expect(unexpected.join(" ")).not.toMatch(/user|password|private-name|private-key|api_key|token|private-fragment/);
  });
});
