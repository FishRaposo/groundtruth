import type { QueryResponse, RetrievalTrace, SourceCitation, StreamEvent } from "@/types";

/**
 * Demo-mode fallback and forced portfolio demo.
 *
 * When NEXT_PUBLIC_DEMO_MODE=true, the UI runs entirely on local fixtures with
 * no backend dependency. When unset, the chat interface tries the real streaming
 * endpoint first and only falls back here on network failure.
 */

export const DEMO_FORCED = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export const DEMO_NOTICE =
  "Sample data — answers are simulated from the demo corpus.";

interface DemoEntry {
  match: RegExp;
  answer: string;
  sources: SourceCitation[];
  confidence: number;
  retrievalTrace: RetrievalTrace;
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

function buildRetrievalTrace(
  confidence: number,
  finalContextChunks: number,
  scores: Record<string, unknown>[] = []
): RetrievalTrace {
  return {
    query_embedding_dim: 384,
    vector_results: finalContextChunks > 0 ? 8 : 3,
    keyword_results: finalContextChunks > 0 ? 5 : 1,
    reranked_results: finalContextChunks > 0 ? 4 : 0,
    final_context_chunks: finalContextChunks,
    confidence,
    latency_ms: finalContextChunks > 0 ? 142 : 98,
    scores,
  };
}

const REMOTE_WORK_TRACE = buildRetrievalTrace(0.91, 2, [
  { chunk_id: "demo-chunk-1", score: 0.94 },
  { chunk_id: "demo-chunk-2", score: 0.88 },
]);

const SECURITY_TRACE = buildRetrievalTrace(0.91, 1, [
  { chunk_id: "demo-chunk-3", score: 0.91 },
]);

const REFUSAL_TRACE = buildRetrievalTrace(0.2, 0);

const DEMO_ENTRIES: DemoEntry[] = [
  {
    match: /remote|work from home|wfh/i,
    answer:
      "Employees may work remotely up to three days per week with manager " +
      "approval [1]. The arrangement must be recorded in the HR system before " +
      "it begins [2].",
    sources: REMOTE_WORK_SOURCES,
    confidence: 0.91,
    retrievalTrace: REMOTE_WORK_TRACE,
  },
  {
    match: /security|access|authentication|mfa/i,
    answer:
      "Production access requires multi-factor authentication and every access " +
      "event is logged for audit [1].",
    sources: SECURITY_SOURCES,
    confidence: 0.91,
    retrievalTrace: SECURITY_TRACE,
  },
];

const REFUSAL_ANSWER =
  "I couldn't find relevant information in the demo documents for that question. " +
  "Try asking about the remote work policy or security access.";

export interface PreloadedChatMessage {
  role: "user" | "assistant";
  content: string;
  sources: SourceCitation[];
  refused: boolean;
  refusalReason?: string;
  confidence?: number;
  retrievalTrace?: RetrievalTrace;
}

/** Preloaded chat transcript for forced portfolio demo mode. */
export function getPreloadedChatMessages(): PreloadedChatMessage[] {
  const remote = getDemoResponse("What is our remote work policy?");
  const salary = getDemoResponse("What are the salary bands?");

  return [
    {
      role: "user",
      content: "What is our remote work policy?",
      sources: [],
      refused: false,
    },
    {
      role: "assistant",
      content: remote.answer,
      sources: remote.sources,
      refused: false,
      confidence: remote.confidence,
      retrievalTrace: remote.retrievalTrace,
    },
    {
      role: "user",
      content: "What are the salary bands?",
      sources: [],
      refused: false,
    },
    {
      role: "assistant",
      content: salary.answer,
      sources: [],
      refused: true,
      refusalReason: salary.answer,
      confidence: salary.confidence,
      retrievalTrace: salary.retrievalTrace,
    },
  ];
}

/** Resolve a demo answer for a question (always returns something). */
export function getDemoResponse(question: string): {
  answer: string;
  sources: SourceCitation[];
  confidence: number;
  retrievalTrace: RetrievalTrace;
  refused: boolean;
} {
  for (const entry of DEMO_ENTRIES) {
    if (entry.match.test(question)) {
      return {
        answer: entry.answer,
        sources: entry.sources,
        confidence: entry.confidence,
        retrievalTrace: entry.retrievalTrace,
        refused: false,
      };
    }
  }
  return {
    answer: REFUSAL_ANSWER,
    sources: [],
    confidence: 0.2,
    retrievalTrace: REFUSAL_TRACE,
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
    yield { type: "refused", reason: demo.answer, retrieval_trace: demo.retrievalTrace };
    yield { type: "done", token_usage: { total_tokens: 0 } };
    return;
  }

  const words = demo.answer.split(" ");
  for (const word of words) {
    yield { type: "token", content: word + " " };
    if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
  }

  yield {
    type: "citations",
    sources: demo.sources,
    retrieval_trace: demo.retrievalTrace,
  };
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
    retrieval_trace: demo.retrievalTrace,
    refused: demo.refused,
    confidence: demo.confidence,
    token_usage: demo.refused ? null : { total_tokens: 48 },
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
