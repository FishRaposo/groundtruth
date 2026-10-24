"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  Conversation,
  Document,
  Identity,
  QueryListItem,
  QueryResponse,
} from "@/types";
import { ConnectedClient } from "@/lib/connected";
import { createSampleState, type SampleState } from "@/lib/portfolioSample";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8400";
const forcedSample = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
const SOURCE_KEY = "groundtruth.source.v1",
  KEY_KEY = "groundtruth.api-key.v1",
  CONVERSATION_KEY = "groundtruth.conversation.v1";
type Source = "sample" | "connected";
interface PortfolioContext {
  source: Source;
  ready: boolean;
  epoch: number;
  key: string;
  connect: (key: string) => void;
  setSource: (source: Source) => void;
  client: ConnectedClient;
  documents: Document[];
  history: QueryListItem[];
  identity: Identity | null;
  conversations: Conversation[];
  conversation: string;
  setConversation: (id: string) => void;
  refresh: () => Promise<void>;
  loading: boolean;
  error: string | null;
  runtime: Record<string, unknown> | null;
  sample: SampleState;
  setSample: React.Dispatch<React.SetStateAction<SampleState>>;
  selectedQuery: QueryResponse | null;
  setSelectedQuery: React.Dispatch<React.SetStateAction<QueryResponse | null>>;
  tour: number | null;
  setTour: React.Dispatch<React.SetStateAction<number | null>>;
  reset: () => void;
}
const Context = createContext<PortfolioContext | null>(null);
function clearSavedQueryURL() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (url.searchParams.has("query")) {
    url.searchParams.delete("query");
    window.history.replaceState(
      null,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    );
  }
}
export function usePortfolio() {
  const context = useContext(Context);
  if (!context) throw new Error("PortfolioProvider is required");
  return context;
}

export default function PortfolioProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [source, updateSource] = useState<Source>("sample");
  const [key, setKey] = useState("");
  const [ready, setReady] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const generation = useRef(0);
  const [sample, setSample] = useState(createSampleState);
  const [selectedQuery, setSelectedQuery] = useState<QueryResponse | null>(
    null,
  );
  const [tour, setTour] = useState<number | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [history, setHistory] = useState<QueryListItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, updateConversation] = useState("");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [runtime, setRuntime] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const client = useMemo(
    () => new ConnectedClient(API_URL, key, epoch),
    [key, epoch],
  );
  useEffect(() => {
    try {
      updateSource(
        forcedSample
          ? "sample"
          : localStorage.getItem(SOURCE_KEY) === "connected"
            ? "connected"
            : "sample",
      );
      setKey(sessionStorage.getItem(KEY_KEY) || "");
      updateConversation(sessionStorage.getItem(CONVERSATION_KEY) || "");
    } catch {
      /* Storage unavailable: the explicit source control still works. */
    }
    setReady(true);
  }, []);
  const clear = useCallback(() => {
    clearSavedQueryURL();
    generation.current += 1;
    client.close();
    setEpoch((value) => value + 1);
    setDocuments([]);
    setHistory([]);
    setConversations([]);
    setIdentity(null);
    setRuntime(null);
    setSelectedQuery(null);
    setError(null);
    setLoading(false);
    setTour(null);
  }, [client]);
  const setSource = useCallback(
    (next: Source) => {
      if (forcedSample && next === "connected") return;
      clear();
      updateSource(next);
      try {
        localStorage.setItem(SOURCE_KEY, next);
      } catch {
        /* Optional preference. */
      }
    },
    [clear],
  );
  const connect = useCallback(
    (nextKey: string) => {
      clear();
      setKey(nextKey);
      updateConversation("");
      try {
        sessionStorage.setItem(KEY_KEY, nextKey);
        sessionStorage.removeItem(CONVERSATION_KEY);
      } catch {
        /* Key stays in tab memory. */
      }
      if (!forcedSample) {
        updateSource("connected");
        try {
          localStorage.setItem(SOURCE_KEY, "connected");
        } catch {
          /* Optional preference. */
        }
      }
    },
    [clear],
  );
  const setConversation = useCallback(
    (id: string) => {
      clearSavedQueryURL();
      generation.current += 1;
      client.close();
      setEpoch((value) => value + 1);
      setSelectedQuery(null);
      setHistory([]);
      updateConversation(id);
      try {
        sessionStorage.setItem(CONVERSATION_KEY, id);
      } catch {
        /* Optional preference. */
      }
    },
    [client],
  );
  const refresh = useCallback(async () => {
    if (!ready || source !== "connected") return;
    const token = generation.current;
    setLoading(true);
    setError(null);
    try {
      const [user, docs, queries, sessions, health] = await Promise.all([
        client.request<Identity>("/api/identity"),
        client.request<{ documents: Document[] }>("/api/documents?limit=100"),
        client.request<{ queries: QueryListItem[] }>(
          `/api/queries?limit=50${conversation ? `&conversation_id=${encodeURIComponent(conversation)}` : ""}`,
        ),
        client.request<Conversation[] | { conversations: Conversation[] }>(
          "/api/conversations",
        ),
        client.request<Record<string, unknown>>("/api/health"),
      ]);
      if (token !== generation.current) return;
      setIdentity(user);
      setDocuments(docs.documents);
      setHistory(queries.queries);
      setConversations(
        Array.isArray(sessions) ? sessions : sessions.conversations,
      );
      setRuntime(health);
    } catch (failure) {
      if (
        token === generation.current &&
        !(failure instanceof DOMException && failure.name === "AbortError")
      )
        setError(
          failure instanceof Error
            ? failure.message
            : "The connected application is unavailable.",
        );
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }, [ready, source, client, conversation]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const reset = useCallback(() => {
    clearSavedQueryURL();
    setEpoch((value) => value + 1);
    setSample(createSampleState());
    setSelectedQuery(null);
    setTour(null);
  }, []);
  return (
    <Context.Provider
      value={{
        source,
        ready,
        epoch,
        key,
        connect,
        setSource,
        client,
        documents: source === "sample" ? sample.documents : documents,
        history: source === "sample" ? sample.queries : history,
        identity,
        conversations,
        conversation,
        setConversation,
        refresh,
        loading,
        error,
        runtime,
        sample,
        setSample,
        selectedQuery,
        setSelectedQuery,
        tour,
        setTour,
        reset,
      }}
    >
      {children}
    </Context.Provider>
  );
}
