"use client";

import { useEffect, useState } from "react";
import { checkLinguisticOutput, object, records, type LinguisticContext, type OutputCheck } from "@/lib/linguistic-evidence";

const scalar=(value:unknown)=>typeof value==="string" || typeof value==="number" ? String(value) : "unknown";
export default function LinguisticAnswerEvidence({ value, ...context }: LinguisticContext & { value: unknown }) {
  const key=JSON.stringify([value,context]);
  const [result,setResult]=useState<{key:string;status:OutputCheck}|null>(null);
  useEffect(()=>{
    let current=true;
    const [capturedValue,capturedContext]=JSON.parse(key);
    void checkLinguisticOutput(capturedValue,capturedContext).then(status=>{if(current)setResult({key,status});});
    return ()=>{current=false;};
  },[key]);
  const status=result?.key===key ? result.status : "pending";
  const record=object(value), rows=records(record.requirements), certificate=object(record.contextual_mixed_output_certificate);
  const matched=status==="matched", refusal=status==="refused";
  const groups=matched ? records(certificate.assessed_inventory).filter(g=>g.supported===true && records(g.origins).some(o=>Array.isArray(record.selected_proposal_ids) && record.selected_proposal_ids.includes(o.proposal_id))) : [];
  const procedure=rows.some(r=>r.kind==="procedure");
  return <section className="gt-selection" aria-label="Answer selection evidence">
    <h3>{procedure ? "Source-declared procedure copy" : "Local extractive reader"}</h3>
    <p className="gt-muted">The browser does not rerun the parser or models, authenticate stored records, or establish source authority. These are recorded server checks.</p>
    <p role="status">{status==="pending" ? "Checking recorded output…" : matched ? "Recorded output matches this answer." : status==="mismatch" ? "Recorded output does not match this answer." : refusal ? "No complete answer published." : status==="error" ? "Execution or integrity verification failed." : status==="unavailable" ? "Recorded output checks are unavailable in this browser." : "Recorded evidence is incomplete or inconsistent."}</p>
    {matched || refusal ? <section aria-label="Request coverage" className="gt-requirements">
      <h4>{rows.filter(r=>r.status==="supported").length} of {rows.length} requirements supported</h4>
      <p className="gt-muted">A complete answer needs every requested requirement. Support scores remain uncalibrated signals.</p>
      <ol>{rows.map((row,index)=>{
        const selected=groups.filter(g=>g.requirement_id===row.id);
        return <li key={scalar(row.id)+index}>
          <strong>{scalar(row.original_text)}</strong>
          <p>{row.status==="supported" ? "Supported by recorded source evidence" : "No verified evidence for this requirement. The complete request was refused."}</p>
          {typeof row.reason==="string" ? <p>Recorded reason: {row.reason}</p> : null}
          {selected.map((g,i)=>{
            const descriptor=object(g.descriptor), proof=object(descriptor.procedure_completeness), guard=object(object(g.source_guard).consumer_proof);
            const count=object(object(descriptor.quantity_binding).binding);
            const checks=records(guard.nli_assessments);
            return <div key={i}>
              {proof.method==="consumer_envelope" ? <>
                <p><strong>Recorded exact instruction coverage</strong></p>
                <p>Subject and applicability use recorded NLI support. Instructions and their order use exact source structure and copy checks.</p>
                <p>{scalar(object(guard.literal_scope).disclosure)}</p>
              </> : null}
              {count.contract==="literal-source-quantity-binding-v1" ? <>
                <p><strong>Recorded source-bound count</strong></p>
                <p>Exact source-field binding precedes recorded clause and whole-source NLI. The browser cross-checks the displayed ranges; it does not rerun those decisions.</p>
                <p>Field: {scalar(object(count.declared_counted_np).text)} · scope: {scalar(object(count.actual_target).text)}</p>
              </> : null}
              <details><summary>{proof.method==="consumer_envelope" ? "Complete source instructions" : "Selected source passage"}</summary><pre className="whitespace-pre-wrap break-words">{scalar(g.value)}</pre></details>
              <details><summary>Source identity and verification details</summary>
                <p>Document {scalar(descriptor.document_id)} · version {scalar(descriptor.document_version)}</p>
                <p className="break-all">Source hash: {scalar(descriptor.content_hash)}</p>
                {records(certificate.selected_fragments).filter(f=>f.requirement_id===row.id && f.document_id===descriptor.document_id).map((f,j)=><p key={j}>Supporting passage source codepoints {scalar(object(f.document_range).start)}–{scalar(object(f.document_range).end)} · answer codepoints {scalar(object(f.answer_range).start)}–{scalar(object(f.answer_range).end)}</p>)}
                {checks.length ? <ul>{checks.map((c,j)=><li key={j}>{scalar(c.name)} · recorded NLI: {scalar(object(c.assessment).label)} · margin {scalar(object(c.assessment).entailment_margin)}</li>)}</ul> : <p>{row.kind==="procedure" ? "Procedure support uses recorded whole-source checks." : "Factual support uses recorded clause and whole-source NLI checks."}</p>}
              </details>
            </div>;
          })}
          {typeof row.prepared_question==="string" && row.prepared_question!==row.original_text ? <details><summary>Interpreted request</summary><p>{row.prepared_question}</p></details> : null}
        </li>;
      })}</ol>
    </section> : null}
    <details><summary>Model and selection details</summary><dl className="gt-details"><dt>Reader</dt><dd>{scalar(record.model)}</dd><dt>Reader revision</dt><dd className="break-all">{scalar(record.revision)}</dd><dt>Support classifier</dt><dd>{scalar(object(record.evidence_support).model)}</dd><dt>Contract</dt><dd>{scalar(record.contract)}</dd></dl></details>
  </section>;
}
