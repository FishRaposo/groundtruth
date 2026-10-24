"use client";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { ConnectedClient } from "@/lib/connected";
import { sampleAudit } from "@/lib/portfolioSample";
import type {
  AdminUsageSummary,
  AuditEvent,
  WorkflowDefinition,
  WorkflowInstance,
} from "@/types";
import { API_URL, usePortfolio } from "./PortfolioProvider";
import {
  Notice,
  PageHeading,
  RuntimeSummary,
  StartTourButton,
} from "./PortfolioShell";

const sampleDefinition: WorkflowDefinition = {
  id: "sample-review",
  name: "Runbook publication review",
  description: "Human sign-off before a procedure is trusted",
  steps_count: 1,
  owner_id: "sample-operator",
  organization_id: null,
  is_active: true,
  is_system: false,
  created_at: "2026-10-23T12:00:00Z",
};
function sampleWorkflow(documentId: string, index: number): WorkflowInstance {
  return {
    id: `sample-workflow-${index + 1}`,
    workflow_definition_id: sampleDefinition.id,
    document_id: documentId,
    status: "in_progress",
    current_step_index: 0,
    triggered_by: "sample-operator",
    trigger_type: "manual",
    metadata: { simulated: true },
    created_at: "2026-10-23T12:00:00Z",
    completed_at: null,
    expires_at: null,
    steps: [
      {
        id: `sample-step-${index + 1}`,
        step_index: 0,
        name: "Operational safety sign-off",
        description: "Verify the procedure and source version.",
        approver_ids: ["sample-operator"],
        approver_role: null,
        is_parallel: false,
        min_approvals: 1,
        status: "pending",
        decisions: null,
        due_at: null,
        completed_at: null,
      },
    ],
  };
}
export function PortfolioWorkflows() {
  const p = usePortfolio();
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [definition, setDefinition] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<WorkflowInstance | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [retry, setRetry] = useState(0);
  const selectedId = selected?.id;
  const streamTerminal = selected
    ? ["completed", "rejected", "cancelled", "expired"].includes(
        selected.status,
      )
    : true;
  useEffect(() => {
    let active = true;
    if (p.source === "sample") {
      setDefinitions([sampleDefinition]);
      setInstances(p.sample.workflows);
      return;
    }
    p.client
      .request<WorkflowDefinition[]>("/api/v1/workflows/definitions")
      .then((results) => {
        if (active) setDefinitions(results);
      })
      .catch((failure) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Workflow definitions unavailable.",
          );
      });
    if (documentId)
      p.client
        .request<WorkflowInstance[]>(
          `/api/v1/workflows/documents/${documentId}/history`,
        )
        .then((results) => {
          if (active) setInstances(results);
        })
        .catch((failure) => {
          if (active)
            setError(
              failure instanceof Error
                ? failure.message
                : "Workflow history unavailable.",
            );
        });
    return () => {
      active = false;
    };
  }, [p.source, p.client, p.sample.workflows, documentId, retry]);
  useEffect(() => {
    if (p.source !== "connected" || !selectedId || streamTerminal) return;
    const stream = new ConnectedClient(API_URL, p.key);
    let active = true;
    void (async () => {
      try {
        for await (const event of stream.events(
          `/api/v1/workflows/instances/${selectedId}/events?after_event_id=0`,
        )) {
          if (!active) break;
          setEvents((previous) => [
            ...previous.slice(-49),
            String(event.data.message || event.data.status || event.event),
          ]);
          const fresh = await stream.request<WorkflowInstance>(
            `/api/v1/workflows/instances/${selectedId}`,
          );
          if (active) setSelected(fresh);
          if (
            ["completed", "rejected", "cancelled", "expired"].includes(
              fresh.status,
            )
          )
            break;
        }
      } catch (failure) {
        if (
          active &&
          !(failure instanceof DOMException && failure.name === "AbortError")
        )
          setError(
            "Workflow event connection lost. Retry reads durable state; sample results will not replace it.",
          );
      }
    })();
    return () => {
      active = false;
      stream.close();
    };
  }, [p.source, p.key, p.epoch, selectedId, streamTerminal, retry]);
  const loadInstance = async (instance: WorkflowInstance) => {
    try {
      setSelected(
        p.source === "sample"
          ? instance
          : await p.client.request<WorkflowInstance>(
              `/api/v1/workflows/instances/${instance.id}`,
            ),
      );
      setEvents([]);
      setError(null);
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Workflow unavailable.",
      );
    }
  };
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const instance =
        p.source === "sample"
          ? sampleWorkflow(documentId, p.sample.workflows.length)
          : await p.client.request<WorkflowInstance>(
              "/api/v1/workflows/instances",
              {
                method: "POST",
                body: JSON.stringify({
                  workflow_definition_id: definition,
                  document_id: documentId,
                  trigger_type: "manual",
                }),
              },
            );
      if (p.source === "sample")
        p.setSample((state) => ({
          ...state,
          workflows: [...state.workflows, instance],
          audit: [...state.audit, sampleAudit("workflow.start", instance.id)],
        }));
      setSelected(instance);
      setInstances((previous) => [...previous, instance]);
      setEvents([]);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Workflow could not start.",
      );
    } finally {
      setBusy(false);
    }
  };
  const decide = async (action: "approve" | "reject" | "cancel") => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      let result: WorkflowInstance;
      if (p.source === "sample") {
        result = {
          ...selected,
          status:
            action === "approve"
              ? "completed"
              : action === "reject"
                ? "rejected"
                : "cancelled",
          steps: selected.steps?.map((step) => ({
            ...step,
            status:
              action === "approve"
                ? "approved"
                : action === "reject"
                  ? "rejected"
                  : "cancelled",
          })),
        };
        p.setSample((state) => ({
          ...state,
          workflows: state.workflows.map((instance) =>
            instance.id === result.id ? result : instance,
          ),
          audit: [...state.audit, sampleAudit(`workflow.${action}`, result.id)],
        }));
      } else {
        if (action === "cancel")
          await p.client.request(
            `/api/v1/workflows/instances/${selected.id}/cancel`,
            { method: "POST" },
          );
        else {
          const step = selected.steps?.find(
            (item) =>
              item.status === "pending" || item.status === "in_progress",
          );
          if (!step)
            throw new Error(
              "No actionable approval step. Refresh the durable workflow state.",
            );
          await p.client.request(`/api/v1/workflows/${selected.id}/approve`, {
            method: "POST",
            body: JSON.stringify({
              step_id: step.id,
              action,
              comment: "Reviewed in the local GroundTruth application.",
            }),
          });
        }
        result = await p.client.request<WorkflowInstance>(
          `/api/v1/workflows/instances/${selected.id}`,
        );
      }
      setSelected(result);
      setInstances((previous) =>
        previous.map((instance) =>
          instance.id === result.id ? result : instance,
        ),
      );
      await p.refresh();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Decision could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };
  const terminal =
    selected &&
    ["completed", "rejected", "cancelled", "expired", "failed"].includes(
      selected.status,
    );
  return (
    <>
      <PageHeading
        eyebrow="Control / Workflows"
        title="Evidence still needs an owner."
        description="Inspect the document, request a real review, and follow its durable approval history."
      />
      {p.error ? (
        <Notice error={p.error} retry={() => void p.refresh()} />
      ) : null}
      {error ? (
        <Notice
          error={error}
          retry={() => {
            setError(null);
            setRetry((value) => value + 1);
            if (selected) void loadInstance(selected);
          }}
        />
      ) : null}
      <section className="gt-panel">
        <h2>Start a document review</h2>
        <div className="gt-form-options">
          <label className="gt-field">
            Document
            <select
              value={documentId}
              onChange={(event) => {
                setDocumentId(event.target.value);
                setSelected(null);
              }}
            >
              <option value="">Select a document</option>
              {p.documents
                .filter((doc) => doc.status === "ready")
                .map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.title}
                  </option>
                ))}
            </select>
          </label>
          <label className="gt-field">
            Workflow definition
            <select
              value={definition}
              onChange={(event) => setDefinition(event.target.value)}
            >
              <option value="">Select a workflow</option>
              {definitions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn-primary"
            disabled={!documentId || !definition || busy}
            onClick={() => void start()}
          >
            Start review <ArrowRight size={15} />
          </button>
        </div>
        {!definitions.length ? (
          <p className="gt-muted">
            No workflow definitions are available to this identity. An
            administrator must create one through the project API.
          </p>
        ) : null}
      </section>
      <div className="gt-operation-grid">
        <section className="gt-panel">
          <h2>Document review history</h2>
          {instances.length ? (
            instances.map((instance) => (
              <button
                className="gt-source-card"
                key={instance.id}
                onClick={() => void loadInstance(instance)}
              >
                <FileCheck2 size={21} />
                <span>
                  <strong>
                    {definitions.find(
                      (item) => item.id === instance.workflow_definition_id,
                    )?.name || "Document review"}
                  </strong>
                  <small>
                    {instance.status} · {instance.id}
                  </small>
                </span>
              </button>
            ))
          ) : (
            <p className="gt-muted">
              Select a document to inspect its recorded workflow history.
            </p>
          )}
        </section>
        <section className="gt-panel" aria-label="Selected workflow">
          <h2>Approval and execution</h2>
          {selected ? (
            <>
              <span
                className={`gt-badge ${selected.status === "completed" ? "success" : selected.status === "rejected" || selected.status === "failed" ? "danger" : terminal ? "" : "warning"}`}
              >
                {selected.status}
              </span>
              <p className="gt-code">{selected.id}</p>
              <ol className="gt-workflow-steps">
                {selected.steps?.map((step) => (
                  <li key={step.id}>
                    <ShieldCheck size={20} />
                    <span>
                      <strong>{step.name}</strong>
                      <small>
                        {step.status} ·{" "}
                        {step.description || "Approval recorded by the server"}
                      </small>
                    </span>
                  </li>
                ))}
              </ol>
              <div className="gt-actions">
                <button
                  className="btn-primary"
                  disabled={busy || !!terminal}
                  onClick={() => void decide("approve")}
                >
                  Approve
                </button>
                <button
                  className="btn-secondary"
                  disabled={busy || !!terminal}
                  onClick={() => void decide("reject")}
                >
                  Reject
                </button>
                <button
                  className="gt-text-button"
                  disabled={busy || !!terminal}
                  onClick={() => void decide("cancel")}
                >
                  Cancel workflow
                </button>
              </div>
              {terminal ? (
                <p className="gt-muted">
                  This workflow has a terminal outcome. Its actions cannot be
                  submitted again.
                </p>
              ) : null}
              <details>
                <summary>
                  {p.source === "sample"
                    ? "Simulated status history"
                    : "Live collector events"}
                </summary>
                <ul>
                  {events.map((message, index) => (
                    <li key={index}>{message}</li>
                  ))}
                </ul>
                <pre>{JSON.stringify(selected, null, 2)}</pre>
              </details>
            </>
          ) : (
            <p className="gt-muted">
              Select or start a review. Approval rights are enforced by the
              connected server.
            </p>
          )}
        </section>
      </div>
    </>
  );
}

