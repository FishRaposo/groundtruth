import LinguisticAnswerEvidence from "@/components/LinguisticAnswerEvidence";
import StagedAnswerEvidence from "@/components/StagedAnswerEvidence";
import { hasStagedEvidence } from "@/lib/staged-evidence";
import { hasLinguisticEvidence } from "@/lib/linguistic-evidence";
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

export function selectionFailureMessage(value: unknown) {
  const record = selectionRecord(value);
  const support = selectionRecord(record.evidence_support);
  const component = support.mode === "local_nli" && support.readiness === "error"
    ? "Local evidence check failed."
    : record.mode === "reader" ? "Reader failed." : "Execution failed.";
  return `${component} This is an execution failure; no completed answer was saved.`;
}

const requirementLabels: Record<string, string> = {
  owner: "Owner", deputy: "Deputy", availability: "Availability", duration: "Duration",
  start_time: "Start time", weekday: "Scheduled day", quantity: "Quantity",
  procedure: "Procedure", prohibition: "Prohibition", boolean: "Requested condition",
  generic: "Requested fact",
};

function hasRecordedSource(value: unknown) {
  return Array.isArray(value) && value.some((item) => {
    const source = selectionRecord(item);
    return typeof source.chunk_id === "string" && source.chunk_id.length > 0
      && typeof source.document_id === "string" && source.document_id.length > 0
      && typeof source.document_version === "number" && Number.isInteger(source.document_version) && source.document_version > 0
      && typeof source.content_hash === "string" && /^[a-f0-9]{64}$/.test(source.content_hash);
  });
}

