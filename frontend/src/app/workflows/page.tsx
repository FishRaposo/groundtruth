"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";
import type { WorkflowDefinition, WorkflowInstance, WorkflowStep } from "@/types";

export default function WorkflowsPage() {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [selectedInstance, setSelectedInstance] = useState<WorkflowInstance | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  
  // Form State for Approval Action
  const [selectedStepId, setSelectedStepId] = useState<string>("");
  const [approvalAction, setApprovalAction] = useState<"approve" | "reject">("approve");
  const [approvalComment, setApprovalComment] = useState<string>("");

  const loadWorkflowData = async () => {
    try {
      setLoading(true);
      const defsData = await apiClient.fetchWorkflowDefinitions();
      setDefinitions(defsData);
      
      // Let's also fetch documents to check if they have active workflow instances or histories.
      const docList = await apiClient.fetchDocuments();
      const activeInstances: WorkflowInstance[] = [];
      
      for (const doc of docList.documents) {
        if (doc.metadata && (doc.metadata as any).active_workflow_id) {
          try {
            const inst = await apiClient.fetchWorkflowInstance((doc.metadata as any).active_workflow_id);
            activeInstances.push(inst);
          } catch (e) {
            console.error("Failed to fetch workflow instance for document", doc.id, e);
          }
        }
      }
      
      setInstances(activeInstances);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workflow information.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWorkflowData();
  }, []);

  const handleSelectInstance = async (instanceId: string) => {
    try {
      setLoading(true);
      const instDetail = await apiClient.fetchWorkflowInstance(instanceId);
      setSelectedInstance(instDetail);
      
      // Pre-select the active pending step if available
      const pendingStep = instDetail.steps?.find((s) => s.status === "pending");
      if (pendingStep) {
        setSelectedStepId(pendingStep.id);
      } else {
        setSelectedStepId("");
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch instance details.");
    } finally {
      setLoading(false);
    }
  };

  const handleProcessApproval = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInstance || !selectedStepId) return;

    try {
      setActionLoading(true);
      setSuccessMsg(null);
      setError(null);

      const res = await apiClient.processApproval(
        selectedInstance.id,
        selectedStepId,
        approvalAction,
        approvalComment || null
      );

      if (res.success) {
        setSuccessMsg(`Workflow step successfully updated to '${res.new_status}'!`);
        setApprovalComment("");
        // Reload details
        await handleSelectInstance(selectedInstance.id);
        await loadWorkflowData();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval action failed.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelWorkflow = async (instanceId: string) => {
    if (!confirm("Are you sure you want to cancel this workflow run?")) return;
    try {
      setActionLoading(true);
      await apiClient.cancelWorkflow(instanceId, "Cancelled from management UI");
      setSuccessMsg("Workflow cancelled successfully.");
      setSelectedInstance(null);
      await loadWorkflowData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel workflow.");
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case "completed":
      case "approved":
        return "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
      case "rejected":
      case "failed":
      case "cancelled":
        return "bg-rose-500/10 text-rose-400 border border-rose-500/20";
      case "pending":
      case "in_progress":
        return "bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse";
      default:
        return "bg-slate-500/10 text-slate-400 border border-slate-500/20";
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 text-slate-100">
      {/* Hero Header with glowing gradient banner */}
      <div className="relative mb-8 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 p-8 shadow-2xl backdrop-blur-md">
        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-violet-600/20 blur-3xl"></div>
        <div className="absolute -left-10 -bottom-10 h-40 w-40 rounded-full bg-sky-600/20 blur-3xl"></div>
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-violet-400 to-sky-400 bg-clip-text text-transparent">
              Workflow Command Center
            </h1>
            <p className="mt-2 text-slate-400 max-w-xl text-sm">
              Model approval chains, track document forms, and authorize ingestion steps across isolated organizational channels.
            </p>
          </div>
          <button
            onClick={loadWorkflowData}
            className="mt-4 md:mt-0 flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 transition-all hover:bg-violet-500 active:scale-95"
          >
            Refresh Data
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-400 backdrop-blur-sm">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="mb-6 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-400 backdrop-blur-sm">
          {successMsg}
        </div>
      )}

      {/* Overview Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-8">
        <div className="rounded-xl border border-slate-850 bg-slate-900/60 p-5 shadow-lg backdrop-blur-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Active Instances</span>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-sky-400">{instances.length}</span>
            <span className="text-xs text-slate-400">running runs</span>
          </div>
        </div>
        <div className="rounded-xl border border-slate-850 bg-slate-900/60 p-5 shadow-lg backdrop-blur-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Workflow Templates</span>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-violet-400">{definitions.length}</span>
            <span className="text-xs text-slate-400">active configurations</span>
          </div>
        </div>
        <div className="rounded-xl border border-slate-850 bg-slate-900/60 p-5 shadow-lg backdrop-blur-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Required SLA</span>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-amber-400">24h</span>
            <span className="text-xs text-slate-400">average SLA deadline</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left Column: Listings */}
        <div className="space-y-6 lg:col-span-7">
          {/* Active Instances Section */}
          <div className="rounded-xl border border-slate-850 bg-slate-900/50 p-6 shadow-xl backdrop-blur-sm">
            <h2 className="text-lg font-bold bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent mb-4">
              Running Workflow Instances
            </h2>

            {loading && instances.length === 0 ? (
              <div className="flex justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent"></div>
              </div>
            ) : instances.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">
                No active document workflows found. Upload a document and trigger approval.
              </p>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {instances.map((inst) => (
                  <div
                    key={inst.id}
                    onClick={() => handleSelectInstance(inst.id)}
                    className={`flex items-center justify-between py-4 cursor-pointer transition-colors group ${selectedInstance?.id === inst.id ? "bg-slate-800/30 -mx-4 px-4 rounded-lg" : "hover:bg-slate-800/10"}`}
                  >
                    <div>
                      <h3 className="font-semibold text-slate-200 group-hover:text-sky-300 transition-colors text-sm">
                        Instance {inst.id.slice(0, 8)}...
                      </h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Triggered manual • {inst.created_at ? new Date(inst.created_at).toLocaleString() : "Date unknown"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${getStatusBadgeClass(inst.status)}`}>
                        {inst.status}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCancelWorkflow(inst.id);
                        }}
                        className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-rose-400"
                        title="Cancel Workflow"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Workflow definitions templates */}
          <div className="rounded-xl border border-slate-850 bg-slate-900/50 p-6 shadow-xl backdrop-blur-sm">
            <h2 className="text-lg font-bold bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent mb-4">
              Configured Workflow Templates
            </h2>
            {loading && definitions.length === 0 ? (
              <div className="flex justify-center py-6">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-400 border-t-transparent"></div>
              </div>
            ) : definitions.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500">No workflow definitions configured.</p>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {definitions.map((def) => (
                  <div key={def.id} className="rounded-lg border border-slate-800 bg-slate-900/80 p-4 relative group hover:border-slate-700 transition-colors">
                    <div className="absolute right-3 top-3 rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold text-violet-400">
                      {def.steps_count} steps
                    </div>
                    <h3 className="font-semibold text-slate-200 text-sm">{def.name}</h3>
                    <p className="text-xs text-slate-500 mt-2 line-clamp-2">{def.description || "No description provided."}</p>
                    <div className="mt-4 flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-800/85 pt-3">
                      <span>Owner: Admin</span>
                      <span className="font-semibold text-emerald-400">Active</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Detail & Interactive approval */}
        <div className="lg:col-span-5">
          {selectedInstance ? (
            <div className="rounded-xl border border-slate-850 bg-slate-900/55 p-6 shadow-xl backdrop-blur-sm sticky top-4 space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="font-bold text-slate-100">Workflow Progress</h2>
                  <p className="text-xs text-slate-500 mt-1">ID: {selectedInstance.id}</p>
                </div>
                <button
                  onClick={() => setSelectedInstance(null)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  Close
                </button>
              </div>

              {/* Steps timeline */}
              <div className="space-y-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Review Timeline</h3>
                
                <div className="relative border-l border-slate-800 pl-6 ml-3 space-y-8">
                  {selectedInstance.steps?.map((step, idx) => (
                    <div key={step.id} className="relative">
                      {/* Timeline dot */}
                      <div className={`absolute -left-[31px] top-1 flex h-4 w-4 items-center justify-center rounded-full border bg-slate-900 text-[8px] font-bold ${
                        step.status === "completed" 
                          ? "border-emerald-500 text-emerald-400" 
                          : step.status === "pending"
                          ? "border-amber-500 text-amber-400 animate-pulse" 
                          : "border-slate-800 text-slate-500"
                      }`}>
                        {idx + 1}
                      </div>

                      <div>
                        <div className="flex items-center justify-between">
                          <h4 className="font-semibold text-slate-200 text-sm">{step.name}</h4>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${getStatusBadgeClass(step.status)}`}>
                            {step.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1">{step.description}</p>
                        
                        {step.approver_ids.length > 0 && (
                          <div className="mt-2 text-[10px] text-slate-500">
                            Approvers: <span className="font-medium text-slate-400">{step.approver_ids.join(", ")}</span>
                          </div>
                        )}

                        {step.decisions && Object.keys(step.decisions).length > 0 && (
                          <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/40 p-2.5 text-[11px] text-slate-400">
                            <span className="font-semibold text-slate-300">Decision Notes:</span>
                            {Object.entries(step.decisions).map(([approver, dec]: [string, any]) => (
                              <div key={approver} className="mt-1">
                                <strong className="text-sky-400">{approver}</strong>: <span className="capitalize">{dec.action}</span>
                                {dec.comment && <p className="italic text-slate-500 mt-0.5">"{dec.comment}"</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Board (If there's a pending step) */}
              {selectedInstance.steps?.some((s) => s.status === "pending") && (
                <div className="rounded-xl border border-violet-500/25 bg-violet-600/5 p-5">
                  <h3 className="text-sm font-bold text-violet-400 mb-3">Execute Approval Review</h3>
                  
                  <form onSubmit={handleProcessApproval} className="space-y-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                        Target Review Step
                      </label>
                      <select
                        value={selectedStepId}
                        onChange={(e) => setSelectedStepId(e.target.value)}
                        className="w-full rounded-lg border border-slate-800 bg-slate-950 p-2 text-xs text-slate-200 outline-none focus:border-violet-500"
                      >
                        {selectedInstance.steps
                          ?.filter((s) => s.status === "pending")
                          .map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                        Recommendation Action
                      </label>
                      <div className="flex gap-4">
                        <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                          <input
                            type="radio"
                            name="action"
                            checked={approvalAction === "approve"}
                            onChange={() => setApprovalAction("approve")}
                            className="accent-violet-500"
                          />
                          <span className="text-emerald-400">Approve Ingestion</span>
                        </label>
                        <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                          <input
                            type="radio"
                            name="action"
                            checked={approvalAction === "reject"}
                            onChange={() => setApprovalAction("reject")}
                            className="accent-violet-500"
                          />
                          <span className="text-rose-400">Reject / Flag</span>
                        </label>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                        Review Remarks & Comments
                      </label>
                      <textarea
                        rows={3}
                        value={approvalComment}
                        onChange={(e) => setApprovalComment(e.target.value)}
                        placeholder="Provide details about the document's validation, form completeness, or compliance flags..."
                        className="w-full rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-xs text-slate-200 outline-none placeholder-slate-600 focus:border-violet-500"
                      />
                    </div>

                    <button
                      type="submit"
                      disabled={actionLoading || !selectedStepId}
                      className="w-full rounded-xl bg-violet-600 py-2.5 text-xs font-bold text-white transition-all hover:bg-violet-500 active:scale-95 disabled:opacity-50"
                    >
                      {actionLoading ? "Processing Action..." : "Submit Review Audit"}
                    </button>
                  </form>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-850 bg-slate-900/30 p-8 text-center text-slate-500 border-dashed">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-10 h-10 mx-auto text-slate-600 mb-3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.375c.84 0 1.566-.513 1.861-1.242L14.5 12l-.264-.758a2.007 2.007 0 00-1.86-1.242H9M3 9.071c0-1.802 1.46-3.267 3.26-3.267.868 0 1.696.34 2.308.95L10.5 8.75m0 0h5.25a3 3 0 003-3v-.75m-8.25 3.75v5.25m0 0l-1.93-1.93M10.5 14h5.25a3 3 0 003 3v.75m-8.25-3.75v-5.25M6.26 15.071c0 1.802-1.46 3.267-3.26 3.267a3.253 3.253 0 01-2.308-.95L1.5 15.25" />
              </svg>
              <h3 className="font-semibold text-slate-400 text-sm">No Instance Selected</h3>
              <p className="text-xs mt-1 text-slate-600 max-w-xs mx-auto">
                Select an active workflow run from the left panel to inspect steps, view previous comments, and execute reviews.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
