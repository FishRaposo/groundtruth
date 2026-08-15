"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { WorkflowStatusEvent } from "@/types";

export default function WorkflowStatusStream({ workflowId }: { workflowId: string }) {
  const [events, setEvents] = useState<WorkflowStatusEvent[]>([]);
  const [connected, setConnected] = useState(true);

  useEffect(() => {
    setEvents([]);
    setConnected(true);
    return apiClient.subscribeWorkflowEvents(
      workflowId,
      (event) => {
        setConnected(true);
        setEvents((current) => [...current.filter((item) => item.id !== event.id), event].slice(-8));
      },
      () => setConnected(false)
    );
  }, [workflowId]);

  return (
    <section aria-label="Live workflow status" className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Local status stream</h3>
        <span className={`text-[10px] font-semibold ${connected ? "text-emerald-400" : "text-amber-400"}`}>
          {connected ? "Live" : "Reconnecting"}
        </span>
      </div>
      {events.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">Waiting for workflow status changes…</p>
      ) : (
        <ol className="mt-3 space-y-2" aria-live="polite">
          {[...events].reverse().map((event) => (
            <li key={event.id} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-semibold text-sky-300">{event.status}</span>
                {event.created_at && <time dateTime={event.created_at} className="text-[10px] text-slate-500">{new Date(event.created_at).toLocaleTimeString()}</time>}
              </div>
              {event.message && <p className="mt-1 text-xs text-slate-300">{event.message}</p>}
              {event.action && <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">{event.action}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