function integer(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function recordedRange(value: unknown): { start: number; end: number } | null {
  const range = selectionRecord(value);
  return integer(range.start) && integer(range.end, 1) && range.end > range.start
    ? { start: range.start, end: range.end } : null;
}

function sameRange(left: unknown, right: unknown) {
  const a = recordedRange(left), b = recordedRange(right);
  return a !== null && b !== null && a.start === b.start && a.end === b.end;
}

/** Python str.isspace, deliberately excluding JavaScript's BOM whitespace. */
function trimSourceWhitespace(text: string, start: number) {
  const points = Array.from(text);
  const whitespace = (point: string) => /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/.test(point);
  let left = 0, right = points.length;
  while (left < right && whitespace(points[left])) left++;
  while (right > left && whitespace(points[right - 1])) right--;
  return { text: points.slice(left, right).join(""), start: start + left, end: start + right };
}

/** Bind recorded literals and codepoint offsets; source authenticity remains producer-owned. */
function numberedSeedMatches(proof: Record<string, unknown>, seed: Record<string, unknown>, raw: { start: number; end: number }) {
  const inventory = selectionRecord(proof.required_inventory), clause = selectionRecord(inventory.seed_clause);
  const range = recordedRange(clause.source_range);
  if (!range || typeof clause.unit_name !== "string" || typeof clause.text !== "string" || typeof seed.text !== "string"
    || Array.from(clause.text).length !== range.end - range.start
    || Array.from(seed.text).length !== raw.end - raw.start || !Array.isArray(inventory.units)) return false;
  const first = inventory.units.map(selectionRecord)
    .filter((unit) => unit.step === 1 && ["instruction", "prohibition"].includes(String(unit.kind)))
    .sort((a, b) => (recordedRange(a.source_range)?.start ?? Infinity) - (recordedRange(b.source_range)?.start ?? Infinity))[0];
  if (!first || first.name !== clause.unit_name || !sameRange(first.source_range, range)) return false;
  const premise = recordedRange(first.premise_range);
  if (!premise || raw.start < premise.start || raw.end > premise.end) return false;
  const accepted = trimSourceWhitespace(seed.text, raw.start), source = trimSourceWhitespace(clause.text, range.start);
  const matches = (candidate: { text: string; start: number; end: number }) => candidate.text !== ""
    && accepted.text === candidate.text && sameRange(accepted, candidate);
  if (matches(source)) return true;
  const points = Array.from(source.text);
  if (![".", "!", "?"].includes(points[points.length - 1])) return false;
  return matches(trimSourceWhitespace(points.slice(0, -1).join(""), source.start));
}

/** Check the recorded source-plan inventory, independently of its assessment count. */
function inventoryDischarged(proof: Record<string, unknown>) {
  const inventory = selectionRecord(proof.required_inventory);
  if (inventory.contract !== "procedure-required-inventory-v1"
    || typeof proof.workspace_id !== "string" || !proof.workspace_id.length
    || ["document_id", "workspace_id", "document_version", "content_hash", "structure"].some((key) => inventory[key] !== proof[key])
    || !sameRange(inventory.extent, proof.extent)
    || !Array.isArray(inventory.step_ranges) || !Array.isArray(proof.step_ranges)
    || inventory.step_ranges.length !== proof.step_ranges.length
    || !Array.isArray(inventory.units) || !Array.isArray(proof.proof_units)
    || !inventory.units.length || inventory.units.length !== proof.proof_units.length
    || !Array.isArray(inventory.structure_edges) || !Array.isArray(proof.structure_edges)
    || inventory.structure_edges.length !== proof.structure_edges.length || proof.structure_edges.length > 64) return false;
  for (let index = 0; index < inventory.step_ranges.length; index++) {
    const required = selectionRecord(inventory.step_ranges[index]), observed = selectionRecord(proof.step_ranges[index]);
    if (required.ordinal !== observed.ordinal || !sameRange(required, observed)) return false;
  }
  const requiredUnits = new Map<string, Record<string, unknown>>(), coveredSteps = new Set<number>();
  for (const value of inventory.units) {
    const required = selectionRecord(value);
    if (typeof required.name !== "string" || !required.name.length || requiredUnits.has(required.name)
      || typeof required.kind !== "string" || !["namespace", "applicability", "request_scope", "instruction", "prohibition", "bound_condition", "whole_method"].includes(required.kind)
      || typeof required.hypothesis !== "string" || !required.hypothesis.length) return false;
    const matches = proof.proof_units.map(selectionRecord).filter((unit) => unit.name === required.name);
    if (matches.length !== 1 || matches[0].kind !== required.kind || matches[0].hypothesis !== required.hypothesis
      || (Object.prototype.hasOwnProperty.call(matches[0], "step") && matches[0].step !== required.step)
      || !sameRange(matches[0].source_range, required.source_range)
      || !sameRange(matches[0].premise_range, required.premise_range)) return false;
    const source = recordedRange(required.source_range), premise = recordedRange(required.premise_range);
    if (!source || !premise || premise.start > source.start || premise.end < source.end
      || !integer(proof.body_length, premise.end)) return false;
    requiredUnits.set(required.name, required);
    if (required.step !== null) {
      if (!integer(required.step, 1, inventory.step_ranges.length) || !["instruction", "prohibition"].includes(required.kind)) return false;
      const step = recordedRange(inventory.step_ranges[required.step - 1]), range = recordedRange(required.source_range);
      if (!step || !range || range.start < step.start || range.end > step.end || !sameRange(step, premise)) return false;
      const joins = inventory.structure_edges.map(selectionRecord).filter((edge) => edge.target === required.name);
      if (joins.length !== 1 || joins[0].step !== required.step) return false;
      coveredSteps.add(required.step);
    } else {
      if (!sameRange(premise, source)) return false;
      if (proof.structure === "numbered" && ["instruction", "prohibition"].includes(required.kind)) {
        const firstStep = recordedRange(inventory.step_ranges[0]);
        if (!firstStep || source.end > firstStep.start) return false;
      }
    }
  }
  if (proof.structure === "numbered" && coveredSteps.size !== inventory.step_ranges.length) return false;
  if (proof.structure === "numbered") {
    const kinds = new Set(Array.from(requiredUnits.values()).map((unit) => unit.kind));
    if (!["namespace", "applicability", "request_scope"].every((kind) => kinds.has(kind))
      || inventory.structure_edges.map(selectionRecord).filter((edge) => edge.name === "namespace_to_applicability").length !== 1) return false;
  }
  const stepCount = inventory.step_ranges.length;
  const edgeKey = (value: unknown): string | null => {
    const edge = selectionRecord(value);
    if (typeof edge.name !== "string" || !["namespace_to_applicability", "namespace_to_action", "applicability_to_action"].includes(edge.name)
      || typeof edge.source !== "string" || !requiredUnits.has(edge.source)
      || typeof edge.target !== "string" || !requiredUnits.has(edge.target)
      || (edge.step !== undefined && !integer(edge.step, 1, stepCount))) return null;
    const source = requiredUnits.get(edge.source)!, target = requiredUnits.get(edge.target)!;
    if (edge.name === "namespace_to_applicability") {
      if (source.kind !== "namespace" || target.kind !== "applicability" || edge.step !== undefined) return null;
    } else if (source.kind !== (edge.name === "namespace_to_action" ? "namespace" : "applicability")
      || !["instruction", "prohibition"].includes(String(target.kind))
      || (target.step === null ? edge.step !== undefined : edge.step !== target.step)) return null;
    return JSON.stringify([edge.name, edge.source, edge.target, edge.step ?? null]);
  };
  const requiredEdges = inventory.structure_edges.map(edgeKey), observedEdges = proof.structure_edges.map(edgeKey);
  return !requiredEdges.includes(null) && !observedEdges.includes(null)
    && new Set(requiredEdges).size === requiredEdges.length && new Set(observedEdges).size === observedEdges.length
    && requiredEdges.every((edge) => observedEdges.includes(edge));
}

/** Decode recorded proof only; missing historical evidence never inherits today's checks. */
function procedureCompleteness(row: Record<string, unknown>, record: Record<string, unknown>, copy = false) {
  const proof = selectionRecord(row.procedure_completeness);
  const extent = recordedRange(proof.extent), closure = selectionRecord(proof.closure);
  const margin = selectionRecord(record.evidence_support).minimum_entailment_margin;
  if (record.contract !== "requirement-evidence-v2" || proof.contract !== (copy ? "complete-immutable-procedure-v3" : "complete-immutable-procedure-v2")
    || proof.status !== "supported" || proof.coverage_complete !== true || !extent
    || typeof closure.kind !== "string" || !["immutable_eof", "independent_section"].includes(closure.kind)
    || closure.end !== extent.end || !integer(proof.body_length, extent.end)
    || (closure.kind === "immutable_eof" && extent.end !== proof.body_length)
    || typeof proof.document_id !== "string" || !proof.document_id.length
    || !integer(proof.document_version, 1)
    || typeof proof.content_hash !== "string" || !/^[a-f0-9]{64}$/.test(proof.content_hash)
    || !integer(proof.mandatory_proof_count, 1, 64)
    || typeof margin !== "number" || !Number.isFinite(margin) || margin < 0 || margin > 4
    || !Array.isArray(proof.step_ranges)
    || !Array.isArray(proof.proof_units) || proof.proof_units.length !== proof.mandatory_proof_count
    || !Array.isArray(proof.fragments) || !proof.fragments.length || proof.fragments.length > 64) return null;
  const narrative = proof.structure === "narrative";
  let steps: number | null = null;
  if (narrative) {
    if (proof.step_count !== null || proof.step_ranges.length !== 0) return null;
  } else {
    if (proof.structure !== "numbered"
      || !integer(proof.step_count, 1, 32) || proof.step_ranges.length !== proof.step_count) return null;
    steps = proof.step_count;
  }
  if (closure.kind === "independent_section") {
    const boundary = recordedRange(closure.boundary_range);
    if (!boundary || boundary.start < extent.end || boundary.end > proof.body_length) return null;
  }
  let stepEnd = extent.start;
  for (let index = 0; index < proof.step_ranges.length; index++) {
    const item = proof.step_ranges[index];
    const step = selectionRecord(item), range = recordedRange(step);
    if (step.ordinal !== index + 1 || !range || range.start < stepEnd
      || (index > 0 && range.start !== stepEnd) || range.end > extent.end) return null;
    stepEnd = range.end;
  }
  if (!narrative && stepEnd !== extent.end) return null;
  const names = new Set<string>();
  const actionRanges: { start: number; end: number }[] = [];
  let wholeMethod = false;
  for (const item of proof.proof_units) {
    const unit = selectionRecord(item), range = recordedRange(unit.source_range);
    if (typeof unit.name !== "string" || !unit.name.length || names.has(unit.name)
      || typeof unit.kind !== "string"
      || typeof unit.hypothesis !== "string" || !unit.hypothesis.length || !range || range.end > closure.end
      || (copy ? !copyAssessmentValid(unit, margin) : unit.supported !== true || unit.label !== "entailment" || !integer(unit.pair_tokens, 1, 512)
      || typeof unit.entailment_margin !== "number" || !Number.isFinite(unit.entailment_margin)
      || unit.entailment_margin < margin)) return null;
    names.add(unit.name);
    const required = selectionRecord(proof.required_inventory).units;
    const firstStepAction = Array.isArray(required) && required.map(selectionRecord).some((item) => item.name === unit.name && item.step === 1);
    if ((narrative && unit.kind === "whole_method")
      || (!narrative && firstStepAction && ["instruction", "prohibition"].includes(unit.kind))) actionRanges.push(range);
    if (unit.kind === "whole_method" && sameRange(range, extent)) wholeMethod = true;
  }
  if ((narrative && !wholeMethod) || !inventoryDischarged(proof)) return null;
  let covered = extent.start;
  for (const item of proof.fragments) {
    const fragment = selectionRecord(item);
    const chunk = recordedRange({ start: fragment.chunk_start, end: fragment.chunk_end });
    const document = recordedRange({ start: fragment.document_start, end: fragment.document_end });
    if (typeof fragment.chunk_id !== "string" || !fragment.chunk_id.length || !chunk || !document
      || document.start !== covered || chunk.end - chunk.start !== document.end - document.start) return null;
    covered = document.end;
  }
  const seed = selectionRecord(proof.raw_seed);
  const rawChunk = recordedRange(seed.chunk_range), rawDocument = recordedRange(seed.document_range);
  if (covered !== extent.end || typeof seed.chunk_id !== "string" || !seed.chunk_id.length
    || !rawChunk || !rawDocument || rawDocument.end > closure.end
    || rawChunk.end - rawChunk.start !== rawDocument.end - rawDocument.start
    || (narrative
      ? !actionRanges.some((range) => range.start <= rawDocument.start && range.end >= rawDocument.end)
      : !numberedSeedMatches(proof, seed, rawDocument))) return null;
  const origin = proof.fragments.map(selectionRecord).filter((fragment) => fragment.chunk_id === seed.chunk_id);
  if (origin.length !== 1 || typeof origin[0].document_start !== "number" || typeof origin[0].chunk_start !== "number"
    || typeof origin[0].document_end !== "number" || typeof origin[0].chunk_end !== "number"
    || rawChunk.start < origin[0].chunk_start || rawChunk.end > origin[0].chunk_end
    || rawDocument.start < origin[0].document_start || rawDocument.end > origin[0].document_end
    || rawDocument.start - rawChunk.start !== origin[0].document_start - origin[0].chunk_start
    || rawDocument.end - rawChunk.end !== origin[0].document_start - origin[0].chunk_start) return null;
  return { steps, parts: proof.fragments.length, checks: proof.mandatory_proof_count };
}

function procedureRefusal(reason: unknown) {
  if (reason === "procedure_mandatory_support_rejected") return "At least one required instruction could not be verified. The complete procedure was refused instead of presenting a partial answer.";
  if (reason === "procedure_raw_not_in_mandatory_action_premise") return "The reader did not identify an answer span inside a verified procedure action. The complete procedure was refused.";
  if (reason === "procedure_support_budget_exceeded") return "This procedure exceeds the supported evidence window. Ask about a smaller named procedure.";
  if (reason === "procedure_extent_unverified") return "The complete procedure's boundaries could not be verified from the saved source version.";
  if (reason === "procedure_chunk_mapping_ambiguous") return "The complete procedure could not be mapped to unambiguous saved source passages.";
  return null;
}

type Discovery = {
  state: "unrecorded" | "recorded" | "invalid";
  profile: Record<string, unknown>;
  selected: Record<string, unknown>[];
  observations: Record<string, unknown>[];
  patterns: Record<string, unknown>[];
};

// Both importers are already inside the existing Next client module graph.
import { useEffect, useState } from "react";
import { pythonCasefold } from "@/lib/python-casefold";
import { conditionalHashPairs, hasConditionalEvidence, inspectConditionalEvidence, inspectRetainedCapture, type ConditionalInspection } from "@/lib/procedure-condition-evidence";
import { contextDisclosures, sourceContextProfile } from "@/lib/source-context-evidence";

type SourceRange = { start: number; end: number };
type BodyHashStatus = "pending" | "matched" | "mismatch" | "unavailable";
const paragraphSpace = "[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]";

function paragraphBody(proof: Record<string, unknown>) {
  if (proof.contract === "complete-immutable-procedure-v3") return proof.source_body;
  return selectionRecord(selectionRecord(proof.required_inventory).declared_paragraphs).source_body;
}

/** No cached/obsolete promise can certify a different record, profile or source. */
function useParagraphBodyHashes(record: Record<string, unknown>) {
  const rows = Array.isArray(record.requirements) ? record.requirements.map(selectionRecord) : [];
  const proofs = rows.map((row) => selectionRecord(row.procedure_completeness)).filter((proof) => proof.structure === "declared_paragraphs");
  const requests = proofs.map((proof) => [paragraphBody(proof), proof.content_hash, proof.document_id, proof.document_version, proof.workspace_id]);
  const primitive = (value: unknown) => typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? value : null;
  const profile = selectionRecord(record.evidence_profile);
  const key = JSON.stringify([
    requests.map((request) => request.map(primitive)),
    ["id", "run_id", "query_id", "request_id", "mode", "contract", "decision"].map((field) => primitive(record[field])),
    ["contract", "proposal_profile", "role_scope_policy", "origin_contract", "role_policy_contract", "pattern_registry_contract"].map((field) => primitive(profile[field])),
    Array.isArray(record.selected_proposal_ids) ? record.selected_proposal_ids.map(primitive) : null,
  ]);
  const [result, setResult] = useState<{ record: Record<string, unknown>; key: string; statuses: Record<string, BodyHashStatus> } | null>(null);
  useEffect(() => {
    if (!proofs.length) return;
    let current = true;
    const pairs = JSON.parse(key)[0] as unknown[][];
    const digest = async (pair: unknown[]): Promise<[string, BodyHashStatus]> => {
      const [body, expected] = pair;
      const pairKey = JSON.stringify([body, expected]);
      if (typeof body !== "string" || typeof expected !== "string" || !/^[a-f0-9]{64}$/.test(expected)
        || Array.from(body).some((point) => point.length === 1 && point.charCodeAt(0) >= 0xd800 && point.charCodeAt(0) <= 0xdfff)
        || typeof TextEncoder === "undefined" || !globalThis.crypto?.subtle?.digest) return [pairKey, "unavailable"];
      try {
        const bytes = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
        const actual = Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
        return [pairKey, actual === expected ? "matched" : "mismatch"];
      } catch {
        return [pairKey, "unavailable"];
      }
    };
    void Promise.all(pairs.map(digest)).then((entries) => {
      if (current) setResult({ record, key, statuses: Object.fromEntries(entries) });
    });
    return () => { current = false; };
    // key contains only selected recorded primitives, including the exact bodies/hashes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record, key]);
  return (proof: Record<string, unknown>): BodyHashStatus => {
    if (typeof paragraphBody(proof) !== "string" || typeof proof.content_hash !== "string") return "unavailable";
    if (result?.record !== record || result.key !== key) return "pending";
    return result.statuses[JSON.stringify([paragraphBody(proof), proof.content_hash])] ?? "unavailable";
  };
}

function exactKeys(value: unknown, keys: string[]) {
  return Object.keys(selectionRecord(value)).sort().join("|") === [...keys].sort().join("|");
}
function exactRange(value: unknown, expected: SourceRange) {
  return exactKeys(value, ["start", "end"]) && sameRange(value, expected);
}
function paragraphParts(body: string): SourceRange[] {
  const points = Array.from(body), result: SourceRange[] = [];
  const white = new RegExp("^" + paragraphSpace + "$");
  let cursor = 0, index = 0;
  const add = (end: number) => {
    const part = trimSourceWhitespace(points.slice(cursor, end).join(""), cursor);
    if (part.text) result.push({ start: part.start, end: part.end });
  };
  while (index < points.length) {
    if (points[index] !== "\n") { index++; continue; }
    let end = index + 1;
    while (end < points.length && points[end] !== "\n" && white.test(points[end])) end++;
    if (points[end] !== "\n") { index++; continue; }
    while (points[end] === "\n") end++;
    add(index); cursor = end; index = end;
  }
  add(points.length);
  return result;
}
const smallCounts = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(" ");
const smallOrdinals = "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth".split(" ");
function declaredCount(text: string) {
  const lower = text.toLowerCase();
  if (/^[0-9]+$/.test(lower)) return Number(lower);
  if (smallCounts.includes(lower)) return smallCounts.indexOf(lower);
  for (const [ten, word] of [[20, "twenty"], [30, "thirty"]] as const) {
    if (lower === word) return ten;
    const unit = smallCounts.indexOf(lower.slice(word.length + 1));
    if (lower.startsWith(word + "-") && unit > 0 && unit < 10) return ten + unit;
  }
  return -1;
}
function declaredOrdinal(number: number, text: string) {
  const suffix = number % 100 >= 10 && number % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[number % 10] ?? "th";
  const word = number < 20 ? smallOrdinals[number] : number % 10 === 0 ? (number === 20 ? "twentieth" : "thirtieth") : (number < 30 ? "twenty-" : "thirty-") + smallOrdinals[number % 10];
  return text.toLowerCase() === word || text.toLowerCase() === number + suffix;
}
function outsideParagraphGovernance(text: string) {
  const points = Array.from(text), white = new RegExp("^" + paragraphSpace + "$");
  const sentences: string[] = []; let start = 0;
  for (let i = 0; i < points.length; i++) {
    if (".!?".includes(points[i]) && (i + 1 === points.length || white.test(points[i + 1]))) {
      sentences.push(points.slice(start, i + 1).join("")); start = i + 1;
    }
  }
  if (start < points.length) sentences.push(points.slice(start).join(""));
  return sentences.some((sentence) => {
    if (/\b(?:must|shall|required|prerequisites?)\b/i.test(sentence)) return true;
    let main = trimSourceWhitespace(sentence, 0).text;
    if (/^(?:before|after|if|when|unless|provided)\b/i.test(main)) {
      if (!main.includes(",")) return true;
      main = trimSourceWhitespace(main.slice(main.indexOf(",") + 1), 0).text;
    }
    const imperative = new RegExp("^(?!(?:the|a|an|this|that|it|they|he|she)\\b)[\\p{L}\\p{N}_-]+" + paragraphSpace + "+(?:the|a|an|both|one|[0-9]+)\\b", "iu");
    return imperative.test(main) || !/\b(?:is|are|was|were|has|have|can|does|makes|lasts|begins|contains|belongs|belong|remains|applies|apply|identifies|supply|uses|concerns|describes|grant)\b/i.test(main);
  });
}

/** Versioned literal source declaration, not an inference about arbitrary English. */
function declaredParagraphSource(body: string, topic: string) {
  const points = Array.from(body), parts = paragraphParts(body);
  const slice = (range: SourceRange) => points.slice(range.start, range.end).join("");
  const headings = parts.map((range, index) => ({ index, match: /^Complete (ordinary|standard|normal) procedure$/i.exec(slice(range)) })).filter((item) => item.match);
  if (headings.length !== 1 || headings[0].index < 1) return null;
  const index = headings[0].index, mode = headings[0].match![1].toLowerCase();
  const title = { start: 0, end: parts[0].end };
  const titleMatch = new RegExp("^" + paragraphSpace + "*([^:\\n.!?]+):[ \\t]*(?:current[ \\t]+)?operation[ \\t]+note\\.?[ \\t]*$", "i").exec(slice(title));
  if (!titleMatch || !parts[index + 1]) return null;
  const scope = trimSourceWhitespace(titleMatch[1], 0).text, declaration = parts[index + 1];
  const declarationPattern = new RegExp("^The next ([\\w-]+) instruction paragraphs are the entire " + mode
    + " procedure, in the stated order\\. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion\\. The procedure ends at the explicit End of " + mode
    + " procedure marker immediately after the ([\\w-]+) instruction paragraph\\. It applies to ([^.!?]+)\\.$", "i");
  const match = declarationPattern.exec(slice(declaration));
  if (!match) return null;
  const count = declaredCount(match[1]), conditions = match[3], markerIndex = index + 2 + count;
  if (!integer(count, 1, 32) || !declaredOrdinal(count, match[2]) || !parts[markerIndex + 2]) return null;
  const markers = parts.map((range, ordinal) => slice(range).toLowerCase() === "end of " + mode + " procedure" ? ordinal : -1).filter((ordinal) => ordinal >= 0);
  if (markers.length !== 1 || markers[0] !== markerIndex || slice(parts[markerIndex + 1]).toLowerCase() !== "record governance commentary") return null;
  const governancePattern = new RegExp("^The " + mode + " run is complete once the ([\\w-]+) preceding instruction paragraphs have been satisfied\\. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition\\.$", "i");
  const governance = governancePattern.exec(slice(parts[markerIndex + 2]));
  if (!governance || declaredCount(governance[1]) !== count
    || !new RegExp("^(?:an?|the)" + paragraphSpace + "+" + mode + "\\b", "i").test(conditions)
    || /\b(?:unless|except|provided)\b|\bonly\s+if\b/i.test(conditions)
    || parts.slice(1, index).some((range) => outsideParagraphGovernance(slice(range)))
    || parts.slice(markerIndex + 3).some((range) => outsideParagraphGovernance(slice(range)))) return null;
  const normal = (text: string) => pythonCasefold(trimSourceWhitespace(text, 0).text).split(new RegExp(paragraphSpace + "+")).join(" ").replace(/^(?:the|an?) /, "");
  let requested = normal(topic); const expected = normal(scope);
  if (requested !== expected) {
    if (requested.startsWith(mode + " ")) requested = requested.slice(mode.length + 1);
    if (requested.endsWith(" run") && /\brun\b/i.test(conditions)) requested = requested.slice(0, -4);
    if (requested !== expected || !new RegExp("\\b" + mode + "\\b", "i").test(conditions)) return null;
  }
  return { body, points, scope, mode, conditions, count, title, heading: parts[index], declaration, paragraphs: parts.slice(index + 2, markerIndex), marker: parts[markerIndex], governance: { start: parts[markerIndex + 1].start, end: points.length } };
}

function declaredParagraphUnits(parsed: NonNullable<ReturnType<typeof declaredParagraphSource>>, descriptor: Record<string, unknown>) {
  const extent = { start: parsed.paragraphs[0].start, end: parsed.paragraphs[parsed.count - 1].end };
  const units: { name: string; kind: string; source_range: SourceRange; premise_range: SourceRange; hypothesis: string; step: null }[] = [];
  const add = (name: string, kind: string, source: SourceRange, hypothesis: string, premise = source) => units.push({ name, kind, source_range: source, premise_range: premise, hypothesis, step: null });
  add("paragraph_namespace", "namespace", parsed.title, `This document concerns ${parsed.scope}.`);
  add("paragraph_declaration", "applicability", parsed.declaration, `The complete ${parsed.mode} procedure applies to ${parsed.conditions} and requires all ${parsed.count} instruction paragraphs in their stated order.`);
  add("paragraph_requested_scope", "request_scope", { start: parsed.title.start, end: parsed.declaration.end }, `The complete procedure is for ${descriptor.request_topic}.`);
  const block = { start: parsed.declaration.start, end: extent.end };
  add("whole_method", "whole_method", extent, `Every one of the ${parsed.count} instruction paragraphs is required, in the stated order, for completion of the ${parsed.mode} procedure.`, block);
  add("paragraph_request_constraints", "bound_condition", block, `These complete ordered instructions satisfy the entire procedure request, including its material conditions: ${descriptor.request_original}`);
  parsed.paragraphs.forEach((range, index) => {
    const text = parsed.points.slice(range.start, range.end).join("");
    add("paragraph_" + (index + 1), /^(?:do\s+not|never)\b/i.test(text) ? "prohibition" : "instruction", range, "The instructions require the following entire instruction: " + text);
  });
  add("paragraph_closure", "closure", { start: parsed.marker.start, end: parsed.governance.end }, `The ${parsed.mode} procedure ends after exactly ${parsed.count} instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.`);
  return units;
}

function declaredParagraphCompleteness(row: Record<string, unknown>, record: Record<string, unknown>, hash: BodyHashStatus, copy = false) {
  const proof = selectionRecord(row.procedure_completeness), inventory = selectionRecord(proof.required_inventory);
  const descriptor = selectionRecord(inventory.declared_paragraphs), body = descriptor.source_body;
  const margin = selectionRecord(record.evidence_support).minimum_entailment_margin;
  if (hash !== "matched" || record.contract !== "requirement-evidence-v2" || proof.contract !== (copy ? "complete-immutable-procedure-v3" : "complete-immutable-procedure-v2")
    || proof.status !== "supported" || proof.coverage_complete !== true || proof.structure !== "declared_paragraphs"
    || typeof body !== "string" || !integer(proof.body_length, 1) || Array.from(body).length !== proof.body_length
    || !nonempty(descriptor.request_topic) || descriptor.request_original !== row.original_text || !nonempty(descriptor.request_original)
    || descriptor.contract !== "declared-paragraph-procedure-v1" || !sourceIdentity(proof)
    || inventory.contract !== "procedure-required-inventory-v1"
    || ["document_id", "document_version", "content_hash", "structure"].some((key) => proof[key] !== inventory[key])
    || ((proof.workspace_id !== undefined || inventory.workspace_id !== undefined) && (!nonempty(proof.workspace_id) || proof.workspace_id !== inventory.workspace_id))
    || proof.step_count !== null || !Array.isArray(proof.step_ranges) || proof.step_ranges.length !== 0
    || !Array.isArray(inventory.step_ranges) || inventory.step_ranges.length !== 0
    || typeof margin !== "number" || !Number.isFinite(margin) || margin < 0 || margin > 4) return null;
  const parsed = declaredParagraphSource(body, descriptor.request_topic);
  if (!parsed) return null;
  const descriptorKeys = ["contract", "source_body", "request_topic", "request_original", "scope", "mode", "conditions", "declared_count", "title_range", "heading_range", "declaration_range", "paragraph_ranges", "end_marker_range", "governance_range"];
  if (!exactKeys(descriptor, descriptorKeys) || descriptor.scope !== parsed.scope || descriptor.mode !== parsed.mode || descriptor.conditions !== parsed.conditions || descriptor.declared_count !== parsed.count
    || !exactRange(descriptor.title_range, parsed.title) || !exactRange(descriptor.heading_range, parsed.heading)
    || !exactRange(descriptor.declaration_range, parsed.declaration) || !exactRange(descriptor.end_marker_range, parsed.marker)
    || !exactRange(descriptor.governance_range, parsed.governance) || !Array.isArray(descriptor.paragraph_ranges)
    || descriptor.paragraph_ranges.length !== parsed.count || descriptor.paragraph_ranges.some((range, index) => !exactRange(range, parsed.paragraphs[index]))) return null;
  const extent = { start: parsed.paragraphs[0].start, end: parsed.paragraphs[parsed.count - 1].end }, closure = selectionRecord(proof.closure);
  if (!exactRange(proof.extent, extent) || !exactRange(inventory.extent, extent) || !exactKeys(closure, ["kind", "end", "boundary_range"])
    || closure.kind !== "declared_paragraph_end" || closure.end !== extent.end || !exactRange(closure.boundary_range, parsed.marker)) return null;
  const units = declaredParagraphUnits(parsed, descriptor);
  if (!integer(proof.mandatory_proof_count, 1, 64) || proof.mandatory_proof_count !== units.length
    || !Array.isArray(inventory.units) || inventory.units.length !== units.length || !Array.isArray(proof.proof_units) || proof.proof_units.length !== units.length) return null;
  for (let index = 0; index < units.length; index++) {
    const expected = units[index], required = selectionRecord(inventory.units[index]), assessed = selectionRecord(proof.proof_units[index]);
    if (!exactKeys(required, ["name", "kind", "source_range", "premise_range", "hypothesis", "step"])
      || required.step !== null || (Object.prototype.hasOwnProperty.call(assessed, "step") && assessed.step !== null)
      || [required, assessed].some((unit) => ["name", "kind", "hypothesis"].some((key) => unit[key] !== expected[key as "name" | "kind" | "hypothesis"])
        || !exactRange(unit.source_range, expected.source_range) || !exactRange(unit.premise_range, expected.premise_range))
      || (copy ? !copyAssessmentValid(assessed, margin) : assessed.supported !== true || assessed.label !== "entailment" || !integer(assessed.pair_tokens, 1, 512)
      || typeof assessed.entailment_margin !== "number" || !Number.isFinite(assessed.entailment_margin) || assessed.entailment_margin <= 0 || assessed.entailment_margin < margin)) return null;
  }
  const targets = units.filter((unit) => unit.name !== "paragraph_declaration");
  for (const value of [inventory.structure_edges, proof.structure_edges]) {
    if (!Array.isArray(value) || value.length !== targets.length || value.some((item, index) => {
      const edge = selectionRecord(item);
      return !exactKeys(edge, ["name", "source", "target"]) || edge.name !== "paragraph_governance" || edge.source !== "paragraph_declaration" || edge.target !== targets[index].name;
    })) return null;
  }
  if (!Array.isArray(proof.fragments) || !proof.fragments.length || proof.fragments.length > 64) return null;
  let cursor = extent.start;
  for (const value of proof.fragments) {
    const part = selectionRecord(value), local = recordedRange({ start: part.chunk_start, end: part.chunk_end }), document = recordedRange({ start: part.document_start, end: part.document_end });
    if (!nonempty(part.chunk_id) || !local || !document || document.start !== cursor || document.end > extent.end
      || local.end - local.start !== document.end - document.start
      || ["document_id", "document_version", "content_hash", "workspace_id"].some((key) => Object.prototype.hasOwnProperty.call(part, key) && part[key] !== proof[key])) return null;
    cursor = document.end;
  }
  const seed = selectionRecord(proof.raw_seed), local = recordedRange(seed.chunk_range), raw = recordedRange(seed.document_range);
  if (cursor !== extent.end || !local || !raw || local.end > proof.body_length || raw.end > proof.body_length
    || typeof seed.text !== "string" || Array.from(seed.text).length !== local.end - local.start || local.end - local.start !== raw.end - raw.start
    || parsed.points.slice(raw.start, raw.end).join("") !== seed.text) return null;
  const core = trimSourceWhitespace(seed.text, raw.start), first = parsed.paragraphs[0], literal = parsed.points.slice(first.start, first.end).join("");
  if (!((sameRange(core, first) && core.text === literal) || (".!?".includes(literal.slice(-1)) && core.start === first.start && core.end === first.end - 1 && core.text === literal.slice(0, -1)))) return null;
  const origin = proof.fragments.map(selectionRecord).filter((part) => part.chunk_id === seed.chunk_id);
  if (origin.length !== 1 || raw.start < (origin[0].document_start as number) || raw.end > (origin[0].document_end as number)
    || local.start < (origin[0].chunk_start as number) || local.end > (origin[0].chunk_end as number)
    || raw.start - local.start !== (origin[0].document_start as number) - (origin[0].chunk_start as number)) return null;
  const proposals = Array.isArray(record.proposals) ? record.proposals.map(selectionRecord) : [];
  const proposal = proposals.find((item) => item.proposal_id === seed.proposal_id);
  if (!proposal || seed.origin !== proposal.origin || (seed.origin === "source_pattern" && proposal.pattern_id !== "complete-declared-paragraph-procedure-v1")
    || !["qa_reader", "source_pattern"].includes(String(seed.origin))) return null;
  return { steps: null, parts: proof.fragments.length, checks: units.length, paragraphs: parsed.count };
}

type PresentationContext = { question: unknown; answer: unknown; sources: unknown; retrievalTrace?: unknown };
type CopyHashes = { body: BodyHashStatus; answer: BodyHashStatus; hash: (body: unknown, expected: unknown) => BodyHashStatus };
const copyContract = "complete-immutable-procedure-v3";
const copyProfile = "source_declared_procedure_copy_v1";

/** Keep record identity and actual output in the async guard, including in-place mutations. */
function useCopyHashes(record: Record<string, unknown>, context: PresentationContext) {
  const proofs = (Array.isArray(record.requirements) ? record.requirements.map(selectionRecord) : [])
    .map((row) => selectionRecord(row.procedure_completeness)).filter((proof) => proof.contract === copyContract);
  const key = JSON.stringify([record, context]);
  const [result, setResult] = useState<{ record: Record<string, unknown>; key: string; hashes: Map<string, BodyHashStatus> } | null>(null);
  useEffect(() => {
    if (!proofs.length) return;
    let current = true;
    const captured = JSON.parse(key) as [Record<string, unknown>, PresentationContext];
    const pairs = (captured[0].requirements as unknown[]).map(selectionRecord).map((row) => selectionRecord(row.procedure_completeness))
      .filter((proof) => proof.contract === copyContract).flatMap((proof) => [
        [proof.source_body, proof.content_hash], [captured[1].answer, selectionRecord(proof.output_certificate).answer_sha256],
      ]);
    pairs.push(...conditionalHashPairs(captured[0]));
    void Promise.all(pairs.map(async ([body, expected]): Promise<[string, BodyHashStatus]> => {
      const pairKey = JSON.stringify([body ?? null, expected ?? null]);
      if (typeof body !== "string" || typeof expected !== "string" || !/^[a-f0-9]{64}$/.test(expected)
        || Array.from(body).some((point) => point.length === 1 && point.charCodeAt(0) >= 0xd800 && point.charCodeAt(0) <= 0xdfff)
        || typeof TextEncoder === "undefined" || !globalThis.crypto?.subtle?.digest) return [pairKey, "unavailable"];
      try {
        const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
        const actual = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
        return [pairKey, actual === expected ? "matched" : "mismatch"];
      } catch { return [pairKey, "unavailable"]; }
    })).then((entries) => { if (current) setResult({ record, key, hashes: new Map(entries) }); });
    return () => { current = false; };
    // All recorded primitives and actual context are captured in key; obsolete completions cannot publish.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record, key]);
  return (proof: Record<string, unknown>): CopyHashes => {
    if (result?.record !== record || result.key !== key) return { body: "pending", answer: "pending", hash: () => "pending" };
    const status = (body: unknown, expected: unknown) => result.hashes.get(JSON.stringify([body ?? null, expected ?? null])) ?? "unavailable";
    return { body: status(proof.source_body, proof.content_hash), answer: status(context.answer, selectionRecord(proof.output_certificate).answer_sha256), hash: status };
  };
}

function copyAssessmentValid(unit: Record<string, unknown>, margin: number) {
  const method = ["namespace", "applicability", "bound_condition"].includes(String(unit.kind)) && unit.name !== "paragraph_request_constraints"
    ? "nli_entailment" : ["instruction", "prohibition"].includes(String(unit.kind)) ? "exact_source_copy" : "exact_source_structure";
  if (unit.verification_method !== method || unit.supported !== true) return false;
  if (method !== "nli_entailment") return exactKeys(unit, ["name", "kind", "source_range", "premise_range", "hypothesis", "verification_method", "supported"]);
  return unit.label === "entailment" && integer(unit.pair_tokens, 1, 512)
    && typeof unit.entailment_margin === "number" && Number.isFinite(unit.entailment_margin) && unit.entailment_margin > 0 && unit.entailment_margin >= margin
    && Array.isArray(unit.logits) && unit.logits.length === 3 && unit.logits.every((value) => typeof value === "number" && Number.isFinite(value));
}

function sameRecorded(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value, index) => sameRecorded(value, right[index]));
  if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
  const a = selectionRecord(left), b = selectionRecord(right);
  return exactKeys(a, Object.keys(b)) && Object.keys(a).every((key) => sameRecorded(a[key], b[key]));
}

/** Closed producer request grammar: material suffixes cannot be silently ignored. */
function copyRequestMatches(row: Record<string, unknown>, proof: Record<string, unknown>, question: string) {
  const binding = selectionRecord(proof.request_binding), range = recordedRange(row.input_range);
  if (!range || !exactKeys(binding, ["question", "requirement_id", "original_text", "input_range", "topic"])
    || binding.question !== question || binding.requirement_id !== row.id || binding.original_text !== row.original_text
    || !sameRange(binding.input_range, range) || !nonempty(binding.topic) || !nonempty(row.original_text)
    || Array.from(question).slice(range.start, range.end).join("") !== row.original_text) return false;
  if (proof.structure === "declared_paragraphs") {
    if (typeof proof.source_body !== "string") return false;
    const parsed = declaredParagraphSource(proof.source_body, binding.topic);
    if (!parsed || !requestedModeMatches(row.original_text, parsed.mode)) return false;
  }
  const topic = binding.topic.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const atom = "(?:(?:its|the|every|all|each)\\s+)?(?:(?:exact|final|last|opening|closing|ordered|material)\\s+)*(?:prerequisites?|conditions?|parameters?|settings?|measurements?|prohibitions?|forbidden\\s+actions?|closure|reconciliation\\s+steps?|actions?|instructions?)";
  const features = atom + "(?:(?:,\\s*(?:and\\s+)?|\\s+and\\s+)" + atom + ")*";
  const patterns = [
    "(?:Give|Provide|State|Quote)\\s+(?:the\\s+)?(?:entire|complete|full)(?:\\s+ordered)?(?:\\s+(?:ordinary|standard|normal))?\\s+(?:procedure|method|instructions|steps)\\s+(?:for|of)\\s+(?:the\\s+)?" + topic + "(?:,\\s*(?:in order,\\s*)?including\\s+" + features + ")?[.!?]?",
    "How do I carry out the complete (?:ordinary|standard|normal) routine at the " + topic + "\\? Quote the full ordered instructions, from prerequisites through final closure[.]?",
    "Provide all instructions for an? " + topic + ", retaining their order and " + features + "[.]?",
    "I need the full " + topic + " procedure, including " + features + "[.]?",
  ];
  return patterns.some((pattern) => pythonSourcePattern(new RegExp("^(?:" + pattern + ")$", "i")).test(trimSourceWhitespace(row.original_text as string, 0).text));
}

/** Replay the versioned renderer against actual citations, not the producer's hash alone. */
function copyOutputMatches(record: Record<string, unknown>, context: PresentationContext, hashes: CopyHashes) {
  if (typeof context.question !== "string" || typeof context.answer !== "string" || !Array.isArray(context.sources) || !Array.isArray(record.requirements)) return false;
  const capture = inspectRetainedCapture(record, context.retrievalTrace);
  if (capture.state !== "missing" && capture.state !== "matched") return false;
  if (sourceContextProfile(selectionRecord(record.evidence_profile)) && capture.state !== "matched") return false;
  const rows = record.requirements.map(selectionRecord), citations = context.sources.map(selectionRecord);
  const questionPoints = Array.from(context.question), consumed = questionPoints.map(() => false);
  for (const row of rows) {
    const range = recordedRange(row.input_range);
    if (row.status !== "supported" || !range || range.end > questionPoints.length || questionPoints.slice(range.start, range.end).join("") !== row.original_text) return false;
    for (let index = range.start; index < range.end; index++) consumed[index] = true;
  }
  const remainder = questionPoints.filter((_point, index) => !consumed[index]).join("");
  if (!pythonSourcePattern(/^(?:\s|[,;.?!])*(?:(?:and|also|then)(?:\s|[,;.?!])*)*$/i).test(remainder)) return false;
  const groups: { row: Record<string, unknown>; proof: Record<string, unknown>; text: string; fragments: Record<string, unknown>[]; indices: number[] }[] = [];
  const identifiers = new Set<string>();
  for (let index = 0; index < citations.length; index++) {
    const citation = citations[index];
    if (!nonempty(citation.chunk_id) || identifiers.has(citation.chunk_id) || citation.citation_index !== index + 1
      || typeof citation.quoted_text !== "string" || !Array.isArray(citation.answer_spans)) return false;
    identifiers.add(citation.chunk_id);
    const points = Array.from(citation.quoted_text);
    for (const value of citation.answer_spans) {
      const span = selectionRecord(value), range = recordedRange(span);
      if (!range || range.end > points.length || points.slice(range.start, range.end).join("") !== span.text) return false;
    }
  }
  for (const row of rows) {
    if (row.kind !== "procedure") continue;
    const proof = selectionRecord(row.procedure_completeness), cert = selectionRecord(proof.output_certificate), extent = recordedRange(proof.extent);
    if (row.status !== "supported" || proof.contract !== copyContract || proof.procedure_verification_profile !== copyProfile
      || !copyRequestMatches(row, proof, context.question) || !extent || typeof proof.source_body !== "string"
      || Array.from(proof.source_body).length !== proof.body_length || !Array.isArray(proof.fragments)
      || !exactKeys(cert, ["contract", "renderer", "request_binding", "source_identity", "required_inventory", "instruction_range", "answer_range", "citation_mapping", "answer_sha256", ...(["procedure-output-cover-v2", "procedure-output-cover-v3", "procedure-output-cover-v4"].includes(String(cert.contract)) ? ["condition_exclusion_inventory"] : [])])
      || !["procedure-output-cover-v1", "procedure-output-cover-v2", "procedure-output-cover-v3", "procedure-output-cover-v4"].includes(String(cert.contract)) || cert.renderer !== "extractive-answer-v1"
      || !sameRecorded(cert.request_binding, proof.request_binding) || !sameRecorded(cert.required_inventory, proof.required_inventory)
      || !sameRecorded(cert.source_identity, { document_id: proof.document_id, document_version: proof.document_version, content_hash: proof.content_hash })
      || !sameRange(cert.instruction_range, extent) || !Array.isArray(cert.citation_mapping) || cert.citation_mapping.length !== proof.fragments.length) return false;
    if (["procedure-output-cover-v2", "procedure-output-cover-v3", "procedure-output-cover-v4"].includes(String(cert.contract)) ? capture.state !== "matched" || conditionInspection(row, record, context, hashes).state !== "verified"
      : hasConditionalEvidence(record, proof, row.id) || capture.conditionalRequirementIds.includes(row.id)) return false;
    const body = Array.from(proof.source_body), fragments = proof.fragments.map(selectionRecord), indices = [];
    let cursor = extent.start;
    for (let index = 0; index < fragments.length; index++) {
      const fragment = fragments[index], local = recordedRange({ start: fragment.chunk_start, end: fragment.chunk_end });
      const document = recordedRange({ start: fragment.document_start, end: fragment.document_end });
      const matches = citations.filter((citation) => citation.chunk_id === fragment.chunk_id);
      if (!local || !document || matches.length !== 1 || document.start !== cursor || document.end > extent.end || local.end - local.start !== document.end - document.start) return false;
      const citation = matches[0], passage = Array.from(citation.quoted_text as string), literal = body.slice(document.start, document.end).join("");
      if (["document_id", "document_version", "content_hash"].some((key) => citation[key] !== proof[key])
        || local.end > passage.length || passage.slice(local.start, local.end).join("") !== literal
        || !sameRecorded(cert.citation_mapping[index], { ...fragment, citation_index: citation.citation_index })
        || !(citation.answer_spans as unknown[]).some((value) => { const span = recordedRange(value); return span && span.start <= local.start && span.end >= local.end; })) return false;
      // The whole quoted chunk must occur uniquely at the implied source offset.
      const start = document.start - local.start, full = passage.join("");
      if (start < 0 || body.slice(start, start + passage.length).join("") !== full
        || body.join("").indexOf(full) !== body.join("").lastIndexOf(full)) return false;
      cursor = document.end; indices.push(citation.citation_index as number);
    }
    if (cursor !== extent.end) return false;
    groups.push({ row, proof, text: body.slice(extent.start, extent.end).join(""), fragments, indices });
  }
  if (!groups.length) return false;
  const disclosures = (Array.isArray(record.role_scope_interpretations) ? record.role_scope_interpretations.map(selectionRecord) : []).filter((item) => item.activity_fallback).map((item) => item.disclosure);
  if (disclosures.some((value) => typeof value !== "string")) return false;
  if (sourceContextProfile(selectionRecord(record.evidence_profile))) disclosures.push(...contextDisclosures(groups.flatMap(group => conditionInspection(group.row, record, context, hashes).exclusions)));
  const prefix = disclosures.length ? "Source extracts with declared activity-scope interpretation:\n\n" : "Source extracts (not model-generated):\n\n";
  let cursor = Array.from(prefix).length;
  const extracts = groups.map((group) => {
    const expected = { start: cursor, end: cursor + Array.from(group.text).length };
    const text = group.text + " " + group.indices.map((index) => `[${index}]`).join(" ");
    cursor += Array.from(text).length + 2;
    return { text, valid: sameRange(selectionRecord(group.proof.output_certificate).answer_range, expected) };
  });
  if (extracts.some((extract) => !extract.valid)) return false;
  for (const citation of citations) {
    const factual = rows.filter((row) => row.kind !== "procedure" && Array.isArray(row.witnesses)).flatMap((row) => (row.witnesses as unknown[]).map(selectionRecord))
      .filter((witness) => sameSource(witness, citation)).map((witness) => {
        const span = selectionRecord(witness.span), range = recordedRange(span);
        return range && Array.from(citation.quoted_text as string).slice(range.start, range.end).join("") === span.text ? range : null;
      }).filter((range): range is SourceRange => range !== null).sort((a, b) => a.start - b.start);
    const covered = groups.flatMap((group) => group.fragments.filter((part) => part.chunk_id === citation.chunk_id)).map((part) => [part.chunk_start as number, part.chunk_end as number]).sort((a, b) => a[0] - b[0]);
    for (const value of citation.answer_spans as unknown[]) {
      const span = recordedRange(value)!;
      let remaining = [[span.start, span.end]];
      for (const [left, right] of covered) remaining = remaining.flatMap(([a, b]) => [[a, Math.min(b, left)], [Math.max(a, right), b]].filter(([x, y]) => x < y));
      for (const [a, b] of remaining) {
        let witnessed = a;
        for (const range of factual) {
          if (range.start > witnessed) break;
          if (range.end > witnessed) witnessed = range.end;
        }
        if (witnessed < b) return false;
        const text = Array.from(citation.quoted_text as string).slice(a, b).join("");
        if (trimSourceWhitespace(text, 0).text) extracts.push({ text: `${text} [${citation.citation_index}]`, valid: true });
      }
    }
  }
  return context.answer === prefix + [...extracts.map((extract) => extract.text), ...disclosures].join("\n\n");
}

function pythonSourcePattern(expression: RegExp) {
  return new RegExp(expression.source.replace(/\\s/g, paragraphSpace).replace(/\\S/g, "[^" + paragraphSpace.slice(1, -1) + "]"), expression.flags);
}

/** The versioned backend request check compares every explicit operating mode. */
function requestedModeMatches(original: string, mode: string) {
  const modes = Array.from(original.matchAll(/\b(?:ordinary|standard|normal)\b/gi), (match) => pythonCasefold(match[0]));
  return modes.every((requested) => requested === pythonCasefold(mode));
}

/** Bind the entire topic to source literals; namespace containment cannot consume conditions. */
function numberedTopicMatches(topic: string, scope: string, conditions: string, worksheet: boolean) {
  const requested = canonicalArgument(topic), namespace = canonicalArgument(scope), applicability = canonicalArgument(conditions);
  // Standard procedure headings may name the activity while their declaration names its full class.
  if (!worksheet) return requested === namespace || requested === applicability;
  // The worksheet grammar factors the declared class and negative mark around its named namespace.
  // These are the source-bound forms in _worksheet_source_scope/_worksheet_factorable, including
  // the plural class used by the canonical source planner; no arbitrary topic prefix/tail survives.
  const declaration = /^(ordinary|standard|normal) worksheets?(.*)$/.exec(applicability);
  if (!declaration) return false;
  const [, mode, tail] = declaration, base = `${mode} ${namespace.replaceAll("-", " ")}`;
  const allowed = new Set([`${base} worksheet${tail}`, `${base} worksheets${tail}`]);
  const negative = /^ with no (.+)$/.exec(tail);
  if (negative) {
    const mark = negative[1];
    allowed.add(`${base} with no ${mark}`);
    allowed.add(`${base} worksheet bearing no ${mark}`);
    allowed.add(`${base} no ${mark} procedure`);
    allowed.add(`${base} no ${mark} method`);
  }
  return allowed.has(requested.replaceAll("-", " "));
}

type CanonicalUnit = { name: string; kind: string; source_range: SourceRange; premise_range: SourceRange; hypothesis: string; step: number | null };
const instructionVerbs = new Set(("verify check copy compare count record place arrange attach leave carry ask confirm retain obtain close lock return end skip reopen scan show wait open sign read select press save stop send keep remove enter inspect review mark label print put turn restart start disconnect connect hold release notify submit write collect file take move set use").split(" "));
function sourceSentences(body: string, start: number, end: number) {
  const points = Array.from(body), text = points.slice(start, end).join("");
  return Array.from(text.matchAll(pythonSourcePattern(/\S[^]*?(?:[.!?](?=\s|$)|$)/g)), (match) => {
    const left = start + Array.from(text.slice(0, match.index)).length;
    return trimSourceWhitespace(match[0], left);
  });
}
function canonicalArgument(text: string) { return pythonCasefold(trimSourceWhitespace(text, 0).text).split(new RegExp(paragraphSpace + "+")).join(" ").replace(/^(?:the|a|an) /, ""); }

/** Reconstruct numbered source obligations before consulting assessment records. */
function numberedCopySource(row: Record<string, unknown>, proof: Record<string, unknown>) {
  if (typeof proof.source_body !== "string") return false;
  const body = proof.source_body, points = Array.from(body), extent = recordedRange(proof.extent), binding = selectionRecord(proof.request_binding);
  if (!extent || extent.end > points.length || typeof binding.topic !== "string" || typeof row.original_text !== "string") return false;
  const slice = (range: SourceRange) => points.slice(range.start, range.end).join("");
  const closure = selectionRecord(proof.closure);
  if (closure.kind === "independent_section") {
    const tail = trimSourceWhitespace(points.slice(extent.end).join(""), extent.end);
    const heading = pythonSourcePattern(/^(?:(?:for|procedure\s+for)\s+([^,:;.?!]+)[,:]|([^,:;.?!\n]+):)\s+/i).exec(tail.text);
    if (!heading || !sameRange(closure.boundary_range, { start: tail.start, end: tail.start + Array.from(heading[0]).length })) return false;
    const target = heading[1] ?? heading[2];
    if (!heading[1] && !pythonCasefold(target).endsWith("procedure")) return false;
    const anchors = (text: string) => Array.from(text.matchAll(/\b[A-Z][A-Za-z0-9-]*\b/g), (match) => pythonCasefold(match[0])).filter((word) => !["for", "procedure", "ordinary", "standard", "normal"].includes(word));
    const named = anchors(target), requested = anchors(binding.topic);
    if (!named.length || !requested.length || named.some((word) => requested.includes(word))) return false;
  } else if (closure.kind !== "immutable_eof" || extent.end !== points.length) return false;
  const rangeOf = (match: RegExpMatchArray) => trimSourceWhitespace(match[0], Array.from(body.slice(0, match.index)).length);
  const all = Array.from(body.slice(0, points.slice(0, extent.end).join("").length).matchAll(pythonSourcePattern(/(?:^|(?<=[.!?;:])\s*)(?:step\s+)?([1-9]\d*)\.(?=\s+[A-Za-z])|(?:^|(?<=[.!?;,:])\s*)(first|next|then|finally)\b/gi)));
  let numeric = false;
  const markers = all.filter((match) => {
    if (match[1]) { if (match[1] === "1") numeric = true; return true; }
    if (numeric && /^(?:then|next|finally)$/i.test(match[2]) && trimSourceWhitespace(body.slice(0, match.index), 0).text.endsWith(",")) return false;
    numeric = false; return true;
  }).filter((match) => Array.from(body.slice(0, match.index)).length >= extent.start);
  if (!markers.length || markers.length > 32 || markers.some((match, index) => Number(match[1]) !== index + 1)) return false;
  const starts = markers.map((match) => Array.from(body.slice(0, match.index! + match[0].indexOf(match[1]))).length);
  const before = points.slice(0, starts[0]).join("");
  const worksheetDeclarations = Array.from(before.matchAll(pythonSourcePattern(/(?:^|(?<=[.!?])\s+)(?:(?:the\s+)?following|this)\s+complete\s+(?:procedure|method)\s+applies\s+to\s+([^.!?]+)[.!?]/gi)));
  const worksheetNamespaces = Array.from(before.matchAll(pythonSourcePattern(/(?:^|(?<=[.!?])\s+)(?:this\s+is\s+(?:an?|the)\s+(?:invented\s+)?)?([^.!?;]+?)\s+worksheet\s+convention[.!?]/gi)));
  let declaration = worksheetDeclarations.at(-1), namespace = worksheetNamespaces.filter((match) => !declaration || match.index! < declaration.index!).at(-1);
  const worksheet = !!namespace;
  if (!worksheet) {
    namespace = pythonSourcePattern(/^\s*([^.!?:\n]+?)\s+procedure[.:](?=\s)/i).exec(body) ?? undefined;
    const declarations = Array.from(before.matchAll(pythonSourcePattern(/(?:^|(?<=[.!?])\s+)(?:this|the\s+following|the)\s+complete\s+(?:procedure|method)\s+applies\s+to\s+([^.!?]+)[.!?]/gi)));
    declaration = declarations.length === 1 ? declarations[0] : undefined;
  }
  if (!namespace || !declaration || namespace.index! + namespace[0].length > declaration.index! || /\b(?:unless|except|not|never)\b/i.test(declaration[1])) return false;
  const ns = rangeOf(namespace), app = rangeOf(declaration), scope = trimSourceWhitespace(namespace[1], 0).text, conditions = trimSourceWhitespace(declaration[1], 0).text;
  if (!numberedTopicMatches(binding.topic, scope, conditions, worksheet)) return false;
  const declaredMode = /^(ordinary|standard|normal) /.exec(canonicalArgument(conditions))?.[1];
  if (declaredMode && !requestedModeMatches(row.original_text, declaredMode)) return false;
  const units: CanonicalUnit[] = [];
  const add = (name: string, kind: string, source_range: SourceRange, hypothesis: string, premise_range = source_range, step: number | null = null) => units.push({ name, kind, source_range: { start: source_range.start, end: source_range.end }, premise_range: { start: premise_range.start, end: premise_range.end }, hypothesis, step });
  add("namespace", "namespace", ns, worksheet ? `This worksheet convention is for ${scope}.` : `This procedure is for ${scope}.`);
  add("applicability", "applicability", app, `The complete procedure applies to ${conditions}.`);
  add("requested_scope", "request_scope", { start: ns.start, end: app.end }, `The complete procedure is for ${binding.topic}.`);
  const edges: { name: string; source: string; target: string; step?: number }[] = [{ name: "namespace_to_applicability", source: "namespace", target: "applicability" }];
  const action = (part: { text: string; start: number; end: number }, name: string, premise?: SourceRange, step: number | null = null) => {
    const clause = part.text.replace(/[.!?]+$/, "");
    const negative = pythonSourcePattern(/^(?:do\s+not|never)\s+([A-Za-z]+)\b/i).exec(clause), verb = negative ? negative[1] : clause.split(pythonSourcePattern(/\s/))[0];
    if (!clause || /["“”]/.test(clause) || !instructionVerbs.has(pythonCasefold(verb))) return false;
    const preserved = clause[0].toLowerCase() + clause.slice(1);
    add(name, negative ? "prohibition" : "instruction", part, negative ? `The instructions require that you ${preserved}.` : `The instructions require you to ${preserved}.`, premise ?? part, step);
    edges.push(step === null ? { name: "namespace_to_action", source: "namespace", target: name } : { name: "applicability_to_action", source: "applicability", target: name, step });
    return true;
  };
  let start = app.start;
  for (const [index, part] of Array.from(sourceSentences(body, 0, starts[0]).entries())) {
    if (sameRange(part, ns) || sameRange(part, app)) continue;
    if (!action(part, "prelude_" + (index + 1))) return false;
    start = Math.min(start, part.start);
  }
  const steps = starts.map((first, index) => ({ ordinal: index + 1, start: first, end: starts[index + 1] ?? extent.end }));
  for (const [index, match] of Array.from(markers.entries())) {
    const instructionStart = Array.from(body.slice(0, match.index! + match[0].length)).length;
    const parts = sourceSentences(body, instructionStart, steps[index].end);
    if (!parts.length || parts.some((part, ordinal) => !action(part, `step_${index + 1}_action_${ordinal + 1}`, steps[index], index + 1))) return false;
  }
  if (start !== extent.start) return false;
  const block = slice(extent), configured = pythonSourcePattern(/\bwith\s+(.+?)(?=,\s*(?:including|covering)|[?.]|$)/i).exec(row.original_text);
  const bound: { range: SourceRange; hypothesis: string }[] = [];
  if (configured && !configured[1].includes(",")) {
    for (const configuration of configured[1].split(pythonSourcePattern(/\s+and\s+/i))) {
      if (pythonSourcePattern(/\d|\bno\s+/i).test(configuration)) continue;
      const literal = canonicalArgument(configuration).split(pythonSourcePattern(/\s+/)).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
      const occurrence = pythonSourcePattern(new RegExp("\\b" + literal + "\\b", "i")).exec(block);
      if (occurrence) {
        const after = occurrence.index + occurrence[0].length, stop = pythonSourcePattern(/[,;.!?](?=\s|$)/).exec(block.slice(after));
        const end = stop ? after + stop.index + stop[0].length : block.length;
        bound.push({ range: { start: extent.start, end: extent.start + Array.from(block.slice(0, end)).length }, hypothesis: `The instructions for ${binding.topic} require using ${configuration}.` });
      }
    }
  }
  if (pythonSourcePattern(/\bno\s+(.+?)(?=\s+(?:procedure|method|worksheet)\b|[,?.]|$)/i).test(row.original_text.replaceAll("-", " ")) && worksheetDeclarations.length) bound.push({ range: { start: app.start, end: app.end }, hypothesis: `The procedure applies to ${declaration[1]}.` });
  if (pythonSourcePattern(/^[\w-]+\s+(?:back|up|down|out|off|on|over|in|away|through)\s+.+$/i).test(binding.topic)) {
    const first = sourceSentences(body, starts[0] + (markers[0][0].length - markers[0][0].indexOf(markers[0][1])), extent.end)[0];
    if (!first) return false;
    bound.push({ range: { start: extent.start, end: first.end }, hypothesis: `The instructions describe how to ${binding.topic}.` });
  }
  for (const destination of Array.from(row.original_text.matchAll(pythonSourcePattern(/\b((?!(?:including|covering)\b)\w+ing)\s+(.+?)\s+to\s+(.+?)(?=[,.?!]|$)/gi)))) bound.push({ range: extent, hypothesis: `The instructions for ${binding.topic} require ${destination[0]}.` });
  bound.forEach((item, index) => add(`bound_condition_${index + 1}`, "bound_condition", item.range, item.hypothesis));
  const inventory = selectionRecord(proof.required_inventory);
  if (!sameRecorded(inventory.units, units) || !sameRecorded(inventory.structure_edges, edges) || !sameRecorded(proof.structure_edges, edges)
    || !sameRecorded(proof.step_ranges, steps) || !sameRecorded(inventory.step_ranges, steps)) return false;
  const first = units.find((unit) => unit.name === "step_1_action_1");
  if (!first || !sameRecorded(inventory.seed_clause, { unit_name: first.name, source_range: first.source_range, text: slice(first.source_range) })) return false;
  const opposed = new Map<string, string>();
  for (const unit of units.filter((unit) => ["instruction", "prohibition"].includes(unit.kind))) {
    let predicate = trimSourceWhitespace(slice(unit.source_range).replace(/[.!?]+$/, ""), 0).text;
    if (unit.kind === "prohibition") predicate = predicate.replace(pythonSourcePattern(/^(?:do\s+not|never)\s+/i), "");
    const key = pythonCasefold(predicate).split(pythonSourcePattern(/\s+/)).join(" ");
    if (opposed.has(key) && opposed.get(key) !== unit.kind) return false;
    opposed.set(key, unit.kind);
  }
  return true;
}

/** The canonical declared parser supplies source obligations to the pure conditional replay. */
function conditionalPlan(body: string, identity: Record<string, unknown>, topic: string, original: string) {
  const parsed = declaredParagraphSource(body, topic);
  if (!parsed || !requestedModeMatches(original, parsed.mode)) return null;
  const descriptor = { contract: "declared-paragraph-procedure-v1", source_body: body, request_topic: topic, request_original: original,
    scope: parsed.scope, mode: parsed.mode, conditions: parsed.conditions, declared_count: parsed.count, title_range: parsed.title, heading_range: parsed.heading,
    declaration_range: parsed.declaration, paragraph_ranges: parsed.paragraphs, end_marker_range: parsed.marker, governance_range: parsed.governance };
  const units = declaredParagraphUnits(parsed, descriptor), extent = { start: parsed.paragraphs[0].start, end: parsed.paragraphs[parsed.count - 1].end };
  const edges = units.filter((unit) => unit.name !== "paragraph_declaration").map((unit) => ({ name: "paragraph_governance", source: "paragraph_declaration", target: unit.name }));
  return { scope: parsed.scope, conditions: parsed.conditions, extent, units, required_inventory: { contract: "procedure-required-inventory-v1", ...identity,
    extent, structure: "declared_paragraphs", step_ranges: [], units, structure_edges: edges, declared_paragraphs: descriptor } };
}
function conditionInspection(row: Record<string, unknown>, record: Record<string, unknown>, context: PresentationContext, hashes: CopyHashes): ConditionalInspection {
  return inspectConditionalEvidence(record, selectionRecord(row.procedure_completeness), row, context.question, {
    plan: conditionalPlan, parts: paragraphParts, pattern: pythonSourcePattern, canonical: canonicalArgument, hash: hashes.hash,
  });
}

function copyCompleteness(row: Record<string, unknown>, record: Record<string, unknown>, context: PresentationContext, hashes: CopyHashes) {
  const proof = selectionRecord(row.procedure_completeness), profile = selectionRecord(record.evidence_profile);
  if (record.mode !== "reader" || selectionRecord(record.evidence_support).mode !== "local_nli"
    || !(profile.contract === "evidence-profile-v2" || sourceContextProfile(profile)) || profile.procedure_verification_profile !== copyProfile
    || hashes.body !== "matched" || hashes.answer !== "matched" || !copyOutputMatches(record, context, hashes)) return null;
  if (proof.structure === "declared_paragraphs") {
    const descriptor = selectionRecord(selectionRecord(proof.required_inventory).declared_paragraphs);
    if (proof.source_body !== descriptor.source_body || descriptor.request_topic !== selectionRecord(proof.request_binding).topic) return null;
    return declaredParagraphCompleteness(row, record, hashes.body, true);
  }
  if (proof.structure === "numbered" && numberedCopySource(row, proof)) return procedureCompleteness(row, record, true);
  return null;
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function sourceIdentity(value: Record<string, unknown>) {
  return nonempty(value.document_id) && integer(value.document_version, 1)
    && typeof value.content_hash === "string" && /^[a-f0-9]{64}$/.test(value.content_hash);
}

function sameSource(left: Record<string, unknown>, right: Record<string, unknown>) {
  return ["document_id", "document_version", "content_hash", "chunk_id"].every((key) => left[key] === right[key]);
}

function sameProposal(left: Record<string, unknown>, right: Record<string, unknown>) {
  return ["contract", "proposal_id", "requirement_id", "origin", "document_id", "document_version", "content_hash", "chunk_id", "text", "pattern_id", "grammar_version", "qa_observation_id"]
    .every((key) => (left[key] ?? null) === (right[key] ?? null))
    && sameRange(left.chunk_range, right.chunk_range) && sameRange(left.document_range, right.document_range);
}

/** A discovery literal must project exactly into its recorded source witness. */
function witnessProposalMatches(witness: Record<string, unknown>, proposal: Record<string, unknown>, procedure: boolean) {
  const span = selectionRecord(witness.span), local = recordedRange(span), document = recordedRange(witness.document_range);
  const chunk = recordedRange(proposal.chunk_range), projected = recordedRange(proposal.document_range);
  if (!local || !document || !chunk || !projected || typeof span.text !== "string") return false;
  const points = Array.from(span.text), delta = document.start - local.start;
  if (points.length !== local.end - local.start || document.end - document.start !== points.length
    || chunk.start < local.start || chunk.end > local.end
    || projected.start < document.start || projected.end > document.end
    || projected.start - chunk.start !== delta || projected.end - chunk.end !== delta
    || points.slice(chunk.start - local.start, chunk.end - local.start).join("") !== proposal.text) return false;
  // A complete procedure value can cover many fragments; its separate proof validates that extent.
  return procedure || (nonempty(witness.value) && span.text.includes(witness.value));
}

function diagnosticObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasRawQaAuthority(diagnostic: Record<string, unknown>) {
  return ["raw_candidates", "raw_span", "parts"].some((key) => Object.prototype.hasOwnProperty.call(diagnostic, key));
}

/** Decode recorded crosslinks only, never reconstruct source text or rerun a model. */
function qaObservationMatchesProposal(observation: Record<string, unknown>, proposal: Record<string, unknown>, legacySpanOnly: boolean) {
  const span = selectionRecord(observation.span);
  if (!diagnosticObject(observation.diagnostics)) return false;
  let diagnostic = observation.diagnostics;
  // Missing raw fields alone cannot turn a modern capture into historical evidence.
  if (!hasRawQaAuthority(diagnostic)) {
    return legacySpanOnly && sameRange(span, proposal.chunk_range) && span.text === proposal.text;
  }
  // Match the producer's unchanged, at-most-three raw discovery candidates. The
  // observation span can subsequently expand to the complete source procedure.
  let choices = diagnostic.raw_candidates;
  if (choices == null) {
    if (Object.prototype.hasOwnProperty.call(diagnostic, "parts") && !Array.isArray(diagnostic.parts)) return false;
    if ((diagnostic.part_count ?? 1) === 1 && Array.isArray(diagnostic.parts) && diagnostic.parts.length) {
      if (!diagnosticObject(diagnostic.parts[0])) return false;
      diagnostic = diagnostic.parts[0];
    }
    choices = diagnostic.raw_candidates;
  }
  if (choices == null) {
    const raw = diagnostic.raw_span;
    choices = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? [raw] : [];
  }
  if (!Array.isArray(choices)) return false;
  const candidates = choices.slice(0, 3);
  return observation.span !== null && candidates.every((item) => item !== null && typeof item === "object" && !Array.isArray(item))
    && candidates.some((item) => {
      const candidate = selectionRecord(item);
      return sameRange(candidate, proposal.chunk_range) && (candidate.text === undefined || candidate.text === proposal.text);
    });
}

function discoveryEvidence(record: Record<string, unknown>, retrievalTrace: unknown): Discovery {
  const profile = selectionRecord(record.evidence_profile), lineage = selectionRecord(record.discovery_lineage);
  const retained = selectionRecord(selectionRecord(selectionRecord(retrievalTrace).provenance).answer_selection);
  const modern = [record, retained].some((selection) => selectionRecord(selection.evidence_profile).contract === "evidence-profile-v2"
    || Array.isArray(selection.requirements) && selection.requirements.some((row) => selectionRecord(selectionRecord(row).procedure_completeness).contract === "complete-immutable-procedure-v3"));
  const legacySpanOnly = (observation: Record<string, unknown>) => profile.contract === "evidence-profile-v1" && !modern
    && !(Array.isArray(retained.qa_observations) && retained.qa_observations.map(selectionRecord).some((captured) =>
      (captured.observation_id === observation.observation_id || captured.requirement_id === observation.requirement_id && captured.chunk_id === observation.chunk_id)
      && (!diagnosticObject(captured.diagnostics) || hasRawQaAuthority(captured.diagnostics))));
  const observations = Array.isArray(record.qa_observations) ? record.qa_observations.map(selectionRecord) : [];
  const patterns = Array.isArray(record.pattern_observations) ? record.pattern_observations.map(selectionRecord) : [];
  const result: Discovery = { state: "invalid", profile, selected: [], observations, patterns };
  const arrays = ["proposals", "selected_proposal_ids", "qa_observations", "pattern_observations"];
  const hasNewFields = Object.prototype.hasOwnProperty.call(record, "evidence_profile")
    || arrays.some((key) => Object.prototype.hasOwnProperty.call(record, key));
  if (!hasNewFields && (record.discovery_lineage === undefined || lineage.status === "legacy_unrecorded")) return { ...result, state: "unrecorded" };
  const limits = selectionRecord(profile.pattern_limits);
  if (!(profile.contract === "evidence-profile-v1" || ((profile.contract === "evidence-profile-v2" || sourceContextProfile(profile))
    && profile.procedure_verification_profile === "source_declared_procedure_copy_v1"))
    || typeof profile.proposal_profile !== "string" || !["qa_only_v1", "qa_plus_source_patterns_v1"].includes(profile.proposal_profile)
    || typeof profile.role_scope_policy !== "string" || !["literal_v1", "ordinary_session_activity_v1"].includes(profile.role_scope_policy)
    || profile.origin_contract !== "proposal-origin-v1" || profile.role_policy_contract !== "ordinary-session-activity-role-v1"
    || profile.pattern_registry_contract !== (profile.proposal_profile === "qa_only_v1" ? "disabled" : "typed-source-patterns-v1")
    || limits.per_source_requirement !== 3 || limits.per_requirement !== 16
    || lineage.status !== "recorded" || lineage.valid !== true
    || arrays.some((key) => !Array.isArray(record[key])) || !Array.isArray(record.requirements)) return result;
  const qa = new Map<string, Record<string, unknown>>();
  for (const observation of observations) {
    const span = selectionRecord(observation.span), range = recordedRange(span);
    if (!nonempty(observation.observation_id) || qa.has(observation.observation_id)
      || !nonempty(observation.requirement_id) || !nonempty(observation.chunk_id)
      || !diagnosticObject(observation.diagnostics)
      || (observation.span !== null && (!range || typeof span.text !== "string" || Array.from(span.text).length !== range.end - range.start))) return result;
    qa.set(observation.observation_id, observation);
  }
  const validProposal = (proposal: Record<string, unknown>) => {
    const chunk = recordedRange(proposal.chunk_range), document = recordedRange(proposal.document_range);
    if (proposal.contract !== "proposal-origin-v1" || !nonempty(proposal.proposal_id)
      || !nonempty(proposal.requirement_id) || !nonempty(proposal.chunk_id) || !sourceIdentity(proposal)
      || !chunk || !document || typeof proposal.text !== "string" || !proposal.text
      || Array.from(proposal.text).length !== chunk.end - chunk.start
      || chunk.end - chunk.start !== document.end - document.start) return false;
    if (proposal.origin === "source_pattern") return profile.proposal_profile === "qa_plus_source_patterns_v1"
      && nonempty(proposal.pattern_id) && proposal.grammar_version === profile.pattern_registry_contract
      && proposal.qa_observation_id == null && proposal.null_margin == null;
    if (proposal.origin !== "qa_reader" || proposal.pattern_id != null || proposal.grammar_version != null
      || !nonempty(proposal.qa_observation_id)) return false;
    const observation = qa.get(proposal.qa_observation_id);
    return observation?.requirement_id === proposal.requirement_id && observation?.chunk_id === proposal.chunk_id
      && qaObservationMatchesProposal(observation, proposal, legacySpanOnly(observation));
  };
  const proposals = new Map<string, Record<string, unknown>>();
  for (const value of record.proposals as unknown[]) {
    const proposal = selectionRecord(value);
    if (!validProposal(proposal) || proposals.has(proposal.proposal_id as string)) return result;
    proposals.set(proposal.proposal_id as string, proposal);
  }
  const selected = new Map<string, Record<string, unknown>>();
  for (const id of record.selected_proposal_ids as unknown[]) {
    if (!nonempty(id) || selected.has(id) || !proposals.has(id)) return result;
    selected.set(id, proposals.get(id)!);
  }
  const referenced = new Set<string>(), requirements = new Set<string>();
  for (const value of record.requirements) {
    const row = selectionRecord(value);
    if (!nonempty(row.id) || requirements.has(row.id)) return result;
    requirements.add(row.id);
    if (row.status !== "supported") continue;
    if (!Array.isArray(row.witnesses) || !row.witnesses.length) return result;
    const rowProposals: Record<string, unknown>[] = [];
    for (const value of row.witnesses) {
      const witness = selectionRecord(value);
      if (!nonempty(witness.value) || !Array.isArray(witness.proposals) || !witness.proposals.length) return result;
      for (const value of witness.proposals) {
        const proposal = selectionRecord(value), canonical = selected.get(proposal.proposal_id as string);
        if (!validProposal(proposal) || !canonical || !sameProposal(proposal, canonical)
          || proposal.requirement_id !== row.id || !sameSource(proposal, witness)
          || !witnessProposalMatches(witness, proposal, row.kind === "procedure")) return result;
        referenced.add(proposal.proposal_id as string); rowProposals.push(proposal);
      }
    }
    if (row.kind === "procedure") {
      const proof = selectionRecord(row.procedure_completeness), seed = selectionRecord(proof.raw_seed);
      if (!rowProposals.some((proposal) => seed.proposal_id === proposal.proposal_id && seed.origin === proposal.origin
        && seed.chunk_id === proposal.chunk_id && seed.text === proposal.text
        && ["document_id", "document_version", "content_hash"].every((key) => proof[key] === proposal[key])
        && sameRange(seed.chunk_range, proposal.chunk_range) && sameRange(seed.document_range, proposal.document_range))) return result;
    }
  }
  if (Array.from(selected.keys()).some((id) => !referenced.has(id))
    || Array.from(proposals.values()).some((proposal) => !requirements.has(proposal.requirement_id as string))) return result;
  return { ...result, state: "recorded", selected: Array.from(selected.values()) };
}

function roleIdentityMatches(row: Record<string, unknown>, role: Record<string, unknown>) {
  const activity = role.effective_scope === "activity";
  const checks: Record<string, boolean> = {
    basis: role.basis === (activity ? "activity_role" : "documented_session_assignment"),
    kind: role.kind === row.kind,
    original_text: nonempty(row.original_text) && role.original_text === row.original_text,
    input_range: sameRange(role.input_range, row.input_range),
    prepared_question: nonempty(row.prepared_question) && role.prepared_question === row.prepared_question,
    effective_target: nonempty(role.effective_target) && role.effective_target === (activity ? role.activity_scope : role.requested_scope),
    source_workspace: role.source_workspace === null ? row.source_workspace == null
      : nonempty(role.source_workspace) && role.source_workspace === row.source_workspace,
  };
  return Object.entries(checks).every(([key, valid]) => !Object.prototype.hasOwnProperty.call(role, key) || valid);
}

function roleScopeEvidence(row: Record<string, unknown>, record: Record<string, unknown>, discovery: Discovery) {
  const role = selectionRecord(row.role_scope_interpretation);
  const attempt = typeof role.disclosure === "string" ? role.disclosure : null;
  if (row.role_scope_interpretation === undefined) return { valid: true, warning: null, disclosure: null, attempt: null };
  const coherent = role.contract === "ordinary-session-activity-role-v1" && role.requirement_id === row.id
    && typeof row.kind === "string" && ["owner", "deputy"].includes(row.kind)
    && ["requested_scope", "session_scope", "activity_scope"].every((key) => nonempty(role[key]))
    && discovery.state === "recorded" && discovery.profile.role_scope_policy === "ordinary_session_activity_v1"
    && ((role.effective_scope === "activity" && role.activity_fallback === true && nonempty(role.disclosure))
      || (role.effective_scope === "session" && role.activity_fallback === false && role.disclosure === null));
  if (!coherent || !roleIdentityMatches(row, role)) return { valid: false, warning: "Role-scope metadata invalid", disclosure: null, attempt };
  if (role.activity_fallback === false) return { valid: true, warning: null, disclosure: null, attempt: null };
  const readSet = selectionRecord(record.role_scope_read_set);
  const documents = Array.isArray(readSet.documents) ? readSet.documents.map(selectionRecord) : [];
  const witnesses = Array.isArray(row.witnesses) ? row.witnesses.map(selectionRecord) : [];
  const inspected = readSet.contract === "role-scope-inspection-read-set-v1" && readSet.complete === true
    && (readSet.reason == null || readSet.reason === "")
    && documents.length > 0 && documents.every(sourceIdentity)
    && witnesses.length > 0 && witnesses.every((witness) => documents.some((document) =>
      ["document_id", "document_version", "content_hash"].every((key) => witness[key] === document[key])));
  if (!inspected) return { valid: false, warning: "Role-scope inspection unknown or incomplete", disclosure: null, attempt };
  return { valid: true, warning: null, disclosure: row.status === "supported" ? attempt : null, attempt: row.status === "supported" ? null : attempt };
}

function DiscoveryDetails({ discovery, readSet }: { discovery: Discovery; readSet: Record<string, unknown> }) {
  const abstentions = discovery.observations.filter((observation) => observation.span === null).length;
  const qa = discovery.selected.some((proposal) => proposal.origin === "qa_reader");
  const pattern = discovery.selected.some((proposal) => proposal.origin === "source_pattern");
  const scalar = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
  return <>
    {discovery.state === "unrecorded" ? <><p>Extraction profile unrecorded</p><p>Discovery origin unrecorded</p></>
      : discovery.state === "invalid" ? <><p>Evidence discovery metadata invalid</p>{abstentions ? <p>Recorded QA abstention (discovery metadata invalid)</p> : null}</>
        : <>
          <p>{qa && pattern ? "Selected discovery: QA reader and typed source pattern" : qa ? "Selected discovery: QA reader" : pattern ? "Selected discovery: typed source pattern" : "No discovery proposal selected"}</p>
          {abstentions ? <p>QA reader abstained on {abstentions} recorded {abstentions === 1 ? "attempt" : "attempts"}.</p> : null}
          {pattern ? <p>Source patterns discover literal spans. Their origin does not establish QA acceptance or semantic support.</p> : null}
        </>}
    {discovery.state !== "unrecorded" ? <details>
      <summary>Evidence discovery details</summary>
      <p>These are recorded crosslinks and decisions, not a source-history attestation or a model rerun.</p>
      <dl className="gt-details">
        <dt>Recorded proposal profile</dt><dd>{scalar(discovery.profile.proposal_profile)}</dd>
        <dt>Recorded role policy</dt><dd>{discovery.profile.role_scope_policy === "ordinary_session_activity_v1" ? "Ordinary-session activity policy" : discovery.profile.role_scope_policy === "literal_v1" ? "Literal scope policy" : "unknown"}</dd>
        {Object.keys(readSet).length ? <>
          <dt>Role-scope inspection</dt><dd>{readSet.contract === "role-scope-inspection-read-set-v1" && readSet.complete === true && (readSet.reason == null || readSet.reason === "") ? "Recorded complete" : "Recorded inspection unknown or incomplete"}</dd>
          <dt>Inspection reason</dt><dd>{scalar(readSet.reason)}</dd>
        </> : null}
      </dl>
      <ul>{discovery.selected.map((proposal) => <li key={proposal.proposal_id as string}>
        <p>{proposal.origin === "qa_reader" ? "QA reader" : "Typed source pattern"} · {scalar(proposal.proposal_id)}</p>
        {proposal.origin === "source_pattern" ? <p>{scalar(proposal.pattern_id)}</p> : null}
        <p>{scalar(proposal.document_id)} · version {scalar(proposal.document_version)} · chunk {scalar(proposal.chunk_id)}</p>
        <p>Chunk codepoints {scalar(selectionRecord(proposal.chunk_range).start)}–{scalar(selectionRecord(proposal.chunk_range).end)}; document codepoints {scalar(selectionRecord(proposal.document_range).start)}–{scalar(selectionRecord(proposal.document_range).end)}</p>
        <p>{scalar(proposal.text)}</p>
      </li>)}</ul>
      <ul>{discovery.observations.map((observation, index) => <li key={index}>
        {observation.span === null ? "Recorded QA observation: abstention" : <span>Recorded QA span: {scalar(selectionRecord(observation.span).text)}</span>}
        <p>Observation {scalar(observation.observation_id)} · requirement {scalar(observation.requirement_id)} · chunk {scalar(observation.chunk_id)}</p>
        <p>Reader: {scalar(selectionRecord(observation.reader).model)} · decision: {scalar(selectionRecord(observation.diagnostics).decision)}</p>
      </li>)}</ul>
      <ul>{discovery.patterns.map((observation, index) => <li key={index}>
        <p>Pattern support decision: {scalar(observation.decision)}</p>
        <p>Pattern proposal {scalar(selectionRecord(observation.proposal).proposal_id)} · requirement {scalar(observation.requirement_id ?? selectionRecord(observation.proposal).requirement_id)} · chunk {scalar(observation.chunk_id ?? selectionRecord(observation.proposal).chunk_id)}</p>
        {nonempty(observation.reason) ? <p>{observation.reason}</p> : null}
      </li>)}</ul>
    </details> : null}
  </>;
}

function ContextReferenceDetails({ exclusions }: { exclusions: Record<string, unknown>[] }) {
  const scopes = exclusions.map(exclusion => selectionRecord(exclusion.condition_scope)).filter(scope => scope.contract === "procedure-condition-scope-v3");
  if (!scopes.length) return null;
  const scalar = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
  return <section aria-label="Recorded context-reference structure">
    <h6>Context-reference binding</h6>
    <p>Policy-authorized discourse roles bind the note&apos;s card, cover and decision references. This records interpretation of the note, without establishing physical identity, existence or successful execution.</p>
    <p>The declared method is selected by the context policy before inference. Every recorded NLI obligation remains separately mandatory.</p>
    {scopes.map((scope, index) => {
      const plan = selectionRecord(scope.obligation_plan), obligations = Array.isArray(scope.reference_obligations) ? scope.reference_obligations.map(selectionRecord) : [];
      return <details key={index}><summary>Recorded typed reference binding · source {index + 1}</summary>
        <p>Mandatory methods: {scalar(plan.mandatory_nli_count)} recorded NLI checks and {scalar(plan.mandatory_exact_reference_count)} exact reference obligation.</p>
        {obligations.map((obligation, i) => {
          const reference = selectionRecord(obligation.reference_plan), guard = selectionRecord(reference.guard);
          const entities = Array.isArray(reference.entities) ? reference.entities.map(selectionRecord) : [];
          const slots = Array.isArray(reference.binding_slots) ? reference.binding_slots.map(selectionRecord) : [];
          const occurrences = Array.isArray(reference.reference_occurrences) ? reference.reference_occurrences.map(selectionRecord) : [];
          return <div key={i}>
            <p>Reference binding method: {scalar(obligation.verification_method)} · result: {scalar(obligation.result)} · contract: {scalar(obligation.contract)}</p>
            <p>Guard: {scalar(guard.connective)} · {scalar(guard.meaning)}</p>
            <ul>{entities.map((entity, j) => <li key={j}>{scalar(entity.id)} · {scalar(entity.type)} · {scalar(entity.literal)} · codepoints {scalar(selectionRecord(entity.source_range).start)}–{scalar(selectionRecord(entity.source_range).end)}{entity.cover_of ? ` · cover of ${scalar(entity.cover_of)}` : ""}</li>)}</ul>
            <ul>{slots.map((slot, j) => <li key={j}>Binding {scalar(slot.binding)} → {scalar(slot.target_role)} · {scalar(slot.literal)} · codepoints {scalar(selectionRecord(slot.source_range).start)}–{scalar(selectionRecord(slot.source_range).end)}</li>)}</ul>
            <ul>{occurrences.map((occurrence, j) => <li key={j}>{scalar(occurrence.literal)} → {scalar(occurrence.target_id)} ({scalar(occurrence.target_type)}) · codepoints {scalar(selectionRecord(occurrence.source_range).start)}–{scalar(selectionRecord(occurrence.source_range).end)}</li>)}</ul>
            <details><summary>Complete typed reference plan</summary><pre>{JSON.stringify(reference, null, 2)}</pre></details>
          </div>;
        })}
      </details>;
    })}
  </section>;
}

function ContextReadingDetails({ exclusions }: { exclusions: Record<string, unknown>[] }) {
  const disclosures = contextDisclosures(exclusions);
  const scalar = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
  return <section aria-label="Context reading">
    <h5>Context reading</h5>
    <p>This is a policy interpretation, separate from recorded NLI support. The client checks recorded bodies, crosslinks and arithmetic; it does not rerun inference or authenticate historical storage.</p>
    <p>Ordinary procedure and marked audit card instructions have separate stated scopes. Opposing card dispositions remain unresolved.</p>
    {disclosures.map(disclosure => <p key={disclosure}>{disclosure}</p>)}
    <ContextReferenceDetails exclusions={exclusions} />
    {exclusions.map((exclusion, index) => {
      const scope = selectionRecord(exclusion.condition_scope), reading = selectionRecord(scope.context_reading), adopted = selectionRecord(reading.adopted_context);
      const clauses = Array.isArray(reading.clause_inventory) ? reading.clause_inventory.map(selectionRecord) : [];
      const edges = Array.isArray(reading.reference_edges) ? reading.reference_edges.map(selectionRecord) : [];
      const checks = Array.isArray(scope.semantic_checks) ? scope.semantic_checks.map(selectionRecord) : [];
      return <details key={index}><summary>Recorded literal clauses and references · source {index + 1}</summary>
        <p>Document {scalar(selectionRecord(exclusion.source_identity).document_id)} · version {scalar(selectionRecord(exclusion.source_identity).document_version)}</p>
        <p>Adopted condition: {scalar(adopted.condition)}. Actor: {scalar(adopted.actor)}. Object: {scalar(adopted.object)}.</p>
        <p>“{scalar(adopted.quantifier_domain)}” is read as {scalar(adopted.resolved_quantifier_domain)}; “{scalar(adopted.choice_domain)}” is read as {scalar(adopted.resolved_choice_domain)}.</p>
        <ul>{clauses.map((clause, i) => <li key={i}><p>{scalar(clause.kind)} · codepoints {scalar(selectionRecord(clause.source_range).start)}–{scalar(selectionRecord(clause.source_range).end)}</p><pre>{scalar(clause.literal)}</pre></li>)}</ul>
        <ul>{edges.map((edge, i) => <li key={i}>{scalar(edge.source_literal)} → {scalar(edge.target_kind)} · codepoints {scalar(selectionRecord(edge.source_range).start)}–{scalar(selectionRecord(edge.source_range).end)}{edge.external_binding ? ` · ${scalar(edge.external_binding)}` : ` · target ${scalar(selectionRecord(edge.target_range).start)}–${scalar(selectionRecord(edge.target_range).end)}`}</li>)}</ul>
        <details><summary>Recorded contextual NLI checks</summary>
          <p>These clause and subject/applicability assessments are recorded classifier support. Contextual reference resolution follows the declared policy.</p>
          <ul>{checks.map((check, i) => { const assessment = selectionRecord(check.assessment); return <li key={i}>
            <p>{scalar(check.name)} · {scalar(check.hypothesis)}</p>
            <p>Recorded NLI method: {scalar(check.verification_method)} · label: {scalar(assessment.label)} · margin: {scalar(assessment.entailment_margin)} · pair tokens: {scalar(assessment.pair_tokens)}</p>
            <p>Recorded NLI logits (contradiction, entailment, neutral): {Array.isArray(assessment.logits) ? assessment.logits.join(", ") : "unavailable"}</p>
            <pre>{scalar(selectionRecord(check.pair).premise)}</pre>
          </li>; })}</ul>
        </details>
        <details><summary>Recorded complete context source</summary><pre>{scalar(reading.source_body)}</pre></details>
      </details>;
    })}
  </section>;
}

function RequirementCoverage({ record, discovery, paragraphHash, copyHash, context }: { record: Record<string, unknown>; discovery: Discovery; paragraphHash: (proof: Record<string, unknown>) => BodyHashStatus; copyHash: (proof: Record<string, unknown>) => CopyHashes; context: PresentationContext }) {
  // Retained execution inputs constrain every presentation path, including legacy dispatch.
  const capture = inspectRetainedCapture(record, context.retrievalTrace);
  const captureReady = capture.state === "missing" || capture.state === "matched";
  const captureWarning = !captureReady ? <p className="gt-muted">{capture.state === "mismatch"
    ? "Recorded requirement evidence unverified: retained query capture does not match the displayed record."
    : "Recorded requirement evidence unverified: retained query capture is malformed."}</p> : null;
  if (!Array.isArray(record.requirements)) {
    return <>{captureWarning}<p className="gt-muted">Requirement coverage was not recorded for this response.</p></>;
  }
  const rows = record.requirements.filter((item) => item !== null && typeof item === "object" && !Array.isArray(item)).map((item) => {
    const row = selectionRecord(item);
    const witnesses = Array.isArray(row.witnesses) ? row.witnesses.map(selectionRecord).map((witness) => witness.value).filter((value): value is string => typeof value === "string" && value.length > 0) : [];
    const text = typeof row.original_text === "string" ? row.original_text : null;
    const retainedV3 = capture.v3RequirementIds?.includes(row.id) ?? false;
    const procedure = row.kind === "procedure" || retainedV3;
    const scope = roleScopeEvidence(row, record, discovery);
    const metadataReady = discovery.state !== "invalid" && scope.valid && captureReady;
    const proof = selectionRecord(row.procedure_completeness), paragraphs = proof.structure === "declared_paragraphs";
    const copy = proof.contract === "complete-immutable-procedure-v3";
    const hashes = copy ? copyHash(proof) : null;
    const hash = copy ? hashes!.body : paragraphs ? paragraphHash(proof) : null;
    const completeness = procedure && metadataReady && (!retainedV3 || copy) ? copy ? copyCompleteness(row, record, context, hashes!) : paragraphs ? declaredParagraphCompleteness(row, record, hash!) : procedureCompleteness(row, record) : null;
    const conditionRecord = copy && hashes ? conditionInspection(row, record, context, hashes) : null;
    const conditional = (!conditionRecord || conditionRecord.state === "absent") && capture.conditionalRequirementIds.includes(row.id)
      ? { state: "invalid" as const, exclusions: [] } : conditionRecord;
    const unknownProcedure = procedure && row.status === "supported" && !completeness;
    const status = row.status === "supported" && text && witnesses.length && !unknownProcedure && metadataReady ? "supported" : row.status === "unsupported" ? "unsupported" : "unknown";
    const kind = typeof row.kind === "string" && Object.prototype.hasOwnProperty.call(requirementLabels, row.kind)
      ? requirementLabels[row.kind] : "Requested fact";
    const prepared = typeof row.prepared_question === "string" && row.prepared_question !== text ? row.prepared_question : null;
    const dependent = row.reason === "dependent_requirement_unresolved";
    const interpretation = selectionRecord(row.interpretation);
    const owner = status === "supported" && interpretation.kind === "owner_relative_deputy"
      && typeof interpretation.resolved_owner === "string"
      && hasRecordedSource(interpretation.owner_evidence)
      && hasRecordedSource(interpretation.deputy_evidence)
      ? interpretation.resolved_owner : null;
    return { text, status, witnesses, kind, prepared, dependent, owner, unknownProcedure, completeness, scope, hash, copy, hashes, conditional, capture, refusal: procedure ? procedureRefusal(row.reason) : null };
  });
  return <section aria-label="Request coverage" className="gt-requirements">
    <h4>{rows.filter((row) => row.status === "supported").length} of {rows.length} requirements supported</h4>
    {captureWarning}
    <p className="gt-muted">A complete answer needs evidence for every requested fact. These are recorded checks, not a guarantee of general correctness.</p>
    <ol>
      {rows.map((row, index) => <li key={index}>
        <p className="gt-muted"><strong>{row.kind}</strong></p>
        <strong>{row.text || "Requirement text unavailable"}</strong>
        <p>{row.status === "supported" ? "Supported by recorded source evidence" : row.status === "unsupported" ? "No verified evidence for this requirement. The complete request was refused." : "Evidence state unknown"}</p>
        {row.unknownProcedure ? <><p><strong>Procedure completeness unknown</strong></p><p className="gt-muted">Recorded status: supported. This record does not establish the current complete-procedure contract, source extent and citation cover.</p></> : null}
        {row.copy && row.status === "supported" && row.completeness ? <><p><strong>Exact instruction coverage verified</strong></p><p>NLI-supported subject and applicability; exact_source_structure and exact_source_copy validate the recorded structure and literal instructions.</p><p>Recorded source-proof validation; this is not cryptographic server attestation.</p></> : null}
        {row.conditional && row.conditional.state !== "absent" ? <>
          {row.status === "supported" && row.conditional.state === "verified" ? sourceContextProfile(discovery.profile) ? <ContextReadingDetails exclusions={row.conditional.exclusions} /> : <>
            <p>Recorded conditional NLI exclusions: {row.conditional.exclusions.length}</p>
            <p>Conditional exclusions were checked from recorded source bodies and classifier logits. No NLI inference is rerun in this view.</p>
          </> : <p>{row.capture?.state === "missing" || row.capture?.state === "invalid"
            ? "Conditional evidence unverified: retained query capture is missing or malformed."
            : row.capture?.state === "mismatch" ? "Conditional evidence unverified: retained query capture does not match the displayed record."
              : `Conditional evidence ${row.conditional.state === "pending" ? "pending" : "unverified"}`}</p>}
          {row.conditional.state === "verified" && !sourceContextProfile(discovery.profile) ? <details><summary>Recorded conditional evidence</summary>
            <p>Recorded context and arithmetic checks do not authenticate historical storage.</p>
            {row.status !== "supported" ? <p>These recorded conditional entries are shown for inspection; their retained query capture is unverified.</p> : null}
            <ul>{row.conditional.exclusions.map((value, index) => {
              const exclusion = selectionRecord(value), identity = selectionRecord(exclusion.source_identity), scope = selectionRecord(exclusion.condition_scope), assessment = selectionRecord(scope.assessment);
              return <li key={index}><p>Document {String(identity.document_id)} · version {String(identity.document_version)}</p>
                <p>{String(scope.hypothesis)}</p><p>Excluded source class: {String(scope.excluded_class)}</p>
                <p>Recorded entailment margin: {String(assessment.entailment_margin)} · pair tokens: {String(assessment.pair_tokens)}</p>
                <p>Recorded NLI method: {String(scope.verification_method)} · label: {String(assessment.label)}</p>
                <p>Recorded NLI logits (contradiction, entailment, neutral): {Array.isArray(assessment.logits) ? assessment.logits.join(", ") : "unavailable"}</p>
                <p>Captured support model: {String(selectionRecord(selectionRecord(scope.model_settings).support).model)}</p>
                <p>Captured minimum entailment margin: {String(selectionRecord(selectionRecord(scope.model_settings).support).minimum_entailment_margin)} · support revision: {String(selectionRecord(selectionRecord(scope.model_settings).support).revision)}</p>
                <details><summary>Recorded full source premise</summary><pre>{String(selectionRecord(scope.pair).premise)}</pre></details>
              </li>;
            })}</ul>
          </details> : null}
        </> : null}
        {row.hashes ? <p className="gt-muted">Recorded output hash: {row.hashes.answer}</p> : null}
        {!row.copy && row.status === "supported" && row.completeness ? <p><strong>Full source extent verified · {"paragraphs" in row.completeness ? `${row.completeness.paragraphs} declared ${row.completeness.paragraphs === 1 ? "paragraph" : "paragraphs"} · ${row.completeness.parts} cited ${row.completeness.parts === 1 ? "passage" : "passages"}` : `${row.completeness.steps === null ? "narrative instructions" : row.completeness.steps + " steps"} · ${row.completeness.parts} cited passages`}</strong></p> : null}
        {row.hash ? <details><summary>Declared paragraph evidence</summary><p>Recorded source-body hash: {row.hash}</p><p>A matching digest checks this record&apos;s body and fingerprint. Source authority and model judgments remain separate.</p></details> : null}
        {row.refusal ? <p>{row.refusal}</p> : null}
        {row.scope.warning ? <p>{row.scope.warning}</p> : null}
        {row.status === "supported" && row.scope.disclosure ? <p>{row.scope.disclosure}</p> : null}
        {row.scope.attempt ? <details><summary>Recorded scope interpretation</summary><p>{row.scope.attempt}</p><p>Recorded interpretation only; it does not establish a supported activity fallback.</p></details> : null}
        {row.dependent ? <p>A preceding fact could not be established, so this dependent question remains unanswered.</p> : null}
        {row.owner ? <p>This paired request uses the verified owner ({row.owner}) and that role&apos;s deputy, with a separate recorded source for each relationship.</p> : null}
        {row.prepared ? <details><summary>Recorded request interpretation</summary><p>{row.prepared}</p></details> : null}
        {row.status === "supported" ? <details><summary>Supporting values</summary><ul>{Array.from(new Set(row.witnesses)).map((witness) => <li key={witness}>{witness}</li>)}</ul></details> : null}
      </li>)}
    </ol>
  </section>;
}

function LegacyAnswerSelectionEvidence({ value, question, answer, sources, retrievalTrace }: { value: unknown; question?: unknown; answer?: unknown; sources?: unknown; retrievalTrace?: unknown }) {
  const record = selectionRecord(value);
  const discovery = discoveryEvidence(record, retrievalTrace);
  const paragraphHash = useParagraphBodyHashes(record);
  const context = { question, answer, sources, retrievalTrace };
  const copyHash = useCopyHashes(record, context);
  const copyView = discovery.state === "recorded" && (discovery.profile.contract === "evidence-profile-v2" || sourceContextProfile(discovery.profile))
    && Array.isArray(record.requirements) && record.requirements.some((row) => selectionRecord(row).kind === "procedure");
  if (selectionRecord(record.presentation_verification).status === "invalid") return (
    <section className="gt-selection" aria-label="Answer selection evidence">
      <h3>Recorded procedure evidence withheld</h3>
      <p>Recorded procedure presentation integrity could not be verified. The saved answer and sources are withheld.</p>
    </section>
  );
  const field = (name: string) => {
    const value = record[name];
    return typeof value === "string" || typeof value === "number" ? String(value) : "unknown";
  };
  return (
    <section className="gt-selection" aria-label="Answer selection evidence">
      <h3>{copyView ? "Source-declared procedure copy" : discovery.state === "recorded" ? discovery.profile.proposal_profile === "qa_only_v1" ? "Local QA-only extraction" : "Composite source extraction" : discovery.state === "invalid" ? "Answer extraction metadata unknown" : selectionLabel(record.mode)}</h3>
      <DiscoveryDetails discovery={discovery} readSet={selectionRecord(record.role_scope_read_set)} />
      {Object.keys(record).length ? (
        <details>
          <summary>Model and selection details</summary>
          <dl className="gt-details">
          <dt>Decision</dt><dd>{field("decision")}</dd>
          <dt>Model</dt><dd>{field("model")}</dd>
          <dt>Revision</dt><dd>{field("revision")}</dd>
          <dt>Contract</dt><dd>{field("contract")}</dd>
          <dt>Null threshold</dt><dd>{field("threshold")}</dd>
          </dl>
        </details>
      ) : <p className="gt-muted">This historical response did not record answer selection metadata.</p>}
      <RequirementCoverage record={record} discovery={discovery} paragraphHash={paragraphHash} copyHash={copyHash} context={context} />
      {Object.keys(selectionRecord(record.evidence_support)).length ? <details>
        <summary>Local support classifier</summary>
        <dl className="gt-details">
          <dt>Model</dt><dd>{String(selectionRecord(record.evidence_support).model || "unknown")}</dd>
          <dt>Revision</dt><dd>{String(selectionRecord(record.evidence_support).revision || "unknown")}</dd>
          <dt>Entailment margin</dt><dd>{String(selectionRecord(record.evidence_support).minimum_entailment_margin ?? "unknown")}</dd>
        </dl>
        <p className="gt-muted">Local non-generative classification checks a source clause against the requested fact. It cannot supply missing facts.</p>
      </details> : null}
      <p className="gt-muted">Selection scores are raw support signals, not calibrated probabilities. Full recorded diagnostics are in provenance.</p>
    </section>
  );
}


export default function AnswerSelectionEvidence(props: { value: unknown; question?: unknown; answer?: unknown; sources?: unknown; retrievalTrace?: unknown }) {
  if (hasStagedEvidence(props.value, props.retrievalTrace)) return <StagedAnswerEvidence {...props} />;
  return hasLinguisticEvidence(props.value,props.retrievalTrace) ? <LinguisticAnswerEvidence {...props} /> : <LegacyAnswerSelectionEvidence {...props} />;
}
