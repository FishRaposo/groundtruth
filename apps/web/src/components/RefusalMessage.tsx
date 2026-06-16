interface RefusalMessageProps {
  reason: string;
  confidence?: number;
  suggestion?: string;
}

export default function RefusalMessage({
  reason,
  confidence,
  suggestion,
}: RefusalMessageProps) {
  return (
    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-start gap-2">
        <span className="text-amber-600 text-lg">&#9888;</span>
        <div>
          <h4 className="text-sm font-semibold text-amber-800">
            Unable to Answer
          </h4>
          <p className="mt-1 text-sm text-amber-700">{reason}</p>
          {confidence !== undefined && (
            <p className="mt-1 text-xs text-amber-600">
              Confidence: {Math.round(confidence * 100)}%
            </p>
          )}
          {suggestion && (
            <p className="mt-2 text-xs text-amber-600 italic">{suggestion}</p>
          )}
        </div>
      </div>
    </div>
  );
}
