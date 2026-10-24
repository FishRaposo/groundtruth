"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Database,
  FileText,
  Layers,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { API_URL, usePortfolio } from "./PortfolioProvider";
import { createSampleState, sampleQuestion } from "@/lib/portfolioSample";

export const TOUR = [
  {
    title: "Ask a real operational question",
    description:
      "The staging rollback answer is tied to a current, immutable runbook passage. Open its citation to inspect the evidence.",
    route: "/chat",
    question: "How do I roll back staging safely?",
  },
  {
    title: "The procedure changed",
    description:
      "Compare the previous rollback instructions with the published revision. Old answers retain the original version and hash.",
    route: "/documents",
    question: null,
  },
  {
    title: "No evidence, no invented answer",
    description:
      "Salary information is absent from these runbooks. The application refuses rather than treating a plausible response as evidence.",
    route: "/chat",
    question: "What is the CEO salary?",
  },
  {
    title: "Conflicting procedures need review",
    description:
      "The curated database procedure group disagrees. This explicit conflict is sent for human resolution, not silently combined.",
    route: "/chat",
    question: "Which conflicting database procedure applies?",
  },
  {
    title: "A failed attachment stays quarantined",
    description:
      "Inspect the failure, then simulate a retry. The rest of the collection remains available throughout.",
    route: "/documents",
    question: null,
  },
  {
    title: "Inspect the actual application",
    description:
      "The sample uses no network services. Connect to the local API for actual ingestion, retrieval, permissions and saved evidence.",
    route: "/workflow",
    question: null,
  },
];

export function Notice({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  const { setSource } = usePortfolio();
  return (
    <div className="gt-notice error" role="alert">
      <strong>Connection or operation failed</strong>
      <p>{error}</p>
      <p>Results have not been replaced with sample data.</p>
      <div className="gt-actions">
        {retry ? (
          <button className="btn-secondary" onClick={retry}>
            Retry
          </button>
        ) : null}
        <button className="btn-secondary" onClick={() => setSource("sample")}>
          Explore sample data
        </button>
      </div>
    </div>
  );
}

export function Dialog({
  title,
  children,
  close,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    const panel = ref.current;
    panel?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
      if (event.key !== "Tab" || !panel) return;
      const controls = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input,select,textarea,summary,[tabindex="0"]',
        ),
      );
      const first = controls[0],
        last = controls.at(-1);
      if (!first) {
        event.preventDefault();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === panel)
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || document.activeElement === panel)
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    panel?.addEventListener("keydown", keydown);
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      panel?.removeEventListener("keydown", keydown);
      document.body.style.overflow = original;
      prior?.focus();
    };
  }, [close]);
  return (
    <div className="gt-overlay">
      <section
        ref={ref}
        className="gt-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="gt-dialog-heading">
          <h2>{title}</h2>
          <button
            aria-label="Close dialog"
            className="icon-button"
            onClick={close}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

export default function PortfolioShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const p = usePortfolio();
  const router = useRouter();
  const path = usePathname();
  const [settings, setSettings] = useState(false);
  const [enteredKey, setEnteredKey] = useState("");
  const closeSettings = useCallback(() => setSettings(false), []);
  const goTour = (step: number) => {
    p.setTour(step);
    const story = TOUR[step];
    if (story.question) {
      const result = sampleQuestion(story.question, p.sample);
      p.setSelectedQuery(result);
      p.setSample((state) => ({
        ...state,
        queries: [
          ...state.queries.filter((q) => q.question !== result.question),
          result,
        ],
      }));
    }
    router.push(story.route);
  };
  const navigation = [
    ["/chat", "Chat", BookOpen],
    ["/documents", "Documents", FileText],
    ["/workflows", "Workflows", Layers],
    ["/admin", "Admin", ShieldCheck],
  ] as const;
  return (
    <>
      <a href="#main-content" className="gt-skip">
        Skip to content
      </a>
      <header className="gt-header">
        <div className="gt-header-inner">
          <Link className="gt-logo" href="/" aria-label="GroundTruth home">
            <span className="gt-mark">
              <Layers size={22} />
            </span>
            <span>
              GroundTruth<small>Evidence before answers</small>
            </span>
          </Link>
          <nav aria-label="Main navigation">
            {navigation.map(([href, name, Icon]) => (
              <Link
                key={href}
                aria-current={path === href ? "page" : undefined}
                href={href}
              >
                <Icon size={16} />
                {name}
              </Link>
            ))}
          </nav>
          <button
            className="gt-settings"
            aria-label="Connection"
            onClick={() => {
              setEnteredKey(p.key);
              setSettings(true);
            }}
          >
            <SlidersHorizontal size={16} />
            <span>Connection</span>
          </button>
        </div>
      </header>
      <div className={`gt-source-bar ${p.source}`}>
        <div>
          <span className="gt-dot" />
          <strong>
            {p.source === "sample"
              ? "Interactive sample data"
              : "Connected local application"}
          </strong>
          <span>
            {p.source === "sample"
              ? "Synthetic runbooks · no network calls"
              : p.identity
                ? `${p.identity.name} · ${p.identity.workspace_id}`
                : "API key identity · private evidence"}
          </span>
        </div>
        <div className="gt-actions">
          {p.source === "sample" ? (
            <>
              <button onClick={p.reset}>Reset demo</button>
              <Link href="/workflow">
                Run the actual project <ArrowRight size={14} />
              </Link>
            </>
          ) : (
            <button onClick={() => p.setSource("sample")}>
              Explore sample data
            </button>
          )}
        </div>
      </div>
      {p.tour !== null && p.source === "sample" ? (
        <aside className="gt-tour" aria-label="Guided demo">
          <div>
            <span className="gt-eyebrow">
              Guided demo · {p.tour + 1} of {TOUR.length}
            </span>
            <h2>{TOUR[p.tour].title}</h2>
            <p>{TOUR[p.tour].description}</p>
          </div>
          <div className="gt-actions">
            <button
              className="btn-secondary"
              disabled={p.tour === 0}
              onClick={() => goTour(p.tour! - 1)}
            >
              Previous
            </button>
            {p.tour < TOUR.length - 1 ? (
              <button
                className="btn-primary"
                onClick={() => goTour(p.tour! + 1)}
              >
                Next step <ArrowRight size={15} />
              </button>
            ) : (
              <button className="btn-primary" onClick={() => p.setTour(null)}>
                Finish tour
              </button>
            )}
            <button className="gt-text-button" onClick={() => p.setTour(null)}>
              Exit tour
            </button>
          </div>
        </aside>
      ) : null}
      <main id="main-content" className="gt-main" tabIndex={-1}>
        <div key={`${p.source}-${p.epoch}`}>{children}</div>
      </main>
      <footer className="gt-footer">
        <span>GroundTruth · Portfolio project 05</span>
        <Link href="/workflow">
          Runtime, setup & engineering evidence <ArrowRight size={14} />
        </Link>
      </footer>
      {settings ? (
        <Dialog title="Connect to your local application" close={closeSettings}>
          <p className="gt-muted">
            Use an API key issued by this GroundTruth instance. The key stays in
            this tab&apos;s session storage and is sent only in request headers.
          </p>
          <p className="gt-code">API: {API_URL}</p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              p.connect(enteredKey.trim());
              setSettings(false);
            }}
          >
            <label className="gt-field">
              API key
              <input
                type="password"
                autoComplete="off"
                value={enteredKey}
                onChange={(event) => setEnteredKey(event.target.value)}
                placeholder="Enter your API key"
              />
            </label>
            <p className="gt-muted">
              Leave empty only when the server explicitly runs in single-user,
              authentication-disabled development mode.
            </p>
            <button
              className="btn-primary"
              type="submit"
              disabled={process.env.NEXT_PUBLIC_DEMO_MODE === "true"}
            >
              Connect application <ArrowRight size={15} />
            </button>
            {process.env.NEXT_PUBLIC_DEMO_MODE === "true" ? (
              <p>This build is explicitly sample-only.</p>
            ) : null}
          </form>
        </Dialog>
      ) : null}
    </>
  );
}

