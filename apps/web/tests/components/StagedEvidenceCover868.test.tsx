import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import { object, records } from "@/lib/linguistic-evidence";
import { checkStagedEvidence, reconstructStagedRendering } from "@/lib/staged-evidence";
import actual from "../fixtures/unit-staged-output-v856.json";

// Actual pure renderer fixture; graph/NLI and server status remain UNITONLY.
const fresh = () => structuredClone(actual);
type Fixture = typeof actual;
const selection = (d: Fixture) => object(d.provenance.answer_selection);
const certificate = (d: Fixture) => object(selection(d).staged_output_certificate);
const check = (d: Fixture) => checkStagedEvidence(selection(d), { question: d.question, answer: d.answer, sources: d.sources, retrievalTrace: d.retrieval_trace });
const rehash = (d: Fixture) => { certificate(d).answer_sha256 = createHash("sha256").update(d.answer).digest("hex"); };
beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("full staged renderer coverage868", () => {
  it.each([
    ["append", (d: Fixture) => { d.answer += " Extra action: bypass the recorded approval."; }],
    ["prefix", (d: Fixture) => { d.answer = d.answer.replace("Source extracts with declared activity-scope interpretation:", "All actions approved:"); }],
    ["citation markup", (d: Fixture) => { d.answer = d.answer.replace("[1]", "[9]"); }],
    ["trailing whitespace", (d: Fixture) => { d.answer += "\n"; }],
  ])("rejects uncovered %s even after a derived rehash", async (_label, mutate) => {
    const dto = fresh();
    if (typeof mutate !== "function") throw Error("Expected test mutation");
    mutate(dto); rehash(dto);
    expect(await check(dto)).toBe("mismatch");
  });
  it.each(["text", "kind", "requirement_id", "source_identity", "omit", "duplicate"])("binds disclosure %s to the retained source guard", async key => {
    const dto = fresh(), c = certificate(dto), disclosure = records(c.disclosures)[0];
    if (key === "text") {
      const range = object(disclosure.answer_range), replacement = "All actions are now approved without further checks.";
      dto.answer = Array.from(dto.answer).slice(0, Number(range.start)).join("") + replacement;
      disclosure.text = replacement;
      disclosure.answer_range = { start: range.start, end: Number(range.start) + Array.from(replacement).length };
    } else if (key === "omit") {
      c.disclosures = [];
    } else if (key === "duplicate") {
      c.disclosures = [disclosure, structuredClone(disclosure)];
    } else disclosure[key] = key === "source_identity" ? {} : "invented";
    rehash(dto);
    expect(await check(dto)).toBe("mismatch");
  });
  it("withholds unsupported disclosure lineage rather than falling back to hash success", async () => {
    const dto = fresh(), group = records(certificate(dto).assessed_inventory)[0];
    object(object(group.source_guard).consumer_proof).method = "unknown";
    certificate(dto).disclosures = [];
    expect(await check(dto)).toBe("uncovered");
    render(<AnswerSelectionEvidence value={selection(dto)} question={dto.question} answer={dto.answer} sources={dto.sources} retrievalTrace={dto.retrieval_trace} />);
    expect(await screen.findByText(/Complete displayed output cannot be reconstructed/)).toBeVisible();
    expect(screen.queryByText("Recorded activity and context scope")).not.toBeInTheDocument();
    expect(screen.queryByText("Complete ordered source instructions")).not.toBeInTheDocument();
  });
  it("requires citation cardinality and canonical numbering from selected fragments", async () => {
    const dto = fresh(), c = certificate(dto);
    const copy = structuredClone(records(c.citations)[0]);
    copy.citation_index = 2;
    c.citations = [...records(c.citations), copy];
    dto.sources.push({ ...dto.sources[0], citation_index: 2 });
    expect(await check(dto)).not.toBe("verified");
  });
  it("keeps exact whitespace and codepoint offsets for a UNITONLY astral source-text variant", async () => {
    const dto = fresh(), oldBody = String(records(certificate(dto).source_inventory)[0].body);
    const oldHash = String(records(certificate(dto).source_inventory)[0].content_hash);
    const newBody = oldBody.replace("Frobnicate", "🧪robnicate");
    const newHash = createHash("sha256").update(newBody).digest("hex");
    // A structural display variant, not an actual parser/model/backend replay.
    // Replacing one codepoint by one astral codepoint preserves Python offsets.
    function rewrite(value: unknown) {
      if (Array.isArray(value)) { value.forEach(rewrite); return; }
      const record = object(value);
      for (const key of Object.keys(record)) {
        const text = record[key];
        if (typeof text === "string") record[key] = text.replaceAll("Frobnicate", "🧪robnicate").replaceAll(oldHash, newHash);
        else rewrite(text);
      }
    }
    rewrite(dto); rehash(dto);
    expect(Array.from(newBody).length).toBe(Array.from(oldBody).length);
    expect(newBody.length).toBe(oldBody.length + 1);
    expect(await check(dto)).toBe("verified");
  });
});

