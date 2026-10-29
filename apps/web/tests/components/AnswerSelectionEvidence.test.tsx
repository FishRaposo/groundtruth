import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import AnswerSelectionEvidence from "@/components/AnswerSelectionEvidence";

function completeProcedure() {
  // Canonical governance and contiguous steps; clause and full-step premises remain distinct.
  const step_ranges = Array.from({ length: 8 }, (_, i) => ({ ordinal: i + 1, start: 20 + i * 10, end: 30 + i * 10 }));
  const descriptor = (name: string, kind: string, start: number, end: number, step: number | null, hypothesis: string) => ({
    name, kind, source_range: { start, end },
    premise_range: step === null ? { start, end } : { start: step_ranges[step - 1].start, end: step_ranges[step - 1].end },
    hypothesis, step,
  });
  const units = [
    descriptor("namespace", "namespace", 0, 5, null, "These instructions govern the transfer."),
    descriptor("applicability", "applicability", 5, 10, null, "These instructions apply to ordinary transfers."),
    descriptor("requested_scope", "request_scope", 0, 10, null, "The complete instructions govern the requested transfer."),
    ...step_ranges.map((range) => descriptor(`step-${range.ordinal}`, "instruction", range.start, range.end - 2, range.ordinal, `The instructions require action ${range.ordinal}.`)),
    descriptor("final-prohibition", "prohibition", 94, 100, 8, "The instructions require that you never reopen the record."),
  ];
  const proof_units = units.map((unit): Omit<typeof unit, "step"> & { step?: number | null; label: string; entailment_margin: number; supported: boolean; pair_tokens: number } => ({
    ...unit, source_range: { ...unit.source_range }, premise_range: { ...unit.premise_range },
    label: "entailment", entailment_margin: 2, supported: true, pair_tokens: 100,
  }));
  const structure_edges: { name: string; source: string; target: string; step?: number }[] = [
    { name: "namespace_to_applicability", source: "namespace", target: "applicability" },
    ...units.filter((unit) => unit.step !== null).map((unit) => ({ name: "applicability_to_action", source: "applicability", target: unit.name, step: unit.step! })),
  ];
  return {
    mode: "reader", contract: "requirement-evidence-v2", evidence_support: { minimum_entailment_margin: 0 },
    requirements: [{ id: "r1", kind: "procedure", original_text: "Give the complete transfer procedure.", status: "supported", witnesses: [{ value: "All eight recorded steps and the closure prohibition." }],
      procedure_completeness: {
        contract: "complete-immutable-procedure-v2", status: "supported", document_id: "document", workspace_id: "workspace", document_version: 1, content_hash: "a".repeat(64),
        body_length: 100, structure: "numbered", extent: { start: 10, end: 100 }, closure: { kind: "immutable_eof", end: 100 }, step_count: 8, mandatory_proof_count: proof_units.length, coverage_complete: true, step_ranges,
        proof_units, structure_edges,
        required_inventory: { contract: "procedure-required-inventory-v1", document_id: "document", workspace_id: "workspace", document_version: 1, content_hash: "a".repeat(64), extent: { start: 10, end: 100 }, structure: "numbered", step_ranges: step_ranges.map((range) => ({ ...range })), units, structure_edges: structure_edges.map((edge) => ({ ...edge })), seed_clause: { unit_name: "step-1", source_range: { start: 20, end: 28 }, text: "Copy it." } as { unit_name: string; source_range: { start: number; end: number }; text: string } | undefined },
        raw_seed: { chunk_id: "first", text: "Copy it.", chunk_range: { start: 20, end: 28 }, document_range: { start: 20, end: 28 } },
        fragments: [{ chunk_id: "first", chunk_start: 10, chunk_end: 60, document_start: 10, document_end: 60 }, { chunk_id: "second", chunk_start: 10, chunk_end: 50, document_start: 60, document_end: 100 }],
      },
    }],
  };
}
type ProcedureRecord = ReturnType<typeof completeProcedure>;
type SeedFixture = { clause?: string; clauseRange?: { start: number; end: number }; raw?: string; rawRange?: { start: number; end: number }; stepStart?: number };
function numberedSeed({ clause = "Copy it.", clauseRange = { start: 20, end: 28 }, raw = clause, rawRange = clauseRange, stepStart = 20 }: SeedFixture = {}) {
  const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
  for (const units of [proof.proof_units, proof.required_inventory.units]) {
    const unit = units.find((item) => item.name === "step-1")!;
    unit.source_range = { ...clauseRange }; unit.premise_range.start = stepStart;
  }
  proof.step_ranges[0].start = stepStart; proof.required_inventory.step_ranges[0].start = stepStart;
  proof.required_inventory.seed_clause = { unit_name: "step-1", source_range: { ...clauseRange }, text: clause };
  proof.raw_seed = { chunk_id: "first", text: raw, chunk_range: { ...rawRange }, document_range: { ...rawRange } };
  return record;
}
function narrativeProcedure() {
  const record = completeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
  const unit = { ...proof.proof_units[0], name: "whole-method", kind: "whole_method", step: null, source_range: { start: 10, end: 100 }, premise_range: { start: 10, end: 100 }, hypothesis: "The transfer instructions require copying the record and completing the closure check." };
  return { ...record, requirements: [{ ...row, procedure_completeness: {
    ...proof, structure: "narrative", step_count: null, step_ranges: [], mandatory_proof_count: 1,
    proof_units: [unit], structure_edges: [], required_inventory: { ...proof.required_inventory, structure: "narrative", step_ranges: [], units: [{ name: unit.name, kind: unit.kind, source_range: { ...unit.source_range }, premise_range: { ...unit.premise_range }, hypothesis: unit.hypothesis, step: null }], structure_edges: [] },
  } }] };
}

function recordedProfile(proposal_profile = "qa_plus_source_patterns_v1", role_scope_policy = "ordinary_session_activity_v1") {
  return { contract: "evidence-profile-v1", proposal_profile, role_scope_policy, origin_contract: "proposal-origin-v1", role_policy_contract: "ordinary-session-activity-role-v1", pattern_registry_contract: proposal_profile === "qa_only_v1" ? "disabled" : "typed-source-patterns-v1", pattern_limits: { per_source_requirement: 3, per_requirement: 16 } };
}

// Invented records following the approved public engineering-fixture schema, never model results.
function profiledRecord(origin = "source_pattern") {
  const source = { document_id: "document", document_version: 1, content_hash: "a".repeat(64), chunk_id: "chunk" };
  const proposal = { ...source, contract: "proposal-origin-v1", proposal_id: "proposal-1", requirement_id: "r1", origin, chunk_range: { start: 0, end: 18 }, document_range: { start: 0, end: 18 }, text: "The record steward", pattern_id: origin === "source_pattern" ? "literal-lead-deputy-v1" : null, grammar_version: origin === "source_pattern" ? "typed-source-patterns-v1" : null, qa_observation_id: origin === "qa_reader" ? "qa-1" : null };
  return {
    mode: "reader", contract: "requirement-evidence-v2", evidence_profile: recordedProfile(origin === "qa_reader" ? "qa_only_v1" : "qa_plus_source_patterns_v1", "literal_v1"),
    discovery_lineage: { status: "recorded", valid: true }, proposals: [proposal], selected_proposal_ids: [proposal.proposal_id],
    qa_observations: [{ observation_id: "qa-1", requirement_id: "r1", chunk_id: "chunk", span: origin === "qa_reader" ? { start: 0, end: 18, text: proposal.text } : null, diagnostics: { decision: origin === "qa_reader" ? "answered" : "no_answer" }, question: "Who leads Meridian review?", reader: { model: "fixture reader", revision: "fixture" } }],
    pattern_observations: origin === "source_pattern" ? [{ origin, proposal: { ...proposal }, decision: "supported", support: { label: "entailment", supported: true, pair_tokens: 12 } }] : [],
    requirements: [{ id: "r1", kind: "owner", original_text: "Who leads Meridian review?", status: "supported", witnesses: [{ ...source, value: proposal.text, span: { start: 0, end: 41, text: "The record steward leads Meridian review." }, document_range: { start: 0, end: 41 }, proposals: [{ ...proposal }] }] }],
  };
}

function profiledProcedure() {
  const record = profiledRecord(), complete = completeProcedure().requirements[0];
  const proposal = { ...record.proposals[0], chunk_id: "first", text: "Copy it.", chunk_range: { start: 20, end: 28 }, document_range: { start: 20, end: 28 } };
  return { ...record, evidence_support: { minimum_entailment_margin: 0 }, proposals: [proposal], requirements: [{ ...complete, witnesses: [{ ...record.requirements[0].witnesses[0], chunk_id: "first", value: "All eight steps and the closure prohibition.", span: { start: 20, end: 28, text: "Copy it." }, document_range: { start: 20, end: 28 }, proposals: [{ ...proposal }] }], procedure_completeness: { ...complete.procedure_completeness, raw_seed: { ...complete.procedure_completeness.raw_seed, origin: proposal.origin, proposal_id: proposal.proposal_id } } }] };
}

function activityRecord() {
  const record = profiledRecord();
  const original_text = "Who leads an ordinary Meridian review session?";
  const input_range = { start: 0, end: Array.from(original_text).length };
  return { ...record, evidence_profile: recordedProfile(), role_scope_read_set: { contract: "role-scope-inspection-read-set-v1", complete: true, reason: null, documents: [{ document_id: "document", document_version: 1, content_hash: "a".repeat(64) }], scopefilters: {}, limits: {} }, requirements: [{ ...record.requirements[0], original_text, input_range: { ...input_range }, prepared_question: "Who leads Meridian review?", source_workspace: null as string | null, role_scope_interpretation: { contract: "ordinary-session-activity-role-v1", requirement_id: "r1", requested_scope: "ordinary Meridian review session", session_scope: "Meridian review session", activity_scope: "Meridian review", effective_scope: "activity", activity_fallback: true, disclosure: "Activity scope: the documented lead for Meridian review is used for this ordinary-session question. The source documents an activity role, rather than a separate session assignment.", basis: "activity_role", kind: "owner", original_text, input_range: { ...input_range }, prepared_question: "Who leads Meridian review?", effective_target: "Meridian review", source_workspace: null as string | null } }] };
}

