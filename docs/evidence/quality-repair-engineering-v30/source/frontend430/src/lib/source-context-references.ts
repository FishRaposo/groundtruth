/** Typed reference projections of the Python-generated v2 authority; no classifier or physical identity claim. */
import grammar from "@/lib/source-context-v2-grammar.generated.json";

type R = Record<string, unknown>;
type Span = { start: number; end: number };
type Literal = { literal: string; source_range: Span };
type Clause = Literal & { kind: string; bindings: Record<string, Literal> };
const spec = grammar.reference_structure;
const count = (text: string) => Array.from(text).length;
const format = (text: string, context: Record<string, string>) => text.replace(/\{([a-z_]+)\}/g, (_all, name) => {
  if (typeof context[name] !== "string") throw new Error("Unknown reference projection slot");
  return context[name];
});
function literalSlot(clause: Clause, literal: string): Literal {
  const offset = clause.literal.indexOf(literal);
  if (offset < 0 || clause.literal.indexOf(literal, offset + 1) >= 0) throw new Error("Missing or competing reference occurrence");
  const start = clause.source_range.start + count(clause.literal.slice(0, offset));
  return { literal, source_range: { start, end: start + count(literal) } };
}
function slot(clause: Clause, selector: string, context: Record<string, string>): Literal {
  if (selector === "whole_clause") return { literal: clause.literal, source_range: { ...clause.source_range } };
  if (selector.startsWith("binding:")) {
    const binding = clause.bindings[selector.slice("binding:".length)];
    if (!binding) throw new Error("Missing exact binding slot");
    return { ...binding, source_range: { ...binding.source_range } };
  }
  return literalSlot(clause, format(selector, context));
}

/** Internal projection seam: caller must reconstruct the complete reading from the literal source first. */
export function contextReferencePlan(reading: R): R {
  if (reading.contract !== grammar.contract || reading.grammar !== grammar.grammar) throw new Error("Unknown typed reference version");
  const context = reading.adopted_context as Record<string, string>;
  const clauses = Object.fromEntries((reading.clause_inventory as Clause[]).map(clause => [clause.kind, clause]));
  const properties = spec.role_properties as Record<string, R>;
  const entities = spec.role_specs.map(([id, type, clause, selector]) => ({
    id, type, declaration_clause: clause, ...slot(clauses[clause], selector, context), ...properties[id],
  }));
  const byId = Object.fromEntries(entities.map(entity => [entity.id, entity]));
  const bodyRange = { start: 0, end: count(reading.source_body as string) };
  const reference_occurrences = spec.reference_specs.map(([id, clauseName, template, target]) => ({
    id, source_clause: clauseName, ...literalSlot(clauses[clauseName], format(template, context)), target_id: target, cardinality: 1,
    source_clause_range: { ...clauses[clauseName].source_range }, compatible_region: { ...bodyRange },
    ...(target === "selected_complete_procedure" ? { target_type: "complete_ordinary_procedure_role", external_binding: target }
      : { target_type: byId[target].type, target_range: { ...byId[target].source_range } }),
  }));
  const guard = { id: "guard", connective: "and", source_range: { ...byId.guard.source_range },
    members: spec.guard_members.map(row => {
      const [kind, template, roles] = row as [string, string, string[]];
      return { kind, ...literalSlot(clauses.classification_prerequisite, format(template, context)), argument_roles: [...roles] };
    }), meaning: spec.guard_meaning };
  const generic = { ...spec.generic_predicate_constants,
    variable_literal: byId.generic_cards.literal, variable_range: { ...byId.generic_cards.source_range },
    source_range: { ...clauses.negative_membership.source_range }, literal: clauses.negative_membership.literal };
  const domains = spec.domain_specs.map(([clauseName, binding, target, adopted]) => ({ source_clause: clauseName,
    raw: slot(clauses[clauseName], `binding:${binding}`, context), adopted_domain: context[adopted], target_role: target }));
  return { contract: spec.contract, policy: "scoped_note_context_v2", context_contract: reading.contract, grammar: reading.grammar,
    source_body_hash: reading.source_body_hash, source_range: bodyRange, assertion_kind: spec.assertion_kind, entities,
    binding_slots: spec.binding_roles.map(([binding, target_role]) => ({ binding, target_role, ...slot(clauses.scoped_directive, `binding:${binding}`, context) })),
    required_reference_count: spec.reference_specs.length, reference_occurrences, guard, generic_card_predicate: generic, domains,
    complete_body_edges: reading.reference_edges };
}

export function contextReferenceObligation(reading: R): R {
  return { name: spec.name, contract: spec.contract, verification_method: spec.method,
    reference_plan: contextReferencePlan(reading), result: "bound", reason: spec.reason };
}

export function contextObligationPlan(reading: R, checks: R[]): R {
  return { contract: spec.plan_contract, source_context_policy: "scoped_note_context_v2", source_context_contract: reading.contract,
    grammar: reading.grammar, mandatory_obligation_count: spec.mandatory_obligation_count,
    mandatory_nli_count: spec.mandatory_nli_count, mandatory_exact_reference_count: spec.mandatory_exact_reference_count,
    obligations: [...checks.map(check => ({ name: check.name, verification_method: "nli_entailment" })),
      { name: spec.name, verification_method: spec.method, method_contract: spec.contract }] };
}