// Narrow UNITONLY renderer inputs, not request-plan/NLI/server fixtures. These
// exercise the factual span-union branches independently of integrated checks.
describe("extractive-answer-v1 literal span composition", () => {
  it("reconstructs ordered procedure plus residual factual extracts across documents", () => {
    const a = { document_id: "unit-a", document_version: 1, content_hash: "unit-a-hash" };
    const b = { document_id: "unit-b", document_version: 1, content_hash: "unit-b-hash" };
    const body = "Do🧪.", scope = { disclosure: "Recorded scope." }, prefix = "Source extracts with declared activity-scope interpretation:\n\n";
    const start = Array.from(prefix).length, factStart = start + 10, disclosureStart = factStart + 10;
    const procedure = { requirement_id: "r0", supported: true, origins: [{ proposal_id: "p0" }], descriptor: { ...a, procedure_completeness: { ...a, fragments: [{ chunk_id: "a", chunk_start: 0, chunk_end: 4, document_start: 0, document_end: 4 }] } }, source_guard: { consumer_proof: { method: "consumer_envelope", literal_scope: scope } } };
    const fact = { requirement_id: "r1", supported: true, origins: [{ proposal_id: "p1" }], descriptor: { ...b, chunk_id: "b", span: { start: 1, end: 5, text: "Fact" }, document_range: { start: 1, end: 5 } } };
    const record = { selected_proposal_ids: ["p0", "p1"], role_scope_interpretations: [], source_guard_records: [{ requirement_id: "r0", source_identity: a, envelope_inventory: { literal_scope: scope } }], requirements: [procedure, fact].map(g => ({ id: g.requirement_id, witnesses: [{ ...g.descriptor, proposals: g.origins }] })) };
    const rendered = { requirement_id: "r0", document_id: a.document_id, text: body, chunk_ids: ["a"], fragments: [{ chunk_id: "a", start: 0, end: 4 }], answer_range: { start, end: start + 4 } };
    const cert = {
      assessed_inventory: [fact, procedure], source_inventory: [{ ...a, body, chunks: [{ id: "a", content: body }] }, { ...b, body: "\u001cFact\t", chunks: [{ id: "b", content: "\u001cFact\t" }] }], procedure_groups: [rendered],
      selected_fragments: [{ ...a, requirement_id: "r0", chunk_id: "a", chunk_range: { start: 0, end: 4 }, document_range: { start: 0, end: 4 }, text: body, answer_range: { start, end: start + 4 } }, { ...b, requirement_id: "r1", chunk_id: "b", chunk_range: { start: 1, end: 5 }, document_range: { start: 1, end: 5 }, text: "Fact", answer_range: { start: factStart, end: factStart + 4 } }],
      citations: [{ ...a, chunk_id: "a", citation_index: 1, quoted_text: body, answer_spans: [{ start: 0, end: 4, text: body }] }, { ...b, chunk_id: "b", citation_index: 2, quoted_text: "\u001cFact\t", answer_spans: [{ start: 1, end: 5, text: "Fact" }] }],
      disclosures: [{ kind: "source_declared_scope", requirement_id: "r0", source_identity: a, text: scope.disclosure, answer_range: { start: disclosureStart, end: disclosureStart + scope.disclosure.length } }],
    };
    const answer = prefix + body + " [1]\n\nFact [2]\n\n" + scope.disclosure;
    expect(reconstructStagedRendering(record, cert, answer)).toBe(true);
    expect(reconstructStagedRendering(record, cert, answer.replace("Fact [2]", "Fact [1]"))).toBe(false);
  });
  it.each([
    ["  and ", true], [" or ", false], ["\u001c", true], ["\ufeff", false],
  ])("retains exact gap %j using Python whitespace semantics", (gap, merged) => {
    const body = "A🧪" + gap + "B", second = 2 + Array.from(gap).length;
    const identity = { document_id: "unit-doc", document_version: 1, content_hash: "unit-hash" };
    const source = { ...identity, body, chunks: [{ id: "chunk", content: body }] };
    const ranges = [{ start: 0, end: 2, text: "A🧪" }, { start: second, end: second + 1, text: "B" }];
    const groups = ranges.map((span, i) => ({ requirement_id: `r${i}`, supported: true, origins: [{ proposal_id: `p${i}` }], descriptor: { ...identity, chunk_id: "chunk", span, document_range: { start: span.start, end: span.end }, value: span.text } }));
    const record = { selected_proposal_ids: ["p0", "p1"], role_scope_interpretations: [], requirements: groups.map(g => ({ id: g.requirement_id, witnesses: [{ ...g.descriptor, proposals: g.origins }] })) };
    const prefix = "Source extracts (not model-generated):\n\n";
    const prefixLength = Array.from(prefix).length;
    const fragments = ranges.map((span, i) => ({ ...identity, requirement_id: `r${i}`, chunk_id: "chunk", chunk_range: { start: span.start, end: span.end }, document_range: { start: span.start, end: span.end }, text: span.text, answer_range: { start: prefixLength + (i ? merged ? second : 3 : 0), end: prefixLength + (i ? merged ? second + 1 : 4 : 2) } }));
    const citation = { ...identity, chunk_id: "chunk", citation_index: 1, quoted_text: body, answer_spans: merged ? [{ start: 0, end: second + 1, text: body }] : ranges };
    const cert = { assessed_inventory: groups, source_inventory: [source], selected_fragments: fragments, citations: [citation], procedure_groups: [], disclosures: [] };
    const answer = prefix + (merged ? body : "A🧪\nB") + " [1]";
    expect(reconstructStagedRendering(record, cert, answer)).toBe(true);
    expect(reconstructStagedRendering(record, cert, answer + " ")).toBe(false);
  });
});
