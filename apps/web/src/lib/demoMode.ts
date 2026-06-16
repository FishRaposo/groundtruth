import type { QueryResponse, SourceCitation, StreamEvent } from "@/types";

/**
 * Demo-mode fallback.
 *
 * When the backend API is unreachable (e.g. the static frontend is opened with
 * no server running), the UI degrades to a self-contained offline demo instead
 * of showing a hard error. This keeps the product explorable with zero backend.
 *
 * Demo mode is *opt-in via auto-detection*: the chat interface tries the real
 * streaming endpoint first and only falls back here when the fetch itself fails
 * (network error / connection refused), never when the server returns a real
 * application error.
 */

export const DEMO_NOTICE =
  "Demo mode: the backend is unavailable, so answers are simulated locally.";

interface DemoEntry {
  match: RegExp;
  answer: string;
  sources: SourceCitation[];
  confidence: number;
  refused?: boolean;
}

const REMOTE_WORK_SOURCES: SourceCitation[] = [
  {
    chunk_id: "demo-chunk-1",
    document_id: "demo-doc-remote",
    document_title: "Remote Work Policy",
    content_preview:
      "Employees may work remotely up to three days per week with manager approval.",
    relevance_score: 0.94,
    citation_index: 1,
  },
  {
    chunk_id: "demo-chunk-2",
    document_id: "demo-doc-remote",
    document_title: "Remote Work Policy",
    content_preview:
      "Remote arrangements must be documented in the HR system before they begin.",
    relevance_score: 0.88,
    citation_index: 2,
  },
];

const SECURITY_SOURCES: SourceCitation[] = [
  {
    chunk_id: "demo-chunk-3",
    document_id: "demo-doc-security",
    document_title: "Security Handbook",
    content_preview:
      "All production access requires multi-factor authentication and is logged.",
    relevance_score: 0.91,
    citation_index: 1,
  },
];

const DEMO_ENTRIES: DemoEntry[] = [
  {
    match: /remote|work from home|wfh/i,
    answer:
      "Employees may work remotely up to three days per week with manager " +
      "approval [1]. The arrangement must be recorded in the HR system before " +
      "it begins [2].",
    sources: REMOTE_WORK_SOURCES,
    confidence: 0.91,
  },
  {
    match: /security|access|authentication|mfa/i,
    answer:
      "Production access requires multi-factor authentication and every access " +
      "event is logged for audit [1].",
    sources: SECURITY_SOURCES,
    confidence: 0.91,
  },
];

const REFUSAL_ANSWER =
  "I couldn't find relevant information in the demo documents for that question. " +
  "Try asking about the remote work policy or security access.";

/** Resolve a demo answer for a question (always returns something). */
export function getDemoResponse(question: string): {
  answer: string;
  sources: SourceCitation[];
  confidence: number;
  refused: boolean;
} {
  for (const entry of DEMO_ENTRIES) {
    if (entry.match.test(question)) {
      return {
        answer: entry.answer,
        sources: entry.sources,
        confidence: entry.confidence,
        refused: false,
      };
    }
  }
  return {
    answer: REFUSAL_ANSWER,
    sources: [],
    confidence: 0.2,
    refused: true,
  };
}

/** Stream a demo response as StreamEvents, mirroring the real SSE shape. */
export async function* streamDemoResponse(
  question: string,
  delayMs = 0
): AsyncGenerator<StreamEvent> {
  const demo = getDemoResponse(question);

  if (demo.refused) {
    yield { type: "refused", reason: demo.answer };
    yield { type: "done", token_usage: { total_tokens: 0 } };
    return;
  }

  const words = demo.answer.split(" ");
  for (const word of words) {
    yield { type: "token", content: word + " " };
    if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
  }

  yield { type: "citations", sources: demo.sources };
  yield {
    type: "done",
    token_usage: { total_tokens: words.length },
  };
}

/** Build a non-streamed demo QueryResponse (for the non-SSE ask path). */
export function buildDemoQueryResponse(question: string): QueryResponse {
  const demo = getDemoResponse(question);
  return {
    id: "demo-query",
    question,
    answer: demo.refused ? null : demo.answer,
    sources: demo.sources,
    retrieval_trace: null,
    refused: demo.refused,
    confidence: demo.confidence,
    token_usage: null,
    created_at: new Date().toISOString(),
  };
}

/**
 * Whether an error thrown by a fetch should trigger demo-mode fallback.
 * Network failures (TypeError from fetch) qualify; application errors do not.
 */
export function isNetworkError(err: unknown): boolean {
  if (err instanceof TypeError) return true;
  if (err instanceof Error) {
    return /failed to fetch|network|connection|fetch failed/i.test(err.message);
  }
  return false;
}