type UsageEvidence = Partial<AdminUsageSummary> & {
  total_cost?: number | null;
  pricing_provenance?: string;
  estimated?: boolean;
  outcomes?: Record<string, number>;
};
export function PortfolioAdmin() {
  const p = usePortfolio();
  const [usage, setUsage] = useState<UsageEvidence | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setError(null);
    setLoading(true);
    if (p.source === "sample") {
      setAudit(p.sample.audit);
      setUsage({
        total_requests: p.sample.queries.length,
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        estimated_cost: 0,
        average_latency_ms: 42,
        p50_latency_ms: 42,
        p95_latency_ms: 42,
        p99_latency_ms: 42,
        error_rate: 0,
        cost_by_model: {},
        cost_by_prompt_version: {},
      });
      setLoading(false);
      return;
    }
    Promise.all([
      p.client.request<UsageEvidence>("/api/v1/admin/usage"),
      p.client.request<AuditEvent[]>("/api/v1/admin/audit"),
    ])
      .then(([summary, records]) => {
        if (active) {
          setUsage(summary);
          setAudit(records);
        }
      })
      .catch((failure) => {
        if (active) {
          setUsage(null);
          setAudit([]);
          setError(
            failure instanceof Error
              ? failure.message
              : "Admin evidence unavailable.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [p.source, p.client, p.sample.audit, p.sample.queries.length, retry]);
  const cost =
    typeof usage?.total_cost === "number"
      ? usage.total_cost
      : typeof usage?.estimated_cost === "number"
        ? usage.estimated_cost
        : null;
  return (
    <>
      <PageHeading
        eyebrow="Operate / Admin"
        title="Make the history inspectable."
        description="Durable audit events and usage provide an account of what actually happened."
      />
      {error ? (
        <Notice error={error} retry={() => setRetry((value) => value + 1)} />
      ) : null}
      {p.source === "connected" && p.identity && !p.identity.is_admin ? (
        <div className="gt-notice warning">
          Administrator access is required. Your ordinary document and query
          permissions remain available in Chat and Documents.
        </div>
      ) : null}
      {loading ? (
        <p role="status" className="gt-notice">
          Loading durable usage and audit history…
        </p>
      ) : null}
      <div className="gt-metrics">
        <div>
          <strong>{usage?.total_requests ?? "—"}</strong>
          <span>Recorded requests</span>
        </div>
        <div>
          <strong>{usage?.total_tokens ?? "—"}</strong>
          <span>Estimated tokens</span>
        </div>
        <div>
          <strong>
            {cost !== null && Number.isFinite(cost)
              ? `$${cost.toFixed(4)}`
              : usage
                ? "Unknown"
                : "—"}
          </strong>
          <span>
            {p.source === "sample"
              ? "Simulated cost · no provider spend"
              : "Estimated cost · pricing may be unknown"}
          </span>
        </div>
      </div>
      <RuntimeSummary />
      <section className="gt-panel">
        <h2>Audit history</h2>
        <p className="gt-muted">
          {p.source === "sample"
            ? "Sample actions appear here and reset with the entire demo."
            : "Only events visible to the authenticated administrator are returned. Token and pricing estimates are not invoices."}
        </p>
        {audit.length ? (
          <div
            className="gt-audit-list"
            tabIndex={0}
            aria-label="Recorded audit events"
          >
            {audit.map((item, index) => (
              <article key={`${item.created_at}-${index}`}>
                <CheckCircle2 size={18} />
                <div>
                  <strong>{item.action}</strong>
                  <p>
                    {item.resource_type} · {item.resource_id || "not recorded"}
                  </p>
                  <small>
                    {item.actor_id} · {item.workspace_id} · {item.created_at}
                  </small>
                  <details>
                    <summary>Event details</summary>
                    <pre>{JSON.stringify(item.metadata, null, 2)}</pre>
                  </details>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="gt-muted">
            {loading
              ? "Loading recorded events…"
              : error
                ? "No audit data was substituted after this error."
                : "No recorded events for this view yet."}
          </p>
        )}
      </section>
      {usage ? (
        <details className="gt-panel">
          <summary>Usage measurements and provenance</summary>
          <pre>{JSON.stringify(usage, null, 2)}</pre>
        </details>
      ) : null}
    </>
  );
}

export function PortfolioHome() {
  const p = usePortfolio();
  return (
    <>
      <section className="gt-hero">
        <div className="gt-eyebrow">
          GroundTruth / An inspectable knowledge application
        </div>
        <h1>
          Ask an operational question.
          <br />
          <em>Inspect the evidence</em>
          <br />
          before trusting the answer.
        </h1>
        <p>
          From a rollback question to the exact runbook passage. See which
          source, which version, and when the system should refuse to answer.
        </p>
        <div className="gt-actions">
          <StartTourButton />
          <Link className="btn-secondary" href="/chat">
            Explore freely <ArrowRight size={17} />
          </Link>
        </div>
        <span className="gt-hero-caption">
          No account or provider key needed for the interactive sample.
        </span>
      </section>
      <section className="gt-preview-grid" aria-label="Evidence workflow">
        <div className="gt-panel gt-question-preview">
          <span className="gt-eyebrow">01 / Operational question</span>
          <h2>“How do I roll back staging safely?”</h2>
          <p>Relevant evidence beats a plausible guess.</p>
          <div className="gt-preview-line" />
          <span className="gt-eyebrow">02 / Authorized retrieval</span>
          <p>Current published sources, scoped to the person asking.</p>
        </div>
        <div className="gt-panel gt-evidence-preview">
          <span className="gt-eyebrow">03 / Inspectable evidence</span>
          <div className="gt-actions">
            <FileCheck2 size={20} />
            <strong>Staging rollback runbook</strong>
            <span className="gt-badge success">Current · v2</span>
          </div>
          <blockquote>
            “Restore the staging snapshot, and{" "}
            <mark>verify the health checks before reopening traffic.</mark>”
          </blockquote>
          <Link href="/chat">
            Open the investigation <ArrowRight size={16} />
          </Link>
        </div>
      </section>
      <section className="gt-value-grid">
        <article>
          <ShieldCheck size={25} />
          <h2>Bounded answers</h2>
          <p>
            Missing or explicitly conflicting evidence results in refusal or
            human review.
          </p>
        </article>
        <article>
          <FileCheck2 size={25} />
          <h2>Versioned sources</h2>
          <p>
            Inspect exact captured passages and compare the procedure that
            changed.
          </p>
        </article>
        <article>
          <CheckCircle2 size={25} />
          <h2>Honest runtime modes</h2>
          <p>
            A credential-free extractive application, a labeled sample, and
            optional generation integrations.
          </p>
        </article>
      </section>
      <div className="gt-bottom-callout">
        <div>
          <h2>See the real project behind the preview.</h2>
          <p>
            Local ingestion, retrieval, permissions and saved evidence — with
            explicit runtime limitations.
          </p>
        </div>
        <Link className="btn-secondary" href="/workflow">
          Actual workflow & evidence <ArrowRight size={16} />
        </Link>
      </div>
      {p.source === "connected" && p.error ? (
        <Notice error={p.error} retry={() => void p.refresh()} />
      ) : null}
    </>
  );
}

export function PortfolioWorkflowGuide() {
  const p = usePortfolio();
  return (
    <>
      <PageHeading
        eyebrow="Project 05 / Actual workflow"
        title="The preview is the introduction."
        description="Run the actual application to verify ingestion, retrieval, source permissions and immutable saved evidence."
      />
      <RuntimeSummary />
      <div className="gt-operation-grid">
        <section className="gt-panel">
          <h2>Connect and investigate</h2>
          <ol className="gt-guide-list">
            <li>
              Start the API on port 8400 with a disposable database and an
              explicitly selected embedding mode.
            </li>
            <li>
              Open Connection, enter an API key issued by that instance, and
              connect.
            </li>
            <li>
              Upload your TXT or PDF. Inspect the durable ingestion job and
              published document version.
            </li>
            <li>
              Ask a question, open its source, then update or restore the
              document and compare versions.
            </li>
            <li>
              Reload the saved query URL. Inspect history, workflow decisions
              and administrator evidence.
            </li>
          </ol>
          <button
            className="btn-primary"
            disabled={process.env.NEXT_PUBLIC_DEMO_MODE === "true"}
            onClick={() => p.setSource("connected")}
          >
            Use connected application <ArrowRight size={16} />
          </button>
        </section>
        <section className="gt-panel">
          <h2>Execution modes are explicit</h2>
          <dl className="gt-details">
            <dt>Interactive sample</dt>
            <dd>
              Tab-local synthetic scenarios. No backend, provider, model
              execution or file transmission.
            </dd>
            <dt>Local semantic embeddings</dt>
            <dd>
              Pinned CPU model loaded from a prepared cache. Missing model files
              are an actionable error.
            </dd>
            <dt>Deterministic portable embeddings</dt>
            <dd>
              Explicit hash-based retrieval profile. A portability tool, not a
              semantic model substitute.
            </dd>
            <dt>Source-extractive generation</dt>
            <dd>
              Answers assembled from retrieved passages. No claim of
              language-model reasoning.
            </dd>
            <dt>Current portable infrastructure</dt>
            <dd>
              Actual SQLite persistence with canonical inline ingestion.
              PostgreSQL/pgvector and Redis live verification is deferred while
              WSL is unavailable.
            </dd>
          </dl>
        </section>
      </div>
      <section className="gt-panel">
        <h2>Engineering evidence & setup</h2>
        <div className="gt-evidence-links">
          <a href="/evidence/portfolio-connected.md">
            Local setup and connected workflow <ArrowRight size={16} />
          </a>
          <a href="/evidence/portfolio-verification.md">
            Verification results and limitations <ArrowRight size={16} />
          </a>
          <a href="/evidence/portfolio-case-study.md">
            Technical case study <ArrowRight size={16} />
          </a>
        </div>
        <p className="gt-muted">
          Synthetic authored cases establish their declared fixture contract,
          not human validation or production capacity. The API enforces
          authorization; a UI label does not grant access.
        </p>
      </section>
      <div className="gt-actions">
        <StartTourButton />
        <Link className="btn-secondary" href="/chat">
          Return to the investigation
        </Link>
      </div>
    </>
  );
}
