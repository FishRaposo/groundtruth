/** Client output crosslinks only; parser, inference and source authority stay server-side. */
export type EvidenceRecord = Record<string, unknown>;
export type LinguisticContext = { question?: unknown; answer?: unknown; sources?: unknown; retrievalTrace?: unknown };
export type OutputCheck = "matched" | "mismatch" | "invalid" | "unavailable" | "refused" | "error";
export const object = (value: unknown): EvidenceRecord => value !== null && typeof value === "object" && !Array.isArray(value) ? value as EvidenceRecord : {};
export const records = (value: unknown): EvidenceRecord[] => Array.isArray(value) ? value.map(object) : [];
const equal = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => equal(v, b[i]));
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const x=object(a), y=object(b);
  return Object.keys(x).length === Object.keys(y).length && Object.keys(x).every(k => Object.hasOwn(y,k) && equal(x[k],y[k]));
};
const retained = (trace: unknown) => object(object(object(trace).provenance).answer_selection);
const modern = (r: EvidenceRecord) => r.contract === "requirement-evidence-v4" || ["evidence-profile-v6","evidence-profile-v7"].includes(String(object(r.evidence_profile).contract)) || ["procedure-output-cover-v6","procedure-output-cover-v7"].includes(String(object(r.contextual_mixed_output_certificate).contract));
export function hasLinguisticEvidence(value: unknown, trace: unknown) { return modern(object(value)) || modern(retained(trace)); }
function stable(value: EvidenceRecord) {
  const copy=structuredClone(value);
  for(const key of ["contextual_mixed_output_certificate","contextual_output_certificate","presentation_verification"]) delete copy[key];
  const read=object(copy.procedure_read_set);
  if(Object.hasOwn(read,"before_publication")) {
    if(!equal(read.before_publication,{consistent:true,reason:null,changed_source_ids:[],changed_groups:[]})) throw Error("Stale publication");
    delete read.before_publication;
  }
  return copy;
}
const points = (value: string, range: unknown) => {
  const r=object(range), text=Array.from(value);
  return Number.isSafeInteger(r.start) && Number.isSafeInteger(r.end) && Number(r.start)>=0 && Number(r.start)<Number(r.end) && Number(r.end)<=text.length ? text.slice(Number(r.start),Number(r.end)).join("") : null;
};
function wellFormed(value: string) {
  return !Array.from(value).some(c => c.length === 1 && c.charCodeAt(0)>=0xd800 && c.charCodeAt(0)<=0xdfff);
}
async function hashMatches(value: unknown, digest: unknown) {
  if(typeof value!=="string" || !wellFormed(value) || typeof digest!=="string" || !/^[a-f0-9]{64}$/.test(digest)) return false;
  const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,"0")).join("")===digest;
}
const citationFields=["citation_index","chunk_id","document_id","document_version","content_hash","quoted_text","answer_spans"];
const coreCitation=(c:EvidenceRecord)=>Object.fromEntries(citationFields.map(k=>[k,c[k]]));
const identityFields=["document_id","document_version","content_hash"];
const sameIdentity=(a:EvidenceRecord,b:EvidenceRecord)=>identityFields.every(k=>a[k]===b[k]);
const containsRange=(outer:unknown,inner:unknown)=>{
  const a=object(outer),b=object(inner);
  return Number.isSafeInteger(a.start) && Number.isSafeInteger(a.end) && Number.isSafeInteger(b.start) && Number.isSafeInteger(b.end)
    && Number(a.start)<=Number(b.start) && Number(b.start)<Number(b.end) && Number(b.end)<=Number(a.end);
};
const composedRange=(chunk:EvidenceRecord,local:unknown,document:unknown)=>{
  const base=object(chunk.document_range),a=object(local),b=object(document);
  return Number(base.start)+Number(a.start)===b.start && Number(base.start)+Number(a.end)===b.end;
};
const sameSource=(a:EvidenceRecord,b:EvidenceRecord)=>sameIdentity(a,b) && a.workspace_id===b.workspace_id;
// Wire-equivalent Python str.split whitespace, without case/Unicode normalization.
const literalSpace=(value:unknown)=>typeof value==="string" ? value.split(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/).filter(Boolean).join(" ") : null;
/** Recorded count crosslinks only. Python owns grammar, parser and NLI decisions. */
function countShape(proof:EvidenceRecord,source:EvidenceRecord,row:EvidenceRecord,group:EvidenceRecord,selection:EvidenceRecord) {
  const binding=object(proof.binding), body=source.body, req=object(binding.request_requirement);
  const raw=object(binding.raw_value), whole=object(binding.whole_source), field=object(binding.canonical_field);
  const number=object(binding.number), amount=object(binding.amount), unit=object(binding.declared_counted_np), target=object(binding.actual_target);
  const alignment=object(object(binding.counted_np_alignment).declared);
  const planned=records(object(selection.request_plan).requirements).find(r=>r.id===row.id);
  if(typeof body!=="string" || proof.contract!=="source-bound-count-capture-v1"
    || binding.contract!=="literal-source-quantity-binding-v1" || binding.method!=="complete_literal_count_field_v3"
    || binding.model_support!=="NOT_ASSERTED" || !sameSource(object(binding.source_identity),source)
    || !equal(field.immutable_field_source,binding.source_identity)
    || req.id!==row.id || req.kind!=="quantity" || req.relation!=="count"
    || req.question!==row.prepared_question || req.original_text!==row.original_text
    || !equal(req,planned)
    || ![field.requested_target,req.topic,alignment.source_np,alignment.requested_np,field.counted_np,object(binding.canonical_value).unit].every(value=>typeof value==="string" && literalSpace(value)!=="")
    || literalSpace(target.text)!==field.requested_target || field.requested_target!==literalSpace(req.topic)
    || literalSpace(unit.text)!==alignment.source_np || alignment.requested_np!==field.counted_np
    || object(binding.canonical_value).unit!==field.counted_np
    || req.input_start!==object(row.input_range).start || req.input_end!==object(row.input_range).end
    || !Array.isArray(req.depends_on) || req.depends_on.length!==0
    || object(object(proof.request_capture).annotation).raw_text!==row.prepared_question
    || object(object(proof.source_capture).annotation).raw_text!==body
    || whole.start!==0 || whole.end!==Array.from(body).length || whole.text!==body
    || typeof binding.value_identity!=="string" || !/^[a-f0-9]{64}$/.test(binding.value_identity)
    || raw.text!==group.value || !containsRange(amount,number)
    || !equal(field.number_range,[number.start,number.end])
    || !equal(field.counted_np_range,[unit.start,unit.end])
    || ![number,amount,unit,target,raw].every(span=>typeof span.text==="string" && points(body,span)===span.text)
    || !records(group.origins).every(origin=>equal(origin.document_range,{start:raw.start,end:raw.end}))) return false;
  const candidates=records(selection.candidates).filter(c=>records(group.origins).some(o=>object(c.proposal).proposal_id===o.proposal_id) && Object.hasOwn(c,"support"));
  return candidates.length===1 && equal(candidates[0].quantity_binding,proof);
}
/** Versioned structural dispatch only. Recorded semantic checks remain server evidence. */
function procedureShape(proof:EvidenceRecord,source:EvidenceRecord,guard:EvidenceRecord,requirementId:unknown) {
  const body=source.body;
  if(typeof body!=="string" || typeof source.workspace_id!=="string" || !source.workspace_id
    || !Number.isSafeInteger(source.document_version) || Number(source.document_version)<1) return false;
  const end=Array.from(body).length,whole={start:0,end},closure={kind:"immutable_eof",offset:end};
  if(proof.contract!=="complete-immutable-procedure-v5" || !sameSource(proof,source) || proof.source_body!==body || proof.body_length!==end
    || !equal(proof.extent,whole) || !equal(proof.closure,closure) || !Array.isArray(proof.proof_units)) return false;
  const inventory=object(proof.inventory), consumer=object(guard.consumer_proof), envelope=object(consumer.envelope_inventory);
  // The current source guard has its own known consumer contract, even where
  // the selected procedure's reconstruction method uses a different inventory.
  if(guard.requirement_id!==requirementId || !sameIdentity(object(guard.source_identity),source)
    || consumer.contract!==proof.contract || consumer.method!=="consumer_envelope" || consumer.status!=="discharged"
    || consumer.requirement_id!==requirementId || !sameSource(object(consumer.source_identity),source)
    || envelope.contract!==proof.contract || envelope.method!==consumer.method || envelope.reading_profile!=="contextual_source_v2"
    || !sameSource(object(envelope.source_identity),source) || envelope.source_body!==body || envelope.body_length!==end
    || !equal(envelope.envelope_range,whole) || !equal(envelope.closure,closure)
    || !equal(consumer.literal_scope,envelope.literal_scope) || typeof object(envelope.literal_scope).disclosure!=="string"
    || !String(object(envelope.literal_scope).disclosure).trim()) return false;
  if(proof.method==="consumer_envelope") {
    if(!equal(inventory,envelope) || proof.proof_units.length!==0) return false;
  } else if(proof.method==="declared_envelope") {
    // The producer explicitly uses the immutable v1 envelope inside this v5 proof.
    if(inventory.contract!=="complete-immutable-procedure-v4" || inventory.reading_profile!=="contextual_source_v1" || Object.hasOwn(inventory,"method")
      || !sameSource(object(inventory.source_identity),source) || inventory.source_body!==body || inventory.body_length!==end
      || !equal(inventory.envelope_range,whole) || !equal(inventory.closure,closure) || !proof.proof_units.length) return false;
  } else if(proof.method==="canonical_discovery") {
    if(inventory.contract!=="procedure-required-inventory-v1" || Object.hasOwn(inventory,"method") || !sameSource(inventory,source)
      || points(body,inventory.extent)===null || !proof.proof_units.length) return false;
  } else return false;
  return records(proof.proof_units).every(unit=>points(body,unit.source_range)!==null
    && (["exact_source_copy","exact_source_structure"].includes(String(unit.verification_method))
      || (unit.verification_method==="nli_entailment" && points(body,unit.premise_range)===unit.premise && typeof unit.hypothesis==="string")));
}

