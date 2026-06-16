import type { SourceCitation as SourceCitationType } from "@/types";

interface SourceCitationProps {
  citation: SourceCitationType;
}

export default function SourceCitation({ citation }: SourceCitationProps) {
  const scorePercent = Math.round(citation.relevance_score * 100);
  const scoreColor =
    scorePercent >= 80
      ? "text-green-600 bg-green-50"
      : scorePercent >= 50
        ? "text-yellow-600 bg-yellow-50"
        : "text-red-600 bg-red-50";

  return (
    <div className="flex items-start gap-3 rounded-md border border-gray-100 bg-gray-50 p-3">
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
        {citation.citation_index}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-gray-700 truncate">
            {citation.document_title}
          </p>
          <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${scoreColor}`}>
            {scorePercent}%
          </span>
        </div>
        <p className="mt-1 text-xs text-gray-500 line-clamp-2">
          {citation.content_preview}
        </p>
      </div>
    </div>
  );
}
