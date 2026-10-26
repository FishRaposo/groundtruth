import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import fixture from "../fixtures/context-contract-v319.json";
import finalFixture from "../fixtures/context-contract-final-v319.json";

type R = Record<string, any>; // DTO mutation tests deliberately include malformed values.
const fresh = (): R => JSON.parse(JSON.stringify(fixture.response));
const selection = (r: R): R => r.provenance.answer_selection;
const proof = (r: R): R => selection(r).requirements[0].procedure_completeness;
const scope = (r: R): R => selection(r).conflicts[0].source_extent_checks[0].condition_scope;
function show(r: R) { return render(<AnswerSelectionEvidence value={selection(r)} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={r.retrieval_trace} />); }
async function settled() { await waitFor(() => expect(screen.queryByText("Recorded output hash: pending")).not.toBeInTheDocument()); }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
beforeEach(() => vi.stubGlobal("crypto", webcrypto));

describe("recorded scoped-note context", () => {
  // Defect: valid producer profile-v3 is rejected, hiding its exact procedure and context disclosure.
  it("presents the actual producer copy and distinguishes contextual interpretation from recorded NLI", async () => {
    show(fresh());
    await waitFor(() => expect(screen.getByText("Exact instruction coverage verified")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Source-declared procedure copy" })).toBeInTheDocument();
    expect(screen.getByText("NLI-supported subject and applicability; exact_source_structure and exact_source_copy validate the recorded structure and literal instructions.")).toBeInTheDocument();
    expect(screen.getByText("Context reading", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText(/opposing card dispositions remain unresolved/).length).toBeGreaterThan(0);
    expect(screen.getByText(/policy interpretation, separate from recorded NLI support/)).toBeInTheDocument();
    expect(screen.getAllByText(/Ordinary procedure and marked audit card/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Recorded literal clauses and references/).length).toBeGreaterThan(0);
  });

  it("also presents the final backend producer without replacing the frozen RED input", async () => {
    show(JSON.parse(JSON.stringify(finalFixture.response)));
    await waitFor(() => expect(screen.getByText("Exact instruction coverage verified")).toBeInTheDocument());
    expect(screen.getByText("Context reading", { exact: true })).toBeInTheDocument();
  });

  it("keeps factual extraction separate from an enabled but unused context policy", () => {
    const r = fresh(), s = selection(r);
    s.requirements = [{ id: "r1", kind: "owner", original_text: "Who owns the activity?", status: "unsupported", witnesses: [] }];
    for (const field of ["proposals", "selected_proposal_ids", "qa_observations", "pattern_observations", "conflicts"]) s[field] = [];
    delete r.retrieval_trace;
    show(r);
    expect(screen.getByRole("heading", { name: "Composite source extraction" })).toBeInTheDocument();
    expect(screen.queryByText("Context reading", { exact: true })).not.toBeInTheDocument();
  });

  it("rejects locally positive replacement logits that differ from the retained capture", async () => {
    const r = fresh();
    function visit(value: unknown) {
      if (!value || typeof value !== "object") return;
      const v = value as R;
      if (v.contract === "procedure-condition-scope-v2") {
        v.semantic_checks[0].assessment.logits = [-4, 5, -5];
        v.semantic_checks[0].assessment.entailment_margin = 9;
      }
      for (const item of Object.values(v)) visit(item);
    }
    visit(selection(r)); show(r); await settled();
    expect(screen.getByText("Recorded requirement evidence unverified: retained query capture does not match the displayed record.")).toBeInTheDocument();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });

  const mutations: [string, (r: R) => void][] = [
    ["missing policy", r => { delete selection(r).evidence_profile.source_context_policy; }],
    ["unknown policy", r => { selection(r).evidence_profile.source_context_policy = "future"; }],
    ["wrong context contract", r => { selection(r).evidence_profile.source_context_contract = "future"; }],
    ["erased profile", r => { delete selection(r).evidence_profile; }],
    ["wrong inventory contract", r => { proof(r).condition_exclusion_inventory.contract = "procedure-condition-exclusion-inventory-v1"; }],
    ["wrong output contract", r => { proof(r).output_certificate.contract = "procedure-output-cover-v2"; }],
    ["wrong scope contract", r => { scope(r).contract = "procedure-condition-scope-v1"; }],
    ["altered body", r => { scope(r).context_reading.source_body += " All runs must discard it."; }],
    ["altered body hash", r => { scope(r).context_reading.source_body_hash = "a".repeat(64); }],
    ["unknown grammar", r => { scope(r).context_reading.grammar = "future"; }],
    ["altered adoption", r => { scope(r).context_reading.adopted_context.object = "all records"; }],
    ["altered clause", r => { scope(r).context_reading.clause_inventory[1].literal += " now"; }],
    ["altered clause range", r => { scope(r).context_reading.clause_inventory[1].source_range.start++; }],
    ["missing clause", r => { scope(r).context_reading.clause_inventory.splice(4, 1); }],
    ["altered gap", r => { scope(r).context_reading.gaps[0].literal = " "; }],
    ["missing reference", r => { scope(r).context_reading.reference_edges.pop(); }],
    ["altered reference", r => { scope(r).context_reading.reference_edges[0].target_kind = "title"; }],
    ["altered reference range", r => { scope(r).context_reading.reference_edges[0].source_range.end++; }],
    ["missing semantic check", r => { scope(r).semantic_checks.pop(); }],
    ["altered check premise", r => { scope(r).semantic_checks[0].pair.premise += " now"; }],
    ["altered check hypothesis", r => { scope(r).semantic_checks[0].hypothesis = "Every action applies."; }],
    ["altered check margin", r => { scope(r).semantic_checks[0].assessment.entailment_margin++; }],
    ["unsupported check logits", r => { scope(r).semantic_checks[0].assessment.logits = [5, -5, 0]; }],
    ["missing capture", r => { delete r.retrieval_trace.provenance; }],
    ["stale capture", r => { r.retrieval_trace.provenance.answer_selection.evidence_profile.source_context_policy = "explicit_target_v1"; }],
    ["missing disclosure", r => { r.answer = r.answer.split("\n\nContext reading:")[0]; }],
    ["edited disclosure", r => { r.answer = r.answer.replace("opposing card dispositions remain unresolved", "opposing card dispositions are resolved"); }],
    ["wrong question", r => { r.question += " Include all audit actions."; }],
    ["wrong answer", r => { r.answer = r.answer.replace("one token", "two tokens"); }],
    ["wrong source", r => { r.sources[0].document_version++; }],
    ["coherent pruning", r => {
      for (const s of [selection(r), r.retrieval_trace.provenance.answer_selection]) {
        s.conflicts[0].source_extent_checks.pop();
        const p = s.requirements[0].procedure_completeness;
        p.condition_exclusion_inventory.exclusions.pop();
        p.output_certificate.condition_exclusion_inventory = p.condition_exclusion_inventory;
      }
    }],
  ];
  // Defect: altered context/capture/output can retain a supported completeness label.
  it.each(mutations)("fails closed for %s", async (_name, mutate) => {
    const r = fresh(); mutate(r); show(r); await settled();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  });

  // Defect: accepting only agreement among duplicate records allows a coherent falsified clause/reference/check.
  const coherent: [string, (scope: R) => void][] = [
    ["adopted context", s => { s.context_reading.adopted_context.resolved_choice_domain = "ordinary run actions"; }],
    ["clause inventory", s => { s.context_reading.clause_inventory.pop(); }],
    ["literal range", s => { s.context_reading.clause_inventory[1].bindings.condition.source_range.start++; }],
    ["reference target", s => { s.context_reading.reference_edges[0].target_kind = "title"; }],
    ["reference range", s => { s.context_reading.reference_edges[0].target_range.end++; }],
    ["external binding", s => { s.context_reading.reference_edges.find((e: R) => e.external_binding).external_binding = "audit_note"; }],
    ["gap inventory", s => { s.context_reading.gaps.pop(); }],
    ["disclosure", s => { s.context_reading.disclosure = "All audit decisions are resolved."; }],
    ["semantic check", s => { s.semantic_checks.pop(); }],
    ["semantic premise", s => { s.semantic_checks[0].pair.premise += " now"; }],
    ["semantic hypothesis", s => { s.semantic_checks[0].hypothesis = "All records must be discarded."; s.semantic_checks[0].pair.hypothesis = s.semantic_checks[0].hypothesis; }],
    ["semantic reference", s => { s.semantic_checks[0].pair.reference_id = "other"; }],
    ["semantic arithmetic", s => { s.semantic_checks[0].assessment.entailment_margin++; }],
    ["semantic method", s => { s.semantic_checks[0].verification_method = "exact_source_copy"; }],
    ["full-body hash", s => { s.context_reading.source_body_hash = "0".repeat(64); }],
  ];
  it.each(coherent)("independently rejects coherently altered %s", async (_name, mutate) => {
    const r = fresh();
    function visit(value: unknown) {
      if (!value || typeof value !== "object") return;
      const v = value as R;
      if (v.contract === "procedure-condition-scope-v2") mutate(v);
      for (const item of Object.values(v)) visit(item);
    }
    visit(r); show(r); await settled();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  });

  // Defect: a recomputed output digest must not certify a different renderer result or missing interpretation disclosure.
  it.each(["disclosure", "instruction", "missing disclosure"])("replays actual output even with a matching hash: %s", async kind => {
    const r = fresh();
    r.answer = kind === "disclosure" ? r.answer.replace("remain unresolved", "are now resolved")
      : kind === "instruction" ? r.answer.replace("one token", "two tokens") : r.answer.split("\n\nContext reading:")[0];
    for (const s of [selection(r), r.retrieval_trace.provenance.answer_selection]) {
      s.requirements[0].procedure_completeness.output_certificate.answer_sha256 = createHash("sha256").update(r.answer).digest("hex");
    }
    show(r); await settled();
    expect(screen.getByText("Recorded output hash: matched")).toBeInTheDocument();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  });
});
