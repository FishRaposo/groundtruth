import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import { checkLinguisticOutput, object, records, type EvidenceRecord } from "@/lib/linguistic-evidence";
import actual from "../fixtures/actual-linguistic-factual-v654.json";

// Actual cached CPU/HTTP engineering response654; no blind/model-quality claim.
function view(dto = structuredClone(actual)) {
  return <AnswerSelectionEvidence value={dto.provenance.answer_selection} question={dto.question} answer={dto.answer} sources={dto.sources} retrievalTrace={dto.retrieval_trace} />;
}
beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("linguistic connected evidence", () => {
  it("binds the actual recorded factual answer without claiming browser model execution", async () => {
    render(view());
    expect(await screen.findByText("Recorded output matches this answer.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "1 of 1 requirements supported" })).toBeVisible();
    expect(screen.getByText(actual.question)).toBeVisible();
    expect(screen.getByText(/The browser does not rerun the parser or models/)).toBeVisible();
  });
  it("does not reuse verification for an altered actual answer", async () => {
    const dto=structuredClone(actual);dto.answer += " Altered.";
    render(view(dto));
    expect(await screen.findByText("Recorded output does not match this answer.")).toBeVisible();
    expect(screen.queryByText("Recorded output matches this answer.")).not.toBeInTheDocument();
  });
  it("uses retained modern evidence to prevent a legacy downgrade", async () => {
    const dto=structuredClone(actual);
    Object.assign(dto.provenance.answer_selection, { contract:"requirement-evidence-v2" });
    render(view(dto));
    await waitFor(() => expect(screen.getByText("Recorded evidence is incomplete or inconsistent.")).toBeVisible());
    expect(screen.queryByRole("heading", { name:"1 of 1 requirements supported" })).not.toBeInTheDocument();
  });
  it("cancels obsolete output checks when the displayed answer changes", async () => {
    const dto=structuredClone(actual);const page=render(view(dto));
    expect(await screen.findByText("Recorded output matches this answer.")).toBeVisible();
    dto.answer+=" Altered.";page.rerender(view(dto));
    expect(await screen.findByText("Recorded output does not match this answer.")).toBeVisible();
    expect(screen.queryByText("Recorded output matches this answer.")).not.toBeInTheDocument();
  });
});

it("does not recognize a coherently unknown procedure sub-contract", async () => {
  const dto=structuredClone(actual);
  dto.provenance.answer_selection.evidence_profile.procedure_contract="future-procedure-contract";
  dto.retrieval_trace.provenance.answer_selection.evidence_profile.procedure_contract="future-procedure-contract";
  dto.provenance.answer_selection.contextual_mixed_output_certificate.model_settings.evidence_profile.procedure_contract="future-procedure-contract";
  render(view(dto));
  expect(await screen.findByText("Recorded evidence is incomplete or inconsistent.")).toBeVisible();
  expect(screen.queryByText("Recorded output matches this answer.")).not.toBeInTheDocument();
});

// Deliberately inconsistent mutations of the real654 DTO. These exercise byte
// crosslinks only; none is an observation of model/backend output or authority.
const fresh=()=>structuredClone(actual) as unknown as EvidenceRecord;
const selection=(d:EvidenceRecord)=>object(object(d.provenance).answer_selection);
const certificate=(d:EvidenceRecord)=>object(selection(d).contextual_mixed_output_certificate);
const check=(d:EvidenceRecord)=>checkLinguisticOutput(selection(d),{
  question:d.question,answer:d.answer,sources:d.sources,retrievalTrace:d.retrieval_trace,
});
const syncCapture=(d:EvidenceRecord)=>{ object(object(d.retrieval_trace).provenance).answer_selection=structuredClone(selection(d)); };
const citedSource=(d:EvidenceRecord)=>records(certificate(d).source_inventory).find(s=>s.document_id===records(d.sources)[0].document_id)!;
const citedChunk=(d:EvidenceRecord)=>records(citedSource(d).chunks)[0];
const syncCitation=(d:EvidenceRecord)=>{ d.sources=structuredClone(certificate(d).citations); };
// Synthetic structural control derived from654, not a server/model procedure
// observation. It exercises the browser's generic multi-kind crosslinks only.
const syntheticProcedure=()=>{
  const d=fresh(),r=selection(d),c=certificate(d),s=citedSource(d),chunk=citedChunk(d),body=String(s.body),end=Array.from(body).length;
  const row=records(r.requirements)[0],g=records(c.assessed_inventory)[0],descriptor=object(g.descriptor),range={start:0,end};
  const identity=Object.fromEntries(["document_id","document_version","content_hash","workspace_id"].map(k=>[k,s[k]]));
  const closure={kind:"immutable_eof",offset:end},literal_scope={disclosure:"Synthetic structural control scope."};
  const envelope={contract:"complete-immutable-procedure-v5",reading_profile:"contextual_source_v2",method:"consumer_envelope",source_identity:identity,source_body:body,body_length:end,envelope_range:range,closure,literal_scope};
  const proof={contract:"complete-immutable-procedure-v5",...identity,method:"consumer_envelope",source_body:body,body_length:end,extent:range,closure,inventory:envelope,proof_units:[],fragments:[{chunk_id:chunk.id,chunk_start:0,chunk_end:end,document_start:0,document_end:end}]};
  g.source_guard={requirement_id:row.id,source_identity:identity,consumer_proof:{contract:proof.contract,method:proof.method,status:"discharged",requirement_id:row.id,source_identity:identity,envelope_inventory:envelope,literal_scope,nli_assessments:[]}};
  row.kind="procedure";records(object(r.request_plan).requirements)[0].kind="procedure";c.request_plan=structuredClone(r.request_plan);
  g.value=body;descriptor.value=body;descriptor.span={...range,text:body};descriptor.document_range=range;descriptor.procedure_completeness=proof;
  const witness=records(row.witnesses)[0];Object.assign(witness,structuredClone(descriptor));row.procedure_completeness=structuredClone(proof);
  c.selected_fragments=[{requirement_id:row.id,document_id:s.document_id,document_version:s.document_version,content_hash:s.content_hash,chunk_id:chunk.id,chunk_range:range,document_range:range,answer_range:range,text:body}];
  records(c.citations)[0].answer_spans=[{...range,text:body}];syncCitation(d);
  c.procedure_groups=[{requirement_id:row.id,document_id:s.document_id,text:body,answer_range:range,chunk_ids:[chunk.id],fragments:[{chunk_id:chunk.id,start:0,end}]}];
  d.answer=body+" [1]";c.answer_sha256=createHash("sha256").update(String(d.answer)).digest("hex");syncCapture(d);
  return d;
};
const procedureProof=(d:EvidenceRecord)=>object(object(records(certificate(d).assessed_inventory)[0].descriptor).procedure_completeness);
const procedureGuard=(d:EvidenceRecord)=>object(records(certificate(d).assessed_inventory)[0].source_guard);
const syncProcedure=(d:EvidenceRecord)=>{
  const row=records(selection(d).requirements)[0],proof=procedureProof(d);
  records(row.witnesses)[0].procedure_completeness=structuredClone(proof);row.procedure_completeness=structuredClone(proof);syncCapture(d);
};
const replaceProcedureParts=(d:EvidenceRecord,ranges:{start:number;end:number}[])=>{
  const c=certificate(d),source=citedSource(d),chunk=citedChunk(d),rendered=records(c.procedure_groups)[0],answerStart=Number(object(rendered.answer_range).start),body=Array.from(String(source.body));
  procedureProof(d).fragments=ranges.map(({start,end})=>({chunk_id:chunk.id,chunk_start:start,chunk_end:end,document_start:start,document_end:end}));
  c.selected_fragments=ranges.map(({start,end})=>({requirement_id:records(selection(d).requirements)[0].id,document_id:source.document_id,document_version:source.document_version,content_hash:source.content_hash,chunk_id:chunk.id,chunk_range:{start,end},document_range:{start,end},answer_range:{start:answerStart+start,end:answerStart+end},text:body.slice(start,end).join("")}));
  records(c.citations)[0].answer_spans=ranges.map(({start,end})=>({start,end,text:body.slice(start,end).join("")}));
  rendered.chunk_ids=ranges.map(()=>chunk.id);rendered.fragments=ranges.map(({start,end})=>({chunk_id:chunk.id,start,end}));
  syncCitation(d);syncProcedure(d);
};

describe("selected evidence crosslinks",()=>{
  const mutations: [string,(d:EvidenceRecord)=>void][]=[
    ["certificate selected value",d=>{records(certificate(d).assessed_inventory)[0].value="999 days";}],
    ["certificate descriptor proof",d=>{object(records(certificate(d).assessed_inventory)[0].descriptor).procedure_completeness={method:"consumer_envelope"};}],
    ["certificate guard labels",d=>{object(records(certificate(d).assessed_inventory)[0].source_guard).consumer_proof={nli_assessments:[{name:"invented"}]};}],
    ["coherent certificate copies detached from witness",d=>{const g=records(certificate(d).assessed_inventory)[0];g.value="999 days";object(g.descriptor).value=g.value;syncCapture(d);}],
    ["missing assessed groups",d=>{certificate(d).assessed_inventory=[];syncCapture(d);}],
    ["unselected assessed origins",d=>{records(records(certificate(d).assessed_inventory)[0].origins)[0].proposal_id="other";syncCapture(d);}],
    ["selected origin omitted",d=>{selection(d).selected_proposal_ids=[];certificate(d).selected_proposal_ids=[];syncCapture(d);}],
    ["duplicated selected origin",d=>{const ids=selection(d).selected_proposal_ids as unknown[];ids.push(ids[0]);certificate(d).selected_proposal_ids=structuredClone(ids);syncCapture(d);}],
    ["complete quote outside body",d=>{const c=citedChunk(d);c.content+=" THIS TEXT IS NOT IN THE IMMUTABLE SOURCE.";records(certificate(d).citations)[0].quoted_text=c.content;syncCitation(d);}],
    ["uncited inventory chunk outside body",d=>{records(certificate(d).source_inventory).find(s=>s.document_id!==records(d.sources)[0].document_id)!.chunks=[{id:"new",content:"forged",document_range:{start:0,end:6}}];}],
    ["missing chunk document range",d=>{delete citedChunk(d).document_range;}],
    ["shifted complete chunk range",d=>{object(citedChunk(d).document_range).start=1;}],
    ["ambiguous duplicate chunk",d=>{const s=citedSource(d);(s.chunks as unknown[]).push(structuredClone(citedChunk(d)));}],
    ["ambiguous duplicate source",d=>{(certificate(d).source_inventory as unknown[]).push(structuredClone(citedSource(d)));}],
    ["no citations",d=>{certificate(d).citations=[];d.sources=[];}],
    ["nonempty unrelated citation",d=>{const s=records(certificate(d).source_inventory).find(s=>s.document_id!==records(d.sources)[0].document_id)!,c=records(s.chunks)[0];certificate(d).citations=[{citation_index:1,chunk_id:c.id,document_id:s.document_id,document_version:s.document_version,content_hash:s.content_hash,quoted_text:c.content,answer_spans:[{start:0,end:5,text:String(c.content).slice(0,5)}]}];syncCitation(d);}],
    ["empty citation source spans",d=>{records(certificate(d).citations)[0].answer_spans=[];syncCitation(d);}],
    ["citation excludes selected fragment",d=>{records(certificate(d).citations)[0].answer_spans=[{start:0,end:3,text:String(citedChunk(d).content).slice(0,3)}];syncCitation(d);}],
    ["citation source span text",d=>{records(records(certificate(d).citations)[0].answer_spans)[0].text="other";syncCitation(d);}],
    ["wrong citation index",d=>{records(certificate(d).citations)[0].citation_index=2;syncCitation(d);}],
    ["duplicated citation",d=>{(certificate(d).citations as unknown[]).push(structuredClone(records(certificate(d).citations)[0]));syncCitation(d);}],
    ["fragment changed source identity",d=>{records(certificate(d).selected_fragments)[0].document_id="other";}],
    ["fragment detached from retained descriptor",d=>{const f=records(certificate(d).selected_fragments)[0];f.text="7 minutes";f.document_range={start:77,end:86};f.chunk_range={start:77,end:86};f.answer_range={start:66,end:75};}],
    ["selected origin text inconsistent across source slices",d=>{
      const g=records(certificate(d).assessed_inventory)[0],origin=records(g.origins)[0];
      const proposal=records(selection(d).proposals).find(p=>p.proposal_id===origin.proposal_id)!;
      const witness=records(records(selection(d).requirements)[0].witnesses)[0];
      origin.text="other";proposal.text="other";records(witness.proposals)[0].text="other";syncCapture(d);
    }],
  ];
  it.each(mutations)("rejects %s",async(_name,mutate)=>{
    const d=fresh();mutate(d);expect(await check(d)).not.toBe("matched");
  });
  it("hides the matching badge and altered selected value after inconsistent display metadata",async()=>{
    const dto=structuredClone(actual);
    dto.provenance.answer_selection.contextual_mixed_output_certificate.assessed_inventory[0].value="999 days";
    render(view(dto));
    expect(await screen.findByText("Recorded evidence is incomplete or inconsistent.")).toBeVisible();
    expect(screen.queryByText("Recorded output matches this answer.")).not.toBeInTheDocument();
    expect(screen.queryByText("999 days")).not.toBeInTheDocument();
  });
  it("keeps the selected value associated with its wider supporting passage",async()=>{
    render(view());
    expect(await screen.findByText("Recorded output matches this answer.")).toBeVisible();
    expect(screen.getByText("7 minutes")).toBeInTheDocument();
    expect(screen.getByText(/Supporting passage source codepoints 51–87/)).toBeInTheDocument();
  });
  it("composes nonzero chunk offsets in Unicode codepoints (synthetic crosslink control)",async()=>{
    const d=fresh(),s=citedSource(d),prefix="🧭\n",offset=Array.from(prefix).length;
    const oldHash=s.content_hash,id=s.document_id,body=prefix+String(s.body)+"\nTail.";
    const digest=createHash("sha256").update(body).digest("hex");
    const visit=(value:unknown)=>{
      if(Array.isArray(value)){value.forEach(visit);return;}
      const item=object(value);
      if(item.content_hash===oldHash)item.content_hash=digest;
      if(item.document_id===id && item.document_range){const range=object(item.document_range);range.start=Number(range.start)+offset;range.end=Number(range.end)+offset;}
      Object.values(item).forEach(v=>{if(v && typeof v==="object")visit(v);});
    };
    visit(d);s.body=body;
    const range=object(citedChunk(d).document_range);range.start=Number(range.start)+offset;range.end=Number(range.end)+offset;
    syncCapture(d);
    expect(await check(d)).toBe("matched");
    // The same repeated text cannot excuse a different document/chunk offset.
    const fragment=records(certificate(d).selected_fragments)[0];
    object(fragment.document_range).start=Number(object(fragment.document_range).start)-offset;
    object(fragment.document_range).end=Number(object(fragment.document_range).end)-offset;
    expect(await check(d)).not.toBe("matched");
  });
  it("binds a synthetic procedure's displayed whole-body value to its actual answer range",async()=>{
    const d=syntheticProcedure();expect(await check(d)).toBe("matched");
    object(records(certificate(d).procedure_groups)[0].answer_range).start=1;
    expect(await check(d)).not.toBe("matched");
  });
  it("rejects synthetic procedure metadata with no proof fragments",async()=>{
    const d=syntheticProcedure(),g=records(certificate(d).assessed_inventory)[0];
    object(object(g.descriptor).procedure_completeness).fragments=[];
    records(records(selection(d).requirements)[0].witnesses)[0].procedure_completeness=structuredClone(object(g.descriptor).procedure_completeness);
    records(selection(d).requirements)[0].procedure_completeness=structuredClone(object(g.descriptor).procedure_completeness);syncCapture(d);
    expect(await check(d)).not.toBe("matched");
  });
});

describe("versioned complete procedure structure (synthetic controls only)",()=>{
  const mutations:[string,(d:EvidenceRecord)=>void][]=[
    ["unknown nested proof contract",d=>{procedureProof(d).contract="complete-immutable-procedure-v999";}],
    ["unknown reconstruction method",d=>{procedureProof(d).method="synthetic_crosslink_control";}],
    ["missing nested contract",d=>{delete procedureProof(d).contract;}],
    ["missing nested method",d=>{delete procedureProof(d).method;}],
    ["mismatched nested source identity",d=>{procedureProof(d).document_id="other";}],
    ["mismatched nested workspace",d=>{procedureProof(d).workspace_id="other";}],
    ["body length",d=>{procedureProof(d).body_length=86;}],
    ["partial declared extent",d=>{procedureProof(d).extent={start:51,end:87};}],
    ["unknown closure",d=>{procedureProof(d).closure={kind:"guessed_eof",offset:87};}],
    ["truncated closure",d=>{procedureProof(d).closure={kind:"immutable_eof",offset:86};}],
    ["unknown nested inventory",d=>{object(procedureProof(d).inventory).contract="complete-immutable-procedure-v999";}],
    ["unknown inventory method",d=>{object(procedureProof(d).inventory).method="other";}],
    ["unknown inventory profile",d=>{object(procedureProof(d).inventory).reading_profile="other";}],
    ["unknown consumer contract",d=>{object(procedureGuard(d).consumer_proof).contract="future";}],
    ["unknown consumer method",d=>{object(procedureGuard(d).consumer_proof).method="other";}],
    ["consumer identity",d=>{object(object(procedureGuard(d).consumer_proof).source_identity).document_version=2;}],
    ["consumer requirement",d=>{object(procedureGuard(d).consumer_proof).requirement_id="other";}],
    ["consumer scope disclosure",d=>{object(object(procedureGuard(d).consumer_proof).literal_scope).disclosure="";}],
    ["proper sentence subset",d=>{replaceProcedureParts(d,[{start:51,end:87}]);}],
    ["uncovered tail",d=>{replaceProcedureParts(d,[{start:0,end:86}]);}],
    ["uncovered middle",d=>{replaceProcedureParts(d,[{start:0,end:50},{start:51,end:87}]);}],
    ["overlap",d=>{replaceProcedureParts(d,[{start:0,end:52},{start:51,end:87}]);}],
    ["reordered partition",d=>{replaceProcedureParts(d,[{start:51,end:87},{start:0,end:51}]);}],
    ["duplicate fragment",d=>{replaceProcedureParts(d,[{start:0,end:87},{start:0,end:87}]);}],
    ["rendered chunk inventory",d=>{records(certificate(d).procedure_groups)[0].chunk_ids=[];}],
    ["rendered fragment inventory",d=>{records(certificate(d).procedure_groups)[0].fragments=[];}],
    ["unknown exact check method",d=>{procedureProof(d).method="canonical_discovery";procedureProof(d).inventory={contract:"procedure-required-inventory-v1",...Object.fromEntries(["document_id","document_version","content_hash","workspace_id"].map(k=>[k,citedSource(d)[k]])),extent:{start:0,end:87}};procedureProof(d).proof_units=[{source_range:{start:0,end:87},verification_method:"trust_me"}];}],
    ["procedure proof on a factual row",d=>{records(selection(d).requirements)[0].kind="duration";records(object(selection(d).request_plan).requirements)[0].kind="duration";certificate(d).request_plan=structuredClone(selection(d).request_plan);}],
  ];
  it.each(mutations)("rejects %s",async(_name,mutate)=>{
    const d=syntheticProcedure();expect(await check(d)).toBe("matched");mutate(d);syncProcedure(d);expect(await check(d)).not.toBe("matched");
  });
  it("rejects a procedure row with only factual proof",async()=>{
    const d=fresh();records(selection(d).requirements)[0].kind="procedure";records(object(selection(d).request_plan).requirements)[0].kind="procedure";certificate(d).request_plan=structuredClone(selection(d).request_plan);syncCapture(d);
    expect(await check(d)).not.toBe("matched");
  });
  it("accepts an ordered complete partition including all separators",async()=>{
    const d=syntheticProcedure();replaceProcedureParts(d,[{start:0,end:51},{start:51,end:87}]);expect(await check(d)).toBe("matched");
  });
  it.each(["declared_envelope","canonical_discovery"])("dispatches recognized %s structural inventory without inferring semantics",async method=>{
    const d=syntheticProcedure(),proof=procedureProof(d),source=citedSource(d),identity=Object.fromEntries(["document_id","document_version","content_hash","workspace_id"].map(k=>[k,source[k]]));
    proof.method=method;proof.proof_units=[{source_range:{start:0,end:87},verification_method:"exact_source_copy"}];
    proof.inventory=method==="declared_envelope"
      ? {contract:"complete-immutable-procedure-v4",reading_profile:"contextual_source_v1",source_identity:identity,source_body:source.body,body_length:87,envelope_range:{start:0,end:87},closure:{kind:"immutable_eof",offset:87}}
      : {contract:"procedure-required-inventory-v1",...identity,extent:{start:0,end:87}};
    syncProcedure(d);expect(await check(d)).toBe("matched");
    object(proof.inventory).contract="future-inventory";syncProcedure(d);expect(await check(d)).not.toBe("matched");
  });
  it("composes the procedure answer offset in Unicode codepoints",async()=>{
    const d=syntheticProcedure(),prefix="🧭 copied:\n",offset=Array.from(prefix).length;
    d.answer=prefix+String(d.answer);certificate(d).answer_sha256=createHash("sha256").update(String(d.answer)).digest("hex");
    records(certificate(d).procedure_groups)[0].answer_range={start:offset,end:offset+87};replaceProcedureParts(d,[{start:0,end:87}]);
    expect(await check(d)).toBe("matched");
    d.answer=String(d.answer)+"\n"+String(citedSource(d).body);certificate(d).answer_sha256=createHash("sha256").update(String(d.answer)).digest("hex");
    const second=Array.from(String(d.answer)).length-87;records(certificate(d).selected_fragments)[0].answer_range={start:second,end:second+87};
    expect(await check(d)).not.toBe("matched");
  });
  it("does not render complete coverage or a matching badge for a proper subset",async()=>{
    const d=syntheticProcedure();replaceProcedureParts(d,[{start:51,end:87}]);
    render(<AnswerSelectionEvidence value={selection(d)} question={d.question} answer={d.answer} sources={d.sources} retrievalTrace={d.retrieval_trace}/>);
    expect(await screen.findByText("Recorded evidence is incomplete or inconsistent.")).toBeVisible();
    expect(screen.queryByText("Recorded output matches this answer.")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading",{name:"1 of 1 requirements supported"})).not.toBeInTheDocument();
  });
});
