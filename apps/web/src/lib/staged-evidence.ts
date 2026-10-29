/** Presentation crosslinks only. No parser, NLI, source-authority or permission verdict. */
import { object, records, type EvidenceRecord, type LinguisticContext } from "@/lib/linguistic-evidence";

export type StagedStatus = "verified" | "unverified" | "refused" | "error" | "invalid" | "mismatch" | "unavailable" | "uncovered";
const retained = (trace: unknown) => object(object(object(trace).provenance).answer_selection);
const marked = (r: EvidenceRecord) => r.contract === "requirement-evidence-v5"
  || object(r.evidence_profile).contract === "evidence-profile-v8"
  || object(r.evidence_profile).evidence_reading_profile === "contextual_source_v3"
  || object(r.request_plan).contract === "staged-request-plan-v1"
  || Object.hasOwn(r, "staged_output_certificate") || Object.hasOwn(r, "staged_request_inputs");
export const hasStagedEvidence = (value: unknown, trace: unknown) => marked(object(value)) || marked(retained(trace));
export const same = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b)
    && a.length === b.length && a.every((v, i) => same(v, b[i]));
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const x = object(a), y = object(b);
  return Object.keys(x).length === Object.keys(y).length && Object.keys(x).every(k => Object.hasOwn(y, k) && same(x[k], y[k]));
};
export function slicePoints(text: unknown, range: unknown): string | null {
  const r = object(range);
  if (typeof text !== "string" || typeof r.start !== "number" || typeof r.end !== "number"
    || !Number.isSafeInteger(r.start) || !Number.isSafeInteger(r.end) || r.start < 0 || r.end <= r.start) return null;
  const points = Array.from(text);
  return r.end <= points.length ? points.slice(r.start, r.end).join("") : null;
}
function stable(record: EvidenceRecord) {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !["presentation_verification", "staged_output_certificate", "staged_publication_check"].includes(key)));
}
const identity = (a: EvidenceRecord, b: EvidenceRecord) => ["document_id", "document_version", "content_hash"].every(k => a[k] === b[k]);
const coreCitation = (c: EvidenceRecord) => Object.fromEntries(["citation_index", "chunk_id", "document_id", "document_version", "content_hash", "quoted_text", "answer_spans"].map(k => [k, c[k]]));
function known(record: EvidenceRecord) {
  const profile = object(record.evidence_profile);
  return record.contract === "requirement-evidence-v5" && record.mode === "reader"
    && Object.entries({ contract: "evidence-profile-v8", evidence_reading_profile: "contextual_source_v3", requirement_contract: "requirement-evidence-v5", request_plan_contract: "staged-request-plan-v1", procedure_contract: "complete-immutable-procedure-v6", output_contract: "procedure-output-cover-v8", scope_cover_contract: "declared-source-scope-cover-v2", role_manifest_contract: "declared-context-role-manifest-v3" }).every(([k, v]) => profile[k] === v);
}
function orderedCopy(body: unknown, rows: unknown) {
  if (typeof body !== "string" || !Array.isArray(rows) || !rows.length) return false;
  let cursor = 0;
  for (const row of records(rows)) {
    if (row.start !== cursor || slicePoints(body, row) !== row.text) return false;
    cursor = Number(row.end);
  }
  return cursor === Array.from(body).length;
}
export function displayedGroups(record: EvidenceRecord, certificate: EvidenceRecord) {
  const ids = record.selected_proposal_ids;
  return records(certificate.assessed_inventory).filter(g => g.supported === true
    && records(g.origins).some(o => Array.isArray(ids) && ids.includes(o.proposal_id)));
}
function selectedGroups(record: EvidenceRecord, certificate: EvidenceRecord) {
  const ids = record.selected_proposal_ids;
  if (!Array.isArray(ids) || !ids.length || ids.some(id => typeof id !== "string" || !id) || new Set(ids).size !== ids.length) return false;
  const groups = displayedGroups(record, certificate);
  return groups.length > 0 && groups.every(g => g.supported === true && records(g.origins).length > 0)
    && ids.every(id => groups.some(g => records(g.origins).some(o => o.proposal_id === id)));
}
function procedureInventory(proof: EvidenceRecord, envelope: EvidenceRecord, source: EvidenceRecord) {
  const inventory = object(proof.inventory);
  if (proof.method === "consumer_envelope") return same(inventory, envelope);
  // These are explicit shared inventory versions inside the v6 descriptor;
  // the independently retained consumer envelope must still be actual v3.
  if (proof.method === "declared_envelope") return inventory.contract === "complete-immutable-procedure-v4"
    && inventory.reading_profile === "contextual_source_v1" && !Object.hasOwn(inventory, "method")
    && identity(object(inventory.source_identity), source) && inventory.source_body === source.body
    && slicePoints(source.body, inventory.envelope_range) === source.body;
  return proof.method === "canonical_discovery" && inventory.contract === "procedure-required-inventory-v1"
    && identity(inventory, source) && slicePoints(source.body, inventory.extent) !== null;
}
function groupShape(group: EvidenceRecord, certificate: EvidenceRecord, record: EvidenceRecord) {
  const descriptor = object(group.descriptor), guard = object(group.source_guard), consumer = object(guard.consumer_proof);
  const sources = records(certificate.source_inventory).filter(s => identity(s, descriptor));
  const row = records(record.requirements).find(r => r.id === group.requirement_id);
  if (!row || sources.length !== 1 || !records(row.witnesses).some(w => Object.keys(descriptor).every(k => same(w[k], descriptor[k])))) return false;
  const source = sources[0];
  if (typeof source.body !== "string" || typeof source.document_version !== "number" || !Number.isSafeInteger(source.document_version)
    || source.document_version < 1 || typeof source.content_hash !== "string" || !/^[a-f0-9]{64}$/.test(source.content_hash)) return false;
  const retainedSources = records(object(record.staged_request_inputs).snapshots).filter(s => identity(object(s.identity), source));
  if (retainedSources.length !== 1 || retainedSources[0].body !== source.body
    || object(retainedSources[0].identity).workspace_id !== source.workspace_id
    || records(retainedSources[0].chunks).length !== records(source.chunks).length
    || !records(source.chunks).every(c => records(retainedSources[0].chunks).filter(p => p.chunk_id === c.id && p.ordinal === c.index
      && object(p.literal).text === c.content && same({ start: object(p.literal).start, end: object(p.literal).end }, c.document_range)).length === 1)) return false;
  if (row.kind !== "procedure") return descriptor.value === group.value && slicePoints(source.body, descriptor.document_range) === group.value;
  const proof = object(descriptor.procedure_completeness), envelope = object(consumer.envelope_inventory);
  const retainedGuards = records(record.source_guard_records).filter(g => g.requirement_id === group.requirement_id && identity(object(g.source_identity), source));
  const fragments = records(certificate.selected_fragments).filter(f => f.requirement_id === group.requirement_id && identity(f, source));
  const rendered = records(certificate.procedure_groups).filter(g => g.requirement_id === group.requirement_id && g.document_id === source.document_id);
  const copiedRanges = fragments.map(f => ({ ...object(f.document_range), text: f.text }));
  const nli = records(consumer.nli_assessments), obligations = records(envelope.nli_obligations);
  return proof.contract === "complete-immutable-procedure-v6" && identity(proof, source)
    && proof.source_body === source.body && proof.body_length === Array.from(source.body).length
    && group.value === source.body && slicePoints(source.body, proof.extent) === source.body
    && envelope.contract === proof.contract && envelope.reading_profile === "contextual_source_v3"
    && identity(object(envelope.source_identity), source) && envelope.source_body === source.body
    && procedureInventory(proof, envelope, source) && orderedCopy(source.body, envelope.ordered_ranges)
    && orderedCopy(source.body, envelope.covered_units)
    && orderedCopy(source.body, copiedRanges) && rendered.length === 1 && rendered[0].text === source.body
    && retainedGuards.length === 1 && same(retainedGuards[0].envelope_inventory, envelope)
    && same(retainedGuards[0].nli_assessments, consumer.nli_assessments)
    && same(consumer.literal_scope, envelope.literal_scope)
    && obligations.length > 0 && nli.length === obligations.length
    && nli.every((c, i) => Object.keys(obligations[i]).every(k => same(c[k], obligations[i][k]))
      && slicePoints(source.body, c.source_range) === c.premise);
}
function fragmentShape(fragment: EvidenceRecord, certificate: EvidenceRecord, answer: unknown) {
  const sources = records(certificate.source_inventory).filter(s => identity(s, fragment));
  const citations = records(certificate.citations).filter(c => identity(c, fragment) && c.chunk_id === fragment.chunk_id);
  if (sources.length !== 1 || citations.length !== 1) return false;
  const chunks = records(sources[0].chunks).filter(c => c.id === fragment.chunk_id);
  if (chunks.length !== 1) return false;
  const chunk = chunks[0], base = object(chunk.document_range), local = object(fragment.chunk_range), document = object(fragment.document_range);
  return slicePoints(sources[0].body, chunk.document_range) === chunk.content && chunk.content === citations[0].quoted_text
    && slicePoints(sources[0].body, document) === fragment.text && slicePoints(chunk.content, local) === fragment.text
    && slicePoints(answer, fragment.answer_range) === fragment.text
    && Number(base.start) + Number(local.start) === document.start && Number(base.start) + Number(local.end) === document.end
    && records(citations[0].answer_spans).some(span => slicePoints(chunk.content, span) === span.text
      && Number(span.start) <= Number(local.start) && Number(span.end) >= Number(local.end));
}
const length = (text: string) => Array.from(text).length;
const pythonSpace = "\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const blank = new RegExp(`^[${pythonSpace}]*$`);
const joiningGap = new RegExp(`^[${pythonSpace},;]*(?:(?:and|but|wherea[sſ]|wh[iİı]le)[${pythonSpace}]*)?$`, "i");
type Interval = { start: number; end: number };
type Passage = Interval & { text: string };
function interval(value: unknown): Interval | null {
  const r = object(value);
  return typeof r.start === "number" && typeof r.end === "number" && Number.isSafeInteger(r.start)
    && Number.isSafeInteger(r.end) && r.start >= 0 && r.end > r.start ? { start: r.start, end: r.end } : null;
}
function pointSlice(text: string, start: number, end: number) { return Array.from(text).slice(start, end).join(""); }
function orderedWitnessGroups(record: EvidenceRecord, certificate: EvidenceRecord): EvidenceRecord[] | null {
  const groups = displayedGroups(record, certificate), chosen: EvidenceRecord[] = [], used = new Set<unknown>();
  const selected = record.selected_proposal_ids;
  if (!Array.isArray(selected)) return null;
  for (const row of records(record.requirements)) {
    let count = 0;
    for (const witness of records(row.witnesses)) {
      const origins = records(witness.proposals);
      if (!origins.some(o => selected.includes(o.proposal_id))) continue;
      const matches = groups.filter(g => g.requirement_id === row.id && same(g.origins, witness.proposals)
        && Object.keys(object(g.descriptor)).every(k => k === "nli_pairs" || same(witness[k], object(g.descriptor)[k])));
      if (matches.length !== 1 || origins.some(o => !selected.includes(o.proposal_id) || used.has(o.proposal_id))) return null;
      origins.forEach(o => used.add(o.proposal_id));
      chosen.push(matches[0]); count++;
    }
    if (!count) return null;
  }
  return used.size === selected.length && chosen.length === groups.length ? chosen : null;
}
function boundDisclosures(record: EvidenceRecord, chosen: EvidenceRecord[]): EvidenceRecord[] | null {
  const result: EvidenceRecord[] = [];
  for (const group of chosen) {
    if (!Object.hasOwn(object(group.descriptor), "procedure_completeness")) continue;
    const consumer = object(object(group.source_guard).consumer_proof);
    if (consumer.method !== "consumer_envelope") return null;
    const source = object(object(group.descriptor).procedure_completeness);
    const guards = records(record.source_guard_records).filter(g => g.requirement_id === group.requirement_id && identity(object(g.source_identity), source));
    if (guards.length !== 1) return null;
    const scope = object(object(guards[0].envelope_inventory).literal_scope);
    if (typeof scope.disclosure !== "string" || blank.test(scope.disclosure) || !same(scope, consumer.literal_scope)) return null;
    result.push({ kind: "source_declared_scope", requirement_id: group.requirement_id, source_identity: guards[0].source_identity, text: scope.disclosure });
  }
  // Role interpretation records belong to the unchanged retained selection;
  // derived certificate role_scope/disclosures cannot introduce new text.
  const interpretations = records(record.role_scope_interpretations);
  for (const row of records(record.requirements)) {
    const matched = interpretations.filter(i => i.requirement_id === row.id);
    if (!matched.length) {
      if (row.role_scope_interpretation) return null;
      continue;
    }
    if (matched.length !== 1 || !same(row.role_scope_interpretation, matched[0]) || matched[0].contract !== "ordinary-session-activity-role-v1") return null;
    const text = matched[0].disclosure;
    if (text === null || text === "") continue;
    if (typeof text !== "string" || blank.test(text)) return null;
    result.push({ kind: "activity_role_scope", requirement_id: row.id, text });
  }
  if (interpretations.some(i => !records(record.requirements).some(r => r.id === i.requirement_id))) return null;
  return result;
}
/** Mirror extractive-answer-v1 literal emissions, not model/authority decisions. */
export function reconstructStagedRendering(record: EvidenceRecord, certificate: EvidenceRecord, answer: unknown): boolean | null {
  const chosen = orderedWitnessGroups(record, certificate);
  if (!chosen) return null;
  const disclosures = boundDisclosures(record, chosen);
  if (!disclosures) return null;
  const fragments: EvidenceRecord[] = [], procedureGroups: EvidenceRecord[] = [];
  const chunks = new Map<unknown, { content: string; source: EvidenceRecord }>();
  for (const group of chosen) {
    const d = object(group.descriptor), source = records(certificate.source_inventory).find(s => identity(s, d));
    if (!source || typeof source.body !== "string") return null;
    for (const chunk of records(source.chunks)) {
      if (typeof chunk.content !== "string" || chunks.has(chunk.id) && !same(chunks.get(chunk.id), { content: chunk.content, source })) return null;
      chunks.set(chunk.id, { content: chunk.content, source });
    }
    const proof = object(d.procedure_completeness), parts: EvidenceRecord[] = [];
    const sourceIdentity = Object.fromEntries(["document_id", "document_version", "content_hash"].map(k => [k, source[k]]));
    if (Object.hasOwn(d, "procedure_completeness")) {
      for (const part of records(proof.fragments)) {
        const document = { start: part.document_start, end: part.document_end }, text = slicePoints(source.body, document);
        if (text === null || !interval({ start: part.chunk_start, end: part.chunk_end })) return null;
        fragments.push({ requirement_id: group.requirement_id, ...sourceIdentity, chunk_id: part.chunk_id, chunk_range: { start: part.chunk_start, end: part.chunk_end }, document_range: document, text });
        parts.push({ chunk_id: part.chunk_id, start: part.chunk_start, end: part.chunk_end });
      }
      procedureGroups.push({ requirement_id: group.requirement_id, document_id: source.document_id, text: source.body, chunk_ids: parts.map(p => p.chunk_id), fragments: parts });
    } else {
      fragments.push({ requirement_id: group.requirement_id, ...sourceIdentity, chunk_id: d.chunk_id, chunk_range: { start: object(d.span).start, end: object(d.span).end }, document_range: d.document_range, text: object(d.span).text });
    }
  }
  const spans = new Map<unknown, Interval[]>();
  for (const f of fragments) {
    const range = interval(f.chunk_range);
    if (!range || !chunks.has(f.chunk_id)) return null;
    spans.set(f.chunk_id, [...(spans.get(f.chunk_id) ?? []), range]);
  }
  const citations: EvidenceRecord[] = [];
  for (const [id, ranges] of Array.from(spans.entries())) {
    const chunk = chunks.get(id);
    if (!chunk) return null;
    const merged: Passage[] = [];
    for (const current of ranges.sort((a, b) => a.start - b.start || a.end - b.end)) {
      let { start, end } = current;
      const previous = merged[merged.length - 1];
      if (previous && (start <= previous.end || joiningGap.test(pointSlice(chunk.content, previous.end, start)))) {
        merged.pop(); start = previous.start; end = Math.max(end, previous.end);
      }
      const text = slicePoints(chunk.content, { start, end });
      if (text === null) return null;
      merged.push({ start, end, text });
    }
    citations.push({ citation_index: citations.length + 1, chunk_id: id, ...Object.fromEntries(["document_id", "document_version", "content_hash"].map(k => [k, chunk.source[k]])), quoted_text: chunk.content, answer_spans: merged });
  }
  const prefix = disclosures.length ? "Source extracts with declared activity-scope interpretation:\n\n" : "Source extracts (not model-generated):\n\n";
  const extracts: string[] = [], segments: { chunk: unknown; start: number; end: number; answerStart: number }[] = [];
  let cursor = length(prefix);
  for (const group of procedureGroups) {
    if (typeof group.text !== "string" || !Array.isArray(group.chunk_ids)) return null;
    const indices = group.chunk_ids.map(id => citations.find(c => c.chunk_id === id)?.citation_index);
    if (indices.some(i => typeof i !== "number")) return null;
    const text = group.text + " " + indices.map(i => `[${i}]`).join(" ");
    group.answer_range = { start: cursor, end: cursor + length(group.text) };
    extracts.push(text); cursor += length(text) + 2;
  }
  for (const citation of citations) {
    const passage = String(citation.quoted_text), sourceSpans = records(citation.answer_spans);
    if (!procedureGroups.length) {
      let local = cursor;
      for (const span of sourceSpans) { segments.push({ chunk: citation.chunk_id, start: Number(span.start), end: Number(span.end), answerStart: local }); local += length(String(span.text)) + 1; }
      const text = sourceSpans.map(s => s.text).join("\n") + ` [${citation.citation_index}]`;
      extracts.push(text); cursor += length(text) + 2;
      continue;
    }
    const covered = procedureGroups.flatMap(g => records(g.fragments)).filter(p => p.chunk_id === citation.chunk_id).map(p => ({ start: Number(p.start), end: Number(p.end) })).sort((a, b) => a.start - b.start || a.end - b.end);
    for (const span of sourceSpans) {
      let remaining = [{ start: Number(span.start), end: Number(span.end) }];
      for (const cover of covered) remaining = [
        ...remaining.filter(r => r.start < Math.min(r.end, cover.start)).map(r => ({ start: r.start, end: Math.min(r.end, cover.start) })),
        ...remaining.filter(r => Math.max(r.start, cover.end) < r.end).map(r => ({ start: Math.max(r.start, cover.end), end: r.end })),
      ];
      for (const r of remaining) {
        const raw = pointSlice(passage, r.start, r.end);
        if (blank.test(raw)) continue;
        segments.push({ chunk: citation.chunk_id, ...r, answerStart: cursor });
        const text = raw + ` [${citation.citation_index}]`;
        extracts.push(text); cursor += length(text) + 2;
      }
    }
  }
  for (const fragment of fragments) {
    const group = procedureGroups.find(g => g.document_id === fragment.document_id);
    const local = object(fragment.chunk_range), source = object(fragment.document_range);
    const segment = segments.find(s => s.chunk === fragment.chunk_id && s.start <= Number(local.start) && Number(local.end) <= s.end);
    const start = group ? Number(object(group.answer_range).start) + Number(source.start) : segment ? segment.answerStart + Number(local.start) - segment.start : null;
    if (start === null || typeof fragment.text !== "string") return null;
    fragment.answer_range = { start, end: start + length(fragment.text) };
  }
  for (const disclosure of disclosures) {
    if (typeof disclosure.text !== "string") return null;
    disclosure.answer_range = { start: cursor, end: cursor + length(disclosure.text) };
    cursor += length(disclosure.text) + 2;
  }
  return answer === prefix + [...extracts, ...disclosures.map(d => d.text)].join("\n\n")
    && same(citations, records(certificate.citations).map(coreCitation))
    && same(fragments, certificate.selected_fragments) && same(procedureGroups, certificate.procedure_groups)
    && same(disclosures, certificate.disclosures);
}
async function digestMatches(text: unknown, digest: unknown) {
  if (typeof text !== "string" || typeof digest !== "string" || !/^[a-f0-9]{64}$/.test(digest)) return false;
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("") === digest;
}
/** A server verification status is necessary; a producer hash/success flag cannot grant it. */
export async function checkStagedEvidence(value: unknown, context: LinguisticContext): Promise<StagedStatus> {
  try {
    const record = object(value), presentation = object(record.presentation_verification);
    if (presentation.status === "invalid" || record.decision === "error" || object(record.evidence_support).readiness === "error") return "error";
    const capture = retained(context.retrievalTrace), plan = object(record.request_plan), rows = records(record.requirements);
    if (!known(record) || !Object.keys(capture).length || !same(stable(record), stable(capture))
      || plan.contract !== "staged-request-plan-v1" || plan.reading_profile !== "contextual_source_v3"
      || plan.question !== context.question || object(record.staged_request_inputs).question !== context.question
      || !Array.isArray(record.requirements) || !Array.isArray(plan.requirements) || rows.length !== plan.requirements.length
      || new Set(rows.map(r => r.id)).size !== rows.length
      || !rows.every(r => records(plan.requirements).some(p => p.id === r.id && p.kind === r.kind && p.original_text === r.original_text)
        && slicePoints(context.question, r.input_range) === r.original_text)) return "invalid";
    if (record.decision === "refused") return "refused";
    if (Object.hasOwn(record, "staged_publication_check") && !same(record.staged_publication_check, { consistent: true, reason: null })) return "invalid";
    const cert = object(record.staged_output_certificate), groups = displayedGroups(record, cert), fragments = records(cert.selected_fragments);
    if (record.decision !== "answer" || !rows.length || rows.some(r => r.status !== "supported")
      || cert.contract !== "procedure-output-cover-v8" || cert.reading_profile !== "contextual_source_v3" || cert.renderer !== "extractive-answer-v1"
      || !same(cert.request_plan, plan) || !same(object(cert.model_settings).evidence_profile, record.evidence_profile)
      || !same(cert.selected_proposal_ids, record.selected_proposal_ids) || !selectedGroups(record, cert)
      || !Array.isArray(context.sources) || !same(context.sources.map(object).map(coreCitation), records(cert.citations).map(coreCitation))
      || !fragments.length || !groups.every(g => groupShape(g, cert, record))) return "invalid";
    if (!fragments.every(f => fragmentShape(f, cert, context.answer))
      || !records(cert.procedure_groups).every(g => slicePoints(context.answer, g.answer_range) === g.text)
      || !records(cert.disclosures).every(d => slicePoints(context.answer, d.answer_range) === d.text)) return "mismatch";
    const covered = reconstructStagedRendering(record, cert, context.answer);
    if (covered === null) return "uncovered";
    if (!covered) return "mismatch";
    if (!globalThis.crypto?.subtle) return "unavailable";
    if (!await digestMatches(context.answer, cert.answer_sha256) || !await digestMatches(context.question, cert.question_sha256)) return "mismatch";
    return presentation.status === "verified" ? "verified" : "unverified";
  } catch {
    return "invalid";
  }
}
