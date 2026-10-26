/** Pure recorded conditional evidence replay. This does not rerun inference or authenticate storage. */
import { pythonCasefold } from "@/lib/python-casefold";
import { contextSemanticChecks, replayContextReading, sourceContextVersion } from "@/lib/source-context-evidence";
import { contextObligationPlan, contextReferenceObligation } from "@/lib/source-context-references";

type RecordValue = Record<string, unknown>;
type Range = { start: number; end: number };
export type ConditionHashStatus = "pending" | "matched" | "mismatch" | "unavailable";
export type CanonicalConditionPlan = {
  scope: string; conditions: string; extent: Range; required_inventory: RecordValue; units: RecordValue[];
};
export type ConditionalInspection = { state: "absent" | "pending" | "invalid" | "verified"; exclusions: RecordValue[] };
export type ConditionReplayServices = {
  plan: (body: string, identity: RecordValue, topic: string, original: string) => CanonicalConditionPlan | null;
  parts: (body: string) => Range[];
  pattern: (expression: RegExp) => RegExp;
  canonical: (text: string) => string;
  hash: (body: unknown, expected: unknown) => ConditionHashStatus;
};
/** Python orders strings by Unicode scalar values, without locale collation or normalization. */
function scalarOrder(left: string, right: string) {
  const a = Array.from(left), b = Array.from(right);
  for (let index = 0; index < Math.min(a.length, b.length); index++) {
    const delta = a[index].codePointAt(0)! - b[index].codePointAt(0)!;
    if (delta) return delta;
  }
  return a.length - b.length;
}
const rec = (value: unknown): RecordValue => value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const list = (value: unknown): RecordValue[] | null => Array.isArray(value) && value.every((item) => item !== null && typeof item === "object" && !Array.isArray(item)) ? value.map(rec) : null;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const integer = (value: unknown, low = 0, high = Number.MAX_SAFE_INTEGER): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= low && value <= high;
const text = (value: unknown): value is string => typeof value === "string" && value.length > 0;
const keys = (value: unknown, expected: string[]) => Object.keys(rec(value)).sort(scalarOrder).join("|") === [...expected].sort(scalarOrder).join("|");
const uuid = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value);
const digest = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const slice = (body: string, range: Range) => Array.from(body).slice(range.start, range.end).join("");
function range(value: unknown, length: number): Range | null {
  const item = rec(value);
  return keys(item, ["start", "end"]) && integer(item.start) && integer(item.end, 1, length) && item.start < item.end ? { start: item.start, end: item.end } : null;
}
function equal(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value, index) => equal(value, right[index]));
  if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
  const a = rec(left), b = rec(right);
  return keys(a, Object.keys(b)) && Object.keys(a).every((key) => equal(a[key], b[key]));
}
function pick(value: RecordValue, fields: string[]) { return Object.fromEntries(fields.map((field) => [field, value[field]])); }
const identityKeys = ["document_id", "document_version", "content_hash", "workspace_id"];
const minimalKeys = ["chunk_id", "document_id", "document_version", "content_hash"];
const memberKeys = [...minimalKeys, "workspace_id", "condition", "conflict_group", "chunk_hash"];
function identityValid(value: RecordValue) { return keys(value, identityKeys) && uuid(value.document_id) && integer(value.document_version, 1) && digest(value.content_hash) && text(value.workspace_id); }
function sortedIds(value: unknown): value is string[] | null {
  return value === null || Array.isArray(value) && value.every(uuid) && equal(value, Array.from(new Set(value)).sort(scalarOrder));
}
function sortedMembers(value: RecordValue[]) { return [...value].sort((a, b) => scalarOrder(String(a.chunk_id), String(b.chunk_id))); }
const readerFields = ["mode", "model", "revision", "threshold", "max_length", "stride", "n_best", "max_span_tokens"];
const supportFields = ["mode", "model", "revision", "license", "minimum_entailment_margin", "max_pair_tokens", "batch_size", "device", "score_semantics"];
function capturedSettings(selection: RecordValue) {
  return { contract: "procedure-condition-model-settings-v1", generation_mode: "extractive", evidence_profile: selection.evidence_profile,
    reader: pick(selection, readerFields), support: pick(rec(selection.evidence_support), supportFields) };
}
function settingsValid(value: RecordValue, selection: RecordValue) {
  if (!equal(value, capturedSettings(selection))) return false;
  const reader = rec(value.reader), support = rec(value.support);
  const readers: Record<string, string> = {
    "934656cdda79824eabf503ed56e15c01ddbdbe3f": "deepset/minilm-uncased-squad2",
    "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4": "deepset/roberta-base-squad2",
  };
  if (reader.mode !== "reader" || typeof reader.revision !== "string" || !Object.prototype.hasOwnProperty.call(readers, reader.revision) || reader.model !== readers[reader.revision]
    || !finite(reader.threshold) || !integer(reader.max_length, 128, 512) || !integer(reader.stride, 0, 256) || !integer(reader.n_best, 1, 100) || !integer(reader.max_span_tokens, 1, 128)) return false;
  return equal(pick(support, supportFields.filter((field) => field !== "minimum_entailment_margin")), {
    mode: "local_nli", model: "cross-encoder/nli-deberta-v3-small", revision: "70de96bd327ef95839a8bd9f6299875cae396433", license: "Apache-2.0",
    max_pair_tokens: 512, batch_size: 8, device: "cpu", score_semantics: "raw contradiction/entailment/neutral logits; uncalibrated",
  }) && finite(support.minimum_entailment_margin) && support.minimum_entailment_margin >= 0 && support.minimum_entailment_margin <= 4;
}
function assessmentValid(assessment: RecordValue, settings: RecordValue) {
  const logits = assessment.logits;
  if (!Array.isArray(logits) || logits.length !== 3 || !logits.every(finite)) return false;
  const margin = logits[1] - Math.max(logits[0], logits[2]);
  return assessment.label === "entailment" && assessment.supported === true && integer(assessment.pair_tokens, 1, 512)
    && finite(assessment.entailment_margin) && assessment.entailment_margin === margin && margin > 0
    && margin >= (rec(settings.support).minimum_entailment_margin as number);
}
export function hasConditionalEvidence(selection: RecordValue, proof: RecordValue, requirementId: unknown) {
  if (Object.prototype.hasOwnProperty.call(proof, "condition_exclusion_inventory") || ["procedure-output-cover-v2", "procedure-output-cover-v3", "procedure-output-cover-v4"].includes(String(rec(proof.output_certificate).contract))) return true;
  return (list(selection.conflicts) ?? []).filter((conflict) => conflict.requirement_id === requirementId).some((conflict) =>
    (list(conflict.source_extent_checks) ?? []).some((check) => Object.prototype.hasOwnProperty.call(check, "condition_scope") || check.reason === "verified_excluded_source_condition"));
}
/** Hash every complete serialized body and every chunk, including members absent from discharges. */
export function conditionalHashPairs(selection: RecordValue): [unknown, unknown][] {
  const pairs: [unknown, unknown][] = [];
  for (const row of list(selection.requirements) ?? []) {
    const proof = rec(row.procedure_completeness), inventory = rec(proof.condition_exclusion_inventory);
    for (const context of list(inventory.source_contexts) ?? []) {
      pairs.push([context.source_body, rec(context.source_identity).content_hash]);
      for (const chunk of list(context.chunks) ?? []) pairs.push([chunk.content, chunk.chunk_hash]);
    }
  }
  const unique = new Map(pairs.map((pair) => [JSON.stringify(pair), pair]));
  return Array.from(unique.values());
}
function method(unit: RecordValue) {
  return ["namespace", "applicability", "bound_condition"].includes(String(unit.kind)) && unit.name !== "paragraph_request_constraints"
    ? "nli_entailment" : ["instruction", "prohibition"].includes(String(unit.kind)) ? "exact_source_copy" : "exact_source_structure";
}
function unitValid(observed: RecordValue, expected: RecordValue, settings: RecordValue) {
  const base = pick(expected, ["name", "kind", "source_range", "premise_range", "hypothesis"]), verification = method(expected);
  if (!equal(pick(observed, Object.keys(base)), base) || observed.verification_method !== verification || observed.supported !== true) return false;
  return verification === "nli_entailment" ? assessmentValid(observed, settings)
    : keys(observed, [...Object.keys(base), "verification_method", "supported"]);
}
function candidate(plan: CanonicalConditionPlan, body: string, metadata: RecordValue, selectedIdentity: RecordValue, services: ConditionReplayServices) {
  if (metadata.condition !== null) return null;
  const conditions = services.pattern(new RegExp("^(?:an?|the)\\s+[^,;.!?]+,\\s+not\\s+(?:an?|the)\\s+([\\p{L}\\p{N}_-]+(?:\\s+[\\p{L}\\p{N}_-]+){0,3})$", "iu")).exec(plan.conditions);
  if (!conditions || !services.pattern(new RegExp("^[\\p{L}\\p{N}'’_-]+(?:\\s+[\\p{L}\\p{N}'’_-]+)*$", "u")).test(conditions[1])
    || /\b(?:is|are|was|were|has|have|may|can|scheduled|assigned|if|when|unless|except|not|no|only)\b/i.test(conditions[1])) return null;
  const parts = services.parts(body);
  if (!parts.length) return null;
  let first = 0;
  const title = /^([^:\n.!?]+):[^\n.!?]+$/.exec(slice(body, parts[0]));
  if (title && services.canonical(title[1]) === services.canonical(plan.scope)) first++;
  if (!parts[first]) return null;
  const header = services.pattern(/^\s*for\s+([^,;:.!?]+)[,:]\s*/i).exec(slice(body, parts[first]));
  if (!header) return null;
  const escaped = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const expected = services.pattern(new RegExp("^(?:the\\s+)?" + escaped(plan.scope) + "\\s+" + escaped(conditions[1]) + "(?:\\s+marked\\s+with\\s+(?:an?|the)\\s+[\\p{L}\\p{N}_-]+)?$", "iu"));
  if (!expected.test(header[1])) return null;
  const start = parts[first].start + Array.from(header[0].slice(0, header[0].indexOf(header[1]))).length;
  return { contract: "procedure-condition-scope-v1", condition: header[1], condition_range: { start, end: start + Array.from(header[1]).length }, excluded_class: conditions[1],
    procedure_source_identity: pick(selectedIdentity, ["document_id", "document_version", "content_hash"]), procedure_conditions: plan.conditions,
    hypothesis: `The instructions apply only to ${header[1]}.`, premise_range: { start: 0, end: Array.from(body).length } };
}
function relation(topic: string, body: string, metadata: RecordValue, services: ConditionReplayServices) {
  let condition = typeof metadata.condition === "string" && services.canonical(metadata.condition) ? metadata.condition : "";
  if (!condition) condition = services.pattern(/^\s*(?:for|when|if)\s+([^,;:.]+)[,;:]/i).exec(body)?.[1]
    ?? services.pattern(/^\s*((?:exception|retest)\b[^,;:.]*)[,;:]/i).exec(body)?.[1] ?? "";
  const grammar = new Set("the a an of for its it that in on at is are does do with".split(" "));
  const words = (value: string) => Array.from(pythonCasefold(value).matchAll(new RegExp("[\\p{L}\\p{N}_][\\p{L}\\p{N}_-]*", "gu")), (match) => match[0]).filter((word) => !grammar.has(word));
  const requested = new Set(words(topic)), conditional = words(condition);
  if (!conditional.length) return "applies";
  if (conditional.some((word) => ["exception", "retest"].includes(word)) && !["exception", "retest"].some((word) => requested.has(word))) return "irrelevant";
  if (conditional.every((word) => requested.has(word))) return "applies";
  return requested.size && !conditional.some((word) => requested.has(word)) ? "irrelevant" : "unknown";
}

