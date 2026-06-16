import type { RetrievalTrace as RetrievalTraceType } from "@/types";

interface RetrievalTraceProps {
  trace: RetrievalTraceType;
}

export default function RetrievalTrace({ trace }: RetrievalTraceProps) {
  return (
    <div className="mt-2 rounded-md border border-gray-200 bg-gray-50 p-4 text-xs">
      <h4 className="mb-2 font-semibold text-gray-700">Retrieval Trace</h4>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <span className="text-gray-500">Vector Results:</span>{" "}
          <span className="font-medium text-gray-700">{trace.vector_results}</span>
        </div>
        <div>
          <span className="text-gray-500">Keyword Results:</span>{" "}
          <span className="font-medium text-gray-700">{trace.keyword_results}</span>
        </div>
        <div>
          <span className="text-gray-500">Reranked:</span>{" "}
          <span className="font-medium text-gray-700">{trace.reranked_results}</span>
        </div>
        <div>
          <span className="text-gray-500">Context Chunks:</span>{" "}
          <span className="font-medium text-gray-700">{trace.final_context_chunks}</span>
        </div>
        <div>
          <span className="text-gray-500">Confidence:</span>{" "}
          <span className="font-medium text-gray-700">
            {Math.round(trace.confidence * 100)}%
          </span>
        </div>
        <div>
          <span className="text-gray-500">Latency:</span>{" "}
          <span className="font-medium text-gray-700">{trace.latency_ms}ms</span>
        </div>
        <div>
          <span className="text-gray-500">Embedding Dim:</span>{" "}
          <span className="font-medium text-gray-700">{trace.query_embedding_dim}</span>
        </div>
      </div>

      {trace.scores.length > 0 && (
        <div className="mt-3">
          <h5 className="mb-1 font-semibold text-gray-700">Score Breakdown</h5>
          <div className="space-y-1">
            {trace.scores.map((scoreItem: any, idx) => (
              <div key={idx} className="flex justify-between text-gray-650">
                <span>Chunk {scoreItem.chunk_id ? `${scoreItem.chunk_id.slice(0, 8)}...` : idx + 1}</span>
                <span>
                  Score: <span className="font-semibold">{typeof scoreItem.score === "number" ? `${Math.round(scoreItem.score * 100)}%` : String(scoreItem.score)}</span>
                  {scoreItem.document_id && ` (Doc: ${scoreItem.document_id.slice(0, 8)}...)`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
