import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import { object, records } from "@/lib/linguistic-evidence";
import { checkStagedEvidence, hasStagedEvidence, slicePoints } from "@/lib/staged-evidence";
import actual from "../fixtures/unit-staged-output-v856.json";

// Actual pure v3 renderer DTO. Graph/NLI and server presentation status are
// UNITONLY synthetic controls, not CPU/HTTP/model quality observations.
const fresh = () => structuredClone(actual);
type Fixture = typeof actual;
const selection = (dto: Fixture) => object(dto.provenance.answer_selection);
const certificate = (dto: Fixture) => object(selection(dto).staged_output_certificate);
const group = (dto: Fixture) => records(certificate(dto).assessed_inventory)[0];
const sync = (dto: Fixture) => { object(dto.retrieval_trace.provenance).answer_selection = structuredClone(selection(dto)); };
const check = (dto: Fixture) => checkStagedEvidence(selection(dto), { question: dto.question, answer: dto.answer, sources: dto.sources, retrievalTrace: dto.retrieval_trace });
beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { vi.unstubAllGlobals(); });
function view(dto = fresh()) {
  return <AnswerSelectionEvidence value={dto.provenance.answer_selection} question={dto.question} answer={dto.answer} sources={dto.sources} retrievalTrace={dto.retrieval_trace} />;
}

describe("staged connected evidence", () => {
  it("dispatches actual v3 and separates recorded semantic support from exact copying", async () => {
    render(view());
    expect(screen.getByRole("heading", { name: "Staged request evidence" })).toBeVisible();
    expect(await screen.findByText("Server reports presentation verified; displayed context matches recorded ranges.")).toBeVisible();
    expect(screen.getByText("Recorded subject and applicability NLI")).toBeVisible();
    expect(screen.getByText("Recorded exact source coverage")).toBeVisible();
    expect(screen.getByRole("heading", { name: "1 of 1 requirements recorded supported" })).toBeVisible();
  });
  it("makes complete ordered source ranges available through native disclosure", async () => {
    render(view());
    const summary = await screen.findByText("Complete ordered source instructions");
    summary.focus();
    expect(summary).toHaveFocus();
    fireEvent.click(summary);
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByText("governing_declaration · source codepoints 0–50")).toBeVisible();
    expect(screen.getByText("opaque_payload · source codepoints 50–73")).toBeVisible();
  });
  it("retains unknown historical verification even with successful self-reports and hashes", async () => {
    const dto = fresh();
    delete selection(dto).presentation_verification;
    expect(await check(dto)).toBe("unverified");
    render(view(dto));
    expect(await screen.findByText(/Presentation verification is unknown or unverified/)).toBeVisible();
    expect(screen.queryByText(/Server reports presentation verified/)).not.toBeInTheDocument();
  });
  it("accepts an independently retained pre-certificate execution without retrocertification", async () => {
    const dto = fresh();
    delete object(dto.retrieval_trace.provenance.answer_selection).staged_output_certificate;
    expect(await check(dto)).toBe("verified");
  });
  it("shows recorded unsupported requirements and unresolved obligations on refusal", async () => {
    const dto = fresh(), record = selection(dto);
    record.decision = "refused";
    records(record.requirements)[0].status = "unsupported";
    records(record.requirements)[0].reason = "Required appendix unavailable";
    object(record.request_plan).unresolved = [{ reason: "Required appendix unavailable", owner_id: "r1" }];
    sync(dto);
    render(view(dto));
    expect(await screen.findByText(/No complete answer published/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "0 of 1 requirements recorded supported" })).toBeVisible();
    expect(screen.getByText("Kind: procedure · recorded status: unsupported")).toBeVisible();
    expect(screen.queryByText("Complete ordered source instructions")).not.toBeInTheDocument();
  });
  it("withholds source details for asset errors and server integrity failure", async () => {
    const dto = fresh();
    selection(dto).decision = "error";
    selection(dto).reason = "Local parser asset unavailable";
    render(view(dto));
    expect(await screen.findByText(/Execution or integrity verification failed/)).toBeVisible();
    expect(screen.getByText("Recorded reason: Local parser asset unavailable")).toBeVisible();
    expect(screen.queryByText("Complete ordered source instructions")).not.toBeInTheDocument();
  });
  it("keeps the staged panel for a sanitized integrity failure using retained markers", async () => {
    render(<AnswerSelectionEvidence value={{ presentation_verification: { status: "invalid", reason: "Saved output changed" } }} retrievalTrace={actual.retrieval_trace} />);
    expect(screen.getByRole("heading", { name: "Staged request evidence" })).toBeVisible();
    expect(await screen.findByText(/Execution or integrity verification failed/)).toBeVisible();
    expect(screen.getByText("Recorded reason: Saved output changed")).toBeVisible();
  });
  it("does not expose uncited planning snapshots or unselected assessed bodies", async () => {
    const dto = fresh(), record = selection(dto);
    object(record.staged_request_inputs).private_debug = "PRIVATE NONCITED PLANNING BODY";
    records(certificate(dto).assessed_inventory).push({ supported: false, value: "PRIVATE UNSELECTED BODY", origins: [] });
    sync(dto);
    render(view(dto));
    expect(await screen.findByText(/Server reports presentation verified/)).toBeVisible();
    expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument();
  });
  it("cancels obsolete verification after the actual answer changes", async () => {
    const dto = fresh(), page = render(view(dto));
    expect(await screen.findByText(/Server reports presentation verified/)).toBeVisible();
    dto.answer += " Additional text";
    page.rerender(view(dto));
    expect(await screen.findByText(/Displayed answer or citations do not match/)).toBeVisible();
    expect(screen.queryByText("Complete ordered source instructions")).not.toBeInTheDocument();
  });
});

