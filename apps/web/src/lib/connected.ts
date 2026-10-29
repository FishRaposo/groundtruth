/** Header-authenticated, cancellable local API boundary. Never substitutes fixtures. */
export class ConnectedClient {
  private controller = new AbortController();
  constructor(
    readonly baseUrl: string,
    private readonly key: string,
    readonly epoch = 0,
  ) {}
  close() {
    this.controller.abort();
  }
  async response(path: string, options: RequestInit = {}) {
    this.controller.signal.throwIfAborted();
    const headers = new Headers(options.headers);
    if (this.key) headers.set("X-API-Key", this.key);
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
      signal: this.controller.signal,
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail =
        typeof payload.detail === "string"
          ? payload.detail
          : `Request failed (${response.status}). Check the connection and your access.`;
      throw new Error(detail.replaceAll(this.key || "\0", "[redacted]"));
    }
    return response;
  }
  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await this.response(path, options);
    return response.status === 204 ? (undefined as T) : response.json();
  }
  async *events(
    path: string,
    options: RequestInit = {},
  ): AsyncGenerator<{
    event: string;
    id: string;
    data: Record<string, unknown>;
  }> {
    const response = await this.response(path, options);
    const reader = response.body?.getReader();
    if (!reader) throw new Error("The server returned no event stream.");
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        // Normalize after joining: a CRLF pair may span network chunks, just
        // as the UTF-8 decoder may need several chunks for one character.
        buffer = (buffer + decoder.decode(value, { stream: !done }))
          .replaceAll("\r\n", "\n");
        let boundary: number;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          let event = "message",
            id = "";
          const data: string[] = [];
          for (const line of block.split("\n")) {
            if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("id:")) id = line.slice(3).trim();
          }
          if (data.length)
            yield { event, id, data: JSON.parse(data.join("\n")) };
        }
        if (done) break;
      }
    } finally {
      await reader.cancel().catch(() => undefined);
      reader.releaseLock();
    }
  }
}