// Frozen actual P168 serializer records. ALL NI entailment/margins/token12 are TEST DOUBLES.
const paragraphProtocols = {
  "protocol": {
    "evidence_kind": "P168 original FAKE-NI token12 protocol",
    "proof": {
      "contract": "complete-immutable-procedure-v2",
      "status": "supported",
      "document_id": "45f4bd3a-3fdf-4519-a05f-1f79ce7cbfe8",
      "document_version": 1,
      "content_hash": "9262522f3078bd43930aa2a679ba73cbdbc1dea36ecd2d3317cba5a82f4c8534",
      "body_length": 1251,
      "extent": {
        "start": 492,
        "end": 811
      },
      "closure": {
        "kind": "declared_paragraph_end",
        "end": 811,
        "boundary_range": {
          "start": 813,
          "end": 838
        }
      },
      "structure": "declared_paragraphs",
      "step_count": null,
      "mandatory_proof_count": 10,
      "coverage_complete": true,
      "step_ranges": [],
      "proof_units": [
        {
          "name": "paragraph_namespace",
          "kind": "namespace",
          "source_range": {
            "start": 0,
            "end": 41
          },
          "premise_range": {
            "start": 0,
            "end": 41
          },
          "hypothesis": "This document concerns Lumen token bench.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_declaration",
          "kind": "applicability",
          "source_range": {
            "start": 114,
            "end": 490
          },
          "premise_range": {
            "start": 114,
            "end": 490
          },
          "hypothesis": "The complete ordinary procedure applies to an ordinary unflagged run, not a postponed audit and requires all 4 instruction paragraphs in their stated order.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_requested_scope",
          "kind": "request_scope",
          "source_range": {
            "start": 0,
            "end": 490
          },
          "premise_range": {
            "start": 0,
            "end": 490
          },
          "hypothesis": "The complete procedure is for Lumen token bench.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "whole_method",
          "kind": "whole_method",
          "source_range": {
            "start": 492,
            "end": 811
          },
          "premise_range": {
            "start": 114,
            "end": 811
          },
          "hypothesis": "Every one of the 4 instruction paragraphs is required, in the stated order, for completion of the ordinary procedure.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_request_constraints",
          "kind": "bound_condition",
          "source_range": {
            "start": 114,
            "end": 811
          },
          "premise_range": {
            "start": 114,
            "end": 811
          },
          "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the entire ordinary procedure for the Lumen token bench, including prerequisites, parameters, prohibitions, and closure.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_1",
          "kind": "instruction",
          "source_range": {
            "start": 492,
            "end": 587
          },
          "premise_range": {
            "start": 492,
            "end": 587
          },
          "hypothesis": "The instructions require the following entire instruction: Before beginning an ordinary token run, obtain the signed card and check that the tray is open.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_2",
          "kind": "instruction",
          "source_range": {
            "start": 589,
            "end": 656
          },
          "premise_range": {
            "start": 589,
            "end": 656
          },
          "hypothesis": "The instructions require the following entire instruction: Place one token in the tray, with the marked edge facing the label.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_3",
          "kind": "prohibition",
          "source_range": {
            "start": 658,
            "end": 734
          },
          "premise_range": {
            "start": 658,
            "end": 734
          },
          "hypothesis": "The instructions require the following entire instruction: Do not remove a marked token or close the tray before the count is recorded.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_4",
          "kind": "instruction",
          "source_range": {
            "start": 736,
            "end": 811
          },
          "premise_range": {
            "start": 736,
            "end": 811
          },
          "hypothesis": "The instructions require the following entire instruction: Count both compartments, write both totals on the card, and close the tray.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_closure",
          "kind": "closure",
          "source_range": {
            "start": 813,
            "end": 1251
          },
          "premise_range": {
            "start": 813,
            "end": 1251
          },
          "hypothesis": "The ordinary procedure ends after exactly 4 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        }
      ],
      "required_inventory": {
        "contract": "procedure-required-inventory-v1",
        "document_id": "45f4bd3a-3fdf-4519-a05f-1f79ce7cbfe8",
        "document_version": 1,
        "content_hash": "9262522f3078bd43930aa2a679ba73cbdbc1dea36ecd2d3317cba5a82f4c8534",
        "extent": {
          "start": 492,
          "end": 811
        },
        "structure": "declared_paragraphs",
        "step_ranges": [],
        "units": [
          {
            "name": "paragraph_namespace",
            "kind": "namespace",
            "source_range": {
              "start": 0,
              "end": 41
            },
            "premise_range": {
              "start": 0,
              "end": 41
            },
            "hypothesis": "This document concerns Lumen token bench.",
            "step": null
          },
          {
            "name": "paragraph_declaration",
            "kind": "applicability",
            "source_range": {
              "start": 114,
              "end": 490
            },
            "premise_range": {
              "start": 114,
              "end": 490
            },
            "hypothesis": "The complete ordinary procedure applies to an ordinary unflagged run, not a postponed audit and requires all 4 instruction paragraphs in their stated order.",
            "step": null
          },
          {
            "name": "paragraph_requested_scope",
            "kind": "request_scope",
            "source_range": {
              "start": 0,
              "end": 490
            },
            "premise_range": {
              "start": 0,
              "end": 490
            },
            "hypothesis": "The complete procedure is for Lumen token bench.",
            "step": null
          },
          {
            "name": "whole_method",
            "kind": "whole_method",
            "source_range": {
              "start": 492,
              "end": 811
            },
            "premise_range": {
              "start": 114,
              "end": 811
            },
            "hypothesis": "Every one of the 4 instruction paragraphs is required, in the stated order, for completion of the ordinary procedure.",
            "step": null
          },
          {
            "name": "paragraph_request_constraints",
            "kind": "bound_condition",
            "source_range": {
              "start": 114,
              "end": 811
            },
            "premise_range": {
              "start": 114,
              "end": 811
            },
            "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the entire ordinary procedure for the Lumen token bench, including prerequisites, parameters, prohibitions, and closure.",
            "step": null
          },
          {
            "name": "paragraph_1",
            "kind": "instruction",
            "source_range": {
              "start": 492,
              "end": 587
            },
            "premise_range": {
              "start": 492,
              "end": 587
            },
            "hypothesis": "The instructions require the following entire instruction: Before beginning an ordinary token run, obtain the signed card and check that the tray is open.",
            "step": null
          },
          {
            "name": "paragraph_2",
            "kind": "instruction",
            "source_range": {
              "start": 589,
              "end": 656
            },
            "premise_range": {
              "start": 589,
              "end": 656
            },
            "hypothesis": "The instructions require the following entire instruction: Place one token in the tray, with the marked edge facing the label.",
            "step": null
          },
          {
            "name": "paragraph_3",
            "kind": "prohibition",
            "source_range": {
              "start": 658,
              "end": 734
            },
            "premise_range": {
              "start": 658,
              "end": 734
            },
            "hypothesis": "The instructions require the following entire instruction: Do not remove a marked token or close the tray before the count is recorded.",
            "step": null
          },
          {
            "name": "paragraph_4",
            "kind": "instruction",
            "source_range": {
              "start": 736,
              "end": 811
            },
            "premise_range": {
              "start": 736,
              "end": 811
            },
            "hypothesis": "The instructions require the following entire instruction: Count both compartments, write both totals on the card, and close the tray.",
            "step": null
          },
          {
            "name": "paragraph_closure",
            "kind": "closure",
            "source_range": {
              "start": 813,
              "end": 1251
            },
            "premise_range": {
              "start": 813,
              "end": 1251
            },
            "hypothesis": "The ordinary procedure ends after exactly 4 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
            "step": null
          }
        ],
        "structure_edges": [
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_namespace"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_requested_scope"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "whole_method"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_request_constraints"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_1"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_2"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_3"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_4"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_closure"
          }
        ],
        "declared_paragraphs": {
          "contract": "declared-paragraph-procedure-v1",
          "source_body": "Lumen token bench: current operation note\n\nThe activity owner is the records clerk.\n\nComplete ordinary procedure\n\nThe next four instruction paragraphs are the entire ordinary procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of ordinary procedure marker immediately after the fourth instruction paragraph. It applies to an ordinary unflagged run, not a postponed audit.\n\nBefore beginning an ordinary token run, obtain the signed card and check that the tray is open.\n\nPlace one token in the tray, with the marked edge facing the label.\n\nDo not remove a marked token or close the tray before the count is recorded.\n\nCount both compartments, write both totals on the card, and close the tray.\n\nEnd of ordinary procedure\n\nRecord governance commentary\n\nThe ordinary run is complete once the four preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.\n\nAfter the final paragraph, the signed record is stored in the station folder. Storage does not grant a recorder authority to destroy it.",
          "request_topic": "Lumen token bench",
          "request_original": "Give the entire ordinary procedure for the Lumen token bench, including prerequisites, parameters, prohibitions, and closure.",
          "scope": "Lumen token bench",
          "mode": "ordinary",
          "conditions": "an ordinary unflagged run, not a postponed audit",
          "declared_count": 4,
          "title_range": {
            "start": 0,
            "end": 41
          },
          "heading_range": {
            "start": 85,
            "end": 112
          },
          "declaration_range": {
            "start": 114,
            "end": 490
          },
          "paragraph_ranges": [
            {
              "start": 492,
              "end": 587
            },
            {
              "start": 589,
              "end": 656
            },
            {
              "start": 658,
              "end": 734
            },
            {
              "start": 736,
              "end": 811
            }
          ],
          "end_marker_range": {
            "start": 813,
            "end": 838
          },
          "governance_range": {
            "start": 840,
            "end": 1251
          }
        }
      },
      "structure_edges": [
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_namespace"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_requested_scope"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "whole_method"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_request_constraints"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_1"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_2"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_3"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_4"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_closure"
        }
      ],
      "raw_seed": {
        "proposal_id": "a1a3c2bc968febda700f6ca58c78dee70c29274bfd30f1984edceb9bfd4a12cb",
        "origin": "source_pattern",
        "chunk_id": "a8b0cb14-229c-403c-b70f-6e53f4edd850",
        "text": "Before beginning an ordinary token run, obtain the signed card and check that the tray is open.",
        "chunk_range": {
          "start": 492,
          "end": 587
        },
        "document_range": {
          "start": 492,
          "end": 587
        }
      },
      "fragments": [
        {
          "chunk_id": "a8b0cb14-229c-403c-b70f-6e53f4edd850",
          "chunk_start": 492,
          "chunk_end": 678,
          "document_start": 492,
          "document_end": 678
        },
        {
          "chunk_id": "291d52fd-e84b-4668-9802-e8b44919bd09",
          "chunk_start": 20,
          "chunk_end": 153,
          "document_start": 678,
          "document_end": 811
        }
      ]
    },
    "proposal": {
      "contract": "proposal-origin-v1",
      "proposal_id": "a1a3c2bc968febda700f6ca58c78dee70c29274bfd30f1984edceb9bfd4a12cb",
      "requirement_id": "r1",
      "origin": "source_pattern",
      "document_id": "45f4bd3a-3fdf-4519-a05f-1f79ce7cbfe8",
      "document_version": 1,
      "content_hash": "9262522f3078bd43930aa2a679ba73cbdbc1dea36ecd2d3317cba5a82f4c8534",
      "chunk_id": "a8b0cb14-229c-403c-b70f-6e53f4edd850",
      "chunk_range": {
        "start": 492,
        "end": 587
      },
      "document_range": {
        "start": 492,
        "end": 587
      },
      "text": "Before beginning an ordinary token run, obtain the signed card and check that the tray is open.",
      "pattern_id": "complete-declared-paragraph-procedure-v1",
      "grammar_version": "typed-source-patterns-v1",
      "qa_observation_id": null
    }
  },
  "single": {
    "evidence_kind": "Actual pure paragraph serializer; FAKE NI all-entailment/token12, no models",
    "proof": {
      "contract": "complete-immutable-procedure-v2",
      "status": "supported",
      "document_id": "f21504de-a1e3-5195-a9f2-795826f21ae8",
      "document_version": 1,
      "content_hash": "3034e3477b2d1284b3004eff8a0d5f3a4a8321481a7173d51396e3008388f290",
      "body_length": 784,
      "extent": {
        "start": 441,
        "end": 483
      },
      "closure": {
        "kind": "declared_paragraph_end",
        "end": 483,
        "boundary_range": {
          "start": 485,
          "end": 510
        }
      },
      "structure": "declared_paragraphs",
      "step_count": null,
      "mandatory_proof_count": 7,
      "coverage_complete": true,
      "step_ranges": [],
      "proof_units": [
        {
          "name": "paragraph_namespace",
          "kind": "namespace",
          "source_range": {
            "start": 0,
            "end": 35
          },
          "premise_range": {
            "start": 0,
            "end": 35
          },
          "hypothesis": "This document concerns Amber latch.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_declaration",
          "kind": "applicability",
          "source_range": {
            "start": 66,
            "end": 439
          },
          "premise_range": {
            "start": 66,
            "end": 439
          },
          "hypothesis": "The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_requested_scope",
          "kind": "request_scope",
          "source_range": {
            "start": 0,
            "end": 439
          },
          "premise_range": {
            "start": 0,
            "end": 439
          },
          "hypothesis": "The complete procedure is for Amber latch.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "whole_method",
          "kind": "whole_method",
          "source_range": {
            "start": 441,
            "end": 483
          },
          "premise_range": {
            "start": 66,
            "end": 483
          },
          "hypothesis": "Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_request_constraints",
          "kind": "bound_condition",
          "source_range": {
            "start": 66,
            "end": 483
          },
          "premise_range": {
            "start": 66,
            "end": 483
          },
          "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete standard procedure for the Amber latch.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_1",
          "kind": "instruction",
          "source_range": {
            "start": 441,
            "end": 483
          },
          "premise_range": {
            "start": 441,
            "end": 483
          },
          "hypothesis": "The instructions require the following entire instruction: Turn the latch and retain the signed card.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_closure",
          "kind": "closure",
          "source_range": {
            "start": 485,
            "end": 784
          },
          "premise_range": {
            "start": 485,
            "end": 784
          },
          "hypothesis": "The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        }
      ],
      "required_inventory": {
        "contract": "procedure-required-inventory-v1",
        "document_id": "f21504de-a1e3-5195-a9f2-795826f21ae8",
        "document_version": 1,
        "content_hash": "3034e3477b2d1284b3004eff8a0d5f3a4a8321481a7173d51396e3008388f290",
        "extent": {
          "start": 441,
          "end": 483
        },
        "structure": "declared_paragraphs",
        "step_ranges": [],
        "units": [
          {
            "name": "paragraph_namespace",
            "kind": "namespace",
            "source_range": {
              "start": 0,
              "end": 35
            },
            "premise_range": {
              "start": 0,
              "end": 35
            },
            "hypothesis": "This document concerns Amber latch.",
            "step": null
          },
          {
            "name": "paragraph_declaration",
            "kind": "applicability",
            "source_range": {
              "start": 66,
              "end": 439
            },
            "premise_range": {
              "start": 66,
              "end": 439
            },
            "hypothesis": "The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.",
            "step": null
          },
          {
            "name": "paragraph_requested_scope",
            "kind": "request_scope",
            "source_range": {
              "start": 0,
              "end": 439
            },
            "premise_range": {
              "start": 0,
              "end": 439
            },
            "hypothesis": "The complete procedure is for Amber latch.",
            "step": null
          },
          {
            "name": "whole_method",
            "kind": "whole_method",
            "source_range": {
              "start": 441,
              "end": 483
            },
            "premise_range": {
              "start": 66,
              "end": 483
            },
            "hypothesis": "Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.",
            "step": null
          },
          {
            "name": "paragraph_request_constraints",
            "kind": "bound_condition",
            "source_range": {
              "start": 66,
              "end": 483
            },
            "premise_range": {
              "start": 66,
              "end": 483
            },
            "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete standard procedure for the Amber latch.",
            "step": null
          },
          {
            "name": "paragraph_1",
            "kind": "instruction",
            "source_range": {
              "start": 441,
              "end": 483
            },
            "premise_range": {
              "start": 441,
              "end": 483
            },
            "hypothesis": "The instructions require the following entire instruction: Turn the latch and retain the signed card.",
            "step": null
          },
          {
            "name": "paragraph_closure",
            "kind": "closure",
            "source_range": {
              "start": 485,
              "end": 784
            },
            "premise_range": {
              "start": 485,
              "end": 784
            },
            "hypothesis": "The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
            "step": null
          }
        ],
        "structure_edges": [
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_namespace"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_requested_scope"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "whole_method"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_request_constraints"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_1"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_closure"
          }
        ],
        "declared_paragraphs": {
          "contract": "declared-paragraph-procedure-v1",
          "source_body": "Amber latch: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.",
          "request_topic": "Amber latch",
          "request_original": "Give the complete standard procedure for the Amber latch.",
          "scope": "Amber latch",
          "mode": "standard",
          "conditions": "a standard inspected run, not a postponed audit",
          "declared_count": 1,
          "title_range": {
            "start": 0,
            "end": 35
          },
          "heading_range": {
            "start": 37,
            "end": 64
          },
          "declaration_range": {
            "start": 66,
            "end": 439
          },
          "paragraph_ranges": [
            {
              "start": 441,
              "end": 483
            }
          ],
          "end_marker_range": {
            "start": 485,
            "end": 510
          },
          "governance_range": {
            "start": 512,
            "end": 784
          }
        }
      },
      "structure_edges": [
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_namespace"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_requested_scope"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "whole_method"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_request_constraints"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_1"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_closure"
        }
      ],
      "raw_seed": {
        "proposal_id": "4db20d691d1952ea86f23c3b54a81f95ae6d5b6fac0085a44430604c9e923741",
        "origin": "source_pattern",
        "chunk_id": "e101e938-1019-5f7e-8968-d7b43a5c92f1",
        "text": "Turn the latch and retain the signed card.",
        "chunk_range": {
          "start": 7,
          "end": 49
        },
        "document_range": {
          "start": 441,
          "end": 483
        }
      },
      "fragments": [
        {
          "chunk_id": "e101e938-1019-5f7e-8968-d7b43a5c92f1",
          "chunk_start": 7,
          "chunk_end": 49,
          "document_start": 441,
          "document_end": 483
        }
      ]
    },
    "proposal": {
      "contract": "proposal-origin-v1",
      "proposal_id": "4db20d691d1952ea86f23c3b54a81f95ae6d5b6fac0085a44430604c9e923741",
      "requirement_id": "r1",
      "origin": "source_pattern",
      "document_id": "f21504de-a1e3-5195-a9f2-795826f21ae8",
      "document_version": 1,
      "content_hash": "3034e3477b2d1284b3004eff8a0d5f3a4a8321481a7173d51396e3008388f290",
      "chunk_id": "e101e938-1019-5f7e-8968-d7b43a5c92f1",
      "chunk_range": {
        "start": 7,
        "end": 49
      },
      "document_range": {
        "start": 441,
        "end": 483
      },
      "text": "Turn the latch and retain the signed card.",
      "pattern_id": "complete-declared-paragraph-procedure-v1",
      "grammar_version": "typed-source-patterns-v1",
      "qa_observation_id": null
    }
  },
  "unicode": {
    "evidence_kind": "Actual pure paragraph serializer; FAKE NI all-entailment/token12, no models",
    "proof": {
      "contract": "complete-immutable-procedure-v2",
      "status": "supported",
      "document_id": "f5678ae4-8d63-51f2-99e2-3c807332b1b4",
      "document_version": 1,
      "content_hash": "855268d94c228ae394390a4ec4560ed825af319d98f09688397e4969af46808d",
      "body_length": 802,
      "extent": {
        "start": 431,
        "end": 507
      },
      "closure": {
        "kind": "declared_paragraph_end",
        "end": 507,
        "boundary_range": {
          "start": 509,
          "end": 532
        }
      },
      "structure": "declared_paragraphs",
      "step_count": null,
      "mandatory_proof_count": 8,
      "coverage_complete": true,
      "step_ranges": [],
      "proof_units": [
        {
          "name": "paragraph_namespace",
          "kind": "namespace",
          "source_range": {
            "start": 0,
            "end": 37
          },
          "premise_range": {
            "start": 0,
            "end": 37
          },
          "hypothesis": "This document concerns Quartz \ud83d\udcc4 rack.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_declaration",
          "kind": "applicability",
          "source_range": {
            "start": 66,
            "end": 429
          },
          "premise_range": {
            "start": 66,
            "end": 429
          },
          "hypothesis": "The complete normal procedure applies to a normal inspected run, not a postponed audit and requires all 2 instruction paragraphs in their stated order.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_requested_scope",
          "kind": "request_scope",
          "source_range": {
            "start": 0,
            "end": 429
          },
          "premise_range": {
            "start": 0,
            "end": 429
          },
          "hypothesis": "The complete procedure is for Quartz \ud83d\udcc4 rack.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "whole_method",
          "kind": "whole_method",
          "source_range": {
            "start": 431,
            "end": 507
          },
          "premise_range": {
            "start": 66,
            "end": 507
          },
          "hypothesis": "Every one of the 2 instruction paragraphs is required, in the stated order, for completion of the normal procedure.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_request_constraints",
          "kind": "bound_condition",
          "source_range": {
            "start": 66,
            "end": 507
          },
          "premise_range": {
            "start": 66,
            "end": 507
          },
          "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete normal procedure for the Quartz \ud83d\udcc4 rack.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_1",
          "kind": "instruction",
          "source_range": {
            "start": 431,
            "end": 467
          },
          "premise_range": {
            "start": 431,
            "end": 467
          },
          "hypothesis": "The instructions require the following entire instruction: Place the \ud83d\udcc4 card on the marked tray.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_2",
          "kind": "prohibition",
          "source_range": {
            "start": 469,
            "end": 507
          },
          "premise_range": {
            "start": 469,
            "end": 507
          },
          "hypothesis": "The instructions require the following entire instruction: Never reopen the rack after the check.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        },
        {
          "name": "paragraph_closure",
          "kind": "closure",
          "source_range": {
            "start": 509,
            "end": 802
          },
          "premise_range": {
            "start": 509,
            "end": 802
          },
          "hypothesis": "The normal procedure ends after exactly 2 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
          "label": "entailment",
          "logits": [
            -5.0,
            5.0,
            -5.0
          ],
          "entailment_margin": 10.0,
          "supported": true,
          "pair_tokens": 12
        }
      ],
      "required_inventory": {
        "contract": "procedure-required-inventory-v1",
        "document_id": "f5678ae4-8d63-51f2-99e2-3c807332b1b4",
        "document_version": 1,
        "content_hash": "855268d94c228ae394390a4ec4560ed825af319d98f09688397e4969af46808d",
        "extent": {
          "start": 431,
          "end": 507
        },
        "structure": "declared_paragraphs",
        "step_ranges": [],
        "units": [
          {
            "name": "paragraph_namespace",
            "kind": "namespace",
            "source_range": {
              "start": 0,
              "end": 37
            },
            "premise_range": {
              "start": 0,
              "end": 37
            },
            "hypothesis": "This document concerns Quartz \ud83d\udcc4 rack.",
            "step": null
          },
          {
            "name": "paragraph_declaration",
            "kind": "applicability",
            "source_range": {
              "start": 66,
              "end": 429
            },
            "premise_range": {
              "start": 66,
              "end": 429
            },
            "hypothesis": "The complete normal procedure applies to a normal inspected run, not a postponed audit and requires all 2 instruction paragraphs in their stated order.",
            "step": null
          },
          {
            "name": "paragraph_requested_scope",
            "kind": "request_scope",
            "source_range": {
              "start": 0,
              "end": 429
            },
            "premise_range": {
              "start": 0,
              "end": 429
            },
            "hypothesis": "The complete procedure is for Quartz \ud83d\udcc4 rack.",
            "step": null
          },
          {
            "name": "whole_method",
            "kind": "whole_method",
            "source_range": {
              "start": 431,
              "end": 507
            },
            "premise_range": {
              "start": 66,
              "end": 507
            },
            "hypothesis": "Every one of the 2 instruction paragraphs is required, in the stated order, for completion of the normal procedure.",
            "step": null
          },
          {
            "name": "paragraph_request_constraints",
            "kind": "bound_condition",
            "source_range": {
              "start": 66,
              "end": 507
            },
            "premise_range": {
              "start": 66,
              "end": 507
            },
            "hypothesis": "These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete normal procedure for the Quartz \ud83d\udcc4 rack.",
            "step": null
          },
          {
            "name": "paragraph_1",
            "kind": "instruction",
            "source_range": {
              "start": 431,
              "end": 467
            },
            "premise_range": {
              "start": 431,
              "end": 467
            },
            "hypothesis": "The instructions require the following entire instruction: Place the \ud83d\udcc4 card on the marked tray.",
            "step": null
          },
          {
            "name": "paragraph_2",
            "kind": "prohibition",
            "source_range": {
              "start": 469,
              "end": 507
            },
            "premise_range": {
              "start": 469,
              "end": 507
            },
            "hypothesis": "The instructions require the following entire instruction: Never reopen the rack after the check.",
            "step": null
          },
          {
            "name": "paragraph_closure",
            "kind": "closure",
            "source_range": {
              "start": 509,
              "end": 802
            },
            "premise_range": {
              "start": 509,
              "end": 802
            },
            "hypothesis": "The normal procedure ends after exactly 2 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.",
            "step": null
          }
        ],
        "structure_edges": [
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_namespace"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_requested_scope"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "whole_method"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_request_constraints"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_1"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_2"
          },
          {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": "paragraph_closure"
          }
        ],
        "declared_paragraphs": {
          "contract": "declared-paragraph-procedure-v1",
          "source_body": "Quartz \ud83d\udcc4 rack: current operation note\n\nComplete normal procedure\n\nThe next 2 instruction paragraphs are the entire normal procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of normal procedure marker immediately after the 2nd instruction paragraph. It applies to a normal inspected run, not a postponed audit.\n\nPlace the \ud83d\udcc4 card on the marked tray.\n\nNever reopen the rack after the check.\n\nEnd of normal procedure\n\nRecord governance commentary\n\nThe normal run is complete once the 2 preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.",
          "request_topic": "Quartz \ud83d\udcc4 rack",
          "request_original": "Give the complete normal procedure for the Quartz \ud83d\udcc4 rack.",
          "scope": "Quartz \ud83d\udcc4 rack",
          "mode": "normal",
          "conditions": "a normal inspected run, not a postponed audit",
          "declared_count": 2,
          "title_range": {
            "start": 0,
            "end": 37
          },
          "heading_range": {
            "start": 39,
            "end": 64
          },
          "declaration_range": {
            "start": 66,
            "end": 429
          },
          "paragraph_ranges": [
            {
              "start": 431,
              "end": 467
            },
            {
              "start": 469,
              "end": 507
            }
          ],
          "end_marker_range": {
            "start": 509,
            "end": 532
          },
          "governance_range": {
            "start": 534,
            "end": 802
          }
        }
      },
      "structure_edges": [
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_namespace"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_requested_scope"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "whole_method"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_request_constraints"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_1"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_2"
        },
        {
          "name": "paragraph_governance",
          "source": "paragraph_declaration",
          "target": "paragraph_closure"
        }
      ],
      "raw_seed": {
        "proposal_id": "6bcbd89a190f72271eb6d8f40935af78694fe0eaae968bc4665349e5c08e083c",
        "origin": "source_pattern",
        "chunk_id": "a67083df-3181-5553-84b3-c524465f595d",
        "text": "Place the \ud83d\udcc4 card on the marked tray.",
        "chunk_range": {
          "start": 7,
          "end": 43
        },
        "document_range": {
          "start": 431,
          "end": 467
        }
      },
      "fragments": [
        {
          "chunk_id": "a67083df-3181-5553-84b3-c524465f595d",
          "chunk_start": 7,
          "chunk_end": 83,
          "document_start": 431,
          "document_end": 507
        }
      ]
    },
    "proposal": {
      "contract": "proposal-origin-v1",
      "proposal_id": "6bcbd89a190f72271eb6d8f40935af78694fe0eaae968bc4665349e5c08e083c",
      "requirement_id": "r1",
      "origin": "source_pattern",
      "document_id": "f5678ae4-8d63-51f2-99e2-3c807332b1b4",
      "document_version": 1,
      "content_hash": "855268d94c228ae394390a4ec4560ed825af319d98f09688397e4969af46808d",
      "chunk_id": "a67083df-3181-5553-84b3-c524465f595d",
      "chunk_range": {
        "start": 7,
        "end": 43
      },
      "document_range": {
        "start": 431,
        "end": 467
      },
      "text": "Place the \ud83d\udcc4 card on the marked tray.",
      "pattern_id": "complete-declared-paragraph-procedure-v1",
      "grammar_version": "typed-source-patterns-v1",
      "qa_observation_id": null
    }
  }
};

function declaredRecord(name: keyof typeof paragraphProtocols = "protocol") {
  const fixture = structuredClone(paragraphProtocols[name]), proof = fixture.proof, proposal = fixture.proposal;
  const descriptor = proof.required_inventory.declared_paragraphs;
  return {
    mode: "reader", contract: "requirement-evidence-v2", evidence_profile: recordedProfile("qa_plus_source_patterns_v1", "literal_v1"),
    evidence_support: { minimum_entailment_margin: 0 }, discovery_lineage: { status: "recorded", valid: true },
    proposals: [proposal], selected_proposal_ids: [proposal.proposal_id],
    qa_observations: [{ observation_id: "explicit-fixture-qa-null", requirement_id: "r1", chunk_id: proposal.chunk_id, span: null, diagnostics: { decision: "no_answer" }, reader: { model: "FAKE protocol reader" }, question: descriptor.request_original }],
    pattern_observations: [{ proposal: { ...proposal }, origin: "source_pattern", decision: "supported", support: { label: "entailment", supported: true, pair_tokens: 12 } }],
    requirements: [{ id: "r1", kind: "procedure", original_text: descriptor.request_original, status: "supported", procedure_completeness: proof,
      witnesses: [{ document_id: proposal.document_id, document_version: proposal.document_version, content_hash: proposal.content_hash, chunk_id: proposal.chunk_id,
        value: Array.from(descriptor.source_body).slice(proof.extent.start, proof.extent.end).join(""), span: { ...proposal.chunk_range, text: proposal.text },
        document_range: { ...proposal.document_range }, proposals: [{ ...proposal }] }] }],
  };
}
type DeclaredRecord = ReturnType<typeof declaredRecord>;
function updateDeclaredHash(record: DeclaredRecord) {
  const proof = record.requirements[0].procedure_completeness;
  const hash = createHash("sha256").update(proof.required_inventory.declared_paragraphs.source_body, "utf8").digest("hex");
  proof.content_hash = hash; proof.required_inventory.content_hash = hash; record.proposals[0].content_hash = hash;
  record.requirements[0].witnesses[0].content_hash = hash; record.requirements[0].witnesses[0].proposals[0].content_hash = hash;
}
function expectDeclaredUnknown() {
  expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
}

