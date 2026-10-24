"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  FileSearch,
  MessageSquarePlus,
  ShieldAlert,
} from "lucide-react";
import { API_URL, usePortfolio } from "./PortfolioProvider";
import { ConnectedClient } from "@/lib/connected";
import { Dialog, Notice, PageHeading, RuntimeSummary } from "./PortfolioShell";
import { sampleQuestion } from "@/lib/portfolioSample";
import type { Conversation, QueryResponse, SourceCitation } from "@/types";

export function SourceDrawer({
  source,
  close,
}: {
  source: SourceCitation;
  close: () => void;
}) {
  const passage =
    source.content || source.quoted_text || source.content_preview;
  const quote = source.quoted_text || source.content_preview;
  const position = quote ? passage.indexOf(quote) : -1;
  return (
    <Dialog
      title={`Source ${source.citation_index}: ${source.document_title}`}
      close={close}
    >
      <div className="gt-actions">
        <span className="gt-badge success">
          {source.source_status || "Status unknown"}
        </span>
        <span className="gt-badge">
          Version {source.document_version ?? "unknown"}
        </span>
      </div>
      <h3>Captured source passage</h3>
      <blockquote className="gt-passage">
        {position >= 0 ? (
          <>
            {passage.slice(0, position)}
            <mark>{quote}</mark>
            {passage.slice(position + quote.length)}
          </>
        ) : (
          passage
        )}
      </blockquote>
      <p className="gt-muted">
        The highlight is the exact quoted evidence saved with this answer.
        Current authorization is checked again when connected evidence is
        opened.
      </p>
      <details>
        <summary>Immutable source identity</summary>
        <dl className="gt-details">
          <dt>Document</dt>
          <dd>{source.document_id}</dd>
          <dt>Chunk</dt>
          <dd>{source.chunk_id}</dd>
          <dt>Content SHA-256</dt>
          <dd>
            {source.content_hash ||
              "Unknown — this historical response did not record a content hash."}
          </dd>
          <dt>Ranking score</dt>
          <dd>
            {source.relevance_score} · relevance signal, not a probability
          </dd>
        </dl>
      </details>
    </Dialog>
  );
}

