import { render, screen } from "@testing-library/react";
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";
import { checkLinguisticOutput, object, records, type EvidenceRecord } from "@/lib/linguistic-evidence";
import fixture from "../fixtures/unit-count-v750.json";

// Actual SQLite/ASGI output; parser/QA replay, explicitly UNITONLY NLI/token count.
// These tests check display crosslinks, not inference, syntax truth or authority.
const fresh=()=>structuredClone(fixture) as unknown as EvidenceRecord;
const selection=(d:EvidenceRecord)=>object(object(d.provenance).answer_selection);
const certificate=(d:EvidenceRecord)=>object(selection(d).contextual_mixed_output_certificate);
const check=(d:EvidenceRecord)=>checkLinguisticOutput(selection(d),{question:d.question,answer:d.answer,sources:d.sources,retrievalTrace:d.retrieval_trace});
beforeEach(()=>vi.stubGlobal("crypto",webcrypto));
afterEach(()=>vi.unstubAllGlobals());

it("crosslinks the new count contract to the actual displayed answer",async()=>{
  expect(await check(fresh())).toBe("matched");
});

it("shows recorded field binding separately from server NLI checks",async()=>{
  const d=fresh();
  render(<AnswerSelectionEvidence value={selection(d)} question={d.question} answer={d.answer} sources={d.sources} retrievalTrace={d.retrieval_trace}/>);
  expect(await screen.findByText("Recorded output matches this answer.")).toBeVisible();
  expect(screen.getAllByText("Recorded source-bound count").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Exact source-field binding precedes recorded clause and whole-source NLI/).length).toBeGreaterThan(0);
  expect(screen.getByText(/The browser does not rerun the parser or models/)).toBeVisible();
});

const mutations:[string,(d:EvidenceRecord)=>void][]=[
  ["missing count policy",d=>{delete object(selection(d).evidence_profile).quantity_verification_profile;}],
  ["future count proof",d=>{object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).contract="future-count-proof";}],
  ["wrong source version",d=>{object(object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding).source_identity={document_version:99};}],
  ["wrong raw source range",d=>{object(object(object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding).raw_value).start=0;}],
  ["unlinked supported candidate",d=>{for(const c of records(selection(d).candidates))delete c.quantity_binding;}],
  ["coherent wrong displayed scope",d=>{object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding={...object(object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding),actual_target:{start:12,end:18,text:"tokens"}};}],
  ["coherent wrong displayed field",d=>{
    const binding=object(object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding);
    binding.declared_counted_np={start:31,end:37,text:"Copper"};object(binding.canonical_field).counted_np_range=[31,37];
  }],
  ...(["missing", "number", "empty", "whitespace"] as const).map((kind):[string,(d:EvidenceRecord)=>void]=>[
    `coherent ${kind} requested count fields`,d=>{
      const binding=object(object(object(records(certificate(d).assessed_inventory)[0].descriptor).quantity_binding).binding);
      const fields:[EvidenceRecord,string][]=[[object(object(binding.counted_np_alignment).declared),"requested_np"],[object(binding.canonical_field),"counted_np"],[object(binding.canonical_value),"unit"]];
      for(const [record,key] of fields) {
        if(kind==="missing") delete record[key];
        else record[key]=kind==="number"?7:kind==="empty"?"":" \u0085\u001c ";
      }
    },
  ]),
  ["FEFF topic coherently mirrored in the recorded plan",d=>setTopic(d,"Copper\uFEFF alignment")],
];
function setTopic(d:EvidenceRecord,topic:string) {
  for(const group of records(certificate(d).assessed_inventory)) {
    object(object(object(group.descriptor).quantity_binding).binding).request_requirement={...object(object(object(object(group.descriptor).quantity_binding).binding).request_requirement),topic};
  }
  for(const plan of [object(selection(d).request_plan),object(certificate(d).request_plan)]) {
    for(const req of records(plan.requirements)) if(req.kind==="quantity") req.topic=topic;
  }
}
function mirrorCaptures(d:EvidenceRecord) {
  for(const group of records(certificate(d).assessed_inventory)) {
    const descriptor=object(group.descriptor), origins=records(group.origins);
    if(!Object.hasOwn(descriptor,"quantity_binding")) continue;
    for(const row of records(selection(d).requirements)) {
      for(const witness of records(row.witnesses)) {
        if(records(witness.proposals).map(p=>p.proposal_id).join("|")===origins.map(p=>p.proposal_id).join("|")) witness.quantity_binding=structuredClone(descriptor.quantity_binding);
      }
    }
    for(const candidate of records(selection(d).candidates)) {
      if(Object.hasOwn(candidate,"support") && origins.some(o=>o.proposal_id===object(candidate.proposal).proposal_id)) candidate.quantity_binding=structuredClone(descriptor.quantity_binding);
    }
  }
  object(object(d.retrieval_trace).provenance).answer_selection=structuredClone(selection(d));
}
it.each(mutations)("withholds matched display for %s",async(_,mutate)=>{
  const d=fresh();mutate(d);
  if(_!=="unlinked supported candidate") {
    mirrorCaptures(d);
  }
  // Coherently mirror the altered capture; exact source/output checks still apply.
  object(object(d.retrieval_trace).provenance).answer_selection=structuredClone(selection(d));
  expect(await check(d)).not.toBe("matched");
});

it.each([" ","\t\n\r\v\f","\u001c\u001d\u001e\u001f","\u0085\u00a0\u1680","\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a","\u2028\u2029\u202f\u205f\u3000"])("preserves Python split wire whitespace %j",async(space)=>{
  const d=fresh();setTopic(d,`${space}Copper${space}alignment${space}`);mirrorCaptures(d);
  expect(await check(d)).toBe("matched");
});