describe("declared paragraph evidence (explicit fake NI/token12)", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each(["protocol", "single", "unicode"] as const)("recognizes the finalized fake-NI declared paragraph protocol: %s", async (name) => {
    const record = declaredRecord(name), proof = record.requirements[0].procedure_completeness;
    const count = proof.required_inventory.declared_paragraphs.declared_count, parts = proof.fragments.length;
    render(<AnswerSelectionEvidence value={record} />);
    expect(await screen.findByText(`Full source extent verified · ${count} declared ${count === 1 ? "paragraph" : "paragraphs"} · ${parts} cited ${parts === 1 ? "passage" : "passages"}`)).toBeVisible();
    expect(screen.getByText("Recorded source-body hash: matched")).toBeInTheDocument();
    expect(screen.queryByText(/\b0 steps\b|\b4 steps\b/)).not.toBeInTheDocument();
  });
  it("keeps a single complete cover and matched optional workspace identity valid", async () => {
    const record = declaredRecord(), proof = record.requirements[0].procedure_completeness, first = proof.fragments[0];
    proof.fragments = [{ ...first, chunk_end: first.chunk_start + proof.extent.end - proof.extent.start, document_end: proof.extent.end }];
    (proof as Record<string, unknown>).workspace_id = "workspace";
    (proof.required_inventory as Record<string, unknown>).workspace_id = "workspace";
    render(<AnswerSelectionEvidence value={record} />);
    expect(await screen.findByText("Full source extent verified · 4 declared paragraphs · 1 cited passage")).toBeVisible();
  });
  it("preserves an original QA seed with actual terminal punctuation omitted", async () => {
    const original = declaredRecord("unicode"), row = original.requirements[0], proof = row.procedure_completeness;
    const source = original.proposals[0], text = source.text.slice(0, -1);
    const proposal = { ...source, origin: "qa_reader", pattern_id: null, grammar_version: null, qa_observation_id: "fixture-accepted-qa", text,
      chunk_range: { ...source.chunk_range, end: source.chunk_range.end - 1 }, document_range: { ...source.document_range, end: source.document_range.end - 1 } };
    const record = { ...original, evidence_profile: recordedProfile("qa_only_v1", "literal_v1"), proposals: [proposal], pattern_observations: [],
      qa_observations: [{ ...original.qa_observations[0], observation_id: "fixture-accepted-qa", span: { ...proposal.chunk_range, text } }],
      requirements: [{ ...row, procedure_completeness: { ...proof, raw_seed: { ...proof.raw_seed, origin: "qa_reader", text, chunk_range: proposal.chunk_range, document_range: proposal.document_range } },
        witnesses: [{ ...row.witnesses[0], proposals: [{ ...proposal }] }] }] };
    render(<AnswerSelectionEvidence value={record} />);
    expect(await screen.findByText("Full source extent verified · 2 declared paragraphs · 1 cited passage")).toBeVisible();
    expect(screen.getByText("Selected discovery: QA reader")).toBeVisible();
  });
  it.each(["count", "order", "truncated paragraph", "lost paragraph", "lost closure proof", "lost scope", "extra unit", "closure kind", "closure boundary", "governance range", "scope", "request", "invented steps", "inventory step", "assessed step", "missing inventory", "missing descriptor", "unknown subtype", "unknown pattern", "seed prefix", "later seed", "seed literal forgery", "cover gap", "carrier translation", "workspace mismatch", "changed hypothesis", "unsupported pair", "unmeasured pair", "zero margin"])("rejects contradictory paragraph proof: %s", async (variant) => {
    const record = declaredRecord(), proof = record.requirements[0].procedure_completeness, inventory = proof.required_inventory, descriptor = inventory.declared_paragraphs;
    const assessed = proof.proof_units.find((unit) => unit.name === "paragraph_2")!, required = inventory.units.find((unit) => unit.name === "paragraph_2")!;
    if (variant === "count") descriptor.declared_count++;
    else if (variant === "order") descriptor.paragraph_ranges.reverse();
    else if (variant === "truncated paragraph") { descriptor.paragraph_ranges[1].end--; assessed.source_range.end--; assessed.premise_range.end--; required.source_range.end--; required.premise_range.end--; }
    else if (["lost paragraph", "lost closure proof", "lost scope"].includes(variant)) {
      const name = variant === "lost paragraph" ? "paragraph_2" : variant === "lost scope" ? "paragraph_requested_scope" : "paragraph_closure";
      proof.proof_units = proof.proof_units.filter((unit) => unit.name !== name); inventory.units = inventory.units.filter((unit) => unit.name !== name);
      proof.structure_edges = proof.structure_edges.filter((edge) => edge.target !== name); inventory.structure_edges = inventory.structure_edges.filter((edge) => edge.target !== name); proof.mandatory_proof_count--;
    } else if (variant === "extra unit") { proof.proof_units.push({ ...assessed, name: "extra" }); inventory.units.push({ ...required, name: "extra" }); proof.mandatory_proof_count++; }
    else if (variant === "closure kind") proof.closure.kind = "independent_section";
    else if (variant === "closure boundary") proof.closure.boundary_range.start++;
    else if (variant === "governance range") descriptor.governance_range.end--;
    else if (variant === "scope") descriptor.scope = "Another activity";
    else if (variant === "request") descriptor.request_original = "Give a different procedure.";
    else if (variant === "invented steps") (proof as Record<string, unknown>).step_count = 4;
    else if (variant === "inventory step") (required as Record<string, unknown>).step = 1;
    else if (variant === "assessed step") (assessed as Record<string, unknown>).step = 1;
    else if (variant === "missing inventory") (proof as Record<string, unknown>).required_inventory = null;
    else if (variant === "missing descriptor") (inventory as Record<string, unknown>).declared_paragraphs = null;
    else if (variant === "unknown subtype") descriptor.contract = "future";
    else if (variant === "unknown pattern") { record.proposals[0].pattern_id = "complete-numbered-procedure-v1"; record.requirements[0].witnesses[0].proposals[0].pattern_id = "complete-numbered-procedure-v1"; }
    else if (variant === "seed prefix" || variant === "later seed" || variant === "seed literal forgery") {
      const range = variant === "later seed" ? descriptor.paragraph_ranges[1] : { start: proof.raw_seed.document_range.start, end: variant === "seed prefix" ? proof.raw_seed.document_range.start + 6 : proof.raw_seed.document_range.end };
      const text = variant === "seed literal forgery" ? "X" + proof.raw_seed.text.slice(1) : Array.from(descriptor.source_body).slice(range.start, range.end).join("");
      Object.assign(proof.raw_seed, { text, document_range: { ...range }, chunk_range: { ...range } });
      Object.assign(record.proposals[0], { text, document_range: { ...range }, chunk_range: { ...range } });
      const witness = record.requirements[0].witnesses[0]; witness.proposals = [{ ...record.proposals[0] }]; witness.span = { ...range, text }; witness.document_range = { ...range };
    } else if (variant === "cover gap") proof.fragments[1].document_start++;
    else if (variant === "carrier translation") proof.fragments[0].chunk_start++;
    else if (variant === "workspace mismatch") { (proof as Record<string, unknown>).workspace_id = "one"; (inventory as Record<string, unknown>).workspace_id = "two"; }
    else if (variant === "changed hypothesis") { assessed.hypothesis = "A different instruction."; required.hypothesis = assessed.hypothesis; }
    else if (variant === "unsupported pair") assessed.supported = false;
    else if (variant === "unmeasured pair") assessed.pair_tokens = 0;
    else assessed.entailment_margin = 0;
    render(<AnswerSelectionEvidence value={record} />);
    await screen.findByText(variant === "missing inventory" || variant === "missing descriptor" ? "Recorded source-body hash: unavailable" : "Recorded source-body hash: matched");
    expectDeclaredUnknown();
  });
  it.each(["declaration count", "governance count", "closure marker", "governing prelude", "reversed applicability", "unexpected namespace suffix", "later namespace line"])("checks source text independently of a coherent new hash: %s", async (variant) => {
    const record = declaredRecord(), proof = record.requirements[0].procedure_completeness, descriptor = proof.required_inventory.declared_paragraphs;
    if (variant === "declaration count") descriptor.source_body = descriptor.source_body.replace("The next four", "The next five");
    else if (variant === "governance count") descriptor.source_body = descriptor.source_body.replace("once the four", "once the five");
    else if (variant === "closure marker") descriptor.source_body = descriptor.source_body.replace("End of ordinary procedure\n", "End of standard procedure\n");
    else if (variant === "governing prelude") descriptor.source_body = descriptor.source_body.replace("The activity owner is the records clerk.", "The activity owner must keep the card.  ");
    else if (variant === "unexpected namespace suffix") descriptor.source_body = descriptor.source_body.replace("current operation note", "unsupported heading xx");
    else if (variant === "later namespace line") descriptor.source_body = descriptor.source_body.replace("current operation note", "operation note\nDo it..");
    else {
      descriptor.source_body = descriptor.source_body.replace(descriptor.conditions, "a postponed audit, not an ordinary unflagged run");
      descriptor.conditions = "a postponed audit, not an ordinary unflagged run";
      for (const units of [proof.proof_units, proof.required_inventory.units]) units.find((unit) => unit.name === "paragraph_declaration")!.hypothesis = "The complete ordinary procedure applies to a postponed audit, not an ordinary unflagged run and requires all 4 instruction paragraphs in their stated order.";
    }
    updateDeclaredHash(record); render(<AnswerSelectionEvidence value={record} />);
    await screen.findByText("Recorded source-body hash: matched"); expectDeclaredUnknown();
  });
  it.each(["unavailable", "mismatch", "rejected"] as const)("keeps a %s Web Crypto check unverified", async (variant) => {
    if (variant === "unavailable") vi.stubGlobal("crypto", {});
    else vi.stubGlobal("crypto", { subtle: { digest: variant === "mismatch" ? vi.fn(async () => new Uint8Array(32).buffer) : vi.fn(async () => { throw new Error("Unavailable"); }) } });
    render(<AnswerSelectionEvidence value={declaredRecord()} />);
    await screen.findByText(`Recorded source-body hash: ${variant === "rejected" ? "unavailable" : variant}`); expectDeclaredUnknown();
  });
  it("does not normalize an unpaired UTF-16 surrogate into a hash-matched source body", async () => {
    const record = declaredRecord("unicode"), descriptor = record.requirements[0].procedure_completeness.required_inventory.declared_paragraphs;
    descriptor.source_body = descriptor.source_body.replace("\u{1F4C4}", "\uD800");
    updateDeclaredHash(record);
    const digest = vi.spyOn(webcrypto.subtle, "digest");
    render(<AnswerSelectionEvidence value={record} />);
    await screen.findByText("Recorded source-body hash: unavailable");
    expect(digest).not.toHaveBeenCalled(); expectDeclaredUnknown();
  });
  it("cannot publish an obsolete hash after reversed promise completion and source change", async () => {
    const pending: ((value: ArrayBuffer) => void)[] = [];
    const digest = vi.fn(() => new Promise<ArrayBuffer>((resolve) => pending.push(resolve)));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const first = declaredRecord(), second = declaredRecord("unicode"), view = render(<AnswerSelectionEvidence value={first} />);
    view.rerender(<AnswerSelectionEvidence value={second} />);
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(2));
    expectDeclaredUnknown();
    const bytes = (record: DeclaredRecord) => Uint8Array.from(Buffer.from(record.requirements[0].procedure_completeness.content_hash, "hex")).buffer;
    await act(async () => { pending[1](bytes(second)); });
    expect(await screen.findByText("Full source extent verified · 2 declared paragraphs · 1 cited passage")).toBeVisible();
    await act(async () => { pending[0](bytes(first)); });
    expect(screen.getByText("Full source extent verified · 2 declared paragraphs · 1 cited passage")).toBeVisible();
    expect(screen.queryByText(/4 declared paragraphs/)).not.toBeInTheDocument();
  });
  it("invalidates a completed hash for a new run/profile even with the same body and expected hash", async () => {
    const pending: ((value: ArrayBuffer) => void)[] = [];
    const digest = vi.fn(() => new Promise<ArrayBuffer>((resolve) => pending.push(resolve)));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const first = declaredRecord(), view = render(<AnswerSelectionEvidence value={first} />);
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(1));
    const bytes = Uint8Array.from(Buffer.from(first.requirements[0].procedure_completeness.content_hash, "hex")).buffer;
    await act(async () => { pending[0](bytes); });
    await screen.findByText("Full source extent verified · 4 declared paragraphs · 2 cited passages");
    const next = { ...first, run_id: "another-run", evidence_profile: { ...first.evidence_profile, role_scope_policy: "ordinary_session_activity_v1" } };
    view.rerender(<AnswerSelectionEvidence value={next} />);
    expectDeclaredUnknown(); expect(screen.getByText("Recorded source-body hash: pending")).toBeInTheDocument();
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(2));
    await act(async () => { pending[1](bytes); });
    expect(await screen.findByText("Full source extent verified · 4 declared paragraphs · 2 cited passages")).toBeVisible();
  });
});