describe("staged presentation boundaries", () => {
  const mutations: [string, (dto: Fixture) => void][] = [
    ["unknown requirement contract", d => { selection(d).contract = "future"; }],
    ["unknown profile", d => { object(selection(d).evidence_profile).contract = "future"; }],
    ["unknown procedure version", d => { object(selection(d).evidence_profile).procedure_contract = "future"; sync(d); }],
    ["new question", d => { d.question += " Why?"; }],
    ["missing retained execution", d => { object(d.retrieval_trace.provenance).answer_selection = {}; }],
    ["changed retained inputs", d => { object(object(d.retrieval_trace.provenance.answer_selection).staged_request_inputs).question = "Other"; }],
    ["missing requirement", d => { selection(d).requirements = []; sync(d); }],
    ["duplicate requirement", d => { const rows = records(selection(d).requirements); rows.push(structuredClone(rows[0])); selection(d).requirements = rows; sync(d); }],
    ["unknown output contract", d => { certificate(d).contract = "future"; }],
    ["changed cited source", d => { records(certificate(d).source_inventory)[0].body = "Other body"; }],
    ["version boolean", d => { records(certificate(d).source_inventory)[0].document_version = true; }],
    ["changed ordered range", d => { const envelope = object(object(group(d).source_guard).consumer_proof).envelope_inventory; records(object(envelope).ordered_ranges)[0].end = 49; }],
    ["missing fragments", d => { certificate(d).selected_fragments = []; }],
    ["missing rendered procedure", d => { certificate(d).procedure_groups = []; }],
    ["detached NLI", d => { records(object(object(group(d).source_guard).consumer_proof).nli_assessments)[0].hypothesis = "Invented"; }],
    ["missing source NLI", d => { object(object(group(d).source_guard).consumer_proof).nli_assessments = []; }],
    ["detached context scope", d => { object(object(group(d).source_guard).consumer_proof).literal_scope = { disclosure: "Unrelated context" }; }],
    ["duplicate source", d => { const sources = records(certificate(d).source_inventory); sources.push(structuredClone(sources[0])); certificate(d).source_inventory = sources; }],
    ["missing full-source fragment", d => { records(certificate(d).selected_fragments)[0].document_range = { start: 50, end: 73 }; }],
    ["unknown consumer version", d => { object(object(object(group(d).source_guard).consumer_proof).envelope_inventory).reading_profile = "future"; }],
    ["unknown procedure method", d => { object(object(group(d).descriptor).procedure_completeness).method = "future"; }],
    ["changed citation quote", d => { d.sources[0].quoted_text += " Changed"; }],
    ["failed publication read", d => { selection(d).staged_publication_check = { consistent: false, reason: "Changed source" }; }],
  ];
  it.each(mutations)("withholds %s", async (_label, mutate) => {
    const dto = fresh(); mutate(dto);
    expect(await check(dto)).toBe("invalid");
  });
  it("refuses a complete answer hash as a substitute for matching source ranges", async () => {
    const dto = fresh(); records(certificate(dto).selected_fragments)[0].answer_range = { start: 1, end: 74 };
    expect(await check(dto)).toBe("mismatch");
  });
  it("keeps verification unknown without browser digest support", async () => {
    vi.stubGlobal("crypto", {});
    expect(await check(fresh())).toBe("unavailable");
  });
  it("uses Unicode codepoint offsets without accepting boolean or empty ranges", () => {
    expect(slicePoints("A🧪Z", { start: 1, end: 2 })).toBe("🧪");
    expect(slicePoints("A🧪Z", { start: true, end: 2 })).toBeNull();
    expect(slicePoints("A🧪Z", { start: 1, end: 1 })).toBeNull();
  });
  // UNITONLY display-shape variants. These are not renderer/model observations;
  // they retain the actual v3 plan and consumer envelope, never a v2 projection.
  it.each(["declared_envelope", "canonical_discovery"])("recognizes the explicit shared %s inventory inside v6", async method => {
    const dto = fresh(), descriptor = object(group(dto).descriptor), proof = object(descriptor.procedure_completeness);
    const source = records(certificate(dto).source_inventory)[0];
    proof.method = method;
    proof.inventory = method === "declared_envelope" ? {
      contract: "complete-immutable-procedure-v4", reading_profile: "contextual_source_v1",
      source_identity: source, source_body: source.body, envelope_range: proof.extent,
    } : { contract: "procedure-required-inventory-v1", ...Object.fromEntries(["document_id", "document_version", "content_hash"].map(k => [k, source[k]])), extent: proof.extent };
    for (const witness of records(records(selection(dto).requirements)[0].witnesses)) witness.procedure_completeness = structuredClone(proof);
    sync(dto);
    expect(await check(dto)).toBe("verified");
  });
  it("recognizes an explicit local asset-readiness failure", async () => {
    const dto = fresh(); object(selection(dto).evidence_support).readiness = "error";
    expect(await check(dto)).toBe("error");
  });
  it.each(["staged_output_certificate", "staged_request_inputs"])("treats malformed %s as a strong staged marker", key => {
    expect(hasStagedEvidence({ [key]: null }, undefined)).toBe(true);
    expect(hasStagedEvidence({}, { provenance: { answer_selection: { [key]: null } } })).toBe(true);
  });
  it("leaves legacy and v2 dispatch untouched", () => {
    expect(hasStagedEvidence({ contract: "requirement-evidence-v4", evidence_profile: { contract: "evidence-profile-v7", evidence_reading_profile: "contextual_source_v2" } }, {})).toBe(false);
    expect(hasStagedEvidence({}, {})).toBe(false);
  });
});
