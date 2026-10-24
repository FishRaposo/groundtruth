/** Render only recorded identity; historical records do not inherit runtime settings. */
export function selectionRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function selectionLabel(mode: unknown) {
  return mode === "reader" ? "Local extractive reader"
    : mode === "lexical" ? "Lexical answer selection"
      : "Answer selection unknown";
}

export default function AnswerSelectionEvidence({ value }: { value: unknown }) {
  const record = selectionRecord(value);
  const field = (name: string) => {
    const value = record[name];
    return typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
  };
  return (
    <section className="gt-selection" aria-label="Answer selection evidence">
      <h3>{selectionLabel(record.mode)}</h3>
      {Object.keys(record).length ? (
        <dl className="gt-details">
          <dt>Decision</dt><dd>{field("decision")}</dd>
          <dt>Model</dt><dd>{field("model")}</dd>
          <dt>Revision</dt><dd>{field("revision")}</dd>
          <dt>Contract</dt><dd>{field("contract")}</dd>
          <dt>Null threshold</dt><dd>{field("threshold")}</dd>
        </dl>
      ) : <p className="gt-muted">This historical response did not record answer selection metadata.</p>}
      <p className="gt-muted">Selection scores are raw support signals, not calibrated probabilities. Full recorded diagnostics are in provenance.</p>
    </section>
  );
}