describe("recorded witness and role identity consistency", () => {
  it.each(["local range outside witness", "document range shift", "witness document shift", "witness local shift", "literal substitution", "value substitution", "missing document mapping", "wrong witness text length"])("rejects %s despite agreeing proposal copies", (variant) => {
    const record = profiledRecord(), proposal = record.proposals[0], witness = record.requirements[0].witnesses[0];
    if (variant === "local range outside witness") proposal.chunk_range = { start: 60, end: 78 };
    else if (variant === "document range shift") proposal.document_range = { start: 500, end: 518 };
    else if (variant === "witness document shift") witness.document_range = { start: 500, end: 541 };
    else if (variant === "witness local shift") witness.span = { ...witness.span, start: 500, end: 541 };
    else if (variant === "literal substitution") proposal.text = "The filing officer";
    else if (variant === "value substitution") witness.value = "A different unsupported role";
    else if (variant === "missing document mapping") delete (witness as Record<string, unknown>).document_range;
    else { witness.span.end = 40; witness.document_range.end = 40; }
    witness.proposals = [{ ...proposal }];
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it("accepts a literal proposal inside a larger source-bound witness value", () => {
    const record = profiledRecord(), proposal = record.proposals[0], witness = record.requirements[0].witnesses[0];
    Object.assign(proposal, { text: "steward", chunk_range: { start: 11, end: 18 }, document_range: { start: 111, end: 118 } });
    witness.document_range = { start: 100, end: 141 }; witness.proposals = [{ ...proposal }];
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
  });
  it.each([false, true])("uses witness Unicode codepoint offsets rather than UTF-16 indices, corrupted: %s", (corrupted) => {
    const record = profiledRecord(), proposal = record.proposals[0], witness = record.requirements[0].witnesses[0];
    Object.assign(proposal, { chunk_range: { start: corrupted ? 12 : 11, end: corrupted ? 30 : 29 }, document_range: { start: corrupted ? 112 : 111, end: corrupted ? 130 : 129 } });
    witness.span = { start: 10, end: 36, text: "\u{1F4C4}The record steward signs." };
    witness.document_range = { start: 110, end: 136 }; witness.proposals = [{ ...proposal }];
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText(corrupted ? "0 of 1 requirements supported" : "1 of 1 requirements supported")).toBeInTheDocument();
  });
  it.each(["full clause", "omitted punctuation", "Python padding"])("preserves original QA procedure seed with accurately mapped witness: %s", (variant) => {
    const record = profiledProcedure(), row = record.requirements[0], proof = row.procedure_completeness, witness = row.witnesses[0];
    const text = variant === "Python padding" ? "\u0085Copy it.\u001C" : variant === "omitted punctuation" ? "Copy it" : "Copy it.";
    const range = { start: variant === "Python padding" ? 19 : 20, end: variant === "Python padding" ? 29 : variant === "omitted punctuation" ? 27 : 28 };
    const proposal = { ...record.proposals[0], origin: "qa_reader", pattern_id: null, grammar_version: null, qa_observation_id: "qa-1", text, chunk_range: { ...range }, document_range: { ...range } };
    record.proposals = [proposal]; witness.proposals = [{ ...proposal }];
    record.evidence_profile = recordedProfile("qa_only_v1", "literal_v1"); record.pattern_observations = [];
    record.qa_observations[0] = { ...record.qa_observations[0], chunk_id: "first", span: { ...range, text }, question: row.original_text };
    proof.raw_seed = { chunk_id: "first", origin: "qa_reader", proposal_id: proposal.proposal_id, text, chunk_range: { ...range }, document_range: { ...range } };
    if (variant === "Python padding") {
      proof.step_ranges[0].start = 18; proof.required_inventory.step_ranges[0].start = 18;
      proof.proof_units.find((unit) => unit.name === "step-1")!.premise_range.start = 18;
      proof.required_inventory.units.find((unit) => unit.name === "step-1")!.premise_range.start = 18;
      witness.span = { start: 18, end: 30, text: " \u0085Copy it.\u001C " }; witness.document_range = { start: 18, end: 30 };
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
    expect(screen.getByText("Selected discovery: QA reader")).toBeVisible();
  });
  it.each(["basis", "kind", "original_text", "input_range", "prepared_question", "effective_target", "source_workspace"])("rejects a contradictory present role identity field: %s", (field) => {
    const record = activityRecord(), role: Record<string, unknown> = record.requirements[0].role_scope_interpretation;
    if (field === "basis") role.basis = "documented_session_assignment";
    else if (field === "kind") role.kind = "deputy";
    else if (field === "original_text") role.original_text = "Who leads another activity?";
    else if (field === "input_range") role.input_range = { start: 5, end: 20 };
    else if (field === "prepared_question") role.prepared_question = "Who leads another activity?";
    else if (field === "effective_target") role.effective_target = "Another activity";
    else role.source_workspace = "another workspace";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.getByText("Role-scope metadata invalid")).toBeVisible();
    expect(screen.getByText(role.disclosure as string)).not.toBeVisible();
  });
  it("accepts matching current role identity and an independently captured workspace constraint", () => {
    const record = activityRecord(), row = record.requirements[0];
    row.source_workspace = "workspace"; row.role_scope_interpretation.source_workspace = "workspace";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.getByText(row.role_scope_interpretation.disclosure)).toBeVisible();
  });
  it.each(["input_range", "prepared_question", "source_workspace"])("does not invent a missing independent role mapping: %s", (field) => {
    const record = activityRecord(), row = record.requirements[0];
    if (field === "source_workspace") row.role_scope_interpretation.source_workspace = "workspace";
    delete (row as Record<string, unknown>)[field];
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.getByText("Role-scope metadata invalid")).toBeVisible();
  });
  it("does not replace an original workspace constraint with a null interpretation", () => {
    const record = activityRecord(); record.requirements[0].source_workspace = "workspace";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it("does not retroactively require absent optional identity fields in an older recorded interpretation", () => {
    const record = activityRecord(), role: Record<string, unknown> = record.requirements[0].role_scope_interpretation;
    for (const field of ["basis", "kind", "original_text", "input_range", "prepared_question", "effective_target", "source_workspace"]) delete role[field];
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
  });
  it("keeps malformed present role identity unknown without rendering an object", () => {
    const record = activityRecord();
    (record.requirements[0].role_scope_interpretation as Record<string, unknown>).prepared_question = { toString: null };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Role-scope metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it("preserves the qualified requested target for a documented direct session assignment", () => {
    const record = activityRecord(), row = record.requirements[0], role = row.role_scope_interpretation;
    const question = "Who leads ordinary Meridian review session?";
    const changed = { ...record, requirements: [{ ...row, prepared_question: question, role_scope_interpretation: { ...role, effective_scope: "session", activity_fallback: false, disclosure: null, basis: "documented_session_assignment", effective_target: role.requested_scope, prepared_question: question } }] };
    render(<AnswerSelectionEvidence value={changed} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText(/^Activity scope:/)).not.toBeInTheDocument();
  });
});

describe("recorded extraction profile", () => {
  it("shows source-pattern discovery after actual recorded QA abstention without calling it QA acceptance", () => {
    render(<AnswerSelectionEvidence value={profiledRecord()} />);
    expect(screen.getByRole("heading", { name: "Composite source extraction" })).toBeVisible();
    expect(screen.getByText("Selected discovery: typed source pattern")).toBeVisible();
    expect(screen.getByText("QA reader abstained on 1 recorded attempt.")).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    const details = screen.getByText("Evidence discovery details").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText("literal-lead-deputy-v1")).toBeInTheDocument();
    expect(within(details).getByText(/document · version 1 · chunk chunk/)).toBeInTheDocument();
    expect(within(details).getByText("Pattern support decision: supported")).toBeInTheDocument();
    expect(screen.queryByText(/QA accepted|Recorded QA span:/)).not.toBeInTheDocument();
  });
  it("shows a recorded QA-only profile and its actual selected QA span", () => {
    render(<AnswerSelectionEvidence value={profiledRecord("qa_reader")} />);
    expect(screen.getByRole("heading", { name: "Local QA-only extraction" })).toBeVisible();
    expect(screen.getByText("Selected discovery: QA reader")).toBeVisible();
    expect(screen.getByText("Recorded QA span: The record steward")).toBeInTheDocument();
    expect(screen.queryByText(/QA reader abstained|Selected discovery: typed source pattern/)).not.toBeInTheDocument();
  });
  it("keeps an explicit recorded QA abstention visible when discovery metadata is invalid", () => {
    const record = profiledRecord(); record.proposals[0].origin = "future";
    record.requirements[0].witnesses[0].proposals[0].origin = "future";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("Recorded QA abstention (discovery metadata invalid)")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it("distinguishes mixed selected origins while preserving an independent QA abstention", () => {
    const record = profiledRecord(), qa = profiledRecord("qa_reader");
    const proposal = { ...qa.proposals[0], proposal_id: "proposal-2", qa_observation_id: "qa-2" };
    record.proposals.push(proposal); record.selected_proposal_ids.push(proposal.proposal_id);
    record.qa_observations.push({ ...qa.qa_observations[0], observation_id: "qa-2" });
    record.requirements[0].witnesses[0].proposals.push({ ...proposal });
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Selected discovery: QA reader and typed source pattern")).toBeVisible();
    expect(screen.getByText("QA reader abstained on 1 recorded attempt.")).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
  });
  it.each(["unknown origin", "missing origin", "QA forgery", "pattern in QA-only", "unknown grammar", "fabricated null margin", "wrong text length", "missing selected link", "unknown selected ID", "duplicate proposal ID", "wrong witness proposal", "wrong witness source", "wrong requirement", "backend invalid lineage"])("does not affirm support with %s", (variant) => {
    const record = profiledRecord(), proposal: Record<string, unknown> = record.proposals[0];
    if (variant === "unknown origin") proposal.origin = "future";
    else if (variant === "missing origin") delete proposal.origin;
    else if (variant === "QA forgery") { proposal.origin = "qa_reader"; proposal.pattern_id = null; proposal.grammar_version = null; proposal.qa_observation_id = "qa-1"; }
    else if (variant === "pattern in QA-only") record.evidence_profile = recordedProfile("qa_only_v1", "literal_v1");
    else if (variant === "unknown grammar") proposal.grammar_version = "future";
    else if (variant === "fabricated null margin") proposal.null_margin = 0;
    else if (variant === "wrong text length") proposal.text = "Wrong";
    else if (variant === "missing selected link") record.selected_proposal_ids = [];
    else if (variant === "unknown selected ID") record.selected_proposal_ids = ["not-recorded"];
    else if (variant === "duplicate proposal ID") record.proposals.push({ ...record.proposals[0] });
    else if (variant === "wrong witness proposal") record.requirements[0].witnesses[0].proposals[0].text = "Different";
    else if (variant === "wrong witness source") record.requirements[0].witnesses[0].document_version = 2;
    else if (variant === "wrong requirement") proposal.requirement_id = "r2";
    else record.discovery_lineage.valid = false;
    if (!["wrong witness proposal", "wrong witness source"].includes(variant)) Object.assign(record.requirements[0].witnesses[0].proposals[0], proposal);
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  });
  it("preserves a valid current procedure proof with source-pattern origin and no invented QA acceptance", () => {
    render(<AnswerSelectionEvidence value={profiledProcedure()} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
    expect(screen.getByText("Selected discovery: typed source pattern")).toBeVisible();
    expect(screen.queryByText(/QA accepted/)).not.toBeInTheDocument();
  });
  it.each(["origin", "proposal ID", "missing origin", "missing proposal ID", "raw literal", "chunk range"])("binds new procedure discovery to its original proposal %s", (variant) => {
    const record = profiledProcedure(), seed = record.requirements[0].procedure_completeness.raw_seed;
    if (variant === "origin") seed.origin = "qa_reader";
    else if (variant === "proposal ID") seed.proposal_id = "other";
    else if (variant === "missing origin") delete (seed as Record<string, unknown>).origin;
    else if (variant === "missing proposal ID") delete (seed as Record<string, unknown>).proposal_id;
    else if (variant === "raw literal") seed.text = "Drop it.";
    else seed.chunk_range = { start: 21, end: 29 };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it("preserves current narrative structural proof without imposing numbered first-clause rules", () => {
    const record = profiledProcedure(), row = record.requirements[0], narrative = narrativeProcedure().requirements[0].procedure_completeness;
    render(<AnswerSelectionEvidence value={{ ...record, requirements: [{ ...row, procedure_completeness: { ...narrative, raw_seed: row.procedure_completeness.raw_seed } }] }} />);
    expect(screen.getByText("Full source extent verified · narrative instructions · 2 cited passages")).toBeVisible();
    expect(screen.getByText("Selected discovery: typed source pattern")).toBeVisible();
  });
  it("shows a coherent applied activity fallback with a complete recorded inspection", () => {
    const record = activityRecord();
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText(record.requirements[0].role_scope_interpretation.disclosure)).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
  it.each(["missing inspection", "incomplete inspection", "unknown inspection", "contradictory reason", "wrong requirement", "incoherent scope", "foreign source", "unresolved"])("does not affirm an activity fallback with %s", (variant) => {
    const record = activityRecord(), interpretation = record.requirements[0].role_scope_interpretation;
    if (variant === "missing inspection") (record as Record<string, unknown>).role_scope_read_set = undefined;
    else if (variant === "incomplete inspection") record.role_scope_read_set.complete = false;
    else if (variant === "unknown inspection") record.role_scope_read_set.contract = "future";
    else if (variant === "contradictory reason") (record.role_scope_read_set as Record<string, unknown>).reason = "role_scope_inspection_changed";
    else if (variant === "wrong requirement") interpretation.requirement_id = "r2";
    else if (variant === "incoherent scope") interpretation.effective_scope = "session";
    else if (variant === "foreign source") record.role_scope_read_set.documents[0].document_version = 2;
    else record.requirements[0].status = "unsupported";
    render(<AnswerSelectionEvidence value={record} />);
    const disclosure = screen.queryByText(interpretation.disclosure);
    if (disclosure) expect(disclosure).not.toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    if (variant !== "unresolved") expect(screen.getByText(/Role-scope inspection unknown or incomplete|Role-scope metadata invalid/)).toBeVisible();
  });
  it("keeps an incomplete inspection reason inspectable without inventing supported scope", () => {
    const record = activityRecord(); record.role_scope_read_set.complete = false;
    (record.role_scope_read_set as Record<string, unknown>).reason = "role_scope_chunk_manifest_changed";
    render(<AnswerSelectionEvidence value={record} />);
    const details = screen.getByText("Evidence discovery details").closest("details")!;
    expect(within(details).getByText("role_scope_chunk_manifest_changed")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it("does not infer activity disclosure from the selected server policy alone", () => {
    const record = profiledRecord(); record.evidence_profile = recordedProfile();
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.queryByText(/^Activity scope:/)).not.toBeInTheDocument();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
  });
  it("keeps a direct session assignment free of an activity-fallback disclosure", () => {
    const record = activityRecord(), role = record.requirements[0].role_scope_interpretation;
    const changed = { ...record, requirements: [{ ...record.requirements[0], prepared_question: "Who leads ordinary Meridian review session?", role_scope_interpretation: { ...role, basis: "documented_session_assignment", effective_target: role.requested_scope, prepared_question: "Who leads ordinary Meridian review session?", effective_scope: "session", activity_fallback: false, disclosure: null } }] };
    render(<AnswerSelectionEvidence value={changed} />);
    expect(screen.queryByText(/^Activity scope:/)).not.toBeInTheDocument();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
  });
  it("keeps historical complete-procedure proof while leaving extraction profile and origin unrecorded", () => {
    render(<AnswerSelectionEvidence value={completeProcedure()} />);
    expect(screen.getByText("Extraction profile unrecorded")).toBeVisible();
    expect(screen.getByText("Discovery origin unrecorded")).toBeVisible();
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
    expect(screen.queryByText(/QA accepted|Composite source extraction|Ordinary-session activity policy/)).not.toBeInTheDocument();
  });
  it.each([
    { name: "unknown proposal profile", profile: { ...recordedProfile(), proposal_profile: "future" } },
    { name: "contradictory registry", profile: { ...recordedProfile("qa_only_v1"), pattern_registry_contract: "typed-source-patterns-v1" } },
    { name: "unknown role policy", profile: { ...recordedProfile(), role_scope_policy: "future" } },
    { name: "wrong limits", profile: { ...recordedProfile(), pattern_limits: { per_source_requirement: 4, per_requirement: 16 } } },
    { name: "malformed enum", profile: { ...recordedProfile(), proposal_profile: { toString: null } } },
    { name: "null profile", profile: null },
  ])("does not affirm a structural proof with $name in new metadata", ({ profile }) => {
    render(<AnswerSelectionEvidence value={{ ...completeProcedure(), evidence_profile: profile, proposals: [], selected_proposal_ids: [], qa_observations: [], pattern_observations: [], discovery_lineage: { status: "recorded", valid: true } }} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it("does not inherit a current profile when new origin fields are recorded without one", () => {
    render(<AnswerSelectionEvidence value={{ ...completeProcedure(), proposals: [], selected_proposal_ids: [], discovery_lineage: { status: "recorded", valid: true } }} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
});

describe("recorded requirement evidence", () => {
  // A contained substring is not the original complete first-action seed core.
  it.each([
    { name: "verb range only", raw: "Copy it.", start: 20, end: 24 },
    { name: "object range only", raw: "Copy it.", start: 25, end: 27 },
    { name: "verb text and range", raw: "Copy", start: 20, end: 24 },
    { name: "object text and range", raw: "it", start: 25, end: 27 },
    { name: "changed full literal", raw: "Drop it.", start: 20, end: 28 },
    { name: "wrong raw literal length", raw: "Copy it..", start: 20, end: 28 },
    { name: "marker prefix", raw: "1. Copy it.", start: 17, end: 28 },
    { name: "cross-clause suffix", raw: "Copy it. X", start: 20, end: 30 },
    { name: "BOM prefix", raw: "\uFEFFCopy it.", start: 19, end: 28 },
    { name: "BOM suffix", raw: "Copy it.\uFEFF", start: 20, end: 29 },
    { name: "zero-width space prefix", raw: "\u200BCopy it.", start: 19, end: 28 },
  ])("rejects incomplete or inconsistent accepted seed: $name", ({ raw, start, end }) => {
    render(<AnswerSelectionEvidence value={numberedSeed({ raw, rawRange: { start, end }, stepStart: 17 })} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it.each(["missing core", "missing raw text", "wrong unit", "wrong core range", "wrong core literal", "wrong core length"])("requires an independent consistent first-clause descriptor: %s", (variant) => {
    const record = completeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
    const core = proof.required_inventory.seed_clause!;
    if (variant === "missing core") proof.required_inventory.seed_clause = undefined;
    else if (variant === "wrong unit") core.unit_name = "step-2";
    else if (variant === "wrong core range") core.source_range.start++;
    else if (variant === "wrong core literal") core.text = "Drop it.";
    else if (variant === "wrong core length") core.text = "Copy it..";
    render(<AnswerSelectionEvidence value={variant === "missing raw text" ? { ...record, requirements: [{ ...row, procedure_completeness: { ...proof, raw_seed: { ...proof.raw_seed, text: undefined } } }] } : record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("does not permit arbitrary last-character omission from a clause without terminal punctuation", () => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: "Copy itx", raw: "Copy it", rawRange: { start: 20, end: 27 } })} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each([".", "!", "?"])("accepts omission only of the clause's actual terminal %s", (punctuation) => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: `Copy it${punctuation}`, raw: "Copy it", rawRange: { start: 20, end: 27 } })} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it("accepts an exact full clause with no terminal punctuation", () => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: "Copy itx" })} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it.each([
    0x0009, 0x000a, 0x000b, 0x000c, 0x000d, 0x001c, 0x001d, 0x001e, 0x001f, 0x0020,
    0x0085, 0x00a0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
    0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
  ])("preserves original source padding for Python whitespace codepoint %i", (codepoint) => {
    const whitespace = String.fromCodePoint(codepoint);
    render(<AnswerSelectionEvidence value={numberedSeed({ raw: `${whitespace}Copy it.${whitespace}`, rawRange: { start: 19, end: 29 }, stepStart: 18 })} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it.each([false, true])("normalizes actual outer source-clause whitespace, punctuation omitted: %s", (omitPunctuation) => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: "\u001CDo it.\u0085", raw: omitPunctuation ? "Do it" : "Do it.", rawRange: { start: 21, end: omitPunctuation ? 26 : 27 } })} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it("counts non-BMP source and raw literals in Unicode codepoints", () => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: "Copy \u{1F4C4}.", clauseRange: { start: 20, end: 27 } })} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it("rejects UTF-16 lengths masquerading as source codepoint offsets", () => {
    render(<AnswerSelectionEvidence value={numberedSeed({ clause: "Copy \u{1F4C4}." })} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["outside step", "outside cited fragment"])("keeps original raw padding inside its %s", (variant) => {
    const record = numberedSeed({ raw: " Copy it. ", rawRange: { start: 19, end: 29 }, stepStart: variant === "outside step" ? 20 : 18 });
    const proof = record.requirements[0].procedure_completeness;
    if (variant === "outside cited fragment") {
      proof.fragments[0].chunk_end = 28; proof.fragments[0].document_end = 28;
      proof.fragments[1].document_start = 28; proof.fragments[1].chunk_end = 82;
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("binds the seed core to the first action by source order instead of inventory order", () => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.proof_units.reverse(); proof.required_inventory.units.reverse();
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it("does not bind a later action inside the first step as the first seed clause", () => {
    const record = numberedSeed({ clause: "Copy", clauseRange: { start: 20, end: 24 } }), proof = record.requirements[0].procedure_completeness;
    const required = { ...proof.required_inventory.units.find((unit) => unit.name === "step-1")!, name: "second-action", source_range: { start: 25, end: 29 }, hypothesis: "The instructions require filing the record." };
    proof.required_inventory.units.push(required);
    proof.proof_units.push({ ...required, label: "entailment", supported: true, entailment_margin: 2, pair_tokens: 100 });
    const edge = { name: "applicability_to_action", source: "applicability", target: "second-action", step: 1 };
    proof.structure_edges.push({ ...edge }); proof.required_inventory.structure_edges.push({ ...edge });
    proof.mandatory_proof_count++;
    proof.required_inventory.seed_clause = { unit_name: "second-action", source_range: { start: 25, end: 29 }, text: "File" };
    proof.raw_seed = { chunk_id: "first", text: "File", chunk_range: { start: 25, end: 29 }, document_range: { start: 25, end: 29 } };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("keeps narrative evidence compatible without numbered seed-core or raw-text fields", () => {
    const record = narrativeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
    render(<AnswerSelectionEvidence value={{ ...record, requirements: [{ ...row, procedure_completeness: { ...proof, raw_seed: { ...proof.raw_seed, text: undefined }, required_inventory: { ...proof.required_inventory, seed_clause: undefined } } }] }} />);
    expect(screen.getByText("Full source extent verified · narrative instructions · 2 cited passages")).toBeVisible();
  });
  // Mutual agreement cannot replace the canonical governance and typed ownership contract.
  it.each(["namespace", "applicability", "requested_scope"])("requires mandatory %s even when both recorded inventories omit it", (missing) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.proof_units = proof.proof_units.filter((unit) => unit.name !== missing);
    proof.required_inventory.units = proof.required_inventory.units.filter((unit) => unit.name !== missing);
    proof.mandatory_proof_count = proof.proof_units.length;
    for (const edges of [proof.structure_edges, proof.required_inventory.structure_edges]) {
      if (missing !== "requested_scope") edges.splice(0, 1);
      if (missing === "applicability") for (const edge of edges) { edge.name = "namespace_to_action"; edge.source = "namespace"; }
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it("requires the namespace-to-applicability join even when recorded edges agree", () => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.structure_edges.shift(); proof.required_inventory.structure_edges.shift();
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["action self-edge", "request-scope source", "wrong namespace source", "wrong applicability target"])("rejects typed ownership with %s", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    for (const edges of [proof.structure_edges, proof.required_inventory.structure_edges]) {
      const edge = edges.find((item) => item.target === (variant === "wrong applicability target" ? "applicability" : "step-1"))!;
      if (variant === "wrong applicability target") edge.target = "requested_scope";
      else if (variant === "wrong namespace source") { edge.name = "namespace_to_action"; edge.source = "applicability"; }
      else edge.source = variant === "action self-edge" ? "step-1" : "requested_scope";
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["gap", "short final step"])("requires complete sibling coverage without a %s", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    if (variant === "gap") {
      proof.step_ranges[1].start = 31; proof.required_inventory.step_ranges[1].start = 31;
      for (const units of [proof.proof_units, proof.required_inventory.units]) {
        const action = units.find((unit) => unit.name === "step-2")!;
        action.source_range.start = 31; action.premise_range.start = 31;
      }
    } else {
      proof.step_ranges[7].end = 99; proof.required_inventory.step_ranges[7].end = 99;
      for (const units of [proof.proof_units, proof.required_inventory.units]) {
        units.find((unit) => unit.name === "step-8")!.premise_range.end = 99;
        const prohibition = units.find((unit) => unit.name === "final-prohibition")!;
        prohibition.source_range.end = 99; prohibition.premise_range.end = 99;
      }
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("requires explicit structure before applying numbered step rules", () => {
    const record = completeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
    render(<AnswerSelectionEvidence value={{ ...record, requirements: [{ ...row, procedure_completeness: {
      ...proof, structure: undefined,
      proof_units: proof.proof_units.map((unit) => ({ ...unit, step: null, premise_range: { ...unit.source_range } })),
      structure_edges: proof.structure_edges.map((edge) => ({ ...edge, step: undefined })),
      required_inventory: { ...proof.required_inventory, structure: undefined,
        units: proof.required_inventory.units.map((unit) => ({ ...unit, step: null, premise_range: { ...unit.source_range } })),
        structure_edges: proof.required_inventory.structure_edges.map((edge) => ({ ...edge, step: undefined })),
      },
    } }] }} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("requires a recorded assessed step to agree with independent inventory membership", () => {
    const record = completeProcedure();
    record.requirements[0].procedure_completeness.proof_units.find((unit) => unit.name === "step-1")!.step = 2;
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("accepts inventory step membership when the assessment omits its optional step", () => {
    const record = completeProcedure();
    for (const unit of record.requirements[0].procedure_completeness.proof_units) delete unit.step;
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it.each(["outside cited origin", "crosses cited fragment", "later step"])("requires the raw seed to belong to the first step and its cited origin: %s", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    if (variant === "crosses cited fragment") {
      proof.fragments[0].chunk_end = 24; proof.fragments[0].document_end = 24;
      proof.fragments[1].document_start = 24; proof.fragments[1].chunk_end = 86;
    } else if (variant === "outside cited origin") {
      proof.raw_seed = { text: "Copy it.", chunk_id: "first", chunk_range: { start: 94, end: 100 }, document_range: { start: 94, end: 100 } };
    } else proof.raw_seed = { text: "Copy it.", chunk_id: "second", chunk_range: { start: 42, end: 48 }, document_range: { start: 92, end: 98 } };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it.each(["units", "steps", "edges"])("keeps malformed %s entries unknown without throwing", (part) => {
    const record = completeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
    const changed = part === "units" ? { ...proof, proof_units: [null, ...proof.proof_units.slice(1)], required_inventory: { ...proof.required_inventory, units: [null, ...proof.required_inventory.units.slice(1)] } }
      : part === "steps" ? { ...proof, step_ranges: [null, ...proof.step_ranges.slice(1)], required_inventory: { ...proof.required_inventory, step_ranges: [null, ...proof.required_inventory.step_ranges.slice(1)] } }
        : { ...proof, structure_edges: [null, ...proof.structure_edges.slice(1)], required_inventory: { ...proof.required_inventory, structure_edges: [null, ...proof.required_inventory.structure_edges.slice(1)] } };
    render(<AnswerSelectionEvidence value={{ ...record, requirements: [{ ...row, procedure_completeness: changed }] }} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["__proto__", "constructor", "toString", "future_kind"])("renders unknown requirement kind %s as a plain fallback", (kind) => {
    render(<AnswerSelectionEvidence value={{ requirements: [{ kind, original_text: "Unknown recorded kind", status: "supported", witnesses: [{ value: "recorded value" }] }] }} />);
    expect(screen.getByText("Requested fact")).toBeVisible();
    expect(screen.getByText("Unknown recorded kind")).toBeVisible();
  });
  it("does not certify a structure edge associated with a different step than its action", () => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.structure_edges.find((edge) => edge.target === "step-2")!.step = 1;
    proof.required_inventory.structure_edges.find((edge) => edge.target === "step-2")!.step = 1;
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("keeps the previous procedure subcontract inspectable without step-context certification", () => {
    const record = completeProcedure(); record.requirements[0].procedure_completeness.contract = "complete-immutable-procedure-v1";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["next step", "partial step", "changed assessed premise", "late action as prelude"])("does not certify $name context as a complete same-step proof", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    if (variant === "late action as prelude") {
      const required = proof.required_inventory.units.find((unit) => unit.name === "final-prohibition")!;
      const assessed = proof.proof_units.find((unit) => unit.name === "final-prohibition")!;
      required.step = null;
      required.premise_range = { ...required.source_range };
      assessed.premise_range = { ...assessed.source_range };
    } else if (variant === "changed assessed premise") proof.proof_units.find((unit) => unit.name === "step-1")!.premise_range.end++;
    else {
      const range = variant === "next step" ? { start: 20, end: 37 } : { start: 21, end: 28 };
      proof.proof_units.find((unit) => unit.name === "step-1")!.premise_range = { ...range };
      proof.required_inventory.units.find((unit) => unit.name === "step-1")!.premise_range = { ...range };
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["unrecorded chunk", "shifted local coordinates"])("does not certify a raw seed with $name", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    if (variant === "unrecorded chunk") proof.raw_seed.chunk_id = "unrecorded";
    else proof.raw_seed.chunk_range = { start: 200, end: 208 };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("does not treat a recorded but uncited overlapping seed as the current complete-cover contract", () => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.raw_seed = { text: "Copy it.", chunk_id: "overlap", chunk_range: { start: 15, end: 23 }, document_range: { start: 20, end: 28 } };
    render(<AnswerSelectionEvidence value={{ ...record, procedure_contexts: [{ document_id: "document", document_version: 1, content_hash: "a".repeat(64), sources: [{ chunk_id: "overlap", document_range: { start: 5, end: 60 } }] }] }} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["whole last step", "last prohibition", "namespace substitution", "inventory identity", "missing edge"])("does not certify a self-consistent count after losing %s", (variant) => {
    const record = completeProcedure(), proof = record.requirements[0].procedure_completeness;
    if (variant === "inventory identity") proof.required_inventory.document_version = 2;
    else if (variant === "missing edge") proof.structure_edges.pop();
    else if (variant === "namespace substitution") proof.proof_units.find((unit) => unit.name === "step-8")!.kind = "namespace";
    else {
      const removed = variant === "whole last step" ? ["step-8", "final-prohibition"] : ["final-prohibition"];
      proof.proof_units = proof.proof_units.filter((unit) => !removed.includes(unit.name));
      proof.structure_edges = proof.structure_edges.filter((edge) => !removed.includes(edge.target));
      proof.mandatory_proof_count = proof.proof_units.length;
    }
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it.each(["closure", "proof unit"])("keeps malformed %s enum data unknown without throwing", (part) => {
    const record = completeProcedure(), row = record.requirements[0], proof = row.procedure_completeness;
    const malformed = { toString: null };
    const changed = part === "closure"
      ? { ...proof, closure: { kind: malformed, end: 100 } }
      : { ...proof, proof_units: [{ ...proof.proof_units[0], kind: malformed }, ...proof.proof_units.slice(1)] };
    render(<AnswerSelectionEvidence value={{ ...record, requirements: [{ ...row, procedure_completeness: changed }] }} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("preserves complete narrative instructions without inventing numbered steps", () => {
    render(<AnswerSelectionEvidence value={narrativeProcedure()} />);
    expect(screen.getByText("Full source extent verified · narrative instructions · 2 cited passages")).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.queryByText(/0 steps|8 steps/)).not.toBeInTheDocument();
  });
  it("requires the narrative whole-method premise to equal the declared full extent", () => {
    const record = narrativeProcedure(), proof = record.requirements[0].procedure_completeness;
    proof.proof_units[0].source_range.start = 0;
    proof.proof_units[0].premise_range.start = 0;
    proof.required_inventory.units[0].source_range.start = 0;
    proof.required_inventory.units[0].premise_range.start = 0;
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("does not certify an EOF prefix shorter than the recorded immutable body", () => {
    const record = completeProcedure(); record.requirements[0].procedure_completeness.body_length = 110;
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("requires one action-relevant proof to contain the entire accepted raw span", () => {
    const record = completeProcedure();
    record.requirements[0].procedure_completeness.raw_seed = { text: "Copy it.", chunk_id: "first", chunk_range: { start: 5, end: 25 }, document_range: { start: 5, end: 25 } };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("does not turn a narrative namespace-only check into method support", () => {
    const record = narrativeProcedure(); record.requirements[0].procedure_completeness.proof_units[0].kind = "namespace";
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it("shows the recorded complete extent and every required citation part", () => {
    render(<AnswerSelectionEvidence value={completeProcedure()} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeInTheDocument();
    expect(screen.getByText("Full source extent verified · 8 steps · 2 cited passages")).toBeVisible();
  });
  it("does not retroactively certify an old supported procedure prefix", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", contract: "requirement-evidence-v1", requirements: [
      { kind: "procedure", original_text: "Give the complete procedure.", status: "supported", witnesses: [{ value: "A recorded prefix." }] },
    ] }} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.getByText(/Recorded status: supported/)).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
  it.each([
    { name: "a missing citation interval", change: (r: ProcedureRecord) => { r.requirements[0].procedure_completeness.fragments[1].document_start = 61; } },
    { name: "an unsupported mandatory action", change: (r: ProcedureRecord) => { r.requirements[0].procedure_completeness.proof_units.find((unit) => unit.name === "step-1")!.supported = false; } },
    { name: "an unmeasured or oversized proof", change: (r: ProcedureRecord) => { r.requirements[0].procedure_completeness.proof_units.find((unit) => unit.name === "step-1")!.pair_tokens = 513; } },
    { name: "a skipped ordinal", change: (r: ProcedureRecord) => { r.requirements[0].procedure_completeness.step_ranges[2].ordinal = 4; } },
    { name: "a decision below its recorded margin", change: (r: ProcedureRecord) => { r.evidence_support.minimum_entailment_margin = 3; } },
    { name: "an unknown proof contract", change: (r: ProcedureRecord) => { r.requirements[0].procedure_completeness.contract = "unrecognized-future-contract"; } },
  ])("leaves completeness unknown for $name", ({ change }) => {
    const record = completeProcedure(); change(record);
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
  });
  it("explains a content budget refusal without calling it a model failure", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [
      { kind: "procedure", original_text: "Give the complete procedure.", status: "unsupported", witnesses: [], reason: "procedure_support_budget_exceeded" },
    ] }} />);
    expect(screen.getByText(/This procedure exceeds the supported evidence window/)).toBeVisible();
    expect(screen.queryByText(/Reader failed|install.*model/i)).not.toBeInTheDocument();
  });
  it.each([
    { reason: "procedure_mandatory_support_rejected", message: "At least one required instruction could not be verified. The complete procedure was refused instead of presenting a partial answer." },
    { reason: "procedure_raw_not_in_mandatory_action_premise", message: "The reader did not identify an answer span inside a verified procedure action. The complete procedure was refused." },
  ])("explains the recorded $reason without presenting an unavailable model", ({ reason, message }) => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [
      { kind: "procedure", original_text: "Give the complete procedure.", status: "unsupported", witnesses: [], reason },
    ] }} />);
    expect(screen.getByText(message)).toBeVisible();
    expect(screen.queryByText(/Reader failed|Execution failed|install.*model/i)).not.toBeInTheDocument();
  });
  it("discloses the recorded owner-relative interpretation only with both evidence edges", () => {
    const source = { chunk_id: "chunk", document_id: "document", document_version: 1, content_hash: "a".repeat(64) };
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [
      { id: "r2", kind: "deputy", original_text: "Who is the deputy?", prepared_question: "Who is the record steward's deputy?", status: "supported", witnesses: [{ value: "shift clerk" }], interpretation: { kind: "owner_relative_deputy", resolved_owner: "record steward", owner_evidence: [source], deputy_evidence: [source] } },
      { id: "r3", kind: "deputy", original_text: "Which other deputy?", status: "unsupported", witnesses: [], interpretation: { kind: "owner_relative_deputy", resolved_owner: "unverified role" } },
    ] }} />);
    expect(screen.getByText(/This paired request uses the verified owner/)).toHaveTextContent("record steward");
    expect(screen.queryByText(/uses the verified owner.*unverified role/)).not.toBeInTheDocument();
  });
  it("keeps malformed historical dependency edges unverified", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [
      { id: "r2", kind: "deputy", original_text: "Who is the deputy?", status: "supported", witnesses: [{ value: "shift clerk" }], interpretation: { kind: "owner_relative_deputy", resolved_owner: "record steward", owner_evidence: [null], deputy_evidence: [{ document_id: "missing-version-and-hash" }] } },
    ] }} />);
    expect(screen.queryByText(/This paired request uses the verified owner/)).not.toBeInTheDocument();
  });
  it("shows each supported and unresolved fact without calling a model", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", contract: "requirement-evidence-v1", requirements: [
      { id: "r1", original_text: "Who owns the review?", status: "supported", witnesses: [{ value: "record steward" }] },
      { id: "r2", original_text: "What are its hours?", status: "unsupported", reason: "dependent_requirement_unresolved", witnesses: [] },
    ], evidence_support: { model: "local classifier", revision: "frozen", minimum_entailment_margin: 4 } }} />);
    const coverage = screen.getByRole("region", { name: "Request coverage" });
    expect(within(coverage).getByText("1 of 2 requirements supported")).toBeInTheDocument();
    expect(within(coverage).getByText("Who owns the review?")).toBeInTheDocument();
    expect(within(coverage).getByText("record steward")).toBeInTheDocument();
    expect(within(coverage).getByText(/No verified evidence for this requirement/)).toBeInTheDocument();
    expect(screen.getByText("Local support classifier")).toBeInTheDocument();
  });
  it("explains which requested attribute is missing and keeps the interpretation inspectable", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [
      { id: "r2", kind: "availability", original_text: "Who owns the review, and what are that person's hours?", prepared_question: "What are the record steward's hours?", status: "unsupported", reason: "dependent_requirement_unresolved", witnesses: [] },
    ] }} />);
    const coverage = screen.getByRole("region", { name: "Request coverage" });
    expect(within(coverage).getByText("Availability")).toBeInTheDocument();
    expect(within(coverage).getByText(/A preceding fact could not be established/)).toBeInTheDocument();
    expect(within(coverage).getByText("Recorded request interpretation")).toBeInTheDocument();
    expect(within(coverage).getByText("What are the record steward's hours?")).toBeInTheDocument();
  });
  it("keeps historical requirement evidence unknown", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", contract: "reader-parts-v14" }} />);
    expect(screen.getByText(/Requirement coverage was not recorded/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Request coverage" })).not.toBeInTheDocument();
  });
  it("handles malformed recorded evidence without inventing supported facts", () => {
    render(<AnswerSelectionEvidence value={{ mode: "reader", requirements: [null, 7, { status: "supported", witnesses: [{ value: {} }] }] }} />);
    expect(screen.getByText("Requirement text unavailable")).toBeInTheDocument();
    expect(screen.getByText("Evidence state unknown")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeInTheDocument();
  });
});


// Actual frozen P176 serializer scope controls. All NI and token12 fields are FAKE.
const unicodeScopeProtocols = [{"name":"sharp-s","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"d4232777a2826fcb22482107552e6337bc0c29f71a367233fa97249f9433d41f","body_length":785,"extent":{"start":442,"end":484},"closure":{"kind":"declared_paragraph_end","end":484,"boundary_range":{"start":486,"end":511}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":36},"premise_range":{"start":0,"end":36},"hypothesis":"This document concerns Stra\u00dfe bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":67,"end":440},"premise_range":{"start":67,"end":440},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":440},"premise_range":{"start":0,"end":440},"hypothesis":"The complete procedure is for STRASSE bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":442,"end":484},"premise_range":{"start":67,"end":484},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":67,"end":484},"premise_range":{"start":67,"end":484},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for STRASSE bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":442,"end":484},"premise_range":{"start":442,"end":484},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":486,"end":785},"premise_range":{"start":486,"end":785},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"d4232777a2826fcb22482107552e6337bc0c29f71a367233fa97249f9433d41f","structure":"declared_paragraphs","extent":{"start":442,"end":484},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":36},"premise_range":{"start":0,"end":36},"hypothesis":"This document concerns Stra\u00dfe bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":67,"end":440},"premise_range":{"start":67,"end":440},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":440},"premise_range":{"start":0,"end":440},"hypothesis":"The complete procedure is for STRASSE bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":442,"end":484},"premise_range":{"start":67,"end":484},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":67,"end":484},"premise_range":{"start":67,"end":484},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for STRASSE bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":442,"end":484},"premise_range":{"start":442,"end":484},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":486,"end":785},"premise_range":{"start":486,"end":785},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"Stra\u00dfe bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"STRASSE bench","request_original":"Give the complete ordinary procedure for STRASSE bench.","scope":"Stra\u00dfe bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":36},"heading_range":{"start":38,"end":65},"declaration_range":{"start":67,"end":440},"paragraph_ranges":[{"start":442,"end":484}],"end_marker_range":{"start":486,"end":511},"governance_range":{"start":513,"end":785}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":442,"end":484},"document_range":{"start":442,"end":484},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":442,"chunk_end":484,"document_start":442,"document_end":484}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"d4232777a2826fcb22482107552e6337bc0c29f71a367233fa97249f9433d41f","chunk_id":"invented-casefold-carrier","chunk_range":{"start":442,"end":484},"document_range":{"start":442,"end":484},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"sigma","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"1bba514afede2a2bb9cbd993c8f6db0b6f83a3a0e0088482b46dd0ee6033b2b0","body_length":781,"extent":{"start":438,"end":480},"closure":{"kind":"declared_paragraph_end","end":480,"boundary_range":{"start":482,"end":507}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":32},"premise_range":{"start":0,"end":32},"hypothesis":"This document concerns \u039f\u03a3 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":63,"end":436},"premise_range":{"start":63,"end":436},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":436},"premise_range":{"start":0,"end":436},"hypothesis":"The complete procedure is for \u03bf\u03c2 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":438,"end":480},"premise_range":{"start":63,"end":480},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":63,"end":480},"premise_range":{"start":63,"end":480},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \u03bf\u03c2 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":438,"end":480},"premise_range":{"start":438,"end":480},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":482,"end":781},"premise_range":{"start":482,"end":781},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"1bba514afede2a2bb9cbd993c8f6db0b6f83a3a0e0088482b46dd0ee6033b2b0","structure":"declared_paragraphs","extent":{"start":438,"end":480},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":32},"premise_range":{"start":0,"end":32},"hypothesis":"This document concerns \u039f\u03a3 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":63,"end":436},"premise_range":{"start":63,"end":436},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":436},"premise_range":{"start":0,"end":436},"hypothesis":"The complete procedure is for \u03bf\u03c2 bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":438,"end":480},"premise_range":{"start":63,"end":480},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":63,"end":480},"premise_range":{"start":63,"end":480},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \u03bf\u03c2 bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":438,"end":480},"premise_range":{"start":438,"end":480},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":482,"end":781},"premise_range":{"start":482,"end":781},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\u039f\u03a3 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"\u03bf\u03c2 bench","request_original":"Give the complete ordinary procedure for \u03bf\u03c2 bench.","scope":"\u039f\u03a3 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":32},"heading_range":{"start":34,"end":61},"declaration_range":{"start":63,"end":436},"paragraph_ranges":[{"start":438,"end":480}],"end_marker_range":{"start":482,"end":507},"governance_range":{"start":509,"end":781}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":438,"end":480},"document_range":{"start":438,"end":480},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":438,"chunk_end":480,"document_start":438,"document_end":480}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"1bba514afede2a2bb9cbd993c8f6db0b6f83a3a0e0088482b46dd0ee6033b2b0","chunk_id":"invented-casefold-carrier","chunk_range":{"start":438,"end":480},"document_range":{"start":438,"end":480},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"ligature","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"03fef1862af4c816de5496ca7a5a5fd80cca1496a903024fe5717c3271d9229c","body_length":780,"extent":{"start":437,"end":479},"closure":{"kind":"declared_paragraph_end","end":479,"boundary_range":{"start":481,"end":506}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \ufb03 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for FFI bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for FFI bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"03fef1862af4c816de5496ca7a5a5fd80cca1496a903024fe5717c3271d9229c","structure":"declared_paragraphs","extent":{"start":437,"end":479},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \ufb03 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for FFI bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for FFI bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\ufb03 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"FFI bench","request_original":"Give the complete ordinary procedure for FFI bench.","scope":"\ufb03 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":31},"heading_range":{"start":33,"end":60},"declaration_range":{"start":62,"end":435},"paragraph_ranges":[{"start":437,"end":479}],"end_marker_range":{"start":481,"end":506},"governance_range":{"start":508,"end":780}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":437,"chunk_end":479,"document_start":437,"document_end":479}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"03fef1862af4c816de5496ca7a5a5fd80cca1496a903024fe5717c3271d9229c","chunk_id":"invented-casefold-carrier","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"dotted-i","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff6a14b275dafe12eca69b69f07e11b10131c86b4bdfa693daf410a6584bfeac","body_length":780,"extent":{"start":437,"end":479},"closure":{"kind":"declared_paragraph_end","end":479,"boundary_range":{"start":481,"end":506}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u0130 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for i\u0307 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for i\u0307 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff6a14b275dafe12eca69b69f07e11b10131c86b4bdfa693daf410a6584bfeac","structure":"declared_paragraphs","extent":{"start":437,"end":479},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u0130 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for i\u0307 bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for i\u0307 bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\u0130 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"i\u0307 bench","request_original":"Give the complete ordinary procedure for i\u0307 bench.","scope":"\u0130 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":31},"heading_range":{"start":33,"end":60},"declaration_range":{"start":62,"end":435},"paragraph_ranges":[{"start":437,"end":479}],"end_marker_range":{"start":481,"end":506},"governance_range":{"start":508,"end":780}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":437,"chunk_end":479,"document_start":437,"document_end":479}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff6a14b275dafe12eca69b69f07e11b10131c86b4bdfa693daf410a6584bfeac","chunk_id":"invented-casefold-carrier","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"astral","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"88e28f1f2c91267d8adb5e20fb01bb3fa3658f86784d02fec007f5e6fd52ffe1","body_length":782,"extent":{"start":439,"end":481},"closure":{"kind":"declared_paragraph_end","end":481,"boundary_range":{"start":483,"end":508}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":33},"premise_range":{"start":0,"end":33},"hypothesis":"This document concerns \ud801\udc00 \ud83d\udcc4 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":64,"end":437},"premise_range":{"start":64,"end":437},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":437},"premise_range":{"start":0,"end":437},"hypothesis":"The complete procedure is for \ud801\udc28 \ud83d\udcc4 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":439,"end":481},"premise_range":{"start":64,"end":481},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":64,"end":481},"premise_range":{"start":64,"end":481},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \ud801\udc28 \ud83d\udcc4 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":439,"end":481},"premise_range":{"start":439,"end":481},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":483,"end":782},"premise_range":{"start":483,"end":782},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"88e28f1f2c91267d8adb5e20fb01bb3fa3658f86784d02fec007f5e6fd52ffe1","structure":"declared_paragraphs","extent":{"start":439,"end":481},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":33},"premise_range":{"start":0,"end":33},"hypothesis":"This document concerns \ud801\udc00 \ud83d\udcc4 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":64,"end":437},"premise_range":{"start":64,"end":437},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":437},"premise_range":{"start":0,"end":437},"hypothesis":"The complete procedure is for \ud801\udc28 \ud83d\udcc4 bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":439,"end":481},"premise_range":{"start":64,"end":481},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":64,"end":481},"premise_range":{"start":64,"end":481},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \ud801\udc28 \ud83d\udcc4 bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":439,"end":481},"premise_range":{"start":439,"end":481},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":483,"end":782},"premise_range":{"start":483,"end":782},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\ud801\udc00 \ud83d\udcc4 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"\ud801\udc28 \ud83d\udcc4 bench","request_original":"Give the complete ordinary procedure for \ud801\udc28 \ud83d\udcc4 bench.","scope":"\ud801\udc00 \ud83d\udcc4 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":33},"heading_range":{"start":35,"end":62},"declaration_range":{"start":64,"end":437},"paragraph_ranges":[{"start":439,"end":481}],"end_marker_range":{"start":483,"end":508},"governance_range":{"start":510,"end":782}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":439,"end":481},"document_range":{"start":439,"end":481},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":439,"chunk_end":481,"document_start":439,"document_end":481}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"88e28f1f2c91267d8adb5e20fb01bb3fa3658f86784d02fec007f5e6fd52ffe1","chunk_id":"invented-casefold-carrier","chunk_range":{"start":439,"end":481},"document_range":{"start":439,"end":481},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"python-whitespace","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff4aab95badf02dbc5ed08a7387b13b4ed04a9c881b30b63a989f038e9c2c235","body_length":784,"extent":{"start":441,"end":483},"closure":{"kind":"declared_paragraph_end","end":483,"boundary_range":{"start":485,"end":510}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber\u001cbench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for \u0085the\u3000AMBER\u001fBENCH\u202f.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \u0085the\u3000AMBER\u001fBENCH\u202f.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff4aab95badf02dbc5ed08a7387b13b4ed04a9c881b30b63a989f038e9c2c235","structure":"declared_paragraphs","extent":{"start":441,"end":483},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber\u001cbench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for \u0085the\u3000AMBER\u001fBENCH\u202f.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \u0085the\u3000AMBER\u001fBENCH\u202f.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"Amber\u001cbench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"\u0085the\u3000AMBER\u001fBENCH\u202f","request_original":"Give the complete ordinary procedure for \u0085the\u3000AMBER\u001fBENCH\u202f.","scope":"Amber\u001cbench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":35},"heading_range":{"start":37,"end":64},"declaration_range":{"start":66,"end":439},"paragraph_ranges":[{"start":441,"end":483}],"end_marker_range":{"start":485,"end":510},"governance_range":{"start":512,"end":784}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":441,"chunk_end":483,"document_start":441,"document_end":483}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"ff4aab95badf02dbc5ed08a7387b13b4ed04a9c881b30b63a989f038e9c2c235","chunk_id":"invented-casefold-carrier","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"all-python-whitespace","expected":true,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","body_length":784,"extent":{"start":441,"end":483},"closure":{"kind":"declared_paragraph_end","end":483,"boundary_range":{"start":485,"end":510}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for \t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","structure":"declared_paragraphs","extent":{"start":441,"end":483},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for \t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for \t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"Amber bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000","request_original":"Give the complete ordinary procedure for \t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000THE\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000AMBER\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000BENCH\t\n\u000b\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000.","scope":"Amber bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":35},"heading_range":{"start":37,"end":64},"declaration_range":{"start":66,"end":439},"paragraph_ranges":[{"start":441,"end":483}],"end_marker_range":{"start":485,"end":510},"governance_range":{"start":512,"end":784}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":441,"chunk_end":483,"document_start":441,"document_end":483}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","chunk_id":"invented-casefold-carrier","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"dotless-i","expected":false,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"6f9f54a0fafea998731b7dd67e2a1274a254b90be6d43e6cc9788c9016feb525","body_length":780,"extent":{"start":437,"end":479},"closure":{"kind":"declared_paragraph_end","end":479,"boundary_range":{"start":481,"end":506}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u0131 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for I bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for I bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"6f9f54a0fafea998731b7dd67e2a1274a254b90be6d43e6cc9788c9016feb525","structure":"declared_paragraphs","extent":{"start":437,"end":479},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u0131 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for I bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for I bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\u0131 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"I bench","request_original":"Give the complete ordinary procedure for I bench.","scope":"\u0131 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":31},"heading_range":{"start":33,"end":60},"declaration_range":{"start":62,"end":435},"paragraph_ranges":[{"start":437,"end":479}],"end_marker_range":{"start":481,"end":506},"governance_range":{"start":508,"end":780}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":437,"chunk_end":479,"document_start":437,"document_end":479}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"6f9f54a0fafea998731b7dd67e2a1274a254b90be6d43e6cc9788c9016feb525","chunk_id":"invented-casefold-carrier","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"no-nfkc","expected":false,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"85e065316125b81f4d85453353acca951408aa6789cfac5c824dd505576f2c46","body_length":780,"extent":{"start":437,"end":479},"closure":{"kind":"declared_paragraph_end","end":479,"boundary_range":{"start":481,"end":506}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \uff21 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for A bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for A bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"85e065316125b81f4d85453353acca951408aa6789cfac5c824dd505576f2c46","structure":"declared_paragraphs","extent":{"start":437,"end":479},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \uff21 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for A bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for A bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\uff21 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"A bench","request_original":"Give the complete ordinary procedure for A bench.","scope":"\uff21 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":31},"heading_range":{"start":33,"end":60},"declaration_range":{"start":62,"end":435},"paragraph_ranges":[{"start":437,"end":479}],"end_marker_range":{"start":481,"end":506},"governance_range":{"start":508,"end":780}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":437,"chunk_end":479,"document_start":437,"document_end":479}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"85e065316125b81f4d85453353acca951408aa6789cfac5c824dd505576f2c46","chunk_id":"invented-casefold-carrier","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"no-canonical-normalization","expected":false,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"395112deb1537f8f47c4237387339af112fb6ebfcfd3277d8ced31ad612207fe","body_length":780,"extent":{"start":437,"end":479},"closure":{"kind":"declared_paragraph_end","end":479,"boundary_range":{"start":481,"end":506}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u00e9 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for e\u0301 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for e\u0301 bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"395112deb1537f8f47c4237387339af112fb6ebfcfd3277d8ced31ad612207fe","structure":"declared_paragraphs","extent":{"start":437,"end":479},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":31},"premise_range":{"start":0,"end":31},"hypothesis":"This document concerns \u00e9 bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":62,"end":435},"premise_range":{"start":62,"end":435},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":435},"premise_range":{"start":0,"end":435},"hypothesis":"The complete procedure is for e\u0301 bench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":437,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":62,"end":479},"premise_range":{"start":62,"end":479},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for e\u0301 bench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":437,"end":479},"premise_range":{"start":437,"end":479},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":481,"end":780},"premise_range":{"start":481,"end":780},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"\u00e9 bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"e\u0301 bench","request_original":"Give the complete ordinary procedure for e\u0301 bench.","scope":"\u00e9 bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":31},"heading_range":{"start":33,"end":60},"declaration_range":{"start":62,"end":435},"paragraph_ranges":[{"start":437,"end":479}],"end_marker_range":{"start":481,"end":506},"governance_range":{"start":508,"end":780}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":437,"chunk_end":479,"document_start":437,"document_end":479}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"395112deb1537f8f47c4237387339af112fb6ebfcfd3277d8ced31ad612207fe","chunk_id":"invented-casefold-carrier","chunk_range":{"start":437,"end":479},"document_range":{"start":437,"end":479},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"bom-not-space","expected":false,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","body_length":784,"extent":{"start":441,"end":483},"closure":{"kind":"declared_paragraph_end","end":483,"boundary_range":{"start":485,"end":510}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for Amber\ufeffbench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for Amber\ufeffbench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","structure":"declared_paragraphs","extent":{"start":441,"end":483},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for Amber\ufeffbench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for Amber\ufeffbench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"Amber bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"Amber\ufeffbench","request_original":"Give the complete ordinary procedure for Amber\ufeffbench.","scope":"Amber bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":35},"heading_range":{"start":37,"end":64},"declaration_range":{"start":66,"end":439},"paragraph_ranges":[{"start":441,"end":483}],"end_marker_range":{"start":485,"end":510},"governance_range":{"start":512,"end":784}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":441,"chunk_end":483,"document_start":441,"document_end":483}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","chunk_id":"invented-casefold-carrier","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}},{"name":"zero-width-not-space","expected":false,"proof":{"contract":"complete-immutable-procedure-v2","status":"supported","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","body_length":784,"extent":{"start":441,"end":483},"closure":{"kind":"declared_paragraph_end","end":483,"boundary_range":{"start":485,"end":510}},"structure":"declared_paragraphs","step_count":null,"step_ranges":[],"mandatory_proof_count":7,"coverage_complete":true,"proof_units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for Amber\u200bbench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for Amber\u200bbench.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null,"label":"entailment","supported":true,"entailment_margin":10,"pair_tokens":12}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"required_inventory":{"contract":"procedure-required-inventory-v1","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","structure":"declared_paragraphs","extent":{"start":441,"end":483},"step_ranges":[],"units":[{"name":"paragraph_namespace","kind":"namespace","source_range":{"start":0,"end":35},"premise_range":{"start":0,"end":35},"hypothesis":"This document concerns Amber bench.","step":null},{"name":"paragraph_declaration","kind":"applicability","source_range":{"start":66,"end":439},"premise_range":{"start":66,"end":439},"hypothesis":"The complete standard procedure applies to a standard inspected run, not a postponed audit and requires all 1 instruction paragraphs in their stated order.","step":null},{"name":"paragraph_requested_scope","kind":"request_scope","source_range":{"start":0,"end":439},"premise_range":{"start":0,"end":439},"hypothesis":"The complete procedure is for Amber\u200bbench.","step":null},{"name":"whole_method","kind":"whole_method","source_range":{"start":441,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"Every one of the 1 instruction paragraphs is required, in the stated order, for completion of the standard procedure.","step":null},{"name":"paragraph_request_constraints","kind":"bound_condition","source_range":{"start":66,"end":483},"premise_range":{"start":66,"end":483},"hypothesis":"These complete ordered instructions satisfy the entire procedure request, including its material conditions: Give the complete ordinary procedure for Amber\u200bbench.","step":null},{"name":"paragraph_1","kind":"instruction","source_range":{"start":441,"end":483},"premise_range":{"start":441,"end":483},"hypothesis":"The instructions require the following entire instruction: Turn the latch and retain the signed card.","step":null},{"name":"paragraph_closure","kind":"closure","source_range":{"start":485,"end":784},"premise_range":{"start":485,"end":784},"hypothesis":"The standard procedure ends after exactly 1 instruction paragraphs. The following record governance commentary adds no ordinary-run instruction or completion condition.","step":null}],"structure_edges":[{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_namespace"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_requested_scope"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"whole_method"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_request_constraints"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_1"},{"name":"paragraph_governance","source":"paragraph_declaration","target":"paragraph_closure"}],"declared_paragraphs":{"contract":"declared-paragraph-procedure-v1","source_body":"Amber bench: current operation note\n\nComplete standard procedure\n\nThe next one instruction paragraphs are the entire standard procedure, in the stated order. Its prerequisites, inspection, prohibited actions, and final reconciliation are part of completion. The procedure ends at the explicit End of standard procedure marker immediately after the first instruction paragraph. It applies to a standard inspected run, not a postponed audit.\n\nTurn the latch and retain the signed card.\n\nEnd of standard procedure\n\nRecord governance commentary\n\nThe standard run is complete once the one preceding instruction paragraphs have been satisfied. The following commentary describes separate post-completion record governance, not an additional ordinary-run instruction or completion condition.","request_topic":"Amber\u200bbench","request_original":"Give the complete ordinary procedure for Amber\u200bbench.","scope":"Amber bench","mode":"standard","conditions":"a standard inspected run, not a postponed audit","declared_count":1,"title_range":{"start":0,"end":35},"heading_range":{"start":37,"end":64},"declaration_range":{"start":66,"end":439},"paragraph_ranges":[{"start":441,"end":483}],"end_marker_range":{"start":485,"end":510},"governance_range":{"start":512,"end":784}}},"raw_seed":{"chunk_id":"invented-casefold-carrier","text":"Turn the latch and retain the signed card.","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"origin":"source_pattern","proposal_id":"invented-casefold-proposal"},"fragments":[{"chunk_id":"invented-casefold-carrier","chunk_start":441,"chunk_end":483,"document_start":441,"document_end":483}]},"proposal":{"contract":"proposal-origin-v1","proposal_id":"invented-casefold-proposal","requirement_id":"r1","origin":"source_pattern","document_id":"invented-casefold-document","document_version":1,"content_hash":"98cc9121ffd24d31fba769d979a397417b3f4562336b34956099f5abdf89c70c","chunk_id":"invented-casefold-carrier","chunk_range":{"start":441,"end":483},"document_range":{"start":441,"end":483},"text":"Turn the latch and retain the signed card.","pattern_id":"complete-declared-paragraph-procedure-v1","grammar_version":"typed-source-patterns-v1","qa_observation_id":null}}];
describe("Python Unicode scope compatibility (fake NI/token12)", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each(unicodeScopeProtocols)("matches Python scope result: $name", async ({ proof, proposal, expected }) => {
    const record = declaredRecord("single"), row = record.requirements[0];
    const descriptor = proof.required_inventory.declared_paragraphs;
    // Preserve the public record schema while using independently serialized proof bytes.
    const value = { ...record, proposals: [proposal], selected_proposal_ids: [proposal.proposal_id],
      qa_observations: [{ ...record.qa_observations[0], question: descriptor.request_original, chunk_id: proposal.chunk_id }], pattern_observations: [],
      requirements: [{ ...row, original_text: descriptor.request_original, procedure_completeness: proof,
        witnesses: [{ ...row.witnesses[0], document_id: proposal.document_id, document_version: proposal.document_version,
          content_hash: proposal.content_hash, chunk_id: proposal.chunk_id,
          value: Array.from(descriptor.source_body).slice(proof.extent.start, proof.extent.end).join(""),
          span: { ...proposal.chunk_range, text: proposal.text }, document_range: proposal.document_range, proposals: [proposal] }] }] };
    render(<AnswerSelectionEvidence value={value} />);
    await screen.findByText("Recorded source-body hash: matched");
    if (expected) expect(screen.getByText(/Full source extent verified/)).toBeVisible();
    else expectDeclaredUnknown();
  });
});


// Exact v216 ASGI producer envelope; external NI/QA models are explicit test doubles.
import combinedProcedureFixture from "../fixtures/combined-procedure-v3.json";

describe("combined procedure profile metadata", () => {
  it("accepts the recorded v2 profile for factual answers without claiming a procedure copy", () => {
    const value = profiledRecord();
    const record = { ...value, evidence_profile: { ...value.evidence_profile, contract: "evidence-profile-v2", procedure_verification_profile: "source_declared_procedure_copy_v1" } };
    render(<AnswerSelectionEvidence value={record} />);
    expect(screen.getByRole("heading", { name: "Composite source extraction" })).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage|Source-declared procedure copy/)).not.toBeInTheDocument();
  });
  it.each(["unknown", "all_units_nli_v1", undefined])("refuses unsupported v2 procedure profile %s", (profile) => {
    const value = profiledRecord();
    render(<AnswerSelectionEvidence value={{ ...value, evidence_profile: { ...value.evidence_profile, contract: "evidence-profile-v2", procedure_verification_profile: profile } }} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
  });
});

type CombinedResponse = typeof combinedProcedureFixture.response;
function combinedResponse(): CombinedResponse { return structuredClone(combinedProcedureFixture.response); }
function CombinedEvidence({ response }: { response: CombinedResponse }) {
  return <AnswerSelectionEvidence value={response.provenance.answer_selection} question={response.question} answer={response.answer} sources={response.sources} />;
}

describe("source-declared v3 output binding", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("validates the actual producer record and distinguishes exact copy from recorded NLI", async () => {
    render(<CombinedEvidence response={combinedResponse()} />);
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
    await screen.findByText(/Exact instruction coverage verified/);
    expect(screen.getByRole("heading", { name: "Source-declared procedure copy" })).toBeVisible();
    expect(screen.getByText(/NLI-supported subject and applicability/)).toBeVisible();
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
    expect(screen.getByText(/exact_source_structure.*exact_source_copy/)).toBeVisible();
  });
  it("withholds completeness when the actual output context is missing", async () => {
    render(<AnswerSelectionEvidence value={combinedResponse().provenance.answer_selection} />);
    await screen.findByText("Recorded source-body hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it.each([
    ["answer omitted instruction", (r: CombinedResponse) => { r.answer = r.answer.replace("Place one token in the tray, with the marked edge facing the label.\n\n", ""); }],
    ["self-hashed answer tampering", (r: CombinedResponse) => { r.answer = r.answer.replace("one token", "two tokens"); r.provenance.answer_selection.requirements[0].procedure_completeness.output_certificate.answer_sha256 = createHash("sha256").update(r.answer).digest("hex"); }],
    ["question", (r: CombinedResponse) => { r.question += " Only after midnight."; }],
    ["certificate range", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.output_certificate.answer_range.end--; }],
    ["citation text", (r: CombinedResponse) => { r.sources[0].quoted_text = r.sources[0].quoted_text.replace("one token", "two tokens"); }],
    ["citation identity", (r: CombinedResponse) => { r.sources[0].document_version++; }],
    ["citation mapping", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.output_certificate.citation_mapping[0].citation_index++; }],
    ["source body", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.source_body += " Extra instruction."; }],
    ["NLI rejection", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.proof_units[0].label = "neutral"; }],
    ["unknown method", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.proof_units[2].verification_method = "unknown"; }],
    ["fabricated classifier fields on exact unit", (r: CombinedResponse) => { Object.assign(r.provenance.answer_selection.requirements[0].procedure_completeness.proof_units[2], { label: "entailment", entailment_margin: 10, logits: [-5, 5, -5], pair_tokens: 12 }); }],
    ["removed inventory and proof obligation", (r: CombinedResponse) => { const p = r.provenance.answer_selection.requirements[0].procedure_completeness; p.required_inventory.units.splice(6, 1); p.proof_units.splice(6, 1); p.mandatory_proof_count--; p.output_certificate.required_inventory.units.splice(6, 1); }],
    ["unknown output contract", (r: CombinedResponse) => { r.provenance.answer_selection.requirements[0].procedure_completeness.output_certificate.contract = "procedure-output-cover-v99"; }],
  ] as const)("does not certify %s", async (_name, mutate) => {
    const response = combinedResponse(); mutate(response);
    render(<CombinedEvidence response={response} />);
    await screen.findByText(/Recorded output hash: (matched|mismatch|unavailable)$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified|Full source extent verified/)).not.toBeInTheDocument();
  });
});