export function inspectConditionalEvidence(selection: RecordValue, proof: RecordValue, row: RecordValue, actualQuestion: unknown, services: ConditionReplayServices): ConditionalInspection {
  const absent: ConditionalInspection = { state: "absent", exclusions: [] }, invalid: ConditionalInspection = { state: "invalid", exclusions: [] };
  if (!hasConditionalEvidence(selection, proof, row.id)) return absent;
  try {
    const inventory = rec(proof.condition_exclusion_inventory), cert = rec(proof.output_certificate), binding = rec(proof.request_binding);
    const version = sourceContextVersion(rec(selection.evidence_profile)), contextual = version !== null;
    if (["evidence-profile-v3", "evidence-profile-v4"].includes(String(rec(selection.evidence_profile).contract)) && !contextual) return invalid;
    if (cert.contract !== (version?.output ?? "procedure-output-cover-v2") || !equal(cert.condition_exclusion_inventory, inventory)
      || !keys(inventory, ["contract", "request_binding", "model_settings", "source_contexts", "inspection_manifest", "groups", "exclusions"])
      || inventory.contract !== (version?.inventory ?? "procedure-condition-exclusion-inventory-v1") || !equal(inventory.request_binding, binding) || binding.question !== actualQuestion
      || binding.requirement_id !== row.id || binding.original_text !== row.original_text || !text(binding.topic) || !text(row.original_text) || !text(proof.source_body)) return invalid;
    const selectedIdentity = pick(proof, identityKeys), main = services.plan(proof.source_body, selectedIdentity, binding.topic, row.original_text);
    const settings = rec(inventory.model_settings);
    if (!identityValid(selectedIdentity) || !main || !equal(main.required_inventory, proof.required_inventory) || !settingsValid(settings, selection)) return invalid;
    const read = rec(selection.procedure_read_set), members = list(read.sources), capturedGroups = list(read.groups), contexts = list(inventory.source_contexts), inspected = list(selection.inspected_sources);
    if (read.contract !== "procedure-inspection-read-set-v1" || rec(read.after_proofs).consistent !== true || rec(read.before_publication).consistent !== true
      || !sortedIds(read.document_ids) || !sortedIds(read.collection_ids) || !members?.length || members.length > 512 || !capturedGroups || !contexts || !inspected) return invalid;
    const byChunk = new Map<string, RecordValue>(), byDocument = new Map<string, RecordValue>(), groupMembers = new Map<string, RecordValue[]>();
    for (const member of members) {
      const identity = pick(member, identityKeys);
      if (!keys(member, memberKeys) || !identityValid(identity) || !uuid(member.chunk_id) || byChunk.has(member.chunk_id) || !digest(member.chunk_hash)
        || !(member.condition === null || text(member.condition)) || !(member.conflict_group === null || text(member.conflict_group))
        || Array.isArray(read.document_ids) && !read.document_ids.includes(member.document_id as string)) return invalid;
      const previous = byDocument.get(member.document_id as string);
      if (previous && !equal(pick(previous, [...identityKeys, "condition", "conflict_group"]), pick(member, [...identityKeys, "condition", "conflict_group"]))) return invalid;
      byChunk.set(member.chunk_id, member); byDocument.set(member.document_id as string, member);
      if (typeof member.conflict_group === "string") groupMembers.set(member.conflict_group, [...groupMembers.get(member.conflict_group) ?? [], member]);
    }
    if (inspected.length !== members.length || new Set(inspected.map((item) => item.chunk_id)).size !== inspected.length
      || !equal(sortedMembers(inspected.map((item) => pick(item, minimalKeys))), sortedMembers(members.map((item) => pick(item, minimalKeys))))) return invalid;
    const expectedGroups = Array.from(groupMembers.keys()).sort(scalarOrder).map((group) => ({ group, sources: sortedMembers(groupMembers.get(group)!) }));
    if (capturedGroups.some((group) => !keys(group, ["group", "sources"]) || !text(group.group) || !list(group.sources))
      || new Set(capturedGroups.map((group) => group.group)).size !== capturedGroups.length
      || !equal(capturedGroups.map((group) => ({ group: group.group, sources: sortedMembers(list(group.sources)!) })).sort((a, b) => scalarOrder(String(a.group), String(b.group))), expectedGroups)) return invalid;
    const manifest = { document_ids: read.document_ids, collection_ids: read.collection_ids, sources: sortedMembers(members), groups: expectedGroups };
    if (!equal(inventory.inspection_manifest, manifest)) return invalid;
    const curatedIds = Array.from(byDocument.keys()).filter((id) => byDocument.get(id)!.conflict_group !== null).sort(scalarOrder);
    if (contexts.length !== curatedIds.length || contexts.length > 64) return invalid;
    const contextMap = new Map<string, RecordValue>(); let pending = false;
    for (let index = 0; index < contexts.length; index++) {
      const context = contexts[index], identity = rec(context.source_identity), metadata = rec(context.metadata), chunks = list(context.chunks), id = curatedIds[index], member = byDocument.get(id)!;
      if (!keys(context, ["source_identity", "source_body", "metadata", "chunks"]) || !equal(identity, pick(member, identityKeys)) || identity.document_id !== id
        || !keys(metadata, ["condition", "conflict_group"]) || !equal(metadata, pick(member, ["condition", "conflict_group"])) || !text(context.source_body)
        || !chunks?.length || chunks.length > 64 || new TextEncoder().encode(context.source_body).length > 128 * 1024) return invalid;
      const body = context.source_body, bodyHash = services.hash(body, identity.content_hash);
      if (bodyHash === "pending") pending = true; else if (bodyHash !== "matched") return invalid;
      let previousStart = -1, previousEnd = -1, previousIndex = -1;
      const ids = new Set<string>();
      for (const chunk of chunks) {
        const location = range(chunk.document_range, Array.from(body).length);
        if (!keys(chunk, ["chunk_id", "index", "content", "document_range", "chunk_hash"]) || !uuid(chunk.chunk_id) || ids.has(chunk.chunk_id)
          || !integer(chunk.index, previousIndex + 1) || !text(chunk.content) || !digest(chunk.chunk_hash) || !location || location.start <= previousStart || location.end <= previousEnd
          || slice(body, location) !== chunk.content || body.indexOf(chunk.content) !== body.lastIndexOf(chunk.content)) return invalid;
        const captured = byChunk.get(chunk.chunk_id);
        if (!captured || !equal(pick(captured, identityKeys), identity) || captured.chunk_hash !== chunk.chunk_hash) return invalid;
        const status = services.hash(chunk.content, chunk.chunk_hash);
        if (status === "pending") pending = true; else if (status !== "matched") return invalid;
        ids.add(chunk.chunk_id); previousStart = location.start; previousEnd = location.end; previousIndex = chunk.index;
      }
      const expectedIds = members.filter((item) => item.document_id === id).map((item) => item.chunk_id as string).sort(scalarOrder);
      if (!equal(Array.from(ids).sort(scalarOrder), expectedIds)) return invalid;
      const records = (list(selection.procedure_contexts) ?? []).filter((item) => item.document_id === id && item.origin === "curated-procedure-inspection");
      if (!records.length || records.some((item) => !equal(pick(item, identityKeys), identity) || !equal(sortedMembers(list(item.sources) ?? []), sortedMembers(chunks.map((chunk) => ({ chunk_id: chunk.chunk_id, ...pick(identity, ["document_id", "document_version", "content_hash"]) })))))) return invalid;
      contextMap.set(id, context);
    }
    // Candidate discovery is independent of whichever recorded exclusion discharges survive.
    const required = new Map<string, RecordValue>();
    for (const [id, context] of Array.from(contextMap.entries())) {
      const proposed = candidate(main, context.source_body as string, rec(context.metadata), selectedIdentity, services);
      if (proposed && relation(binding.topic, context.source_body as string, rec(context.metadata), services) !== "irrelevant") {
        if (contextual) {
          const reading = replayContextReading(context.source_body as string, main.scope, proposed.excluded_class as string, rec(context.source_identity).content_hash as string, version!.policy);
          if (!reading) return invalid;
          const base: RecordValue = { ...proposed }; delete base.hypothesis;
          const checks = contextSemanticChecks(reading);
          required.set(id, { ...base, contract: version!.scope, context_reading: reading, semantic_checks: checks,
            ...(version!.policy === "scoped_note_context_v2" ? { obligation_plan: contextObligationPlan(reading, checks), reference_obligations: [contextReferenceObligation(reading)] } : {}) });
        } else required.set(id, proposed);
      }
    }
    if (!required.size || required.size > 64) return invalid;
    const conflicts = (list(selection.conflicts) ?? []).filter((item) => item.requirement_id === row.id), expectedInventoryGroups: RecordValue[] = [], exclusions: RecordValue[] = [];
    const requiredGroups = Array.from(new Set(Array.from(required.keys()).map((id) => rec(contextMap.get(id)!.metadata).conflict_group as string))).sort(scalarOrder);
    for (const group of requiredGroups) {
      const groupSources = sortedMembers(groupMembers.get(group)!), matching = conflicts.filter((item) => item.group === group);
      if (matching.length !== 1) return invalid;
      const conflict = matching[0], checks = list(conflict.source_extent_checks);
      if (conflict.inspection_method !== "complete-immutable-procedure-v3" || conflict.inspection_complete !== true || conflict.relevant !== false
        || !equal(sortedMembers(list(conflict.inspection_sources) ?? []), groupSources) || !checks) return invalid;
      const excluded: string[] = [], applicable: string[] = []; let checked = 0;
      for (const id of Array.from(new Set(groupSources.map((item) => item.document_id as string))).sort(scalarOrder)) {
        const context = contextMap.get(id)!, identity = rec(context.source_identity), metadata = rec(context.metadata), body = context.source_body as string;
        if (relation(binding.topic, body, metadata, services) === "irrelevant") { excluded.push(id); continue; }
        const matchingChecks = checks.filter((item) => item.document_id === id);
        if (matchingChecks.length !== 1) return invalid;
        const check = matchingChecks[0], representative = (context.chunks as RecordValue[])[0]; checked++;
        if (!equal(pick(check, minimalKeys), { chunk_id: representative.chunk_id, ...pick(identity, ["document_id", "document_version", "content_hash"]) })
          || check.proposal_origin !== "structural-opponent-inspection" || check.answer_witness !== false) return invalid;
        const proposed = required.get(id);
        if (proposed) {
          const scope = rec(check.condition_scope), assessment = rec(scope.assessment);
          if (contextual) {
            const checks = list(scope.semantic_checks), planned = list(proposed.semantic_checks);
            if (!checks || !planned || checks.length !== planned.length) return invalid;
            const semantic_checks = planned.map((planned, index) => {
              const check = checks[index], assessment = rec(check.assessment);
              if (!keys(assessment, ["label", "logits", "entailment_margin", "supported", "pair_tokens"]) || !assessmentValid(assessment, settings)) throw new Error("Invalid contextual NLI");
              return { ...planned, pair: { premise: slice(body, planned.premise_range as Range), hypothesis: planned.hypothesis, requirement_id: row.id,
                reference_id: `${id}:context-scope:${planned.name}` }, assessment, verification_method: "nli_entailment" };
            });
            const expected = { ...proposed, semantic_checks, model_settings: settings, verification_method: version!.method, reason: "verified_contextual_excluded_source_condition" };
            if (!equal(scope, expected) || check.status !== "irrelevant" || check.reason !== expected.reason) return invalid;
            exclusions.push({ group, source_identity: identity, condition_scope: expected }); excluded.push(id);
            continue;
          }
          const expected = { ...proposed, model_settings: settings, pair: { premise: body, hypothesis: proposed.hypothesis, requirement_id: row.id, reference_id: `${id}:condition-scope` },
            assessment, verification_method: "nli_entailment", reason: "verified_excluded_source_condition" };
          if (!equal(scope, expected) || !keys(assessment, ["label", "logits", "entailment_margin", "supported", "pair_tokens"]) || !assessmentValid(assessment, settings)
            || check.status !== "irrelevant" || check.reason !== "verified_excluded_source_condition") return invalid;
          exclusions.push({ group, source_identity: identity, condition_scope: expected }); excluded.push(id);
        } else {
          const plan = services.plan(body, identity, binding.topic, row.original_text), records = list(check.proof_units);
          if (!plan || check.status !== "supported" || !equal(check.required_inventory, plan.required_inventory) || !equal(check.extent, plan.extent)
            || slice(body, plan.extent) !== slice(proof.source_body, main.extent) || check.mandatory_proof_count !== plan.units.length || !records || records.length !== plan.units.length
            || check.step_count !== (check.contract === "complete-immutable-procedure-v3" ? null : 0)
            || records.some((record, index) => !unitValid(record, plan.units[index], settings)) || (check.source_body !== undefined && check.source_body !== body)) return invalid;
          applicable.push(id);
        }
      }
      if (checks.length !== checked || !Array.isArray(conflict.subject_scope_excluded_documents) || !Array.isArray(conflict.applicable_documents)
        || !equal([...conflict.subject_scope_excluded_documents].sort(scalarOrder), excluded) || !equal([...conflict.applicable_documents].sort(scalarOrder), applicable)
        || conflict.requested_fact_agreement !== Boolean(applicable.length) || conflict.outcome !== (applicable.length ? "agreement" : "not_relevant")) return invalid;
      expectedInventoryGroups.push({ group, sources: groupSources, excluded_documents: excluded, applicable_documents: applicable });
    }
    const mainRecords = list(proof.proof_units);
    if (!mainRecords || mainRecords.length !== main.units.length || mainRecords.some((record, index) => !unitValid(record, main.units[index], settings))) return invalid;
    for (const conflict of conflicts) for (const check of list(conflict.source_extent_checks) ?? []) if (check.condition_scope !== undefined && !required.has(check.document_id as string)) return invalid;
    const expected = { contract: version?.inventory ?? "procedure-condition-exclusion-inventory-v1", request_binding: proof.request_binding, model_settings: settings, inspection_manifest: manifest,
      source_contexts: contexts, groups: expectedInventoryGroups, exclusions };
    if (!equal(inventory, expected)) return invalid;
    return { state: pending ? "pending" : "verified", exclusions };
  } catch { return invalid; }
}
/** Frozen v264 execution-input projection; derived proof/rendering stamps are deliberately excluded. */
function captureSignature(selection: RecordValue) {
  const nullable = (value: RecordValue, fields: string[]) => Object.fromEntries(fields.map((field) => [field, value[field] ?? null]));
  const requireFields = (value: RecordValue, fields: string[]) => {
    if (fields.some((field) => !Object.prototype.hasOwnProperty.call(value, field))) throw new Error("Incomplete retained capture");
    return pick(value, fields);
  };
  const canonicalValue = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(canonicalValue);
    if (value && typeof value === "object") return Object.fromEntries(Object.keys(rec(value)).sort(scalarOrder).map((key) => [key, canonicalValue(rec(value)[key])]));
    return value ?? null;
  };
  const ordered = (items: RecordValue[]) => items.map((item) => canonicalValue(item) as RecordValue)
    .sort((a, b) => scalarOrder(JSON.stringify(a), JSON.stringify(b)));
  const array = (value: unknown) => { const result = list(value); if (!result) throw new Error("Malformed retained capture"); return result; };
  const sources = (value: unknown) => ordered(array(value).map((source) => requireFields(source, minimalKeys)));
  const read = rec(selection.procedure_read_set);
  if (!Object.prototype.hasOwnProperty.call(selection, "evidence_profile")) throw new Error("Missing retained profile");
  return {
    requirements: array(selection.requirements).map((row) => nullable(row, ["id", "kind", "original_text", "input_range", "source_workspace", "depends_on", "prepared_question"])),
    evidence_profile: selection.evidence_profile,
    reader: nullable(selection, [...readerFields, "reader_contract"]), support: nullable(rec(selection.evidence_support), supportFields),
    inspected_sources: sources(selection.inspected_sources),
    procedure_contexts: ordered(array(selection.procedure_contexts === undefined ? [] : selection.procedure_contexts).map((context) => ({
      ...requireFields(context, [...identityKeys, "origin"]), sources: sources(context.sources),
    }))),
    procedure_read_set: { ...nullable(read, ["contract", "document_ids", "collection_ids"]),
      sources: ordered(array(read.sources === undefined ? [] : read.sources)),
      groups: ordered(array(read.groups === undefined ? [] : read.groups).map((group) => ({ group: requireFields(group, ["group"]).group, sources: ordered(array(group.sources)) }))),
    },
    ...(["scoped_note_context_v1", "scoped_note_context_v2"].includes(String(rec(selection.evidence_profile).source_context_policy)) ? {
      contextual_semantics: { conflicts: selection.conflicts ?? [], proofs: array(selection.requirements).filter(row => row.kind === "procedure").map(row =>
        nullable(rec(row.procedure_completeness), ["proof_units", "required_inventory", "request_binding", "extent", "source_body"])) },
    } : {}),
  };
}
export type RetainedCaptureInspection = { state: "missing" | "invalid" | "matched" | "mismatch"; conditionalRequirementIds: unknown[]; v3RequirementIds?: unknown[] };
export function inspectRetainedCapture(selection: RecordValue, actualTrace: unknown): RetainedCaptureInspection {
  if (actualTrace === null || actualTrace === undefined) return { state: "missing", conditionalRequirementIds: [] };
  try {
    if (typeof actualTrace !== "object" || Array.isArray(actualTrace)) return { state: "invalid", conditionalRequirementIds: [] };
    const trace = rec(actualTrace), provenance = trace.provenance;
    if (provenance !== null && provenance !== undefined && (typeof provenance !== "object" || Array.isArray(provenance))) return { state: "invalid", conditionalRequirementIds: [] };
    if (provenance === null || provenance === undefined || !Object.prototype.hasOwnProperty.call(provenance, "answer_selection")) {
      const known = list(selection.inspected_sources), scores = list(trace.scores === undefined ? [] : trace.scores);
      if (!known || !scores) return { state: "invalid", conditionalRequirementIds: [] };
      for (const score of scores) {
        const version = score.document_version;
        if (!Object.prototype.hasOwnProperty.call(score, "document_id") || version !== null && version !== undefined && !integer(version, 1)) return { state: "invalid", conditionalRequirementIds: [] };
        if (!known.some((member) => member.document_id === score.document_id
          && (version === null || version === undefined || member.document_version === version)
          && (score.chunk_id === null || score.chunk_id === undefined || member.chunk_id === score.chunk_id))) return { state: "mismatch", conditionalRequirementIds: [] };
      }
      return { state: "missing", conditionalRequirementIds: [] };
    }
    const retained = rec(rec(provenance).answer_selection), requirements = list(retained.requirements);
    if (!requirements) return { state: "invalid", conditionalRequirementIds: [] };
    const conditionalRequirementIds = requirements.filter((row) => hasConditionalEvidence(retained, rec(row.procedure_completeness), row.id)).map((row) => row.id);
    const v3RequirementIds = requirements.filter((row) => rec(row.procedure_completeness).contract === "complete-immutable-procedure-v3"
      || conditionalRequirementIds.includes(row.id)).map((row) => row.id);
    const retainedSignature = captureSignature(retained);
    // A malformed presentation cannot erase the obligations of a valid retained capture.
    try {
      return { state: equal(captureSignature(selection), retainedSignature) ? "matched" : "mismatch", conditionalRequirementIds, v3RequirementIds };
    } catch { return { state: "mismatch", conditionalRequirementIds, v3RequirementIds }; }
  } catch { return { state: "invalid", conditionalRequirementIds: [] }; }
}