export function StartTourButton() {
  const p = usePortfolio();
  const router = useRouter();
  return (
    <button
      className="btn-primary"
      onClick={() => {
        p.setSource("sample");
        p.reset();
        p.setTour(0);
        const result = sampleQuestion(TOUR[0].question!, createSampleState());
        p.setSample((state) => ({ ...state, queries: [result] }));
        p.setSelectedQuery(result);
        router.push("/chat");
      }}
    >
      Start guided demo <ArrowRight size={17} />
    </button>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="gt-page-heading">
      <div>
        <span className="gt-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}

export function RuntimeSummary() {
  const { source, runtime } = usePortfolio();
  const profile = (runtime?.runtime ||
    runtime?.execution_profile ||
    runtime ||
    {}) as Record<string, unknown>;
  const embedding = profile.embedding as Record<string, unknown> | undefined;
  const mode = String(embedding?.mode || profile.embedding_mode || "unknown");
  const embeddingLabel =
    mode === "local"
      ? "Local CPU semantic embeddings"
      : mode === "deterministic"
        ? "Deterministic portable embeddings"
        : `Embedding mode: ${mode}`;
  return (
    <div className="gt-runtime">
      <Database size={16} />
      {source === "sample" ? (
        <span>
          Simulated retrieval · synthetic sources · no model execution
        </span>
      ) : runtime ? (
        <div>
          <span>
            {embeddingLabel} ·{" "}
            {String(profile.generation_mode || "unknown generation")} ·{" "}
            {String(profile.persistence || "unknown persistence")} ·{" "}
            {String(profile.ingestion_mode || "unknown ingestion")} ingestion
          </span>
          <details>
            <summary>Runtime details reported by API</summary>
            <pre>{JSON.stringify(profile, null, 2)}</pre>
          </details>
        </div>
      ) : (
        <span>
          Runtime unavailable — connect to inspect the actual execution profile.
        </span>
      )}
      <CheckCircle2 size={16} />
    </div>
  );
}