import numberedProcedureFixture from "../fixtures/combined-numbered-procedure-v3.json";
describe("numbered v3 canonical source inventory", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("validates all worksheet actions plus the independent applicability NLI check", async () => {
    const r = numberedProcedureFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText(/Exact instruction coverage verified/);
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
  it.each(["instruction", "bound_condition", "prohibition"])("rejects a coherently removed %s obligation", async (kind) => {
    const r = structuredClone(numberedProcedureFixture.response), p = r.provenance.answer_selection.requirements[0].procedure_completeness;
    const index = p.required_inventory.units.findIndex((unit) => unit.kind === kind);
    const [removed] = p.required_inventory.units.splice(index, 1);
    p.proof_units.splice(index, 1); p.mandatory_proof_count--;
    p.structure_edges = p.structure_edges.filter((edge) => edge.target !== removed.name);
    p.required_inventory.structure_edges = p.required_inventory.structure_edges.filter((edge) => edge.target !== removed.name);
    p.output_certificate.required_inventory = structuredClone(p.required_inventory);
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

describe("v3 source boundary integrity", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("rejects a self-consistent truncated numbered procedure with a fabricated independent-section closure", async () => {
    const r = structuredClone(numberedProcedureFixture.response), p = r.provenance.answer_selection.requirements[0].procedure_completeness;
    const end = p.step_ranges[7].start;
    p.extent.end = end;
    Object.assign(p.closure, { kind: "independent_section", end, boundary_range: { start: end, end: end + 2 } });
    p.step_ranges.pop(); p.step_count--;
    p.required_inventory.extent.end = end; p.required_inventory.step_ranges.pop();
    p.required_inventory.units = p.required_inventory.units.filter((unit) => unit.step !== 8);
    p.proof_units = p.proof_units.filter((unit) => !unit.name.startsWith("step_8_"));
    p.mandatory_proof_count = p.proof_units.length;
    p.structure_edges = p.structure_edges.filter((edge) => edge.step !== 8);
    p.required_inventory.structure_edges = structuredClone(p.structure_edges);
    p.fragments[0].chunk_end = end; p.fragments[0].document_end = end;
    const c = p.output_certificate;
    c.required_inventory = structuredClone(p.required_inventory); c.instruction_range.end = end;
    c.citation_mapping[0].chunk_end = end; c.citation_mapping[0].document_end = end;
    c.answer_range.end = c.answer_range.start + end - p.extent.start;
    const literal = Array.from(p.source_body).slice(p.extent.start, end).join("");
    r.answer = "Source extracts (not model-generated):\n\n" + literal + " [1]";
    r.sources[0].answer_spans = [{ start: p.extent.start, end, text: literal }];
    c.answer_sha256 = createHash("sha256").update(r.answer).digest("hex");
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

describe("v3 complete actual request binding", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("does not use a self-consistent source descriptor for a different actual requested topic", async () => {
    const r = combinedResponse(), row = r.provenance.answer_selection.requirements[0], p = row.procedure_completeness;
    r.question = r.question.replaceAll("Lumen", "Cedar"); row.original_text = r.question;
    p.request_binding = { ...p.request_binding, question: r.question, original_text: r.question, topic: "Cedar token bench" };
    p.required_inventory.declared_paragraphs.request_original = r.question;
    for (const units of [p.required_inventory.units, p.proof_units]) {
      const unit = units.find((item) => item.name === "paragraph_request_constraints")!;
      unit.hypothesis = unit.hypothesis.replaceAll("Lumen", "Cedar");
    }
    p.output_certificate.request_binding = structuredClone(p.request_binding);
    p.output_certificate.required_inventory = structuredClone(p.required_inventory);
    render(<CombinedEvidence response={r} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it("does not discard an unknown actual-question suffix even if all recorded request bindings are changed", async () => {
    const r = combinedResponse(), p = r.provenance.answer_selection.requirements[0].procedure_completeness;
    r.question += " Only after midnight.";
    p.request_binding.question = r.question; p.output_certificate.request_binding.question = r.question;
    render(<CombinedEvidence response={r} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

describe("v3 async presentation verification", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("never reuses an old record's delayed digest to certify a new record", async () => {
    const pending: { resolve: (value: ArrayBuffer) => void; value: ArrayBuffer }[] = [];
    const digest = vi.fn((_algorithm: unknown, data: ArrayBuffer) => new Promise<ArrayBuffer>((resolve) => {
      const bytes = Uint8Array.from(createHash("sha256").update(new Uint8Array(data)).digest()).buffer;
      pending.push({ resolve, value: bytes });
    }));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const view = render(<CombinedEvidence response={combinedResponse()} />);
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(3));
    const old = pending.splice(0);
    view.rerender(<CombinedEvidence response={combinedResponse()} />);
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(6));
    await act(async () => { old.forEach((item) => item.resolve(item.value)); });
    expect(screen.getByText("Recorded output hash: pending")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
    await act(async () => { pending.forEach((item) => item.resolve(item.value)); });
    await screen.findByText(/Exact instruction coverage verified/);
  });
  it.each(["missing", "rejected"])("leaves v3 unverified when WebCrypto is %s", async (kind) => {
    vi.stubGlobal("crypto", kind === "missing" ? {} : { subtle: { digest: async () => { throw new Error("Unavailable"); } } });
    render(<CombinedEvidence response={combinedResponse()} />);
    await screen.findByText("Recorded output hash: unavailable");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

describe("v3 selected-output coverage", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("rejects a self-hashed extra source extract without a selected factual witness", async () => {
    const r = combinedResponse(), p = r.provenance.answer_selection.requirements[0].procedure_completeness;
    const text = Array.from(r.sources[0].quoted_text).slice(0, 41).join("");
    r.sources[0].answer_spans.push({ start: 0, end: 41, text });
    r.answer += "\n\n" + text + " [1]";
    p.output_certificate.answer_sha256 = createHash("sha256").update(r.answer).digest("hex");
    render(<CombinedEvidence response={r} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it.each(["reader mode", "classifier mode"])("does not certify a v3 record without its required %s", async (mode) => {
    const r = combinedResponse();
    if (mode === "reader mode") r.provenance.answer_selection.mode = "lexical";
    else r.provenance.answer_selection.evidence_support.mode = "none";
    render(<CombinedEvidence response={r} />);
    await screen.findByText(/Recorded output hash: matched$/);
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

import multipleProcedureFixture from "../fixtures/combined-multiple-procedure-v3.json";
import unicodeProcedureFixture from "../fixtures/combined-unicode-procedure-v3.json";
import mixedProcedureFixture from "../fixtures/combined-mixed-procedure-v3.json";
import disclosureProcedureFixture from "../fixtures/combined-disclosure-procedure-v3.json";
import { selectionRecord } from "@/components/AnswerSelectionEvidence";

describe("actual v3 renderer composition protocols", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "multiple procedures", fixture: multipleProcedureFixture, count: 2 },
    { name: "Unicode codepoints", fixture: unicodeProcedureFixture, count: 1 },
    { name: "mixed factual extract", fixture: mixedProcedureFixture, count: 1 },
    { name: "activity-scope disclosure", fixture: disclosureProcedureFixture, count: 1 },
  ])("validates the actual $name producer response", async ({ fixture, count }) => {
    const r = fixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await waitFor(() => expect(screen.getAllByText(/Exact instruction coverage verified/)).toHaveLength(count));
    const requirements = r.provenance.answer_selection.requirements.length;
    expect(screen.getByText(`${requirements} of ${requirements} requirements supported`)).toBeVisible();
  });
  it("rejects UTF-16 answer offsets for a non-BMP instruction", async () => {
    const r = structuredClone(unicodeProcedureFixture.response), p = r.provenance.answer_selection.requirements[0].procedure_completeness;
    p.output_certificate.answer_range.end++;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it.each([
    { name: "second procedure", fixture: multipleProcedureFixture },
    { name: "factual extract", fixture: mixedProcedureFixture },
    { name: "scope disclosure", fixture: disclosureProcedureFixture },
  ])("rejects omission of the $name even with updated answer digests", async ({ fixture }) => {
    const r = structuredClone(fixture.response);
    r.answer = r.answer.slice(0, r.answer.lastIndexOf("\n\n"));
    for (const row of r.provenance.answer_selection.requirements) {
      const proof = selectionRecord(selectionRecord(row).procedure_completeness);
      if (proof.contract === "complete-immutable-procedure-v3") selectionRecord(proof.output_certificate).answer_sha256 = createHash("sha256").update(r.answer).digest("hex");
    }
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await waitFor(() => expect(screen.getAllByText("Recorded output hash: matched")).toHaveLength(fixture === multipleProcedureFixture ? 2 : 1));
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

import numberedSpace1cFixture from "../fixtures/combined-numbered-space-1c-procedure-v3.json";
import numberedSpace85Fixture from "../fixtures/combined-numbered-space-85-procedure-v3.json";
describe("v3 Python source whitespace protocols", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "U+001C", fixture: numberedSpace1cFixture },
    { name: "U+0085", fixture: numberedSpace85Fixture },
  ])("accepts actual numbered ASGI source whitespace $name", async ({ fixture }) => {
    const r = fixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText(/Exact instruction coverage verified/);
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
});

describe("v3 Python whitespace exclusion", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("rejects a tampered self-hashed BOM step separator that Python does not classify as whitespace", async () => {
    // Negative wire mutation of the actual producer fixture, never an accepted backend fixture.
    let r = JSON.parse(JSON.stringify(numberedProcedureFixture.response).replaceAll("1. Verify", "1.\ufeffVerify")) as typeof numberedProcedureFixture.response;
    const oldHash = r.provenance.answer_selection.requirements[0].procedure_completeness.content_hash;
    const body = r.provenance.answer_selection.requirements[0].procedure_completeness.source_body;
    const newHash = createHash("sha256").update(body).digest("hex");
    r = JSON.parse(JSON.stringify(r).replaceAll(oldHash, newHash)) as typeof numberedProcedureFixture.response;
    r.provenance.answer_selection.requirements[0].procedure_completeness.output_certificate.answer_sha256 = createHash("sha256").update(r.answer).digest("hex");
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText(/Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
});

function rebindActualProcedureRequest(r: CombinedResponse | typeof numberedProcedureFixture.response, question: string, topic?: string) {
  const row = selectionRecord(r.provenance.answer_selection.requirements[0]), p = selectionRecord(row.procedure_completeness);
  r.question = question; row.original_text = question; row.input_range = { start: 0, end: Array.from(question).length };
  const binding = selectionRecord(p.request_binding), inventory = selectionRecord(p.required_inventory);
  Object.assign(binding, { question, original_text: question, input_range: structuredClone(row.input_range), ...(topic === undefined ? {} : { topic }) });
  if (inventory.declared_paragraphs) selectionRecord(inventory.declared_paragraphs).request_original = question;
  for (const values of [inventory.units, p.proof_units]) for (const value of values as unknown[]) {
    const unit = selectionRecord(value);
    if (unit.name === "paragraph_request_constraints") unit.hypothesis = `These complete ordered instructions satisfy the entire procedure request, including its material conditions: ${question}`;
    if (unit.name === "requested_scope" && topic !== undefined) unit.hypothesis = `The complete procedure is for ${topic}.`;
  }
  const cert = selectionRecord(p.output_certificate);
  cert.request_binding = structuredClone(binding); cert.required_inventory = structuredClone(inventory);
}

describe("v227 canonical procedure request scope", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "new lowercase prefix", topic: "urgent ordinary Harbor docket worksheets with no seal" },
    { name: "new subject class", topic: "night-shift ordinary Harbor docket worksheets with no seal" },
    { name: "quantity condition", topic: "ordinary Harbor docket worksheets with no seal and five milliliters of solvent" },
    { name: "unit condition", topic: "ordinary Harbor docket worksheets with no seal at 12 V" },
    { name: "foreign role", topic: "ordinary Harbor docket worksheets with no seal for archive administrators" },
    { name: "time condition", topic: "ordinary Harbor docket worksheets with no seal before noon" },
    { name: "completion condition", topic: "ordinary Harbor docket worksheets with no seal after the final count" },
    { name: "additional seal condition", topic: "ordinary Harbor docket worksheets with no seal and a red stamp" },
    { name: "foreign subject", topic: "ordinary Harbor docket worksheets with no seal for Cedar" },
  ])("rejects unconsumed $name while all producer proof and certificate bindings agree", async ({ topic }) => {
    const r = structuredClone(numberedProcedureFixture.response);
    rebindActualProcedureRequest(r, `Give the complete ordered method for ${topic}.`, topic);
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each(["standard", "normal"])("rejects requested %s mode when the source declares ordinary mode", async (mode) => {
    const r = combinedResponse(); rebindActualProcedureRequest(r, r.question.replace("ordinary", mode));
    render(<CombinedEvidence response={r} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
});

import declaredStandardFixture from "../fixtures/combined-declared-standard-procedure-v3.json";
import declaredNormalFixture from "../fixtures/combined-declared-normal-procedure-v3.json";
import standardHeadingFixture from "../fixtures/combined-standard-heading-procedure-v3.json";
describe("v227 actual source-derived request controls", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "declared standard mode", fixture: declaredStandardFixture },
    { name: "declared normal mode", fixture: declaredNormalFixture },
    { name: "standard numbered heading and its full applicability class", fixture: standardHeadingFixture },
  ])("preserves the actual ASGI $name result", async ({ fixture }) => {
    const r = fixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
  it.each([
    { name: "standard to ordinary", fixture: declaredStandardFixture, from: "standard", to: "ordinary" },
    { name: "normal to standard", fixture: declaredNormalFixture, from: "normal", to: "standard" },
  ])("rejects a coherent wire request change from $name", async ({ fixture, from, to }) => {
    const r = structuredClone(fixture.response);
    rebindActualProcedureRequest(r, r.question.replace(from, to));
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
});

import conditionPositiveFixture from "../fixtures/combined-condition-positive-v252.json";
import conditionNegativeGetFixture from "../fixtures/combined-condition-negative-get-v252.json";
import conditionNegativePublicationFixture from "../fixtures/combined-condition-negative-publication-v252.json";

describe("conditional cover v2 actual API protocols", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("keeps the retired cover-v2 prototype without complete serialized source contexts unverified", async () => {
    const r = conditionPositiveFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
  it("renders safe integrity status from the actual withheld GET without exposing stored source bodies", () => {
    const r = conditionNegativeGetFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    expect(screen.getByRole("heading", { name: "Recorded procedure evidence withheld" })).toBeVisible();
    expect(screen.getByText("Recorded procedure presentation integrity could not be verified. The saved answer and sources are withheld.")).toBeVisible();
    expect(screen.queryByText(/postponed audit|discard the marked card|Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it("leaves the actual invalid prepared publication record unverified", async () => {
    const r = conditionNegativePublicationFixture.tampered_record;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
});

import conditionRuntimeFixture from "../fixtures/combined-condition-positive-v252r1.json";
import conditionApplicableFixture from "../fixtures/combined-condition-applicable-v252r1.json";
import conditionMultichunkFixture from "../fixtures/combined-condition-multichunk-v252r1.json";
import conditionRuntimeGetFixture from "../fixtures/combined-condition-negative-get-v252r1.json";
import conditionRuntimePublicationFixture from "../fixtures/combined-condition-negative-publication-v252r1.json";
import { fireEvent } from "@testing-library/react";

describe("conditional cover v2 runtime source graph", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "all excluded members", fixture: conditionRuntimeFixture },
    { name: "applicable member retained", fixture: conditionApplicableFixture },
    { name: "two chunks per opponent", fixture: conditionMultichunkFixture },
  ])("validates actual API $name using only real component props", async ({ fixture }) => {
    const r = fixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("Recorded conditional NLI exclusions: 2")).toBeVisible();
    expect(screen.getByText("Conditional exclusions were checked from recorded source bodies and classifier logits. No NLI inference is rerun in this view.")).toBeVisible();
    const summary = screen.getByText("Recorded conditional evidence"), details = summary.closest("details")!;
    expect(details.open).toBe(false); summary.focus(); expect(summary).toHaveFocus();
    fireEvent.click(summary); expect(details.open).toBe(true);
    expect(within(details).getAllByText(/The instructions apply only to/)).toHaveLength(2);
    expect(within(details).getAllByText(/Recorded entailment margin: 10/)).toHaveLength(2);
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
  it("renders the r1 withheld GET as safe integrity-only status", () => {
    const r = conditionRuntimeGetFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    expect(screen.getByRole("heading", { name: "Recorded procedure evidence withheld" })).toBeVisible();
    expect(screen.queryByText(/postponed audit|discard the marked card|Exact instruction coverage verified/)).not.toBeInTheDocument();
  });
  it("rejects actual r1 invalid prepared publication evidence", async () => {
    const r = conditionRuntimePublicationFixture.tampered_record;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
});

type ConditionalWire = { question: string; answer: string; sources: unknown; retrieval_trace?: unknown; provenance: { answer_selection: Record<string, unknown> } };
function conditionalWire(fixture: { response: unknown } = conditionRuntimeFixture): ConditionalWire { return structuredClone(fixture.response) as ConditionalWire; }
function conditionalState(r: ConditionalWire) {
  const record = r.provenance.answer_selection, row = selectionRecord((record.requirements as unknown[])[0]), proof = selectionRecord(row.procedure_completeness);
  return { record, row, proof, inventory: selectionRecord(proof.condition_exclusion_inventory), certificate: selectionRecord(proof.output_certificate) };
}
function conditionalElement(r: ConditionalWire) { return <AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />; }
function walkConditional(value: unknown, mutate: (item: Record<string, unknown>) => void) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) { value.forEach((item) => walkConditional(item, mutate)); return; }
  const item = selectionRecord(value); mutate(item); Object.values(item).forEach((child) => walkConditional(child, mutate));
}
function changeScopes(r: ConditionalWire, mutate: (item: Record<string, unknown>) => void) { walkConditional(r.provenance.answer_selection, (item) => { if (item.contract === "procedure-condition-scope-v1") mutate(item); }); }
function copyConditionalInventory(r: ConditionalWire) { const state = conditionalState(r); state.certificate.condition_exclusion_inventory = structuredClone(state.inventory); }
function synchronizeConditionalTrace(r: ConditionalWire) { const provenance = selectionRecord(selectionRecord(r.retrieval_trace).provenance); provenance.answer_selection = structuredClone(r.provenance.answer_selection); }

describe("conditional cover v2 graph tampering", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  const cases: { name: string; mutate: (r: ConditionalWire) => void }[] = [
    { name: "unknown certificate version", mutate: (r) => { conditionalState(r).certificate.contract = "procedure-output-cover-v999"; } },
    { name: "cover-v1 downgrade", mutate: (r) => { const s = conditionalState(r); s.certificate.contract = "procedure-output-cover-v1"; delete s.certificate.condition_exclusion_inventory; delete s.proof.condition_exclusion_inventory; } },
    { name: "missing source contexts", mutate: (r) => { delete conditionalState(r).inventory.source_contexts; copyConditionalInventory(r); } },
    { name: "coherent exclusion pruning", mutate: (r) => {
      const s = conditionalState(r), exclusions = s.inventory.exclusions as Record<string, unknown>[], removed = exclusions.shift()!, id = selectionRecord(removed.source_identity).document_id;
      for (const group of s.inventory.groups as Record<string, unknown>[]) group.excluded_documents = (group.excluded_documents as unknown[]).filter((value) => value !== id);
      for (const conflict of s.record.conflicts as Record<string, unknown>[]) {
        conflict.source_extent_checks = (conflict.source_extent_checks as Record<string, unknown>[]).filter((check) => check.document_id !== id);
        conflict.subject_scope_excluded_documents = (conflict.subject_scope_excluded_documents as unknown[]).filter((value) => value !== id);
      }
      copyConditionalInventory(r);
    } },
    { name: "coherent complete group pruning", mutate: (r) => { const s = conditionalState(r); s.inventory.groups = []; s.inventory.exclusions = []; s.record.conflicts = []; copyConditionalInventory(r); } },
    { name: "context pruning", mutate: (r) => { (conditionalState(r).inventory.source_contexts as unknown[]).pop(); copyConditionalInventory(r); } },
    { name: "changed complete source body", mutate: (r) => { const source = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0]; source.source_body += " Ordinary runs also discard the card."; copyConditionalInventory(r); } },
    { name: "changed chunk content", mutate: (r) => { const source = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0]; (source.chunks as Record<string, unknown>[])[0].content += " FORGED"; copyConditionalInventory(r); } },
    { name: "shifted chunk range", mutate: (r) => { const source = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0]; selectionRecord((source.chunks as Record<string, unknown>[])[0].document_range).start = 1; copyConditionalInventory(r); } },
    { name: "foreign source identity", mutate: (r) => { const source = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0]; selectionRecord(source.source_identity).document_id = "00000000-0000-0000-0000-000000000001"; copyConditionalInventory(r); } },
    { name: "explicit metadata condition narrowing", mutate: (r) => { const source = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0]; selectionRecord(source.metadata).condition = "ordinary runs"; copyConditionalInventory(r); } },
    { name: "shifted condition range", mutate: (r) => { changeScopes(r, (scope) => { const range = selectionRecord(scope.condition_range); range.start = Number(range.start) + 1; }); } },
    { name: "changed excluded class", mutate: (r) => { changeScopes(r, (scope) => { scope.excluded_class = "ordinary run"; }); } },
    { name: "foreign selected procedure identity", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.procedure_source_identity).document_id = "00000000-0000-0000-0000-000000000001"; }); } },
    { name: "changed entire condition", mutate: (r) => { changeScopes(r, (scope) => { scope.condition = "the Cedar station postponed audit"; scope.hypothesis = `The instructions apply only to ${scope.condition}.`; selectionRecord(scope.pair).hypothesis = scope.hypothesis; }); } },
    { name: "selected prefix premise", mutate: (r) => { changeScopes(r, (scope) => { const pair = selectionRecord(scope.pair); pair.premise = String(pair.premise).split("\n\n")[0]; }); } },
    { name: "contradictory raw logits", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).logits = [5, -5, -5]; }); } },
    { name: "neutral raw logits", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).logits = [-5, -5, 5]; }); } },
    { name: "forged recorded margin", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).entailment_margin = 11; }); } },
    { name: "boolean token count", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).pair_tokens = true; }); } },
    { name: "oversized token count", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).pair_tokens = 513; }); } },
    { name: "nonfinite raw logit", mutate: (r) => { changeScopes(r, (scope) => { selectionRecord(scope.assessment).logits = [NaN, 5, -5]; }); } },
    { name: "fabricated exact-copy condition method", mutate: (r) => { changeScopes(r, (scope) => { scope.verification_method = "exact_source_copy"; }); } },
    { name: "unknown support model across settings", mutate: (r) => {
      const state = conditionalState(r); selectionRecord(state.record.evidence_support).model = "unapproved/model";
      walkConditional(state.record, (item) => { if (item.contract === "procedure-condition-model-settings-v1") selectionRecord(item.support).model = "unapproved/model"; });
    } },
    { name: "unknown reader revision across settings", mutate: (r) => {
      const state = conditionalState(r); state.record.revision = "unapproved";
      walkConditional(state.record, (item) => { if (item.contract === "procedure-condition-model-settings-v1") selectionRecord(item.reader).revision = "unapproved"; });
    } },
    { name: "captured minimum margin exceeds decision", mutate: (r) => {
      const state = conditionalState(r); selectionRecord(state.record.evidence_support).minimum_entailment_margin = 4;
      walkConditional(state.record, (item) => { if (item.contract === "procedure-condition-model-settings-v1") selectionRecord(item.support).minimum_entailment_margin = 4; });
      changeScopes(r, (scope) => { Object.assign(selectionRecord(scope.assessment), { logits: [-1, 1, -1], entailment_margin: 2 }); });
    } },
    { name: "unknown scope field", mutate: (r) => { changeScopes(r, (scope) => { scope.extra = "unrecognized"; }); } },
    { name: "main namespace NLI decision tampering", mutate: (r) => { const s = conditionalState(r); selectionRecord((s.proof.proof_units as unknown[])[0]).logits = [5, -5, -5]; } },
  ];
  it.each(cases)("retracts a valid badge for $name", async ({ mutate }) => {
    const r = conditionalWire(), view = render(conditionalElement(r));
    await screen.findByText("Exact instruction coverage verified");
    mutate(r); synchronizeConditionalTrace(r); view.rerender(conditionalElement(r));
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Recorded conditional evidence")).not.toBeInTheDocument();
  });
  it("rejects coherent inspection-member pruning while full two-chunk contexts remain", async () => {
    const r = conditionalWire(conditionMultichunkFixture), state = conditionalState(r), contexts = state.inventory.source_contexts as Record<string, unknown>[];
    const removed = (contexts[0].chunks as Record<string, unknown>[])[1].chunk_id;
    const without = (value: unknown) => (value as Record<string, unknown>[]).filter((item) => item.chunk_id !== removed);
    state.record.inspected_sources = without(state.record.inspected_sources);
    const read = selectionRecord(state.record.procedure_read_set); read.sources = without(read.sources);
    for (const group of read.groups as Record<string, unknown>[]) group.sources = without(group.sources);
    for (const conflict of state.record.conflicts as Record<string, unknown>[]) conflict.inspection_sources = without(conflict.inspection_sources);
    const manifest = selectionRecord(state.inventory.inspection_manifest); manifest.sources = without(manifest.sources);
    for (const group of manifest.groups as Record<string, unknown>[]) group.sources = without(group.sources);
    for (const group of state.inventory.groups as Record<string, unknown>[]) group.sources = without(group.sources);
    copyConditionalInventory(r); synchronizeConditionalTrace(r);
    render(conditionalElement(r)); await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
});

describe("conditional cover v2 asynchronous context guards", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each(["query identity", "complete chunk context"])("ignores obsolete hashes after in-place %s change", async (change) => {
    const pending: { resolve: (value: ArrayBuffer) => void; value: ArrayBuffer }[] = [];
    const digest = vi.fn((_algorithm: unknown, data: ArrayBuffer) => new Promise<ArrayBuffer>((resolve) => {
      pending.push({ resolve, value: Uint8Array.from(createHash("sha256").update(new Uint8Array(data)).digest()).buffer });
    }));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const r = conditionalWire(), view = render(conditionalElement(r));
    await waitFor(() => expect(pending.length).toBe(5));
    const old = pending.splice(0);
    if (change === "query identity") r.provenance.answer_selection.query_id = "new-record";
    else {
      const context = (conditionalState(r).inventory.source_contexts as Record<string, unknown>[])[0];
      (context.chunks as Record<string, unknown>[])[0].content += " FORGED"; copyConditionalInventory(r);
    }
    view.rerender(conditionalElement(r));
    await waitFor(() => expect(pending.length).toBeGreaterThan(0));
    await act(async () => { old.forEach((item) => item.resolve(item.value)); });
    expect(screen.getByText("Recorded output hash: pending")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    await act(async () => { pending.forEach((item) => item.resolve(item.value)); });
    await screen.findByText("Recorded output hash: matched");
    if (change === "query identity") expect(screen.getByText("Exact instruction coverage verified")).toBeVisible();
    else expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
  it("does not expose untrusted bodies or reasons when presentation is explicitly withheld", () => {
    render(<AnswerSelectionEvidence value={{ presentation_verification: { status: "invalid", reason: "PRIVATE-STORED-BODY" }, requirements: [{ kind: "procedure", original_text: "PRIVATE-STORED-BODY", witnesses: [{ value: "PRIVATE-STORED-BODY" }] }] }} />);
    expect(screen.getByRole("heading", { name: "Recorded procedure evidence withheld" })).toBeVisible();
    expect(screen.queryByText(/PRIVATE-STORED-BODY/)).not.toBeInTheDocument();
  });
});

describe("conditional retained trace authority regression", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("rejects coherent full graph pruning and cover-v1 downgrade against the unchanged actual retrieval trace", async () => {
    const r = conditionalWire(), state = conditionalState(r);
    walkConditional(state.record, (item) => {
      delete item.condition_exclusion_inventory;
      if (item.contract === "procedure-output-cover-v2") item.contract = "procedure-output-cover-v1";
    });
    delete state.record.procedure_read_set; state.record.procedure_contexts = []; state.record.inspected_sources = []; state.record.conflicts = [];
    render(<AnswerSelectionEvidence value={state.record} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={conditionRuntimeFixture.response.retrieval_trace} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
});

describe("conditional canonical opaque group ordering", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("accepts a generated z/é metadata-wire control with unchanged actual source bodies and recorded model decisions", async () => {
    // This is a generated protocol ordering control, not a new actual-ASGI fixture.
    const r = conditionalWire(), state = conditionalState(r), read = selectionRecord(state.record.procedure_read_set);
    const contexts = state.inventory.source_contexts as Record<string, unknown>[];
    const labels = ["z-condition", "é-condition"], groupByDocument = new Map(contexts.map((context, index) => [selectionRecord(context.source_identity).document_id, labels[index]]));
    for (const source of read.sources as Record<string, unknown>[]) if (groupByDocument.has(source.document_id)) source.conflict_group = groupByDocument.get(source.document_id);
    for (const context of contexts) selectionRecord(context.metadata).conflict_group = groupByDocument.get(selectionRecord(context.source_identity).document_id);
    const groups = labels.map((group) => ({ group, sources: (read.sources as Record<string, unknown>[]).filter((source) => source.conflict_group === group) }));
    read.groups = structuredClone(groups);
    const original = (state.record.conflicts as Record<string, unknown>[])[0];
    state.record.conflicts = groups.map((group) => {
      const id = group.sources[0].document_id;
      return { ...structuredClone(original), group: group.group, inspection_sources: structuredClone(group.sources),
        source_extent_checks: (original.source_extent_checks as Record<string, unknown>[]).filter((check) => check.document_id === id),
        subject_scope_excluded_documents: [id], applicable_documents: [] };
    });
    const manifest = selectionRecord(state.inventory.inspection_manifest); manifest.sources = structuredClone(read.sources); manifest.groups = structuredClone(groups);
    state.inventory.groups = groups.map((group) => ({ ...structuredClone(group), excluded_documents: [group.sources[0].document_id], applicable_documents: [] }));
    for (const exclusion of state.inventory.exclusions as Record<string, unknown>[]) exclusion.group = groupByDocument.get(selectionRecord(exclusion.source_identity).document_id);
    copyConditionalInventory(r);
    const trace = structuredClone(conditionRuntimeFixture.response.retrieval_trace);
    selectionRecord(trace.provenance).answer_selection = structuredClone(state.record);
    render(<AnswerSelectionEvidence value={state.record} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={trace} />);
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("Recorded conditional NLI exclusions: 2")).toBeVisible();
  });
});

import conditionAuthorityFixture from "../fixtures/combined-condition-positive-v264.json";
import coverOneDerivedFixture from "../fixtures/combined-cover1-derived-get-v264.json";
import conditionPrunedGetFixture from "../fixtures/combined-condition-whole-prune-get-v264.json";
import conditionPrunedPublicationFixture from "../fixtures/combined-condition-whole-prune-publication-v264.json";
describe("conditional actual retained capture v264", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("verifies the actual completed response with its independent raw retrieval trace", async () => {
    const r = conditionAuthorityFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("Recorded conditional NLI exclusions: 2")).toBeVisible();
  });
  it("preserves actual cover-v1 GET when only derived presentation stamps differ", async () => {
    const r = coverOneDerivedFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Exact instruction coverage verified");
  });
  it.each([
    { name: "GET", fixture: conditionPrunedGetFixture },
    { name: "publication", fixture: conditionPrunedPublicationFixture },
  ])("rejects the actual coherently pruned $name presentation against its unchanged trace", async ({ fixture }) => {
    const r = fixture.tampered_record;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
  it.each([undefined, null, {}, { provenance: {} }])("leaves cover-v2 unverified with unavailable actual capture %j", async (capture) => {
    const r = conditionAuthorityFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={capture} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Conditional evidence unverified: retained query capture is missing or malformed.")).toBeVisible();
    expect(screen.getByText("Recorded conditional evidence")).toBeVisible();
  });
});

describe("conditional immutable capture inputs", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([
    { name: "prepared question", mutate: (r: ConditionalWire) => { conditionalState(r).row.prepared_question = "Give a different source procedure."; } },
    { name: "workspace scope", mutate: (r: ConditionalWire) => { conditionalState(r).row.source_workspace = "foreign-workspace"; } },
    { name: "dependency", mutate: (r: ConditionalWire) => { conditionalState(r).row.depends_on = ["unproved-r9"]; } },
    { name: "reader threshold", mutate: (r: ConditionalWire) => { r.provenance.answer_selection.threshold = 9; } },
    { name: "reader contract", mutate: (r: ConditionalWire) => { r.provenance.answer_selection.reader_contract = "unknown-reader-contract"; } },
    { name: "support device", mutate: (r: ConditionalWire) => { selectionRecord(r.provenance.answer_selection.evidence_support).device = "other-device"; } },
    { name: "captured document scope", mutate: (r: ConditionalWire) => { selectionRecord(r.provenance.answer_selection.procedure_read_set).document_ids = []; } },
    { name: "captured member count", mutate: (r: ConditionalWire) => { (r.provenance.answer_selection.inspected_sources as unknown[]).pop(); } },
    { name: "retained trace input", mutate: (r: ConditionalWire) => { selectionRecord(selectionRecord(selectionRecord(r.retrieval_trace).provenance).answer_selection).threshold = 9; } },
  ])("rejects changed $name against the separate actual retained inputs", async ({ mutate }) => {
    const r = conditionalWire(conditionAuthorityFixture), view = render(conditionalElement(r));
    await screen.findByText("Exact instruction coverage verified");
    mutate(r); view.rerender(conditionalElement(r));
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Conditional evidence unverified: retained query capture does not match the displayed record.")).toBeVisible();
  });
  it("ignores only derived presentation/readiness fields while retaining full body replay", async () => {
    const r = conditionalWire(conditionAuthorityFixture);
    r.provenance.answer_selection.presentation_verification = { status: "verified", reason: null };
    r.provenance.answer_selection.readiness = "not_loaded";
    selectionRecord(r.provenance.answer_selection.evidence_support).readiness = "not_loaded";
    const traceSelection = selectionRecord(selectionRecord(selectionRecord(r.retrieval_trace).provenance).answer_selection);
    delete traceSelection.presentation_verification; traceSelection.readiness = "ready";
    selectionRecord(traceSelection.evidence_support).readiness = "ready";
    render(conditionalElement(r)); await screen.findByText("Exact instruction coverage verified");
  });
  it("retracts a complete conditional badge while new retained-context hashes are outstanding", async () => {
    const pending: { resolve: (value: ArrayBuffer) => void; value: ArrayBuffer }[] = [];
    const digest = vi.fn((_algorithm: unknown, data: ArrayBuffer) => new Promise<ArrayBuffer>((resolve) => {
      pending.push({ resolve, value: Uint8Array.from(createHash("sha256").update(new Uint8Array(data)).digest()).buffer });
    }));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const r = conditionalWire(conditionAuthorityFixture), view = render(conditionalElement(r));
    await waitFor(() => expect(pending.length).toBe(5));
    const old = pending.splice(0);
    selectionRecord(selectionRecord(selectionRecord(r.retrieval_trace).provenance).answer_selection).threshold = 9;
    view.rerender(conditionalElement(r)); await waitFor(() => expect(pending.length).toBeGreaterThan(0));
    await act(async () => { old.forEach((item) => item.resolve(item.value)); });
    expect(screen.getByText("Recorded output hash: pending")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    await act(async () => { pending.forEach((item) => item.resolve(item.value)); });
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
});

describe("retained capture ordering semantics", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("normalizes aggregate source/context ordering while retaining duplicate counts", async () => {
    const r = conditionalWire(conditionAuthorityFixture), retained = selectionRecord(selectionRecord(selectionRecord(r.retrieval_trace).provenance).answer_selection);
    (retained.inspected_sources as unknown[]).reverse();
    const contexts = retained.procedure_contexts as Record<string, unknown>[]; contexts.reverse();
    contexts.forEach((context) => (context.sources as unknown[]).reverse());
    const read = selectionRecord(retained.procedure_read_set); (read.sources as unknown[]).reverse(); (read.groups as unknown[]).reverse();
    (read.groups as Record<string, unknown>[]).forEach((group) => (group.sources as unknown[]).reverse());
    const view = render(conditionalElement(r)); await screen.findByText("Exact instruction coverage verified");
    (retained.inspected_sources as unknown[]).push(structuredClone((retained.inspected_sources as unknown[])[0]));
    view.rerender(conditionalElement(r)); await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
  it("keeps requirement order semantic when checking actual retained cover-v1 input", async () => {
    const r = structuredClone(multipleProcedureFixture.response), retained = selectionRecord(selectionRecord(r.retrieval_trace.provenance).answer_selection);
    (retained.requirements as unknown[]).reverse();
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await waitFor(() => expect(screen.getAllByText("Recorded output hash: matched")).toHaveLength(2));
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getAllByText("Procedure completeness unknown")).toHaveLength(2);
  });
});

describe("legacy metadata-only retrieval capture", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("preserves legitimate cover-v1 with a metadata-only trace covering its inspected source", async () => {
    const r = coverOneDerivedFixture.response;
    const trace = { scores: r.retrieval_trace.scores, refusal_threshold: null };
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={trace} />);
    await screen.findByText("Exact instruction coverage verified");
  });
  it("requires a full capture for cover-v2 even when legacy score membership is complete", async () => {
    const r = conditionAuthorityFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={{ scores: r.retrieval_trace.scores, refusal_threshold: null }} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("Conditional evidence unverified: retained query capture is missing or malformed.")).toBeVisible();
  });
  it("rejects erased capture and primary-only inspection when legacy trace scores still retain opponents", async () => {
    const r = conditionalWire(), state = conditionalState(r);
    walkConditional(state.record, (item) => { delete item.condition_exclusion_inventory; if (item.contract === "procedure-output-cover-v2") item.contract = "procedure-output-cover-v1"; });
    const primary = (state.record.inspected_sources as Record<string, unknown>[]).find((source) => source.document_id === state.proof.document_id)!;
    state.record.inspected_sources = [primary]; state.record.procedure_contexts = []; state.record.conflicts = []; delete state.record.procedure_read_set;
    render(<AnswerSelectionEvidence value={state.record} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={{ scores: conditionRuntimeFixture.response.retrieval_trace.scores, refusal_threshold: null }} />);
    await screen.findByText("Recorded output hash: matched");
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
});

describe("conditional trace-only presentation switches", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each(["derived stamp", "legacy metadata"])("binds cached results when only retrievalTrace changes to %s", async (change) => {
    let hold = false;
    const pending: { resolve: (value: ArrayBuffer) => void; value: ArrayBuffer }[] = [];
    const digest = vi.fn((_algorithm: unknown, data: ArrayBuffer) => {
      const value = Uint8Array.from(createHash("sha256").update(new Uint8Array(data)).digest()).buffer;
      return hold ? new Promise<ArrayBuffer>((resolve) => pending.push({ resolve, value })) : Promise.resolve(value);
    });
    vi.stubGlobal("crypto", { subtle: { digest } });
    const r = conditionalWire(conditionAuthorityFixture), view = render(conditionalElement(r));
    await screen.findByText("Exact instruction coverage verified"); hold = true;
    if (change === "derived stamp") {
      const capture = selectionRecord(selectionRecord(selectionRecord(r.retrieval_trace).provenance).answer_selection);
      selectionRecord(capture.evidence_support).readiness = "ready";
    } else r.retrieval_trace = { scores: selectionRecord(r.retrieval_trace).scores, refusal_threshold: null };
    view.rerender(conditionalElement(r)); await waitFor(() => expect(pending).toHaveLength(4));
    expect(screen.getByText("Recorded output hash: pending")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    await act(async () => { pending.forEach((item) => item.resolve(item.value)); });
    await screen.findByText("Recorded output hash: matched");
    if (change === "derived stamp") expect(screen.getByText("Exact instruction coverage verified")).toBeVisible();
    else {
      expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
      expect(screen.getByText("Conditional evidence unverified: retained query capture is missing or malformed.")).toBeVisible();
    }
  });
});

import metadataOnlyGetFixture from "../fixtures/combined-cover1-metadata-only-get-v264r1.json";
describe("actual metadata-only legacy GET", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("verifies the actual full trace DTO with provenance null and complete retained score membership", async () => {
    const r = metadataOnlyGetFixture.response;
    render(<AnswerSelectionEvidence value={r.provenance.answer_selection} question={r.question} answer={r.answer} sources={r.sources} retrievalTrace={selectionRecord(r).retrieval_trace} />);
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
});

describe("conditional recorded inference inspection", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("exposes raw decisions and captured model revision/margin without claiming a new inference", async () => {
    const r = conditionalWire(conditionAuthorityFixture); render(conditionalElement(r));
    await screen.findByText("Exact instruction coverage verified");
    const details = screen.getByText("Recorded conditional evidence").closest("details")!;
    fireEvent.click(within(details).getByText("Recorded conditional evidence"));
    expect(within(details).getAllByText("Recorded NLI logits (contradiction, entailment, neutral): -5, 5, -5")).toHaveLength(2);
    expect(within(details).getAllByText("Recorded NLI method: nli_entailment · label: entailment")).toHaveLength(2);
    expect(within(details).getAllByText("Captured minimum entailment margin: 0 · support revision: 70de96bd327ef95839a8bd9f6299875cae396433")).toHaveLength(2);
  });
});

describe("retained authority before proof version dispatch", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  const mutations: [string, (r: ConditionalWire) => void][] = [
    ["legacy v2", (r) => { conditionalState(r).proof.contract = "complete-immutable-procedure-v2"; }],
    ["legacy v1", (r) => { conditionalState(r).proof.contract = "complete-immutable-procedure-v1"; }],
    ["unknown version", (r) => { conditionalState(r).proof.contract = "complete-immutable-procedure-v999"; }],
    ["removed version", (r) => { delete conditionalState(r).proof.contract; }],
    ["removed proof", (r) => { delete conditionalState(r).row.procedure_completeness; }],
    ["factual relabel", (r) => { const state = conditionalState(r); state.row.kind = "fact"; state.proof.contract = "complete-immutable-procedure-v2"; }],
  ];
  for (const [label, fixture] of [["conditional cover-v2", conditionAuthorityFixture], ["ordinary cover-v1", coverOneDerivedFixture]] as const) {
    it.each(mutations)(`${label}: %s cannot select a weaker validator`, async (_name, mutate) => {
      const r = conditionalWire(fixture), state = conditionalState(r), originalTrace = structuredClone(r.retrieval_trace);
      delete state.proof.output_certificate; delete state.proof.condition_exclusion_inventory; state.record.conflicts = [];
      for (const unit of state.proof.proof_units as Record<string, unknown>[]) {
        unit.label = "entailment"; unit.entailment_margin = 10; unit.pair_tokens = 81; unit.supported = true;
      }
      mutate(r); render(conditionalElement(r));
      if (selectionRecord(state.row.procedure_completeness).structure === "declared_paragraphs") await screen.findByText("Recorded source-body hash: matched");
      expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
      expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
      expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
      expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
      expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
      expect(r.retrieval_trace).toEqual(originalTrace);
    });
  }
  it.each(["missing", "empty"])("retained requirements remain visible as an unverified capture when presentation rows are %s", (change) => {
    const r = conditionalWire(conditionAuthorityFixture), state = conditionalState(r);
    if (change === "missing") delete state.record.requirements; else state.record.requirements = [];
    render(conditionalElement(r));
    expect(screen.getByText("Recorded requirement evidence unverified: retained query capture does not match the displayed record.")).toBeVisible();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Supported by recorded source evidence")).not.toBeInTheDocument();
  });
  it("retracts legacy completion immediately when only the actual trace switches to modern authority", async () => {
    const r = conditionalWire(conditionAuthorityFixture), state = conditionalState(r), trace = r.retrieval_trace;
    state.proof.contract = "complete-immutable-procedure-v2"; delete state.proof.output_certificate; delete state.proof.condition_exclusion_inventory; state.record.conflicts = [];
    for (const unit of state.proof.proof_units as Record<string, unknown>[]) {
      unit.label = "entailment"; unit.entailment_margin = 10; unit.pair_tokens = 81; unit.supported = true;
    }
    delete r.retrieval_trace;
    const view = render(conditionalElement(r));
    await screen.findByText(/Full source extent verified/);
    r.retrieval_trace = trace; view.rerender(conditionalElement(r));
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
    expect(screen.getByText("Procedure completeness unknown")).toBeVisible();
  });
});

import liveCedarGetFixture from "../fixtures/combined-live-cedar-api-v286.json";
describe("actual live QA candidate discovery contract", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  function liveWire() { return structuredClone(liveCedarGetFixture) as ConditionalWire; }
  function observation(r: ConditionalWire) { return selectionRecord((r.provenance.answer_selection.qa_observations as unknown[])[0]); }
  it("verifies the unchanged live GET whose selected third raw QA candidate differs from its expanded span", async () => {
    const r = liveWire(), record = r.provenance.answer_selection, obs = observation(r);
    const proposals = record.proposals as Record<string, unknown>[];
    expect(proposals.filter((item) => item.origin === "qa_reader")).toHaveLength(3);
    expect(conditionalState(r).proof.raw_seed).toMatchObject({ origin: "qa_reader", chunk_range: { start: 100, end: 169 } });
    expect(obs.span).toMatchObject({ start: 0, end: 399 });
    expect(selectionRecord(obs.diagnostics).raw_candidates).toHaveLength(3);
    render(conditionalElement(r));
    expect(screen.getByRole("heading", { name: "Source-declared procedure copy" })).toBeVisible();
    await screen.findByText("Exact instruction coverage verified");
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
    expect(screen.queryByText("Evidence discovery metadata invalid")).not.toBeInTheDocument();
  });
  const corruptions: [string, (r: ConditionalWire) => void][] = [
    ["third raw candidate text", (r) => { (selectionRecord(observation(r).diagnostics).raw_candidates as Record<string, unknown>[])[2].text = "Invented instruction"; }],
    ["third raw candidate range", (r) => { (selectionRecord(observation(r).diagnostics).raw_candidates as Record<string, unknown>[])[2].start = 99; }],
    ["selected raw candidate moved beyond the three candidate budget", (r) => { const d = selectionRecord(observation(r).diagnostics), a = d.raw_candidates as Record<string, unknown>[]; d.raw_candidates = [a[0], a[1], a[0], a[2]]; }],
    ["non-object raw candidate", (r) => { (selectionRecord(observation(r).diagnostics).raw_candidates as unknown[])[0] = null; }],
    ["non-array raw candidates", (r) => { selectionRecord(observation(r).diagnostics).raw_candidates = {}; }],
    ["unrelated QA requirement", (r) => { observation(r).requirement_id = "other"; }],
    ["unrelated QA chunk", (r) => { observation(r).chunk_id = "other"; }],
    ["duplicate QA observation", (r) => { const a = r.provenance.answer_selection.qa_observations as unknown[]; a.push(structuredClone(a[0])); }],
    ["expanded span text with wrong codepoint extent", (r) => { selectionRecord(observation(r).span).end = 398; }],
  ];
  it.each(corruptions)("rejects %s while preserving the actual complete-proof capture", async (_name, mutate) => {
    const r = liveWire(); mutate(r); render(conditionalElement(r));
    await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.queryByText(/Full source extent verified/)).not.toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
  });
});

describe("metadata raw authority and legacy boundary", () => {
  beforeEach(() => { vi.stubGlobal("crypto", webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  function narrowedLive() {
    const r = structuredClone(liveCedarGetFixture) as ConditionalWire, record = r.provenance.answer_selection;
    record.proposals = (record.proposals as Record<string, unknown>[]).filter((proposal) => proposal.origin !== "qa_reader" || (record.selected_proposal_ids as unknown[]).includes(proposal.proposal_id));
    const proposal = (record.proposals as Record<string, unknown>[]).find((item) => item.origin === "qa_reader")!;
    const observation = selectionRecord((record.qa_observations as unknown[])[0]), candidate = { ...selectionRecord(proposal.chunk_range), text: proposal.text };
    observation.span = { ...candidate };
    return { r, observation, candidate };
  }
  function oldRecord() {
    const record: Record<string, unknown> = profiledRecord("qa_reader");
    record.inspected_sources = [{ document_id: "document", document_version: 1, content_hash: "a".repeat(64), chunk_id: "chunk" }];
    return record;
  }
  it.each([null, [], false, "bad diagnostics", 0])("rejects explicit malformed diagnostic container %# even after exact raw-span narrowing", async (diagnostics) => {
    const { r, observation } = narrowedLive(); observation.diagnostics = diagnostics;
    render(conditionalElement(r)); await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
  });
  it.each([null, {}, "bad parts", true, 1, [null], [[]], [false]])("rejects malformed one-part containers %# without using a top-level raw-span rescue", async (parts) => {
    const { r, observation, candidate } = narrowedLive(); observation.diagnostics = { parts, part_count: 1, raw_span: candidate };
    render(conditionalElement(r)); await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
  it.each([false, true])("requires raw authority for a modern profile even with retained capture absent: %s", async (absentCapture) => {
    const { r, observation } = narrowedLive(); observation.diagnostics = { decision: "answer" };
    if (absentCapture) delete r.retrieval_trace;
    render(conditionalElement(r)); await screen.findByText("Recorded output hash: matched");
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("Exact instruction coverage verified")).not.toBeInTheDocument();
  });
  it("does not let a displayed old-profile label erase modern retained metadata authority", () => {
    const { r, observation } = narrowedLive(); observation.diagnostics = { decision: "answer" };
    r.provenance.answer_selection.evidence_profile = recordedProfile();
    render(conditionalElement(r));
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("1 of 1 requirements supported")).not.toBeInTheDocument();
  });
  it.each(["absent", "legacy metadata", "old full capture"])("preserves genuine profile-v1 selected-span history with %s", (context) => {
    const record = oldRecord(), trace = context === "absent" ? undefined : context === "legacy metadata" ? { scores: [] } : { provenance: { answer_selection: structuredClone(record) } };
    render(<AnswerSelectionEvidence value={record} retrievalTrace={trace} />);
    expect(screen.queryByText("Evidence discovery metadata invalid")).not.toBeInTheDocument();
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
  });
  it("retains captured raw-observation authority even when its historical profile is v1", () => {
    const record = oldRecord(), captured = structuredClone(record), observation = selectionRecord((captured.qa_observations as unknown[])[0]);
    observation.diagnostics = { raw_candidates: [{ ...selectionRecord(observation.span) }] };
    render(<AnswerSelectionEvidence value={record} retrievalTrace={{ provenance: { answer_selection: captured } }} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.queryByText("1 of 1 requirements supported")).not.toBeInTheDocument();
  });
  it("retracts legacy metadata support when only retained QA raw authority changes", () => {
    const record = oldRecord(), trace = { provenance: { answer_selection: structuredClone(record) } }, view = render(<AnswerSelectionEvidence value={record} retrievalTrace={trace} />);
    expect(screen.getByText("1 of 1 requirements supported")).toBeVisible();
    const observation = selectionRecord((trace.provenance.answer_selection.qa_observations as unknown[])[0]);
    observation.diagnostics = { raw_span: { ...selectionRecord(observation.span) } };
    view.rerender(<AnswerSelectionEvidence value={record} retrievalTrace={trace} />);
    expect(screen.getByText("Evidence discovery metadata invalid")).toBeVisible();
    expect(screen.getByText("0 of 1 requirements supported")).toBeVisible();
  });
});
