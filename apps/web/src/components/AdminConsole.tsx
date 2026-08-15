"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { AdminUsageSummary, AuditEvent } from "@/types";

export default function AdminConsole() {
  const [usage, setUsage] = useState<AdminUsageSummary | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([apiClient.fetchAdminUsage(), apiClient.fetchAuditEvents()])
      .then(([usageData, auditData]) => {
        if (!active) return;
        setUsage(usageData);
        setEvents(auditData);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load admin evidence");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <p className="py-16 text-center text-sm text-gray-500">Loading operational evidence…</p>;
  }

  return (
    <div className="space-y-8">
      {error && (
        <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Admin API unavailable: {error}. Showing the local empty-state fallback.
        </div>
      )}
      <section aria-labelledby="usage-heading">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 id="usage-heading" className="text-xl font-semibold text-gray-900">Usage</h2>
            <p className="mt-1 text-sm text-gray-500">Read-only workspace totals from the local cost ledger.</p>
          </div>
          <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Read only</span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label="Requests" value={formatInteger(usage?.total_requests ?? 0)} />
          <Metric label="Tokens" value={formatInteger(usage?.total_tokens ?? 0)} />
          <Metric label="Estimated cost" value={`$${(usage?.estimated_cost ?? 0).toFixed(2)}`} />
          <Metric label="Average latency" value={`${Math.round(usage?.average_latency_ms ?? 0)} ms`} />
        </div>
        {usage && Object.keys(usage.cost_by_model).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Usage by model">
            {Object.entries(usage.cost_by_model).map(([model, cost]) => (
              <span key={model} className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-600">
                {model}: ${cost.toFixed(4)}
              </span>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="audit-heading">
        <h2 id="audit-heading" className="text-xl font-semibold text-gray-900">Audit trail</h2>
        <p className="mt-1 text-sm text-gray-500">Recent immutable actions. Sensitive metadata is redacted by the API.</p>
        <div className="mt-4 overflow-hidden rounded-xl border border-gray-200 bg-white">
          {events.length === 0 ? (
            <p className="p-8 text-center text-sm text-gray-500">No audit events recorded.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {events.map((event, index) => (
                <li key={`${event.created_at}:${event.request_id ?? index}`} className="grid gap-2 p-4 text-sm sm:grid-cols-[10rem_1fr_auto] sm:items-center">
                  <time className="text-xs text-gray-500" dateTime={event.created_at}>
                    {new Date(event.created_at).toLocaleString()}
                  </time>
                  <div>
                    <p className="font-medium text-gray-800"><span className="font-mono text-brand-700">{event.action}</span> by {event.actor_id}</p>
                    <p className="mt-0.5 text-xs text-gray-500">{event.resource_type} · {event.resource_id || "n/a"}</p>
                  </div>
                  <span className="font-mono text-[10px] text-gray-400">{event.workspace_id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-gray-900">{value}</p>
    </div>
  );
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
