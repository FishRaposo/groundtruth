"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import SourceCitation from "./SourceCitation";
import RetrievalTrace from "./RetrievalTrace";
import RefusalMessage from "./RefusalMessage";
import CitationText from "./CitationText";
import { apiClient } from "@/lib/api";
import {
  DEMO_NOTICE,
  isNetworkError,
  streamDemoResponse,
} from "@/lib/demoMode";
import type {
  QueryResponse,
  StreamEvent,
  SourceCitation as SourceCitationType,
  QueryListItem,
} from "@/types";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources: SourceCitationType[];
  refused: boolean;
  refusalReason?: string;
  confidence?: number;
  retrievalTrace?: QueryResponse["retrieval_trace"];
  streaming?: boolean;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState<string>("");
  const [streaming, setStreaming] = useState<boolean>(false);
  const [demoMode, setDemoMode] = useState<boolean>(false);
  const [showTrace, setShowTrace] = useState<Record<string, boolean>>({});
  const [queryHistory, setQueryHistory] = useState<QueryListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [highlightedCitation, setHighlightedCitation] = useState<Record<string, number>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const applyEvent = useCallback((event: StreamEvent): void => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last.role !== "assistant") return prev;
      if (event.type === "token") {
        updated[updated.length - 1] = {
          ...last,
          content: last.content + event.content,
        };
      } else if (event.type === "citations") {
        updated[updated.length - 1] = {
          ...last,
          sources: event.sources,
          retrievalTrace: event.retrieval_trace,
        };
      } else if (event.type === "refused") {
        updated[updated.length - 1] = {
          ...last,
          refused: true,
          refusalReason: event.reason,
          content: event.reason,
          retrievalTrace: event.retrieval_trace,
        };
      } else if (event.type === "done") {
        updated[updated.length - 1] = { ...last, streaming: false };
      }
      return updated;
    });
  }, []);

  const scrollToBottom = useCallback((): void => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    let active = true;
    apiClient.getQueryHistory(8)
      .then((response) => {
        if (active && response.queries.length > 0) setQueryHistory(response.queries);
      })
      .catch(() => {
        // History is additive; chat remains usable if the endpoint is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  const loadPersistedQuery = async (queryId: string): Promise<void> => {
    try {
      setHistoryLoading(true);
      const query = await apiClient.getQueryDetail(queryId);
      setMessages([
        { role: "user", content: query.question, sources: [], refused: false },
        {
          role: "assistant",
          content: query.answer || "",
          sources: query.sources,
          refused: query.refused,
          confidence: query.confidence ?? undefined,
          retrievalTrace: query.retrieval_trace,
          refusalReason: query.refused ? query.answer || "Insufficient grounded evidence." : undefined,
        },
      ]);
      setShowTrace({});
      setHighlightedCitation({});
    } finally {
      setHistoryLoading(false);
    }
  };

  const highlightCitation = (messageIndex: number, citationIndex: number): void => {
    setHighlightedCitation((current) => ({ ...current, [String(messageIndex)]: citationIndex }));
    document.getElementById(`source-citation-${messageIndex}-${citationIndex}`)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    const question = input.trim();
    if (!question || streaming) return;

    setInput("");
    setStreaming(true);

    const userMessage: ChatMessage = { role: "user", content: question, sources: [], refused: false };
    const assistantMessage: ChatMessage = {
      role: "assistant",
      content: "",
      sources: [],
      refused: false,
      streaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    try {
      const stream = apiClient.streamQuestion({ question });
      for await (const event of stream) {
        applyEvent(event);
      }
    } catch (err) {
      if (isNetworkError(err)) {
        // Backend unreachable: degrade gracefully to offline demo mode.
        setDemoMode(true);
        // Reset the in-progress assistant message before replaying demo events.
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: "",
              sources: [],
              refused: false,
              streaming: true,
            };
          }
          return updated;
        });
        try {
          for await (const event of streamDemoResponse(question)) {
            applyEvent(event);
          }
        } catch {
          applyEvent({ type: "done", token_usage: { total_tokens: 0 } });
        }
      } else {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: err instanceof Error ? err.message : "An error occurred",
              sources: [],
              refused: true,
              streaming: false,
            };
          }
          return updated;
        });
      }
    } finally {
      setStreaming(false);
    }
  };

  const toggleTrace = (messageIndex: number): void => {
    setShowTrace((prev) => ({
      ...prev,
      [String(messageIndex)]: !prev[String(messageIndex)],
    }));
  };

  return (
    <div className="flex flex-col">
      {demoMode && (
        <div
          role="status"
          data-testid="demo-banner"
          className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800"
        >
          {DEMO_NOTICE}
        </div>
      )}
      {queryHistory.length > 0 && (
        <section aria-label="Persisted query history" className="mb-4 rounded-lg border border-gray-200 bg-white p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Recent queries</p>
            {historyLoading && <span className="text-xs text-gray-400">Loading trace…</span>}
          </div>
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {queryHistory.map((query) => (
              <button
                key={query.id}
                type="button"
                onClick={() => void loadPersistedQuery(query.id)}
                disabled={historyLoading}
                className="max-w-52 shrink-0 truncate rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-left text-xs text-gray-700 hover:border-brand-300 hover:bg-brand-50 disabled:opacity-50"
              >
                {query.question}
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="mb-4 max-h-[60vh] space-y-4 overflow-y-auto">
        {messages.length === 0 && (
          <div className="py-12 text-center text-gray-500">
            Ask a question about your uploaded documents.
          </div>
        )}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`rounded-lg p-4 ${
              msg.role === "user" ? "bg-brand-50 ml-12" : "bg-white border border-gray-200 mr-12"
            }`}
          >
            <p className="whitespace-pre-wrap text-sm text-gray-800">
              {msg.role === "assistant" && !msg.refused ? (
                <CitationText
                  text={msg.content}
                  sources={msg.sources}
                  onCitationClick={(citationIndex) => highlightCitation(idx, citationIndex)}
                />
              ) : (
                msg.content
              )}
              {msg.streaming && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-brand-600 align-text-bottom" />
              )}
            </p>

            {msg.refused && msg.role === "assistant" && (
              <RefusalMessage
                reason={msg.content}
                confidence={msg.confidence}
                suggestion="Try rephrasing your question or uploading more relevant documents."
              />
            )}

            {msg.retrievalTrace && msg.retrievalTrace.confidence >= 0.5 && msg.retrievalTrace.confidence < 0.7 && !msg.refused && msg.role === "assistant" && (
              <div className="mt-3 rounded-md border border-yellow-250 bg-yellow-50 p-3 text-xs text-yellow-800">
                <div className="flex items-center gap-1.5 font-semibold">
                  <span>⚠️</span>
                  <span>Low Confidence Answer</span>
                </div>
                <p className="mt-1 text-yellow-700">
                  The retrieved document passages are only partially related. Please verify the sources below carefully.
                </p>
              </div>
            )}

            {msg.sources.length > 0 && (
              <div className="mt-3 space-y-2">
                <p className="text-xs font-medium text-gray-500">Sources:</p>
                {msg.sources.map((source) => (
                  <SourceCitation
                    key={source.chunk_id}
                    citation={source}
                    highlighted={highlightedCitation[String(idx)] === source.citation_index}
                    anchorId={`source-citation-${idx}-${source.citation_index}`}
                  />
                ))}
              </div>
            )}

            {msg.retrievalTrace && msg.role === "assistant" && (
              <div className="mt-3">
                <button
                  onClick={() => toggleTrace(idx)}
                  className="text-xs text-brand-600 hover:underline"
                >
                  {showTrace[String(idx)] ? "Hide" : "Show"} Retrieval Trace
                </button>
                {showTrace[String(idx)] && (
                  <RetrievalTrace trace={msg.retrievalTrace} />
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your documents..."
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          disabled={streaming}
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="btn-primary disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
