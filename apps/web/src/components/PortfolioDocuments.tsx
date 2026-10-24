"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, History, RefreshCw, Upload } from "lucide-react";
import { usePortfolio } from "./PortfolioProvider";
import { Dialog, Notice, PageHeading } from "./PortfolioShell";
import {
  CURRENT_HASH,
  CURRENT_PASSAGE,
  OLD_HASH,
  OLD_PASSAGE,
  recoverSample,
  restoreSample,
  sampleAudit,
} from "@/lib/portfolioSample";
import type { Document, DocumentVersion, IngestionJob } from "@/types";

interface Snapshot {
  content?: string;
  normalized_content?: string;
  content_hash?: string;
  version_number?: number;
}
export default function PortfolioDocuments() {
  const p = usePortfolio();
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Document | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [comparison, setComparison] = useState<string | null>(null);
  const [updateFile, setUpdateFile] = useState<File | null>(null);
  const [pendingRestore, setPendingRestore] = useState<number | null>(null);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const close = useCallback(() => {
    setSelected(null);
    setPendingRestore(null);
    setSnapshot(null);
    setComparison(null);
    setUpdateFile(null);
  }, []);
  const inProgress =
    p.documents.some(
      (doc) =>
        doc.status === "processing" ||
        doc.status === "pending" ||
        ["queued", "processing"].includes(doc.latest_ingestion?.status || ""),
    ) || jobs.some((job) => ["queued", "processing"].includes(job.status));
  const { source, client, refresh } = p;
  useEffect(() => {
    if (source !== "connected" || !inProgress) return;
    let active = true;
    const timer = setInterval(() => {
      void refresh();
      void Promise.all(
        jobs
          .filter((job) => ["queued", "processing"].includes(job.status))
          .map((job) =>
            client.request<IngestionJob>(`/api/ingestions/${job.id}`),
          ),
      )
        .then((results) => {
          if (active)
            setJobs((previous) =>
              previous.map(
                (job) => results.find((result) => result.id === job.id) || job,
              ),
            );
        })
        .catch(() => {
          if (active)
            setError(
              "Ingestion progress is unavailable. Retry to inspect durable job state.",
            );
        });
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [source, client, refresh, inProgress, jobs]);
  const validate = (items: File[]) => {
    if (items.length > 5)
      throw new Error("Choose at most five files per request.");
    if (items.some((file) => file.size > 10 * 1024 * 1024))
      throw new Error("Each file must be no larger than 10 MiB.");
    if (!items.length) throw new Error("Choose a document first.");
  };
  const upload = async () => {
    setError(null);
    setNotice("");
    setBusy(true);
    try {
      validate(files);
      if (p.source === "sample") {
        setNotice(
          "Sample selection only. No file content was read or transmitted. Use the simulated quarantine recovery below, or connect to ingest a real document.",
        );
        return;
      }
      const body = new FormData();
      files.forEach((file) => body.append("files", file));
      const result = await p.client.request<{
        documents: Document[];
        ingestions?: IngestionJob[];
      }>("/api/documents/upload", { method: "POST", body });
      setJobs(result.ingestions || []);
      setFiles([]);
      if (fileInput.current) fileInput.current.value = "";
      setNotice(
        `${result.documents.length} document(s) submitted. Durable ingestion status appears below.`,
      );
      await p.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };
  const inspect = async (doc: Document) => {
    setError(null);
    setBusy(true);
    setSnapshot(null);
    setComparison(null);
    setPendingRestore(null);
    setSelected(doc);
    try {
      const history =
        p.source === "sample"
          ? doc.id === "sample-rollback"
            ? [
                {
                  id: "sample-v1",
                  document_id: doc.id,
                  version_number: 1,
                  content_hash: OLD_HASH,
                  created_at: "2026-10-21T12:00:00Z",
                  change_summary:
                    "Historical procedure — no health verification",
                  chunk_count: 1,
                },
                {
                  id: "sample-v2",
                  document_id: doc.id,
                  version_number: 2,
                  content_hash: CURRENT_HASH,
                  created_at: "2026-10-22T12:00:00Z",
                  change_summary:
                    "Require snapshot restore and health verification",
                  chunk_count: 1,
                },
                ...(doc.version_number && doc.version_number > 2
                  ? [
                      {
                        id: "sample-restored",
                        document_id: doc.id,
                        version_number: doc.version_number,
                        content_hash: doc.content_hash || "",
                        created_at: "2026-10-23T12:00:00Z",
                        change_summary:
                          "Simulated restoration published as a new revision",
                        chunk_count: 1,
                      },
                    ]
                  : []),
              ]
            : []
          : await p.client.request<DocumentVersion[]>(
              `/api/v1/documents/${doc.id}/versions`,
            );
      setVersions(history.sort((a, b) => b.version_number - a.version_number));
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Version history unavailable.",
      );
    } finally {
      setBusy(false);
    }
  };
  const versionSnapshot = async (version: number) => {
    if (!selected) return;
    setError(null);
    try {
      setSnapshot(
        p.source === "sample"
          ? {
              content: version === 1 ? OLD_PASSAGE : CURRENT_PASSAGE,
              content_hash: version === 1 ? OLD_HASH : CURRENT_HASH,
              version_number: version,
            }
          : await p.client.request<Snapshot>(
              `/api/v1/documents/${selected.id}/versions/${version}`,
            ),
      );
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Snapshot unavailable.",
      );
    }
  };
  const compare = async () => {
    if (!selected || versions.length < 2) return;
    setError(null);
    try {
      setComparison(
        p.source === "sample"
          ? `PREVIOUS v1\n− ${OLD_PASSAGE}\n\nCURRENT v2\n+ ${CURRENT_PASSAGE}`
          : (
              await p.client.request<{ line_diff: string }>(
                `/api/v1/documents/${selected.id}/versions/diff?from_version=${versions[1].version_number}&to_version=${versions[0].version_number}`,
              )
            ).line_diff,
      );
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Comparison failed.",
      );
    }
  };
  const restore = async () => {
    if (!selected || pendingRestore === null) return;
    setBusy(true);
    setError(null);
    try {
      if (p.source === "sample")
        p.setSample((state) =>
          restoreSample(state, selected.id, pendingRestore),
        );
      else
        await p.client.request(
          `/api/v1/documents/${selected.id}/versions/${pendingRestore}/restore`,
          { method: "POST" },
        );
      setNotice(
        `Restored version ${pendingRestore} as a new revision. Existing saved citations remain tied to their original snapshot.`,
      );
      close();
      await p.refresh();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Restore failed. The previous published revision remains available.",
      );
    } finally {
      setBusy(false);
    }
  };
  const update = async () => {
    if (!selected || !updateFile) return;
    setBusy(true);
    setError(null);
    try {
      validate([updateFile]);
      const body = new FormData();
      body.append("file", updateFile);
      if (selected.version_number)
        body.append("base_version", String(selected.version_number));
      if (p.source === "sample")
        throw new Error(
          "Connect the actual project to publish file content. Sample files are never transmitted.",
        );
      const result = await p.client.request<{
        ingestion_id?: string;
        ingestion?: IngestionJob;
      }>(
        `/api/v1/documents/${selected.id}/versions${selected.version_number ? `?base_version=${selected.version_number}` : ""}`,
        { method: "POST", body },
      );
      if (result.ingestion)
        setJobs((previous) => [...previous, result.ingestion!]);
      setNotice(
        "Update submitted. The existing published revision stays available until the replacement is indexed successfully.",
      );
      close();
      await p.refresh();
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Content update failed.",
      );
    } finally {
      setBusy(false);
    }
  };
  const retry = async (doc: Document) => {
    setBusy(true);
    setError(null);
    try {
      if (p.source === "sample") {
        p.setSample(recoverSample);
        setNotice(
          "Simulated recovery completed. No file parser or backend was called.",
        );
      } else {
        if (doc.latest_ingestion?.id)
          await p.client.request(
            `/api/ingestions/${doc.latest_ingestion.id}/retry`,
            { method: "POST" },
          );
        else
          await p.client.request(`/api/documents/${doc.id}/reindex`, {
            method: "POST",
          });
        await p.refresh();
        setNotice(
          "Explicit retry submitted. Inspect the durable attempt before trusting the new revision.",
        );
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Retry failed.");
    } finally {
      setBusy(false);
    }
  };
  const remove = async (doc: Document) => {
    setBusy(true);
    setError(null);
    try {
      if (p.source === "sample")
        p.setSample((state) => ({
          ...state,
          documents: state.documents.filter((d) => d.id !== doc.id),
          audit: [...state.audit, sampleAudit("document.delete", doc.id)],
        }));
      else {
        await p.client.request(`/api/documents/${doc.id}`, {
          method: "DELETE",
        });
        await p.refresh();
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Document deletion failed.",
      );
    } finally {
      setBusy(false);
    }
  };
  const errorDocs = p.documents.filter(
    (doc) => doc.status === "error" || doc.latest_ingestion?.status === "error",
  );
  return (
    <>
      <PageHeading
        eyebrow="Knowledge / Documents"
        title="The evidence has a history."
        description="Published versions stay usable while replacements are parsed, embedded and indexed."
      />
      <div className="gt-metrics">
        <div>
          <strong>{p.documents.length}</strong>
          <span>Authorized documents</span>
        </div>
        <div>
          <strong>
            {p.documents.filter((doc) => doc.status === "ready").length}
          </strong>
          <span>Published & ready</span>
        </div>
        <div>
          <strong>{errorDocs.length}</strong>
          <span>Need attention</span>
        </div>
      </div>
      {p.error ? (
        <Notice error={p.error} retry={() => void p.refresh()} />
      ) : null}
      {error ? <Notice error={error} retry={() => void p.refresh()} /> : null}
      {notice ? (
        <div className="gt-notice" role="status">
          {notice}
        </div>
      ) : null}
      <section className="gt-panel gt-upload">
        <div>
          <Upload size={22} />
          <h2>Bring your documents</h2>
          <p>
            TXT, Markdown, PDF, HTML and DOCX · up to five files · 10 MiB each.
          </p>
        </div>
        <label className="gt-field">
          Choose documents
          <input
            ref={fileInput}
            type="file"
            accept=".txt,.md,.pdf,.html,.docx"
            multiple
            onChange={(event) => {
              setFiles(Array.from(event.target.files || []));
              setError(null);
            }}
          />
        </label>
        <button
          className="btn-primary"
          disabled={!files.length || busy}
          onClick={() => void upload()}
        >
          {p.source === "sample" ? "Preview file selection" : "Upload & ingest"}
        </button>
        {files.length ? (
          <p>{files.map((file) => file.name).join(", ")}</p>
        ) : null}
        {p.source === "sample" ? (
          <small>
            Sample selection stays on this device; it never uploads or parses
            your content.
          </small>
        ) : null}
      </section>
      {jobs.length ? (
        <section className="gt-panel">
          <h2>Ingestion jobs</h2>
          {jobs.map((job) => (
            <div className="gt-job" key={job.id}>
              <strong>{job.status}</strong>
              <span>
                {job.stage} · attempt {job.attempt}
              </span>
              <code>{job.id}</code>
              {job.error ? <p>{job.error}</p> : null}
            </div>
          ))}
        </section>
      ) : null}
      <section className="gt-document-list" aria-label="Document collection">
        {p.documents.map((doc) => (
          <article className="gt-panel gt-document" key={doc.id}>
            <FileText size={23} />
            <div className="gt-document-content">
              <div className="gt-document-title">
                <h2>{doc.title}</h2>
                <span
                  className={`gt-badge ${doc.status === "ready" ? "success" : doc.status === "error" ? "danger" : "warning"}`}
                >
                  {doc.status === "error" ? "Quarantined" : doc.status}
                </span>
              </div>
              <p>
                Version {doc.version_number ?? "unknown"} ·{" "}
                {doc.source_type.toUpperCase()} ·{" "}
                {doc.permissions?.write === false
                  ? "Read access"
                  : "Owner / editable"}
              </p>
              {doc.latest_ingestion ? (
                <p className="gt-muted">
                  Latest attempt: {doc.latest_ingestion.status} ·{" "}
                  {doc.latest_ingestion.stage} ·{" "}
                  {doc.latest_ingestion.error || "Publication is atomic"}
                </p>
              ) : null}
              {doc.status === "error" && !doc.latest_ingestion ? (
                <p className="gt-warning">
                  {String(
                    doc.metadata?.quarantine_reason ||
                      "The parser could not process this file. Inspect or retry the attempt.",
                  )}
                </p>
              ) : null}
              <div className="gt-actions">
                <button
                  className="btn-secondary"
                  disabled={busy}
                  onClick={() => void inspect(doc)}
                >
                  <History size={14} /> Versions & evidence
                </button>
                {(doc.status === "error" ||
                  doc.latest_ingestion?.status === "error") &&
                doc.permissions?.write !== false ? (
                  <button
                    className="btn-secondary"
                    disabled={busy}
                    onClick={() => void retry(doc)}
                  >
                    <RefreshCw size={14} />{" "}
                    {p.source === "sample"
                      ? "Simulate recovery"
                      : "Retry ingestion"}
                  </button>
                ) : null}
                {doc.permissions?.write !== false ? (
                  <details>
                    <summary>Delete document</summary>
                    <p>Existing answers may lose access to this evidence.</p>
                    <button
                      className="gt-danger-button"
                      disabled={busy}
                      onClick={() => void remove(doc)}
                    >
                      Confirm delete
                    </button>
                  </details>
                ) : null}
              </div>
            </div>
          </article>
        ))}
        {!p.documents.length ? (
          <div className="gt-empty">
            <FileText size={32} />
            <h2>
              {p.loading ? "Loading documents…" : "No authorized documents yet"}
            </h2>
            <p>
              Upload a file to start. Private documents are visible only to
              their authorized owner and collection members.
            </p>
          </div>
        ) : null}
      </section>
      {selected ? (
        <Dialog title={`Version history: ${selected.title}`} close={close}>
          <p className="gt-muted">
            A source revision is immutable. Restoring publishes a new revision
            with compatible regenerated embeddings.
          </p>
          {busy ? <p role="status">Loading / indexing…</p> : null}
          {error ? (
            <div role="alert" className="gt-notice error">
              {error}
            </div>
          ) : null}
          {versions.length > 1 ? (
            <button className="btn-secondary" onClick={() => void compare()}>
              Compare previous and current
            </button>
          ) : null}
          <div className="gt-versions">
            {versions.map((version) => (
              <article key={version.id}>
                <h3>
                  Version {version.version_number}{" "}
                  <span className="gt-badge">
                    {version.version_number === selected.version_number
                      ? "Current"
                      : "Historical"}
                  </span>
                </h3>
                <p>{version.change_summary || "Change summary unavailable"}</p>
                <code>{version.content_hash || "Hash unknown"}</code>
                <div className="gt-actions">
                  <button
                    className="btn-secondary"
                    onClick={() => void versionSnapshot(version.version_number)}
                  >
                    Inspect passage v{version.version_number}
                  </button>
                  {selected.permissions?.write !== false ? (
                    <button
                      className="gt-text-button"
                      disabled={busy}
                      onClick={() => setPendingRestore(version.version_number)}
                    >
                      Restore v{version.version_number}
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          {!versions.length && !busy ? (
            <p>No captured version snapshots for this document.</p>
          ) : null}
          {comparison ? (
            <section aria-label="Version comparison">
              <h3>Procedure changes</h3>
              <pre className="gt-version-diff">{comparison}</pre>
            </section>
          ) : null}
          {snapshot ? (
            <section aria-label="Version snapshot">
              <h3>Captured passage · version {snapshot.version_number}</h3>
              <blockquote className="gt-passage">
                {snapshot.content ||
                  snapshot.normalized_content ||
                  "No textual snapshot was recorded."}
              </blockquote>
              <code>{snapshot.content_hash || "Hash unknown"}</code>
            </section>
          ) : null}
          {pendingRestore !== null ? (
            <div className="gt-notice warning">
              <p>
                Publish version {pendingRestore} as a new revision? This changes
                the current procedure used by future questions.
              </p>
              <div className="gt-actions">
                <button
                  className="btn-primary"
                  disabled={busy}
                  onClick={() => void restore()}
                >
                  Confirm restore
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => setPendingRestore(null)}
                >
                  Cancel restore
                </button>
              </div>
            </div>
          ) : null}
          {selected.permissions?.write !== false && p.source === "connected" ? (
            <section className="gt-update">
              <h3>Publish a content update</h3>
              <label className="gt-field">
                Replacement file
                <input
                  type="file"
                  accept=".txt,.md,.pdf,.html,.docx"
                  onChange={(event) =>
                    setUpdateFile(event.target.files?.[0] || null)
                  }
                />
              </label>
              <button
                className="btn-primary"
                disabled={!updateFile || busy}
                onClick={() => void update()}
              >
                Submit new version
              </button>
            </section>
          ) : null}
        </Dialog>
      ) : null}
    </>
  );
}