export default function PortfolioChat() {
  const p = usePortfolio();
  const [question, setQuestion] = useState("");
  const [method, setMethod] = useState("reranked");
  const [scope, setScope] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<SourceCitation | null>(null);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const [useStreaming, setUseStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const activeRequest = useRef<ConnectedClient | null>(null);
  const restoredFromURL = useRef(false);
  const { source, client, sample, setSelectedQuery } = p;
  useEffect(() => () => activeRequest.current?.close(), []);
  const load = useCallback(
    async (id: string) => {
      setError(null);
      setBusy(true);
      try {
        const result =
          source === "sample"
            ? sample.queries.find((query) => query.id === id)
            : await client.request<QueryResponse>(
                `/api/queries/${encodeURIComponent(id)}`,
              );
        if (result) {
          setSelectedQuery(result);
          window.history.replaceState(
            null,
            "",
            `/chat?query=${encodeURIComponent(id)}`,
          );
        } else
          throw new Error(
            "This sample query no longer exists. Reset or ask a new question.",
          );
      } catch (failure) {
        if (!(failure instanceof DOMException && failure.name === "AbortError"))
          setError(
            failure instanceof Error
              ? failure.message
              : "Saved answer unavailable",
          );
      } finally {
        setBusy(false);
      }
    },
    [source, client, sample.queries, setSelectedQuery],
  );
  useEffect(() => {
    if (!p.ready || restoredFromURL.current) return;
    restoredFromURL.current = true;
    const id = new URLSearchParams(window.location.search).get("query");
    if (
      p.ready &&
      id &&
      p.selectedQuery?.id !== id &&
      (p.source === "connected" || p.sample.queries.some((q) => q.id === id))
    )
      void load(id);
  }, [p.ready, p.source, p.epoch, load, p.selectedQuery?.id, p.sample.queries]);
  const ask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      let result: QueryResponse;
      if (p.source === "sample")
        result = sampleQuestion(question.trim(), p.sample);
      else {
        const client = new ConnectedClient(API_URL, p.key);
        activeRequest.current = client;
        const options = {
          method: "POST",
          body: JSON.stringify({
            question: question.trim(),
            top_k: 5,
            retrieval_method: method,
            ...(scope ? { document_ids: [scope] } : {}),
            ...(p.conversation ? { conversation_id: p.conversation } : {}),
          }),
        };
        if (!useStreaming)
          result = await client.request<QueryResponse>("/api/queries", options);
        else {
          let completed: QueryResponse | null = null;
          setStreamText("");
          for await (const event of client.events(
            "/api/queries/stream",
            options,
          )) {
            const data = event.data;
            if (data.type === "token")
              setStreamText(
                (previous) => previous + String(data.content || ""),
              );
            if (data.type === "error")
              throw new Error(
                String(
                  data.message ||
                    data.error ||
                    "Generation interrupted; no completed answer was confirmed.",
                ),
              );
            if (data.type === "done" || data.type === "refused") {
              if (!data.id)
                throw new Error(
                  "The stream ended without a durable query identity.",
                );
              completed = data as unknown as QueryResponse;
              break;
            }
          }
          if (!completed)
            throw new Error(
              "The stream closed before a completed query was saved.",
            );
          result = completed;
        }
      }
      if (p.source === "sample")
        p.setSample((state) => ({
          ...state,
          queries: [...state.queries, result],
        }));
      p.setSelectedQuery(result);
      setQuestion("");
      window.history.replaceState(
        null,
        "",
        `/chat?query=${encodeURIComponent(result.id)}`,
      );
      await p.refresh();
    } catch (failure) {
      if (!(failure instanceof DOMException && failure.name === "AbortError"))
        setError(
          failure instanceof Error
            ? failure.message
            : "The question could not be completed.",
        );
    } finally {
      activeRequest.current?.close();
      activeRequest.current = null;
      setStreamText("");
      setBusy(false);
    }
  };
  const inspect = async (source: SourceCitation) => {
    setError(null);
    try {
      setDrawer(
        p.source === "sample"
          ? source
          : await p.client.request<SourceCitation>(
              `/api/queries/${encodeURIComponent(p.selectedQuery!.id)}/sources/${source.citation_index}`,
            ),
      );
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "This source is unavailable or your access changed.",
      );
    }
  };
  const createConversation = async () => {
    try {
      const response = await p.client.request<Conversation>(
        "/api/conversations",
        {
          method: "POST",
          body: JSON.stringify({ title: "Operational investigation" }),
        },
      );
      p.setConversation(response.id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not create conversation.",
      );
    }
  };
  const query =
    p.selectedQuery || (p.source === "sample" ? p.sample.queries.at(-1) : null);
  return (
    <>
      <PageHeading
        eyebrow="Investigate / Chat"
        title="Ask. Then inspect the evidence."
        description="A readable answer is the starting point. The versioned passage is what you can verify."
      />
      <RuntimeSummary />
      {p.error ? (
        <Notice error={p.error} retry={() => void p.refresh()} />
      ) : null}
      {error ? <Notice error={error} retry={() => void p.refresh()} /> : null}
      <div className="gt-chat-grid">
        <aside className="gt-panel gt-history">
          <h2>Investigation history</h2>
          {p.source === "connected" ? (
            <>
              <label className="gt-field">
                Conversation
                <select
                  value={p.conversation}
                  onChange={(event) => p.setConversation(event.target.value)}
                >
                  <option value="">All my conversations</option>
                  {p.conversations.map((conversation) => (
                    <option key={conversation.id} value={conversation.id}>
                      {conversation.title}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="btn-secondary"
                onClick={() => void createConversation()}
              >
                <MessageSquarePlus size={15} /> New conversation
              </button>
            </>
          ) : (
            <p className="gt-muted">
              One tab-local sample investigation. Reset clears every route
              together.
            </p>
          )}
          <div className="gt-history-list">
            {p.history.length ? (
              [...p.history].reverse().map((item) => (
                <button
                  key={item.id}
                  aria-current={query?.id === item.id ? "true" : undefined}
                  onClick={() => void load(item.id)}
                  disabled={busy}
                >
                  <span>{item.question}</span>
                  <small>{item.refused ? "Refused" : "Saved evidence"}</small>
                </button>
              ))
            ) : (
              <p className="gt-muted">
                {p.loading
                  ? "Loading saved investigations…"
                  : "Your questions and saved answers will appear here."}
              </p>
            )}
          </div>
        </aside>
        <section className="gt-chat-body">
          <form
            className="gt-panel gt-question"
            onSubmit={(event) => void ask(event)}
          >
            <label htmlFor="question">What do you need to know?</label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about your documents…"
              rows={3}
              disabled={busy}
            />
            <div className="gt-form-options">
              <label className="gt-field">
                Retrieval method
                <select
                  value={method}
                  onChange={(event) => setMethod(event.target.value)}
                >
                  <option value="reranked">Hybrid + heuristic reranking</option>
                  <option value="hybrid">Hybrid RRF</option>
                  <option value="vector">Vector similarity</option>
                  <option value="keyword">Keyword</option>
                </select>
              </label>
              <label className="gt-field">
                Document scope
                <select
                  value={scope}
                  onChange={(event) => setScope(event.target.value)}
                >
                  <option value="">All authorized documents</option>
                  {p.documents
                    .filter((d) => d.status === "ready")
                    .map((doc) => (
                      <option value={doc.id} key={doc.id}>
                        {doc.title}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="btn-primary"
                type="submit"
                disabled={busy || !question.trim() || !p.ready}
              >
                {busy ? "Retrieving evidence…" : "Ask question"}
                <ArrowRight size={16} />
              </button>
            </div>
            {p.source === "connected" ? (
              <label className="gt-checkbox">
                <input
                  type="checkbox"
                  checked={useStreaming}
                  onChange={(event) => setUseStreaming(event.target.checked)}
                  disabled={busy}
                />{" "}
                Stream the actual answer (SSE)
              </label>
            ) : null}
            {busy ? (
              <div role="status" className="gt-notice">
                <p>{streamText || "Retrieving authorized evidence…"}</p>
                {p.source === "connected" ? (
                  <button
                    className="btn-secondary"
                    type="button"
                    onClick={() => {
                      activeRequest.current?.close();
                      setError(
                        "Request cancelled. No completed answer has been confirmed.",
                      );
                    }}
                  >
                    Cancel request
                  </button>
                ) : null}
              </div>
            ) : null}
            <div className="gt-suggestions">
              {[
                "How do I roll back staging safely?",
                "What is the CEO salary?",
                "Which conflicting database procedure applies?",
              ].map((text) => (
                <button
                  type="button"
                  key={text}
                  onClick={() => setQuestion(text)}
                >
                  {text}
                </button>
              ))}
            </div>
            <small>
              Suggested questions prepare the request. You decide when to send
              it.
            </small>
          </form>
          {query ? (
            <article
              className="gt-panel gt-answer"
              aria-label="Answer and evidence"
            >
              <div className="gt-answer-heading">
                <span
                  className={`gt-badge ${query.refused ? "warning" : query.outcome === "error" || query.outcome === "interrupted" ? "danger" : "success"}`}
                >
                  {query.refused ? (
                    <ShieldAlert size={14} />
                  ) : (
                    <Check size={14} />
                  )}{" "}
                  {query.outcome ||
                    (query.refused ? "refused" : "Legacy outcome unknown")}
                </span>
                <small>
                  {query.execution_mode || "Legacy execution mode unknown"}
                </small>
              </div>
              <h2>{query.question}</h2>
              <ol
                className="gt-pipeline"
                aria-label="Question to answer stages"
              >
                {[
                  "Question",
                  "Authorized retrieval",
                  "Source evidence",
                  query.refused ? "Refusal / review" : "Answer",
                ].map((stage, index) => (
                  <li key={stage}>
                    <span>{index + 1}</span>
                    {stage}
                  </li>
                ))}
              </ol>
              {query.evidence_access === "restricted" ? (
                <div className="gt-notice warning">
                  Your source access has changed. Saved answer content is
                  withheld.
                </div>
              ) : (
                <div
                  className={`gt-answer-text ${query.refused ? "gt-refusal" : ""}`}
                >
                  <p>
                    {query.answer ||
                      query.refusal_reason ||
                      (query.refused
                        ? "Insufficient authorized evidence. No answer was generated."
                        : "No completed answer was saved.")}
                  </p>
                </div>
              )}
              <section aria-label="Answer sources">
                <h3>
                  {query.sources.length
                    ? "Inspect the sources"
                    : "No answer citations"}
                </h3>
                {query.sources.map((source) => (
                  <button
                    className="gt-source-card"
                    key={`${source.chunk_id}-${source.citation_index}`}
                    onClick={() => void inspect(source)}
                  >
                    <span className="gt-source-number">
                      {source.citation_index}
                    </span>
                    <span>
                      <strong>{source.document_title}</strong>
                      <small>
                        Version {source.document_version ?? "unknown"} ·{" "}
                        {source.source_status || "historical status unknown"}
                      </small>
                      <span>
                        {source.quoted_text || source.content_preview}
                      </span>
                    </span>
                    <FileSearch size={20} />
                  </button>
                ))}
              </section>
              <details className="gt-trace">
                <summary>Retrieval trace & provenance</summary>
                <p className="gt-muted">
                  Scores are ranking/support signals, not calibrated confidence
                  probabilities. Historical missing fields remain unknown.
                </p>
                <pre>
                  {JSON.stringify(
                    {
                      retrieval: query.retrieval_trace,
                      provenance: query.provenance || "unknown",
                      token_usage: query.token_usage,
                      query_id: query.id,
                      conversation_id: query.conversation_id || "unknown",
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </article>
          ) : (
            <div className="gt-empty">
              <FileSearch size={35} />
              <h2>Begin with a question</h2>
              <p>
                Upload a document or use a suggested request. An answer will
                show exactly which passage supports it.
              </p>
            </div>
          )}
        </section>
      </div>
      {drawer ? <SourceDrawer source={drawer} close={closeDrawer} /> : null}
    </>
  );
}
