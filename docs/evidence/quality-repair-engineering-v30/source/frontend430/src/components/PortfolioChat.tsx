"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  FileSearch,
  MessageSquarePlus,
  ShieldAlert,
  AlertTriangle,
} from "lucide-react";
import { API_URL, usePortfolio } from "./PortfolioProvider";
import { ConnectedClient } from "@/lib/connected";
import { Dialog, Notice, PageHeading, RuntimeSummary } from "./PortfolioShell";
import { sampleQuestion } from "@/lib/portfolioSample";
import type { Conversation, QueryResponse, SourceCitation } from "@/types";
import AnswerSelectionEvidence, { selectionRecord, selectionFailureMessage } from "./AnswerSelectionEvidence";

export function SourceDrawer({
  source,
  close,
  sampleData = false,
}: {
  source: SourceCitation;
  close: () => void;
  sampleData?: boolean;
}) {
  const quote = source.quoted_text;
  const points = Array.from(quote || "");
  const spans = source.answer_spans;
  const valid = !!quote && !!spans?.length && spans.every((span, index) => {
    const previousEnd = spans[index - 1]?.end || 0;
    return Number.isInteger(span.start) && Number.isInteger(span.end) &&
      span.start >= previousEnd && span.end > span.start && span.end <= points.length &&
      points.slice(span.start, span.end).join("") === span.text;
  });
  return (
    <Dialog
      title={`Source ${source.citation_index}: ${source.document_title}`}
      close={close}
      sampleData={sampleData}
    >
      <div className="gt-actions">
        <span className={`gt-badge ${source.source_status ? "success" : ""}`}>
          {source.source_status || "Status unknown"}
        </span>
        <span className="gt-badge">
          Version {source.document_version ?? "unknown"}
        </span>
        {source.score_status === "not_ranked" ? <span className="gt-badge">Procedure context · not ranked</span> : null}
      </div>
      <h3>Captured source passage</h3>
      <blockquote className="gt-passage" aria-label="Canonical quoted evidence">
        {valid ? <>
          {spans!.map((span, index) => {
            const prefix = points.slice(spans![index - 1]?.end || 0, span.start).join("");
            return <span key={`${span.start}-${span.end}`}>{prefix}<mark data-answer-span="true">{span.text}</mark></span>;
          })}
          {points.slice(spans!.at(-1)!.end).join("")}
        </> : quote ? spans === undefined ? <mark data-canonical-passage="true">{quote}</mark> : quote : source.content || source.content_preview}
      </blockquote>
      <p className="gt-muted">
        {valid ? "Highlighted answer spans exactly match the saved canonical quote. Offsets use Unicode codepoints relative to this quote."
          : spans?.length ? "Saved answer spans could not be verified against the canonical quote; no answer span highlight is shown."
            : spans ? "No answer spans were recorded for this source."
              : "Answer span metadata unknown : this historical response did not record selected spans." + (quote ? " The canonical passage is highlighted in full." : "")}
        {" "}Current authorization is checked again when connected evidence is opened.
      </p>
      {!quote ? <p className="gt-muted">Canonical quote unavailable : showing only the captured context or preview; selected evidence cannot be verified.</p> : null}
      {source.content && source.content !== quote ? <details>
        <summary>Captured source context</summary>
        <blockquote className="gt-passage">{source.content}</blockquote>
      </details> : null}
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
              "Unknown : this historical response did not record a content hash."}
          </dd>
          <dt>Ranking score</dt>
          <dd>
            {source.score_status === "not_ranked" ? "Not ranked: loaded to complete the procedure." : <>{source.relevance_score} · relevance signal, not a probability</>}
          </dd>
          <dt>Answer span offsets</dt>
          <dd>{spans ? JSON.stringify(spans.map(({ start, end }) => ({ start, end }))) + " · Unicode codepoints, end exclusive" : "Unknown : no selected spans were recorded."}</dd>
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
  const [useStreaming, setUseStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [creatingConversation, setCreatingConversation] = useState(false);
  const creationInFlight = useRef(false);
  const activityGeneration = useRef(0);
  const activeRequest = useRef<ConnectedClient | null>(null);
  const failedSavedRead = useRef<string | null>(null);
  const inspectionGeneration = useRef(0);
  const activeInspection = useRef<ConnectedClient | null>(null);
  const cancelInspection = useCallback(() => {
    inspectionGeneration.current += 1;
    activeInspection.current?.close();
    activeInspection.current = null;
  }, []);
  const closeDrawer = useCallback(() => {
    cancelInspection();
    setDrawer(null);
  }, [cancelInspection]);
  const restoredFromURL = useRef(false);
  const { source, client, sample, setSelectedQuery } = p;
  useEffect(() => {
    const invalidate = () => {
      activityGeneration.current += 1;
      activeRequest.current?.close();
      activeRequest.current = null;
      failedSavedRead.current = null;
      cancelInspection();
      creationInFlight.current = false;
    };
    invalidate();
    setBusy(false);
    setCreatingConversation(false);
    setDrawer(null);
    setError(null);
    setStreamText("");
    return invalidate;
  }, [source, client, p.epoch, p.conversation, cancelInspection]);
  useEffect(() => {
    setQuestion("");
    setScope("");
  }, [source, p.key]);
  const load = useCallback(
    async (id: string) => {
      const token = ++activityGeneration.current;
      activeRequest.current?.close();
      cancelInspection();
      setDrawer(null);
      const ownedClient = source === "connected"
        ? new ConnectedClient(API_URL, p.key, p.epoch)
        : null;
      activeRequest.current = ownedClient;
      failedSavedRead.current = null;
      setError(null);
      setBusy(true);
      try {
        const result =
          source === "sample"
            ? sample.queries.find((query) => query.id === id)
            : await ownedClient!.request<QueryResponse>(
                `/api/queries/${encodeURIComponent(id)}`,
              );
        if (token !== activityGeneration.current) return;
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
        if (token === activityGeneration.current && !(failure instanceof DOMException && failure.name === "AbortError")) {
          failedSavedRead.current = id;
          setError(
            failure instanceof Error
              ? failure.message
              : "Saved answer unavailable",
          );
        }
      } finally {
        ownedClient?.close();
        if (activeRequest.current === ownedClient) activeRequest.current = null;
        if (token === activityGeneration.current) setBusy(false);
      }
    },
    [source, p.key, p.epoch, sample.queries, setSelectedQuery, cancelInspection],
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
    if (!question.trim() || busy || creationInFlight.current) return;
    const token = ++activityGeneration.current;
    cancelInspection();
    setDrawer(null);
    let ownedClient: ConnectedClient | null = null;
    setBusy(true);
    failedSavedRead.current = null;
    setError(null);
    try {
      let result: QueryResponse;
      if (p.source === "sample")
        result = sampleQuestion(question.trim(), p.sample);
      else {
        const client = new ConnectedClient(API_URL, p.key, p.epoch);
        ownedClient = client;
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
            if (token !== activityGeneration.current) break;
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
      if (token !== activityGeneration.current) return;
      // The durable outcome replaces provisional tokens before any background
      // history request can delay their retraction, including a late refusal.
      setStreamText("");
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
      if (token === activityGeneration.current && !(failure instanceof DOMException && failure.name === "AbortError"))
        setError(
          failure instanceof Error
            ? failure.message
            : "The question could not be completed.",
        );
    } finally {
      ownedClient?.close();
      if (activeRequest.current === ownedClient) activeRequest.current = null;
      if (token === activityGeneration.current) {
        setStreamText("");
        setBusy(false);
      }
    }
  };
  const inspect = async (source: SourceCitation) => {
    cancelInspection();
    const token = inspectionGeneration.current;
    const contextToken = activityGeneration.current;
    const ownedClient = p.source === "connected"
      ? new ConnectedClient(API_URL, p.key, p.epoch)
      : null;
    activeInspection.current = ownedClient;
    const current = () => token === inspectionGeneration.current && contextToken === activityGeneration.current;
    setDrawer(null);
    failedSavedRead.current = null;
    setError(null);
    try {
      const result =
        p.source === "sample"
          ? source
          : await ownedClient!.request<SourceCitation>(
              `/api/queries/${encodeURIComponent(p.selectedQuery!.id)}/sources/${source.citation_index}`,
            );
      if (current()) setDrawer(result);
    } catch (failure) {
      if (current() && !(failure instanceof DOMException && failure.name === "AbortError")) setError(
        failure instanceof Error
          ? failure.message
          : "This source is unavailable or your access changed.",
      );
    } finally {
      ownedClient?.close();
      if (activeInspection.current === ownedClient) activeInspection.current = null;
    }
  };
  const createConversation = async () => {
    if (busy || creationInFlight.current) return;
    creationInFlight.current = true;
    setCreatingConversation(true);
    const token = ++activityGeneration.current;
    cancelInspection();
    setDrawer(null);
    failedSavedRead.current = null;
    setError(null);
    try {
      const response = await p.client.request<Conversation>(
        "/api/conversations",
        {
          method: "POST",
          body: JSON.stringify({ title: "Operational investigation" }),
        },
      );
      if (token === activityGeneration.current) p.setConversation(response.id);
    } catch (failure) {
      if (token === activityGeneration.current && !(failure instanceof DOMException && failure.name === "AbortError")) setError(
        failure instanceof Error
          ? failure.message
          : "Could not create conversation.",
      );
    } finally {
      if (token === activityGeneration.current) {
        creationInFlight.current = false;
        setCreatingConversation(false);
      }
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
      {error ? <Notice error={error} retry={() => {
        const id = failedSavedRead.current;
        if (id) void load(id);
        else void p.refresh();
      }} /> : null}
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
                disabled={busy || creatingConversation}
                onClick={() => void createConversation()}
              >
                <MessageSquarePlus size={15} /> {creatingConversation ? "Creating conversation…" : "New conversation"}
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
                  disabled={busy || creatingConversation}
                >
                  <span>{item.question}</span>
                  <small>{item.outcome === "error" ? "Execution failed" : item.outcome === "interrupted" ? "Interrupted" : item.refused ? "Refused" : item.outcome === "completed" ? "Saved evidence" : "Historical outcome unknown"}</small>
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
                disabled={busy || creatingConversation || !question.trim() || !p.ready}
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
                      activityGeneration.current += 1;
                      activeRequest.current?.close();
                      activeRequest.current = null;
                      setStreamText("");
                      setBusy(false);
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
                  {query.outcome === "error" || query.outcome === "interrupted" ? <AlertTriangle size={14} /> : query.refused ? (
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
                  query.outcome === "error" ? "Execution failed" : query.refused ? "Refusal / review" : "Answer",
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
                    {query.outcome === "error" ? selectionFailureMessage(query.provenance?.answer_selection) : query.answer ||
                      query.refusal_reason ||
                      (query.refused
                        ? "Insufficient authorized evidence. No answer was generated."
                        : "No completed answer was saved.")}
                  </p>
                </div>
              )}
              <AnswerSelectionEvidence value={query.provenance?.answer_selection} question={query.question} answer={query.answer} sources={query.sources} retrievalTrace={query.retrieval_trace} />
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
      {drawer ? <SourceDrawer source={drawer} close={closeDrawer} sampleData={p.source === "sample"} /> : null}
    </>
  );
}
