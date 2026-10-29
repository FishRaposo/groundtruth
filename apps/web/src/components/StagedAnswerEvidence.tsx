"use client";

import { useEffect, useState } from "react";
import { object, records, type EvidenceRecord, type LinguisticContext } from "@/lib/linguistic-evidence";
import { checkStagedEvidence, displayedGroups, type StagedStatus } from "@/lib/staged-evidence";

const scalar = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
const range = (value: unknown) => `${scalar(object(value).start)}–${scalar(object(value).end)}`;
function RecordedSource({ group, certificate }: { group: EvidenceRecord; certificate: EvidenceRecord }) {
  const descriptor = object(group.descriptor), proof = object(descriptor.procedure_completeness);
  const consumer = object(object(group.source_guard).consumer_proof), envelope = object(consumer.envelope_inventory);
  const procedure = proof.contract === "complete-immutable-procedure-v6";
  return <div>
    <p><strong>{procedure ? "Recorded exact source coverage" : "Recorded factual source support"}</strong></p>
    {procedure ? <>
      <p>Instructions, conditions, prohibitions and their order are retained as source text. Exact copying does not establish that an action is true, safe or applicable now.</p>
      <p><strong>Recorded subject and applicability NLI</strong></p>
      <p>NLI concerns the source subject and declared applicability. It does not validate the copied actions. Scores are uncalibrated signals.</p>
      <p>{scalar(object(consumer.literal_scope).disclosure)}</p>
    </> : <p>Clause and whole-source NLI checks are recorded server decisions; the browser does not rerun them.</p>}
    <details><summary>{procedure ? "Complete ordered source instructions" : "Selected source passage"}</summary>
      {procedure ? <ol>{records(envelope.ordered_ranges).map((part, i) => <li key={i}>
        <p>{scalar(part.kind)} · source codepoints {range(part)}</p>
        <pre className="whitespace-pre-wrap break-words">{scalar(part.text)}</pre>
      </li>)}</ol> : <pre className="whitespace-pre-wrap break-words">{scalar(group.value)}</pre>}
    </details>
    <details><summary>Source identity, citation fragments and recorded checks</summary>
      <p>Document {scalar(descriptor.document_id)} · version {scalar(descriptor.document_version)}</p>
      <p className="break-all">Source hash: {scalar(descriptor.content_hash)}</p>
      {procedure ? <p>Complete source codepoints {range(proof.extent)} · closure: {scalar(object(proof.closure).kind)}</p> : null}
      <ol>{records(certificate.selected_fragments).filter(f => f.requirement_id === group.requirement_id && f.document_id === descriptor.document_id).map((f, i) => <li key={i}>
        <p>Source codepoints {range(f.document_range)} · chunk {scalar(f.chunk_id)} codepoints {range(f.chunk_range)} · answer codepoints {range(f.answer_range)}</p>
        <blockquote className="whitespace-pre-wrap break-words">{scalar(f.text)}</blockquote>
      </li>)}</ol>
      {records(consumer.nli_assessments).length ? <ul>{records(consumer.nli_assessments).map((check, i) => <li key={i}>
        <p>{scalar(check.name)} · recorded NLI: {scalar(object(check.assessment).label)} · margin {scalar(object(check.assessment).entailment_margin)}</p>
        <p>Source codepoints {range(check.source_range)} · premise: {scalar(check.premise)}</p>
        <p>Hypothesis: {scalar(check.hypothesis)}</p>
      </li>)}</ul> : null}
    </details>
  </div>;
}
const messages: Record<StagedStatus | "pending", string> = {
  pending: "Checking displayed evidence context…",
  verified: "Server reports presentation verified; displayed context matches recorded ranges.",
  unverified: "Presentation verification is unknown or unverified. Recorded evidence is not newly certified here.",
  refused: "No complete answer published. One or more request obligations remain unresolved.",
  error: "Execution or integrity verification failed. Answer evidence is withheld.",
  invalid: "Recorded evidence is incomplete or inconsistent. Answer evidence is withheld.",
  mismatch: "Displayed answer or citations do not match recorded evidence. Answer evidence is withheld.",
  unavailable: "Displayed evidence checks are unavailable in this browser. Verification remains unknown.",
  uncovered: "Complete displayed output cannot be reconstructed. Verification remains unknown; answer evidence is withheld.",
};
export default function StagedAnswerEvidence({ value, ...context }: LinguisticContext & { value: unknown }) {
  const key = JSON.stringify([value, context]);
  const [result, setResult] = useState<{ key: string; status: StagedStatus } | null>(null);
  useEffect(() => {
    let current = true;
    const [capturedValue, capturedContext] = JSON.parse(key);
    void checkStagedEvidence(capturedValue, capturedContext).then(status => { if (current) setResult({ key, status }); });
    return () => { current = false; };
  }, [key]);
  const status = result?.key === key ? result.status : "pending";
  const record = object(value), certificate = object(record.staged_output_certificate), plan = object(record.request_plan);
  const rows = records(record.requirements), show = ["verified", "unverified", "refused"].includes(status);
  const groups = status === "verified" || status === "unverified" ? displayedGroups(record, certificate) : [];
  const reason = object(record.presentation_verification).reason ?? record.reason;
  return <section className="gt-selection" aria-label="Answer selection evidence">
    <h3>Staged request evidence</h3>
    <p className="gt-muted">Recorded server checks. This browser cross-checks displayed text and ranges; it does not rerun the parser or models, authenticate sources, grant access, or measure answer quality.</p>
    <p role="status">{messages[status]}</p>
    {typeof reason === "string" ? <p>Recorded reason: {reason}</p> : null}
    {show ? <>
      <details><summary>Original question</summary><p>{scalar(context.question)}</p></details>
      <section className="gt-requirements" aria-label="Request coverage">
        <h4>{rows.filter(r => r.status === "supported").length} of {rows.length} requirements recorded supported</h4>
        <p className="gt-muted">Resolving the request structure does not itself establish source authority, currentness or factual support.</p>
        <ol>{rows.map((row, i) => <li key={scalar(row.id) + i}>
          <strong>{scalar(row.original_text)}</strong>
          <p>Kind: {scalar(row.kind)} · recorded status: {scalar(row.status)}</p>
          {row.status !== "supported" ? <p>No supported evidence recorded for this requirement.</p> : null}
          {typeof row.reason === "string" ? <p>Recorded reason: {row.reason}</p> : null}
          {groups.filter(g => g.requirement_id === row.id).map((group, j) => <RecordedSource key={j} group={group} certificate={certificate} />)}
          {typeof row.prepared_question === "string" && row.prepared_question !== row.original_text ? <details><summary>Interpreted request</summary><p>{row.prepared_question}</p></details> : null}
        </li>)}</ol>
        {records(plan.unresolved).length ? <details><summary>Unresolved request obligations</summary><ul>{records(plan.unresolved).map((item, i) => <li key={i}>{scalar(item.reason)} · {scalar(item.obligation_id ?? item.owner_id)}</li>)}</ul></details> : null}
      </section>
      {records(certificate.disclosures).length ? <details><summary>Recorded activity and context scope</summary>{records(certificate.disclosures).map((d, i) => <p key={i}>{scalar(d.text)}</p>)}</details> : null}
    </> : null}
    <details><summary>Contract and model details</summary><dl className="gt-details">
      <dt>Requirement contract</dt><dd>{scalar(record.contract)}</dd>
      <dt>Reading profile</dt><dd>{scalar(object(record.evidence_profile).evidence_reading_profile)}</dd>
      <dt>Output contract</dt><dd>{scalar(certificate.contract)}</dd>
      <dt>Reader</dt><dd>{scalar(record.model)} · {scalar(record.revision)}</dd>
      <dt>Support classifier</dt><dd>{scalar(object(record.evidence_support).model)} · {scalar(object(record.evidence_support).revision)}</dd>
    </dl><p className="gt-muted">Historical missing verification stays unknown. Model names and hashes are recorded identities, not browser attestations.</p></details>
  </section>;
}
