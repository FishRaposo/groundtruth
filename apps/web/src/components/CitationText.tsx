import type { SourceCitation } from "@/types";

interface CitationTextProps {
  /** Answer text that may contain [n] citation markers. */
  text: string;
  /** Sources available to resolve markers against. */
  sources: SourceCitation[];
  /** Optional callback when a resolved citation marker is clicked. */
  onCitationClick?: (citationIndex: number) => void;
}

const MARKER_RE = /\[(\d+)\]/g;

/**
 * Render answer text with inline [n] citation markers highlighted.
 *
 * Markers that resolve to a provided source are rendered as a clickable,
 * highlighted badge; unresolved (dangling) markers are rendered muted so the
 * reader can tell grounded claims from ungrounded ones.
 */
export default function CitationText({
  text,
  sources,
  onCitationClick,
}: CitationTextProps) {
  const available = new Set(sources.map((s) => s.citation_index));
  const parts: React.ReactNode[] = [];

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  MARKER_RE.lastIndex = 0;
  while ((match = MARKER_RE.exec(text)) !== null) {
    const [marker, numStr] = match;
    const num = Number(numStr);
    const start = match.index;

    if (start > lastIndex) {
      parts.push(text.slice(lastIndex, start));
    }

    const resolved = available.has(num);
    if (resolved) {
      parts.push(
        <button
          key={`cite-${key++}`}
          type="button"
          onClick={() => onCitationClick?.(num)}
          aria-label={`Citation ${num}`}
          data-testid={`citation-marker-${num}`}
          className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-brand-100 px-1 align-baseline text-[0.7rem] font-bold text-brand-700 hover:bg-brand-200"
        >
          {num}
        </button>
      );
    } else {
      parts.push(
        <span
          key={`cite-${key++}`}
          data-testid={`citation-dangling-${num}`}
          className="mx-0.5 text-gray-400"
          title="No matching source"
        >
          {marker}
        </span>
      );
    }

    lastIndex = start + marker.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <span className="whitespace-pre-wrap">{parts}</span>;
}
