"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { DocumentVersion, DocumentVersionDiff } from "@/types";

interface DocumentVersionPanelProps {
  documentId: string;
  documentTitle: string;
  onClose?: () => void;
}

export default function DocumentVersionPanel({
  documentId,
  documentTitle,
  onClose,
}: DocumentVersionPanelProps) {
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [fromVersion, setFromVersion] = useState<number | "">("");
  const [toVersion, setToVersion] = useState<number | "">("");
  const [diff, setDiff] = useState<DocumentVersionDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadVersions = useCallback(async () => {
    try {
      setLoading(true);
      const history = await apiClient.fetchDocumentVersions(documentId);
      const ordered = [...history].sort((a, b) => b.version_number - a.version_number);
      setVersions(ordered);
      if (ordered.length > 1) {
        setFromVersion((current) => current || ordered[1].version_number);
        setToVersion((current) => current || ordered[0].version_number);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load version history");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  const latestVersion = useMemo(
    () => Math.max(0, ...versions.map((version) => version.version_number)),
    [versions]
  );

  const compare = async (): Promise<void> => {
    if (fromVersion === "" || toVersion === "" || fromVersion === toVersion) return;
    try {
      setBusy(true);
      setDiff(await apiClient.diffDocumentVersions(documentId, fromVersion, toVersion));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to compare versions");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (version: number): Promise<void> => {
    if (!confirm(`Restore ${documentTitle} from version ${version}? A new version will be created.`)) {
      return;
    }
    try {
      setBusy(true);
      const result = await apiClient.restoreDocumentVersion(documentId, version);
      setNotice(`Version ${result.restored_version} restored as version ${result.new_version}`);
      setDiff(null);
      await loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore version");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label={`Version history for ${documentTitle}`}
      className="mt-3 rounded-xl border border-brand-200 bg-brand-50/40 p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h4 className="font-semibold text-gray-900">Version history</h4>
          <p className="text-xs text-gray-500">{documentTitle}</p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} className="text-xs font-medium text-gray-500">
            Close
          </button>
        )}
      </div>

      {error && <p role="alert" className="mt-3 text-xs text-red-700">{error}</p>}
      {notice && <p role="status" className="mt-3 text-xs font-medium text-emerald-700">{notice}</p>}

      {loading ? (
        <p className="mt-4 text-sm text-gray-500">Loading versions…</p>
      ) : versions.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">No version snapshots are available yet.</p>
      ) : (
        <>
          <div className="mt-4 space-y-2">
            {versions.map((version) => (
              <article
                key={version.id}
                className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-800">
                    Version {version.version_number}
                    {version.version_number === latestVersion && (
                      <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] text-emerald-700">Current</span>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-gray-600">
                    {version.change_summary || "Snapshot"} · {version.chunk_count} chunks
                  </p>
                  <p className="mt-1 truncate font-mono text-[10px] text-gray-400" title={version.content_hash}>
                    {version.content_hash}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy || version.version_number === latestVersion}
                  onClick={() => void restore(version.version_number)}
                  aria-label={`Restore version ${version.version_number}`}
                  className="btn-secondary shrink-0 px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Restore
                </button>
              </article>
            ))}
          </div>

          {versions.length > 1 && (
            <div className="mt-4 rounded-lg border border-gray-200 bg-white p-3">
              <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                <label className="text-xs font-medium text-gray-600">
                  From version
                  <select
                    aria-label="From version"
                    value={fromVersion}
                    onChange={(event) => setFromVersion(Number(event.target.value))}
                    className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-2 py-2 text-sm"
                  >
                    {versions.map((version) => <option key={version.id} value={version.version_number}>{version.version_number}</option>)}
                  </select>
                </label>
                <label className="text-xs font-medium text-gray-600">
                  To version
                  <select
                    aria-label="To version"
                    value={toVersion}
                    onChange={(event) => setToVersion(Number(event.target.value))}
                    className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-2 py-2 text-sm"
                  >
                    {versions.map((version) => <option key={version.id} value={version.version_number}>{version.version_number}</option>)}
                  </select>
                </label>
                <button type="button" onClick={() => void compare()} disabled={busy || fromVersion === toVersion} className="btn-primary disabled:opacity-40">
                  Compare versions
                </button>
              </div>
              {diff && (
                <div className="mt-4">
                  <p className="text-xs font-semibold text-gray-700">{diff.total_changes} line changes</p>
                  <p className="mt-1 text-[11px] text-gray-500">
                    +{diff.added_lines} / -{diff.removed_lines} · {Math.round(diff.similarity_ratio * 100)}% similar
                  </p>
                  <pre aria-label="Version diff" className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-200">
                    {diff.line_diff || "No text changes"}
                  </pre>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
