import type { Page } from "@playwright/test";

type Violation = { reason: string; origin: string };

function frontendOrigin(baseURL: string | undefined) {
  if (!baseURL) throw new Error("Offline guard requires the configured frontend baseURL");
  const url = parsedURL(baseURL);
  if (!url || !["http:", "https:"].includes(url.protocol) || url.username || url.password)
    throw new Error("Offline guard requires an HTTP frontend origin without credentials");
  return url.origin;
}

function parsedURL(value: string): URL | null {
  try { return new URL(value); } catch { return null; }
}

function apiPathViolation(url: URL): string | null {
  let pathname = url.pathname;
  for (let depth = 0; depth < 8; depth++) {
    // Include encoded separators/dot segments and repeated encodings, so an API
    // root cannot become an allowed navigation merely through URL spelling.
    pathname = new URL(url.origin + pathname.replace(/\\/g, "/").replace(/\/{2,}/g, "/")).pathname;
    if (/^\/api(?:\/|$)/i.test(pathname)) return "api-namespace";
    let decoded: string;
    try { decoded = decodeURIComponent(pathname); } catch { return "invalid-path-encoding"; }
    if (decoded === pathname) return null;
    pathname = decoded;
  }
  return "ambiguous-path-encoding";
}

export function offlineRequestViolation(value: string, method: string, baseURL: string | undefined): Violation | null {
  const allowed = frontendOrigin(baseURL), url = parsedURL(value);
  if (!url) return { reason: "invalid-request-url", origin: "unavailable" };
  // These browser-local resources do not initiate a network connection. Any HTTP
  // request subsequently created by their content still passes this guard.
  if (["blob:", "data:", "about:"].includes(url.protocol)) return null;
  const origin = url.origin === "null" ? "opaque" : url.origin;
  if (!["http:", "https:"].includes(url.protocol)) return { reason: "unsupported-protocol", origin };
  if (origin !== allowed) return { reason: "different-origin", origin };
  if (url.username || url.password) return { reason: "request-credentials", origin };
  if (!["GET", "HEAD"].includes(method)) return { reason: "write-method", origin };
  const reason = apiPathViolation(url);
  return reason ? { reason, origin } : null;
}

export function offlineWebSocketViolation(value: string): Violation {
  const url = parsedURL(value);
  return { reason: "websocket", origin: url && url.origin !== "null" ? url.origin : "unavailable" };
}

/** Record attempted connections; assertions in both specs reject any violation. */
export function installOfflineNetworkGuard(page: Page, baseURL: string | undefined, unexpected: string[]) {
  frontendOrigin(baseURL);
  const record = (violation: Violation | null) => {
    if (violation) unexpected.push(`reason=${violation.reason}; origin=${violation.origin}`);
  };
  page.on("request", (request) => record(offlineRequestViolation(request.url(), request.method(), baseURL)));
  page.on("websocket", (socket) => record(offlineWebSocketViolation(socket.url())));
}
