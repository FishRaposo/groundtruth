"use client";

import { useState, useEffect } from "react";
import DocumentUploader from "@/components/DocumentUploader";
import { DocumentListSkeleton } from "@/components/LoadingSkeleton";
import type { Document } from "@/types";
import { apiClient } from "@/lib/api";

interface ProcessingResult {
  documentId: string;
  type: "ocr" | "template";
  data: unknown;
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
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
  }, []);

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
      <h1 className="mb-6 text-3xl font-bold text-gray-900">Documents</h1>

      <DocumentUploader onUploadComplete={handleUploadComplete} />

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          {error}
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
                className="card flex items-center justify-between"
              >
                <div>
                  <h3 className="font-medium text-gray-900">{doc.title}</h3>
                  <p className="text-sm text-gray-500">
                    {(doc.metadata as Record<string, unknown>)?.file_type || doc.source_type} —{" "}
                    {new Date(doc.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[doc.status] || "bg-gray-100 text-gray-800"}`}
                  >
                    {doc.status}
                  </span>
                  <button
                    onClick={() => handleOcr(doc.id)}
                    disabled={processing[doc.id]}
                    className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                    title="Extract text with OCR"
                  >
                    {processing[doc.id] ? "..." : "OCR"}
                  </button>
                  <button
                    onClick={() => handleDetectTemplate(doc.id)}
                    disabled={processing[doc.id]}
                    className="text-xs px-2 py-1 rounded bg-purple-50 text-purple-700 hover:bg-purple-100 disabled:opacity-50"
                    title="Detect document template"
                  >
                    {processing[doc.id] ? "..." : "Template"}
                  </button>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="text-sm text-red-500 hover:text-red-700"
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
