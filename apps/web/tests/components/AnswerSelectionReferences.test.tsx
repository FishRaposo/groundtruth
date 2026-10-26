import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import fixture from "../fixtures/context-reference-v2-initial-v345.json";
import legacyFixture from "../fixtures/context-contract-final-v319.json";

type R = Record<string, any>;
const fresh = (): R => JSON.parse(JSON.stringify(fixture.response));
const selection = (r: R): R => r.provenance.answer_selection;
function visit(value: unknown, fn: (v: R) => void) {
  if (!value || typeof value !== "object") return;
  const record = value as R; fn(record);
  for (const item of Object.values(record)) visit(item, fn);
}
const scopes = (r: R, fn: (v: R) => void) => visit(r, v => { if (v.contract === "procedure-condition-scope-v3") fn(v); });
function show(r: R) { render(<AnswerSelectionEvidence value={selection(r)} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={r.retrieval_trace} />); }
async function settled() { await waitFor(() => expect(screen.queryByText("Recorded output hash: pending")).not.toBeInTheDocument()); }
function withheld() {
  expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Recorded context-reference structure" })).not.toBeInTheDocument();
}
beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("versioned typed context-reference evidence", () => {
  // Defect: the new producer is rejected, or exact reference structure is falsely presented as classifier support.
  it("presents the frozen producer with distinct mandatory reference and NLI methods", async () => {
    show(fresh());
    await waitFor(() => expect(screen.getByText("Exact instruction coverage verified")).toBeInTheDocument());
    const reference = screen.getByRole("region", { name: "Recorded context-reference structure" });
    expect(within(reference).getAllByText(/exact_context_reference_structure/).length).toBeGreaterThan(0);
    expect(within(reference).getAllByText(/Policy-authorized discourse roles/).length).toBeGreaterThan(0);
    expect(within(reference).queryByText(/Recorded NLI logits|Recorded NLI method|pair tokens|entailment margin/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/card and cover references/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/opposing card dispositions remain unresolved/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recorded contextual NLI checks").length).toBeGreaterThan(0);
  });

  const mutation: [string, (s: R) => void][] = [
    ["missing obligation plan", s => { delete s.obligation_plan; }],
    ["missing reference proof", s => { delete s.reference_obligations; }],
    ["duplicate reference proof", s => { s.reference_obligations.push(s.reference_obligations[0]); }],
    ["unknown obligation plan", s => { s.obligation_plan.contract = "future"; }],
    ["boolean obligation count", s => { s.obligation_plan.mandatory_exact_reference_count = true; }],
    ["weakened obligation count", s => { s.obligation_plan.mandatory_obligation_count--; }],
    ["pruned obligation", s => { s.obligation_plan.obligations.pop(); }],
    ["wrong selected method", s => { s.obligation_plan.obligations.at(-1).verification_method = "nli_entailment"; }],
    ["fake exact NLI label", s => { s.reference_obligations[0].label = "entailment"; }],
    ["fake exact logits", s => { s.reference_obligations[0].logits = [-5, 5, -5]; }],
    ["fake exact assessment", s => { s.reference_obligations[0].assessment = { label: "entailment", pair_tokens: 20 }; }],
    ["wrong exact method", s => { s.reference_obligations[0].verification_method = "nli_entailment"; }],
    ["unbound exact result", s => { s.reference_obligations[0].result = "unbound"; }],
    ["unknown exact contract", s => { s.reference_obligations[0].contract = "future"; }],
    ["wrong exact reason", s => { s.reference_obligations[0].reason = "NLI failed fallback"; }],
    ["pruned entity", s => { s.reference_obligations[0].reference_plan.entities.pop(); }],
    ["duplicate entity", s => { s.reference_obligations[0].reference_plan.entities.push(s.reference_obligations[0].reference_plan.entities[0]); }],
    ["card event collapse", s => { s.reference_obligations[0].reference_plan.entities.find((r: R) => r.id === "card").type = "audit_event_or_state_role"; }],
    ["wrong cover owner", s => { s.reference_obligations[0].reference_plan.entities.find((r: R) => r.id === "cover").cover_of = "event"; }],
    ["physical identity claim", s => { s.reference_obligations[0].reference_plan.assertion_kind = "physical_card_identity"; }],
    ["wrong binding role", s => { s.reference_obligations[0].reference_plan.binding_slots[2].target_role = "event"; }],
    ["wrong binding range", s => { s.reference_obligations[0].reference_plan.binding_slots[2].source_range.start++; }],
    ["missing binding", s => { s.reference_obligations[0].reference_plan.binding_slots.pop(); }],
    ["pruned occurrence", s => { s.reference_obligations[0].reference_plan.reference_occurrences.pop(); }],
    ["duplicate occurrence", s => { s.reference_obligations[0].reference_plan.reference_occurrences.push(s.reference_obligations[0].reference_plan.reference_occurrences[0]); }],
    ["wrong typed target", s => { s.reference_obligations[0].reference_plan.reference_occurrences.find((r: R) => r.id === "classification_card").target_id = "event"; }],
    ["wrong target type", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].target_type = "operator_role"; }],
    ["boolean cardinality", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].cardinality = true; }],
    ["competing cardinality", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].cardinality = 2; }],
    ["wrong source occurrence", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].source_range.end++; }],
    ["wrong target range", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].target_range.end++; }],
    ["weakened compatible region", s => { s.reference_obligations[0].reference_plan.reference_occurrences[0].compatible_region.start++; }],
    ["wrong external binding", s => { s.reference_obligations[0].reference_plan.reference_occurrences.find((r: R) => r.external_binding).external_binding = "audit_note"; }],
    ["guard disjunction", s => { s.reference_obligations[0].reference_plan.guard.connective = "or"; }],
    ["pruned guard", s => { s.reference_obligations[0].reference_plan.guard.members.pop(); }],
    ["guard reordered", s => { s.reference_obligations[0].reference_plan.guard.members.reverse(); }],
    ["guard wrong arguments", s => { s.reference_obligations[0].reference_plan.guard.members[0].argument_roles = ["event"]; }],
    ["execution claim", s => { s.reference_obligations[0].reference_plan.guard.meaning = "successful execution"; }],
    ["generic singular card", s => { s.reference_obligations[0].reference_plan.generic_card_predicate.variable_role = "card"; }],
    ["weakened negative predicate", s => { s.reference_obligations[0].reference_plan.generic_card_predicate.relation = "mark_implies_condition"; }],
    ["raw domain strengthening", s => { s.reference_obligations[0].reference_plan.domains[0].raw.literal = "only card dispositions"; }],
    ["wrong adopted domain", s => { s.reference_obligations[0].reference_plan.domains[0].adopted_domain = "all ordinary actions"; }],
    ["pruned whole body edge", s => { s.reference_obligations[0].reference_plan.complete_body_edges.pop(); }],
    ["wrong full body hash", s => { s.reference_obligations[0].reference_plan.source_body_hash = "0".repeat(64); }],
    ["missing remaining NLI", s => { s.semantic_checks.pop(); }],
    ["remaining NLI neutral", s => { s.semantic_checks[0].assessment.label = "neutral"; }],
    ["remaining NLI arithmetic", s => { s.semantic_checks[0].assessment.entailment_margin++; }],
    ["wrong scope method", s => { s.verification_method = "contextual_source_reading_and_nli"; }],
    ["unknown reading grammar", s => { s.context_reading.grammar = "future"; }],
    ["old disclosure", s => { s.context_reading.disclosure = "Context reading: old disclosure"; }],
  ];
  // All duplicates including raw capture are mutated: reconstruction must exceed matching producer copies.
  it.each(mutation)("rejects coherent %s", async (_name, change) => {
    const r = fresh(); scopes(r, change); show(r); await settled(); withheld();
  });

  const actual: [string, (r: R) => void][] = [
    ["missing capture", r => { delete r.retrieval_trace; }],
    ["locally positive changed NLI capture", r => { scopes(selection(r), s => { s.semantic_checks[0].assessment.logits = [-4, 5, -5]; s.semantic_checks[0].assessment.entailment_margin = 9; }); }],
    ["wrong question", r => { r.question += " Include all audit actions."; }],
    ["wrong source", r => { r.sources[0].document_version++; }],
    ["wrong quoted source", r => { r.sources[0].quoted_text += "Extra"; }],
    ["missing citation span", r => { r.sources[0].answer_spans = []; }],
    ["missing actual disclosure with rehash", r => {
      r.answer = r.answer.split("\n\nContext reading:")[0];
      visit(r, p => { if (p.contract === "procedure-output-cover-v4") p.answer_sha256 = createHash("sha256").update(r.answer).digest("hex"); });
    }],
    ["coherent erased profile", r => { visit(r, v => { if (v.evidence_profile?.contract === "evidence-profile-v4") v.evidence_profile = {}; }); }],
    ["coherent legacy profile downgrade", r => { visit(r, v => { if (v.contract === "evidence-profile-v4") { v.contract = "evidence-profile-v3"; v.source_context_policy = "scoped_note_context_v1"; v.source_context_contract = "source-note-context-v1"; } }); }],
  ];
  it.each(actual)("withholds %s", async (_name, change) => { const r = fresh(); change(r); show(r); await settled(); withheld(); });

  it("does not describe an enabled but unused v2 policy as adopted reference reading", () => {
    const r = fresh(), s = selection(r);
    s.requirements = [{ id: "r1", kind: "owner", original_text: "Who owns the activity?", status: "unsupported", witnesses: [] }];
    for (const field of ["proposals", "selected_proposal_ids", "qa_observations", "pattern_observations", "conflicts"]) s[field] = [];
    delete r.retrieval_trace; show(r);
    expect(screen.getByRole("heading", { name: "Composite source extraction" })).toBeInTheDocument();
    expect(screen.queryByText("Context reading", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Recorded context-reference structure" })).not.toBeInTheDocument();
  });

  it("rejects coherent reference pruning even when the recorded occurrence count is also reduced", async () => {
    const r = fresh(); scopes(r, s => { const plan = s.reference_obligations[0].reference_plan; plan.reference_occurrences.pop(); plan.required_reference_count--; });
    show(r); await settled(); withheld();
  });

  it.each(["neutral", "missing", "typed replacement"])("preserves v1's mandatory identity NLI: %s", async mode => {
    const r: R = JSON.parse(JSON.stringify(legacyFixture.response));
    visit(r, s => {
      if (s.contract !== "procedure-condition-scope-v2") return;
      if (mode === "neutral") s.semantic_checks.find((c: R) => c.name === "card_reference_identity").assessment.label = "neutral";
      else s.semantic_checks = s.semantic_checks.filter((c: R) => c.name !== "card_reference_identity");
      if (mode === "typed replacement") {
        const example = selection(fresh()).conflicts[0].source_extent_checks[0].condition_scope;
        s.reference_obligations = example.reference_obligations; s.obligation_plan = example.obligation_plan;
      }
    });
    show(r); await settled(); withheld();
  });

  it("rejects full v2-to-v1 marker erasure with matching old disclosure but only 22 NLI checks", async () => {
    const r = fresh();
    const disclosure = (condition: string) => `Context reading: the note's bare disposition and action references are read within its stated ${condition} and marked audit card context. The opposing card dispositions remain unresolved.`;
    r.answer = r.answer.replace(/Context reading: the note's card and cover references and its bare disposition and action references[^\n]+/g,
      (text: string) => text.replace("card and cover references and its bare", "bare"));
    scopes(r, s => {
      delete s.obligation_plan; delete s.reference_obligations; s.contract = "procedure-condition-scope-v2";
      s.verification_method = "contextual_source_reading_and_nli";
      s.context_reading.contract = "source-note-context-v1"; s.context_reading.grammar = "scoped-note-grammar-v1";
      s.context_reading.disclosure = disclosure(s.condition);
    });
    visit(r, v => {
      if (v.contract === "evidence-profile-v4") { v.contract = "evidence-profile-v3"; v.source_context_policy = "scoped_note_context_v1"; v.source_context_contract = "source-note-context-v1"; }
      if (v.contract === "procedure-condition-exclusion-inventory-v3") v.contract = "procedure-condition-exclusion-inventory-v2";
      if (v.contract === "procedure-output-cover-v4") { v.contract = "procedure-output-cover-v3"; v.answer_sha256 = createHash("sha256").update(r.answer).digest("hex"); }
    });
    show(r); await settled(); withheld();
  });

  it("withholds all contextual literals when recorded presentation integrity is invalid", () => {
    const r = fresh(); selection(r).presentation_verification = { status: "invalid" }; show(r); withheld();
    expect(screen.getByText("Recorded procedure evidence withheld")).toBeInTheDocument();
    expect(screen.queryByText(/Context reading: the note's card and cover/)).not.toBeInTheDocument();
    expect(screen.queryByText("Recorded literal clauses and references")).not.toBeInTheDocument();
  });
});