/** A matching result checks these rendered bytes/crosslinks, never general answer correctness. */
export async function checkLinguisticOutput(value: unknown, context: LinguisticContext): Promise<OutputCheck> {
  try {
    const record=object(value), profile=object(record.evidence_profile), capture=retained(context.retrievalTrace);
    const countProfile=profile.contract==="evidence-profile-v7", outputContract=countProfile ? "procedure-output-cover-v7" : "procedure-output-cover-v6";
    const knownProfile={ contract:countProfile ? "evidence-profile-v7" : "evidence-profile-v6", evidence_reading_profile:"contextual_source_v2", requirement_contract:"requirement-evidence-v4", request_plan_contract:"linguistic-request-plan-v1", scope_cover_contract:"declared-source-scope-cover-v1", role_manifest_contract:"declared-context-role-manifest-v2", procedure_contract:"complete-immutable-procedure-v5", output_contract:outputContract, request_parser_mode:"local_dependency", request_parser_contract:"dependency-request-capture-v1", ...(countProfile ? {quantity_verification_profile:"literal_source_count_v1",quantity_binding_contract:"literal-source-quantity-binding-v1"} : {}) };
    if(record.mode!=="reader" || !Object.entries(knownProfile).every(([key,v])=>profile[key]===v) || record.contract!=="requirement-evidence-v4"
      || !equal(stable(record),stable(capture)) || !Object.keys(capture).length || !Array.isArray(record.requirements)) return "invalid";
    const plan=object(record.request_plan);
    if(plan.contract!=="linguistic-request-plan-v1" || plan.question!==context.question) return "invalid";
    if(record.decision==="error" || object(record.presentation_verification).status==="invalid") return "error";
    if(record.decision==="refused") return "refused";
    const cert=object(record.contextual_mixed_output_certificate), rows=records(record.requirements), planned=records(plan.requirements);
    if(record.decision!=="answer" || cert.contract!==outputContract || cert.reading_profile!=="contextual_source_v2" || cert.renderer!=="extractive-answer-v1"
      || !equal(cert.request_plan,plan) || !equal(object(cert.model_settings).evidence_profile,profile) || !equal(cert.selected_proposal_ids,record.selected_proposal_ids)
      || !rows.length || rows.length!==planned.length || !rows.every((row,i)=>row.id===planned[i].id && row.kind===planned[i].kind && row.status==="supported"
        && typeof context.question==="string" && points(context.question,row.input_range)===row.original_text)
      || typeof context.answer!=="string" || !Array.isArray(context.sources)) return "invalid";
    if(!equal(records(cert.citations).map(coreCitation),context.sources.map(object).map(coreCitation))) return "mismatch";
    const inventory=records(cert.source_inventory), fragments=records(cert.selected_fragments), disclosures=records(cert.disclosures), citations=records(cert.citations);
    const assessed=records(cert.assessed_inventory), selected=record.selected_proposal_ids;
    // The display consumes assessed proof metadata, so bind it to the independent
    // retained copy as well as the selected witnesses below. This is not inference.
    if(!Array.isArray(cert.assessed_inventory) || !equal(cert.assessed_inventory,object(capture.contextual_mixed_output_certificate).assessed_inventory)
      || !Array.isArray(selected) || !selected.length || new Set(selected).size!==selected.length || selected.some(id=>typeof id!=="string" || !id)) return "invalid";
    const sources=new Map(inventory.map(s=>[s.document_id,s]));
    if(!inventory.length || sources.size!==inventory.length || !fragments.length || !citations.length || new Set(context.sources.map(object).map(s=>s.document_id)).size>8
      || new Set(rows.map(r=>r.id)).size!==rows.length) return "invalid";
    const chunkIds=new Set<unknown>();
    for(const source of inventory) {
      if(typeof source.document_id!=="string" || !source.document_id || typeof source.body!=="string" || !Array.isArray(source.chunks) || !source.chunks.length) return "invalid";
      for(const chunk of records(source.chunks)) {
        if(typeof chunk.id!=="string" || !chunk.id || chunkIds.has(chunk.id) || typeof chunk.content!=="string" || points(source.body,chunk.document_range)!==chunk.content) return "invalid";
        chunkIds.add(chunk.id);
      }
    }
    const citedChunks=new Set<unknown>();
    for(let index=0;index<citations.length;index++) {
      const citation=citations[index];
      const source=sources.get(citation.document_id), chunk=source && records(source.chunks).find(c=>c.id===citation.chunk_id);
      const spans=records(citation.answer_spans);
      if(!source || !chunk || !sameIdentity(source,citation) || chunk.content!==citation.quoted_text || citation.citation_index!==index+1 || citedChunks.has(citation.chunk_id)
        || !spans.length || !spans.every(s=>points(String(chunk.content),s)===s.text) || !context.answer.includes(`[${index+1}]`)) return "invalid";
      citedChunks.add(citation.chunk_id);
    }
    for(const f of fragments) {
      const source=sources.get(f.document_id), chunk=source && records(source.chunks).find(c=>c.id===f.chunk_id);
      const citation=citations.find(c=>c.chunk_id===f.chunk_id && sameIdentity(c,f));
      if(!source || !chunk || typeof source.body!=="string" || typeof chunk.content!=="string" || source.document_version!==f.document_version || source.content_hash!==f.content_hash
        || points(source.body,f.document_range)!==f.text || points(chunk.content,f.chunk_range)!==f.text || points(context.answer,f.answer_range)!==f.text
        || !composedRange(chunk,f.chunk_range,f.document_range) || !citation || !records(citation.answer_spans).some(s=>containsRange(s,f.chunk_range))
        || !rows.some(r=>r.id===f.requirement_id)) return "mismatch";
    }
    if(!citations.every(c=>fragments.some(f=>f.chunk_id===c.chunk_id && sameIdentity(f,c)))
      || !rows.every(row=>fragments.some(f=>f.requirement_id===row.id)) || disclosures.some(d=>points(String(context.answer),d.answer_range)!==d.text)) return "invalid";
    const selectedGroups=assessed.filter(g=>records(g.origins).some(o=>selected.includes(o.proposal_id)));
    const used=new Set<unknown>();
    for(const group of selectedGroups) {
      const descriptor=object(group.descriptor), origins=records(group.origins), row=rows.find(r=>r.id===group.requirement_id);
      const source=sources.get(descriptor.document_id), proof=object(descriptor.procedure_completeness);
      const witness=row && records(row.witnesses).find(w=>equal(w.proposals,group.origins));
      if(group.supported!==true || !origins.length || !source || !witness || group.value!==descriptor.value || typeof group.value!=="string" || !group.value
        || !Object.entries(descriptor).every(([k,v])=>k==="nli_pairs" || equal(witness[k],v))
        || new Set(origins.map(o=>o.proposal_id)).size!==origins.length
        || !origins.every(o=>selected.includes(o.proposal_id) && !used.has(o.proposal_id) && sameIdentity(o,descriptor)
          && o.requirement_id===group.requirement_id && records(record.proposals).some(p=>equal(p,o)))) return "invalid";
      for(const origin of origins) {
        const chunk=records(source.chunks).find(c=>c.id===origin.chunk_id);
        if(!chunk || typeof origin.text!=="string" || points(String(source.body),origin.document_range)!==origin.text
          || points(String(chunk.content),origin.chunk_range)!==origin.text || !composedRange(chunk,origin.chunk_range,origin.document_range)) return "invalid";
        used.add(origin.proposal_id);
      }
      if(countProfile && row?.kind==="quantity") {
        if(!countShape(object(descriptor.quantity_binding),source,row,group,record)) return "invalid";
      } else if(Object.hasOwn(descriptor,"quantity_binding")) return "invalid";
      const parts=fragments.filter(f=>f.requirement_id===group.requirement_id && sameIdentity(f,descriptor));
      if(row?.kind==="procedure") {
        const proofParts=records(proof.fragments), rendered=records(cert.procedure_groups).find(g=>g.requirement_id===group.requirement_id && g.document_id===descriptor.document_id);
        if(!procedureShape(proof,source,object(group.source_guard),group.requirement_id)
          || group.value!==source.body || proof.source_body!==source.body || !equal(witness.procedure_completeness,row.procedure_completeness)
          || !rendered || rendered.text!==group.value || points(context.answer,rendered.answer_range)!==group.value
          || !proofParts.length || parts.length!==proofParts.length
          || !equal(rendered.chunk_ids,proofParts.map(p=>p.chunk_id))
          || !equal(rendered.fragments,proofParts.map(p=>({chunk_id:p.chunk_id,start:p.chunk_start,end:p.chunk_end})))) return "invalid";
        let cursor=0;
        for(let index=0;index<proofParts.length;index++) {
          const p=proofParts[index],f=parts[index],answerStart=Number(object(rendered.answer_range).start);
          // Full-body producer emits an exact ordered partition: no omitted
          // whitespace, separators, overlaps, duplicate parts or repeated-text remapping.
          if(p.document_start!==cursor || !Number.isSafeInteger(p.document_end) || Number(p.document_end)<=cursor
            || f.chunk_id!==p.chunk_id || !equal(f.chunk_range,{start:p.chunk_start,end:p.chunk_end})
            || !equal(f.document_range,{start:p.document_start,end:p.document_end})
            || !equal(f.answer_range,{start:answerStart+cursor,end:answerStart+Number(p.document_end)})) return "invalid";
          cursor=Number(p.document_end);
        }
        if(cursor!==Array.from(String(source.body)).length) return "invalid";
      } else if(Object.hasOwn(descriptor,"procedure_completeness") || Object.hasOwn(row || {},"procedure_completeness")
        || !parts.some(f=>f.chunk_id===descriptor.chunk_id && equal(f.document_range,descriptor.document_range)
        && equal(f.chunk_range,{start:object(descriptor.span).start,end:object(descriptor.span).end}) && f.text===object(descriptor.span).text
        && typeof f.text==="string" && f.text.includes(String(group.value)))) return "invalid";
    }
    if(used.size!==selected.length || !rows.every(row=>selectedGroups.some(g=>g.requirement_id===row.id))
      || !fragments.every(f=>selectedGroups.some(g=>g.requirement_id===f.requirement_id && sameIdentity(object(g.descriptor),f)))) return "invalid";
    if(!globalThis.crypto?.subtle?.digest || typeof TextEncoder==="undefined") return "unavailable";
    const valid=await Promise.all([hashMatches(context.question,cert.question_sha256),hashMatches(context.answer,cert.answer_sha256),...inventory.map(s=>hashMatches(s.body,s.content_hash))]);
    return valid.every(Boolean) ? "matched" : "mismatch";
  } catch { return "invalid"; }
}
