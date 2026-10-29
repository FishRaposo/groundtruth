/** Recorded policy replay from the Python-generated descriptor. No inference or storage attestation. */
import legacyGrammar from "@/lib/source-context-grammar.generated.json";
import referenceGrammar from "@/lib/source-context-v2-grammar.generated.json";
import { contextReferencePlan } from "@/lib/source-context-references";

type R = Record<string, unknown>;
type Span = { start: number; end: number };
type Binding = { literal: string; source_range: Span; members?: string[] };
type Clause = { kind: string; literal: string; source_range: Span; bindings: Record<string, Binding>; references: Record<string, string> };
const rec = (v: unknown): R => v !== null && typeof v === "object" && !Array.isArray(v) ? v as R : {};
const count = (v: string) => Array.from(v).length;
const escape = (v: string) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const space = "[\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
// Python \w is Unicode alphanumeric plus underscore, not JavaScript's ASCII \w.
const word = "\\p{L}\\p{N}_";
function expression(value: string, flags = "du") {
  return new RegExp(value.replace(/\(\?P</g, "(?<").replace(/\\w/g, word).replace(/\\s/g, space)
    .replace(/\\b/g, `(?:(?<![${word}])(?=[${word}])|(?<=[${word}])(?![${word}]))`), flags);
}
const full = (pattern: string, value: string) => expression(`^(?:${pattern})`).exec(value)?.[0] === value;
// This fixed ASCII predicate uses Python re.I, which merges I/i/İ/ı; JS iu omits
// the latter two. Its predicate-only view preserves Unicode word boundaries.
// The original nominal/body still drives every case-sensitive production and range.
const nominal = (value: string, grammar = legacyGrammar) => full(grammar.nominal, value)
  && !expression(grammar.nominal_reject, "iu").test(value.replace(/[İı]/g, "i"));
function expand(pattern: string, slots: Record<string, string>) {
  return pattern.replace(/CONTEXT_[A-Z]+/g, slot => escape(slots[slot]));
}
function template(value: string, slots: Record<string, string>) {
  return value.replace(/\{([a-z_]+)\}/g, (_all, name) => {
    if (!Object.prototype.hasOwnProperty.call(slots, name)) throw new Error("Unknown grammar projection slot");
    return slots[name];
  });
}

/** Consume every codepoint and rebuild all literal clauses, bindings, gaps and reference edges. */
export function replayContextReading(body: string, operation: string, state: string, contentHash: string, policy = "scoped_note_context_v1"): R | null {
  try {
    const grammar = policy === "scoped_note_context_v1" ? legacyGrammar : policy === "scoped_note_context_v2" ? referenceGrammar : null;
    if (!grammar || !nominal(operation, grammar) || !nominal(state, grammar) || count(body) > 128 * 1024) return null;
    const slots: Record<string, string> = { CONTEXT_OPERATION: operation, CONTEXT_STATE: state };
    const title = expression(`^(?:${expand(grammar.title, slots)})`).exec(body);
    if (!title?.groups?.action) return null;
    slots.CONTEXT_ACTION = title.groups.action; slots.CONTEXT_TITLE = title[0];
    let cursor = title[0].length;
    const ws = expression(`^(?:${grammar.whitespace})`).exec(body.slice(cursor));
    if (!ws) return null;
    cursor += ws[0].length;
    const header = expression(`^(?:${expand(grammar.directive, slots)})`).exec(body.slice(cursor));
    if (!header?.groups || !full(grammar.location, header.groups.destination) || !nominal(header.groups.mark, grammar)) return null;
    slots.CONTEXT_MARK = header.groups.mark;
    const clauses: Clause[] = [], gaps: { literal: string; source_range: Span }[] = [];
    cursor = 0;
    for (const production of grammar.clauses) {
      const gap = expression(`^(?:${grammar.whitespace})`).exec(body.slice(cursor));
      if (gap) {
        gaps.push({ literal: gap[0], source_range: { start: count(body.slice(0, cursor)), end: count(body.slice(0, cursor + gap[0].length)) } });
        cursor += gap[0].length;
      }
      const match = expression(`^(?:${expand(production.pattern, slots)})`).exec(body.slice(cursor));
      if (!match) return null;
      const bindings: Record<string, Binding> = {};
      for (const [key, literal] of Object.entries(match.groups ?? {})) {
        const indices = match.indices?.groups?.[key];
        if (!indices) return null;
        bindings[key] = { literal, source_range: { start: count(body.slice(0, cursor + indices[0])), end: count(body.slice(0, cursor + indices[1])) } };
        if (key === "attributes" || key === "excluded_objects") {
          const members = literal.split(/, (?:or )?| or /);
          if (members.length < 2 || members.some(member => !full(grammar.list_categories[key], member))) return null;
          bindings[key].members = members;
        }
      }
      clauses.push({ kind: production.kind, literal: match[0], source_range: { start: count(body.slice(0, cursor)), end: count(body.slice(0, cursor + match[0].length)) }, bindings, references: production.references as Record<string, string> });
      cursor += match[0].length;
    }
    if (cursor < body.length) {
      if (!full(grammar.whitespace, body.slice(cursor))) return null;
      gaps.push({ literal: body.slice(cursor), source_range: { start: count(body.slice(0, cursor)), end: count(body) } });
    }
    const byKind = Object.fromEntries(clauses.map(clause => [clause.kind, clause]));
    const edges = clauses.flatMap(clause => Object.entries(clause.references).map(([literal, target]) => {
      const start = clause.source_range.start + count(clause.literal.slice(0, clause.literal.indexOf(literal)));
      return { source_literal: literal, source_range: { start, end: start + count(literal) }, target_kind: target,
        ...(byKind[target] ? { target_range: byKind[target].source_range } : { external_binding: "selected_complete_procedure" }) };
    }));
    const inputs: Record<string, string> = { operation, state, ...header.groups };
    const adopted = Object.fromEntries([...grammar.context_inputs, ...grammar.context_directive_bindings].map(key => [key, inputs[key]]));
    const reading = { contract: grammar.contract, grammar: grammar.grammar, source_body: body, source_body_hash: contentHash,
      adopted_context: { ...adopted, ...grammar.context_constants }, clause_inventory: clauses, gaps, reference_edges: edges,
      disclosure: template(grammar.disclosure_template, inputs) };
    if (policy === "scoped_note_context_v2") contextReferencePlan(reading);
    return reading;
  } catch { return null; }
}

/** Check templates are projected from the same generated producer descriptor, never inferred here. */
export function contextSemanticChecks(reading: R): R[] {
  const grammar = reading.contract === legacyGrammar.contract && reading.grammar === legacyGrammar.grammar ? legacyGrammar
    : reading.contract === referenceGrammar.contract && reading.grammar === referenceGrammar.grammar ? referenceGrammar : null;
  if (!grammar) throw new Error("Unknown contextual semantic version");
  const clauses = reading.clause_inventory as Clause[], byKind = Object.fromEntries(clauses.map(clause => [clause.kind, clause]));
  const slots = { ...rec(reading.adopted_context), action_content: byKind.scoped_directive.literal.split("must ")[1] } as Record<string, string>;
  return [
    ...clauses.filter(clause => clause.kind !== "title").map(clause => ({ name: clause.kind, premise_range: clause.source_range, hypothesis: clause.literal })),
    ...grammar.semantic_templates.map(([name, first, last, hypothesis]) => ({ name,
      premise_range: { start: byKind[first].source_range.start, end: byKind[last].source_range.end }, hypothesis: template(hypothesis, slots) })),
  ];
}

export function sourceContextProfile(profile: R) {
  return sourceContextVersion(profile) !== null;
}

export function sourceContextVersion(profile: R) {
  if (profile.contract === "evidence-profile-v3" && profile.source_context_policy === "scoped_note_context_v1" && profile.source_context_contract === legacyGrammar.contract) {
    return { policy: "scoped_note_context_v1", scope: "procedure-condition-scope-v2", inventory: "procedure-condition-exclusion-inventory-v2", output: "procedure-output-cover-v3", method: "contextual_source_reading_and_nli" };
  }
  if (profile.contract === "evidence-profile-v4" && profile.source_context_policy === "scoped_note_context_v2" && profile.source_context_contract === referenceGrammar.contract) {
    return { policy: "scoped_note_context_v2", scope: "procedure-condition-scope-v3", inventory: "procedure-condition-exclusion-inventory-v3", output: "procedure-output-cover-v4", method: "contextual_source_reading_nli_and_exact_reference" };
  }
  return null;
}

/** Output disclosure is independently replayed from validated scopes, sorted like Python strings. */
export function contextDisclosures(exclusions: R[]) {
  const compare = (a: string, b: string) => {
    const left = Array.from(a), right = Array.from(b);
    for (let i = 0; i < Math.min(left.length, right.length); i++) {
      const diff = left[i].codePointAt(0)! - right[i].codePointAt(0)!; if (diff) return diff;
    }
    return left.length - right.length;
  };
  return Array.from(new Set(exclusions.map(exclusion => rec(rec(exclusion.condition_scope).context_reading).disclosure)
    .filter((v): v is string => typeof v === "string"))).sort(compare);
}
