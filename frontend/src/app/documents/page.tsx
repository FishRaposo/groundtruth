"use client";

import { useState, useEffect } from "react";
import DocumentUploader from "@/components/DocumentUploader";
import { DocumentListSkeleton } from "@/components/LoadingSkeleton";
import type { Document, WorkflowDefinition } from "@/types";
import { apiClient } from "@/lib/api";

interface ProcessingResult {
  documentId: string;
  type: "ocr" | "template";
  data: unknown;
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [processing, setProcessing] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<ProcessingResult | null>(null);

  const fetchDocuments = async (): Promise<void> => {
    try {
      setLoading(true);
      const response = await apiClient.fetchDocuments();
      setDocuments(response.documents);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    apiClient.fetchWorkflowDefinitions()
      .then(setDefinitions)
      .catch((e) => console.error("Failed to load workflow definitions", e));
  }, []);

  const handleStartWorkflow = async (documentId: string, definitionId: string) => {
    if (!definitionId) return;
    try {
      setProcessing((prev) => ({ ...prev, [documentId]: true }));
      setSuccessMsg(null);
      const inst = await apiClient.startWorkflow(definitionId, documentId);
      
      // Update local doc state with active workflow id
      setDocuments((prev) =>
        prev.map((doc) => {
          if (doc.id === documentId) {
            const updatedMeta = { ...doc.metadata, active_workflow_id: inst.id };
            return { ...doc, metadata: updatedMeta };
          }
          return doc;
        })
      );
      setSuccessMsg(`Workflow started successfully for document!`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start workflow");
    } finally {
      setProcessing((prev) => ({ ...prev, [documentId]: false }));
    }
  };

  const handleUploadComplete = (): void => {
    fetchDocuments();
  };

  const handleDelete = async (documentId: string): Promise<void> => {
    try {
      await apiClient.deleteDocument(documentId);
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  };

  const handleOcr = async (documentId: string): Promise<void> => {
    setProcessing((prev) => ({ ...prev, [documentId]: true }));
    try {
      const data = await apiClient.processOcr(documentId);
      setResults({ documentId, type: "ocr", data });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR failed");
    } finally {
      setProcessing((prev) => ({ ...prev, [documentId]: false }));
    }
  };

  const handleDetectTemplate = async (documentId: string): Promise<void> => {
    setProcessing((prev) => ({ ...prev, [documentId]: true }));
    try {
      const data = await apiClient.detectTemplate(documentId);
      setResults({ documentId, type: "template", data });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Template detection failed");
    } finally {
      setProcessing((prev) => ({ ...prev, [documentId]: false }));
    }
  };

  const statusColors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    processing: "bg-blue-100 text-blue-800",
    ready: "bg-green-100 text-green-800",
    error: "bg-red-100 text-red-800",
  };

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-900 font-sans tracking-tight">Documents</h1>
        <a
          href="/workflows"
          className="text-sm font-semibold rounded-xl border border-gray-200 bg-white px-4 py-2 text-gray-700 shadow-sm hover:bg-gray-50 transition-all active:scale-95"
        >
          Manage Workflows
        </a>
      </div>

      <DocumentUploader onUploadComplete={handleUploadComplete} />

      {error && (
        <div className="mb-4 rounded-xl bg-red-50 border border-red-100 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="mb-4 rounded-xl bg-emerald-50 border border-emerald-100 p-4 text-sm text-emerald-700">
          {successMsg}
        </div>
      )}

      {loading ? (
        <DocumentListSkeleton />
      ) : (
        <div className="mt-8 space-y-3">
          {documents.length === 0 ? (
            <p className="py-8 text-center text-gray-500">
              No documents uploaded yet. Upload your first document above.
            </p>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.id}
                className="card flex items-center justify-between p-4 rounded-xl border border-gray-100 bg-white shadow-sm hover:shadow-md transition-shadow"
              >
                <div>
                  <h3 className="font-semibold text-gray-900 text-sm">{doc.title}</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    {(doc.metadata as Record<string, unknown>)?.file_type || doc.source_type} —{" "}
                    {new Date(doc.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusColors[doc.status] || "bg-gray-100 text-gray-800"}`}
                  >
                    {doc.status}
                  </span>
                  <button
                    onClick={() => handleOcr(doc.id)}
                    disabled={processing[doc.id]}
                    className="text-xs px-2.5 py-1.5 rounded-lg bg-blue-50 text-blue-750 hover:bg-blue-100 disabled:opacity-50 transition-colors font-medium"
                    title="Extract text with OCR"
                  >
                    {processing[doc.id] ? "..." : "OCR"}
                  </button>
                  <button
                    onClick={() => handleDetectTemplate(doc.id)}
                    disabled={processing[doc.id]}
                    className="text-xs px-2.5 py-1.5 rounded-lg bg-purple-50 text-purple-750 hover:bg-purple-100 disabled:opacity-50 transition-colors font-medium"
                    title="Detect document template"
                  >
                    {processing[doc.id] ? "..." : "Template"}
                  </button>
                  
                  {/* Workflow Integration Trigger/Link */}
                  {(doc.metadata as any)?.active_workflow_id ? (
                    <a
                      href="/workflows"
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 font-semibold transition-colors"
                    >
                      Active Workflow
                    </a>
                  ) : (
                    definitions.length > 0 && (
                      <select
                        onChange={(e) => handleStartWorkflow(doc.id, e.target.value)}
                        disabled={processing[doc.id]}
                        defaultValue=""
                        className="text-xs px-2 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 outline-none hover:bg-gray-50 cursor-pointer disabled:opacity-50 font-medium"
                      >
                        <option value="" disabled>Start Workflow</option>
                        {definitions.map((def) => (
                          <option key={def.id} value={def.id}>
                            {def.name}
                          </option>
                        ))}
                      </select>
                    )
                  )}

                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="text-xs text-rose-500 hover:text-rose-700 font-semibold px-2 py-1"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {results && (
        <div className="mt-8 rounded-lg border border-gray-200 bg-gray-50 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              {results.type === "ocr" ? "OCR Results" : "Template Detection"}
            </h3>
            <button
              onClick={() => setResults(null)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Close
            </button>
          </div>
          <pre className="overflow-auto rounded bg-white p-4 text-sm text-gray-700 border border-gray-200">
            {JSON.stringify(results.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
