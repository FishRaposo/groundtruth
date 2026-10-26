# Independent first frozen blind-pair audit V519 — FAILED / QUIET

Checked locally 2026-10-26, after V518 authorized inspection of both sealed first
reports. Scope: frozen499 observations and source/label/runtime provenance. No
new prediction, model import/execution, provider, API, service, browser,
installation, WSL, source/label/scorer/settings/report edit, or publication.
Only this new V519 directory was written. Cash unknown; FTH-016 support.

## Decision

The frozen candidate fails the specified gate decisively. Exact portable replay
reproduces the original comparison, including every recorded case field and
summary: default reranked17/120 positives versus original baseline69/120,
80/80 negatives, and zero recorded execution/access/citation/span errors.
Threshold114/120 and improvement are both unmet. All103 positive failures are
whole-request refusals, not successful answers rejected for a paraphrase.

| Method | Original positives | Candidate positives | Original negatives | Candidate negatives |
|---|---:|---:|---:|---:|
| keyword |69/120|17/120|79/80|80/80|
| vector |63/120|17/120|79/80|80/80|
| hybrid |70/120|17/120|79/80|80/80|
| reranked |69/120|17/120|79/80|80/80|

The opposition supplement's **80 missing inspections is a helper shape error**,
not80 absent source observations. All40 candidate required case/method pairs
contain both required immutable opponents in `inspected_sources` and
`conflicts[].source_scope_decisions`, with included=true. The helper recognizes
only `source_extent_checks` and procedure-condition exclusions. Do not erase its
first result or rewrite the score. Correcting that accounting would not rescue
the failed positive gate. The actual semantic conflict comparison has empty
assessments and `not_relevant` outcomes; the negative refusals therefore do not
prove contradiction recognition.

## Frozen binding and chronology

`audit.py` exit0 ran932 checks. It rehashed every original arm/pair sealed entry
(including private files by bytes only, without printing/copying contents), both
author/reviewer freeze inventories, source31's232 entries, original417's215
entries, all frozen scorer files, all three model manifests/assets, runtime446,
493 dependency pins and496's exact reviewed-file approval. No mismatch against
those frozen byte inventories. Before/after audit pins agree. Exact hashes are
in `input-hashes.json`, rather than inferred from report claims.

Important pins:

- Candidate commit `de79a787d922b2ace0c5a9ee06c5a17a7a497730`;
  baseline `e19006c9e8f1a11ef4930e24ed88128e765b6bf5`.
- Freeze446 `15b6e024134e2615e8fb2584fdbb0e2a0181971a534a8a09fa07448ed8064939`.
- Source31 manifest `466c062d8ce8a7f64ee6b9a8722b2ae81a75757ede7a3cfdd930da80e754a671`.
- Raw manifest `a5e732c5220bda88c63c774d9b40a8daed54cd686f36cff884b48229e9409894`.
- Author freeze inventory `763cbc2db100a62bc1f8fa8b5e308b638081ad3640e86e963079a68b9f1a830e`;
  reviewer458 inventory `7d89ae8c6fb512ff0d9e020037f1859997df06324f973536fcd38e6191f7a01a`.
- Selection479 `65336fa55b7be077a014da9c039cc38f810fbdedd0c5784e6444a9ffa27a8d29`.
- Baseline first report `5cbe1d709f08a5fc74f4debdd98dbe5a1e37c95ff57aee0c382f550a4d6a941f`;
  candidate first report `81d9e42cf9588383a50f9d8d2269fdebc345765f5469b1e749f6f223d9ed8190`.
- Arm seals baseline `abc891b048e11679600cf1d7584d61920ae4457414758ff2a5c47cf7093ded72`,
  candidate `fe17400cbf80d754931c8b19ba0ab28fce4453a5b620e5f33828b8af7881908d`;
  pair seal `8e87d25ffe229ba2cd5501d0248923dd0bfbbe35ff4f5752f513ab321c094b78`.

Freeze446 is21:01:49.990557Z. Author/reviewer freeze pointers' filesystem mtimes
are21:12:03.705223Z and21:15:46.522286Z; selection479 binding is21:26:03.949899Z.
Baseline report is21:51:04.063726Z, sealed21:51:08.293105Z. Candidate report is
22:30:45.584455Z, sealed22:31:00.587680Z. Pair seal is22:31:03.310289Z. This matches
sequential baseline then candidate, closed children and paired seal before
postseal comparison/opposition in the controller. Filesystem timestamps are
local corroboration, not an external timestamp authority. The evaluation writes
each report only at completion, so report created_at alone does not date the
first query; retained API logs place baseline readiness/ingestion around21:47Z,
after both freezes. No outcome inspection is claimed before the pair seal.

`source_binding.py` reads only exact named frozen manifest paths using Git
`cat-file --batch`. Initial strict-byte comparison returned1:168/232 candidate
and209/215 baseline files differ from Git blobs. Follow-up comparison establishes
**every difference is CRLF versus LF only**, zero other content differences,
exit0. Both results are retained separately; frozen snapshot byte checks remain
exact and unchanged. Do not call these Git-blob byte equality. The pinned
original archive also hashes correctly.

Original487 remains infrastructure_partial, no pair seal, incomplete first arm,
and no report binding. Its sealed runtime-check failure was not a discarded
quality score. V493/496 repairs only RECORD raw-byte representation checking;
current worker/controller/pins match the independently approved hashes.

## Actual source, HTTP and runtime scope

Both reports contain all200 exact case IDs/categories through all four methods,
800 HTTP200 rows per arm. Portable source maps bind110 logical documents and
their immutable version/chunk observations; common source/case contract and raw
identity agree across independently compiled arm views. Frozen replay validates
questions, selected runtime, full required fact/ordered-step coverage, source
versions/hashes, authorization, citations and candidate spans against canonical
sources, rather than ranks or source mentions. No score/field disagreement.

Retained `commands.json` uses the canonical optional Python with real
`-m uvicorn app.main:app`, source417 cwd for8401 and source31 cwd for8402, separate
SQLite paths, inline HTTP seed/version observations and source31 schema2 tools.
Actual API logs contain source417/source31 embedding import paths respectively;
candidate readiness has reader-parts-v14, requirement-evidence-v2,
ordinary_session_activity_v1, source_declared_procedure_copy_v1 and
scoped_note_context_v2. Baseline keeps its original lexical/disabled-support API
configuration; tool-only profile changes do not substitute its API source.
Candidate is reader/extractive with local pinned embedding/reader/NLI fingerprints.
This is evidence of the intended source-bound local runtime, with no identified
impostor. It is **not installed-binary attestation**; package RECORD verification
binds metadata, not every executable/library binary.

Both runtime/compile/selection/migrate/seed commands exit0; each evaluator exits1
for quality failure. API exit1 follows owned Windows process-tree termination;
both cleanup records say children_closed and port_closed true. Postseal
comparison/opposition each exit1. No service/process was started or stopped by
this audit.

## Definite refusal mechanisms and semantic checks

Machine-readable case evidence is in `positive-mechanisms.json`; counts below
are reranked case/requirement counts, not mutually exclusive causal totals.
All methods fail the same103 positives. By author subgroup: a1 procedures+roles
0/20; a2 quantity+location0/20; a3 duration7/20; a4 prohibitions0/20; a5 scoped
conditional facts0/20; a6 special-session roles10/20.

1. **Request decomposition loses required semantics.** V451-01-a1's activity
   lead and routine become generic; V451-03-a1 collapses lead, deputy and routine
   into one procedure; V451-04-a1 makes the routine generic and detached role
   fragments lack an interpretable subject. Only11/20 a1 requests have any
   procedure-kind requirement. This prevents complete authored coverage before
   retrieval quality can help.
2. **Unnumbered ordinary procedures are rejected.** All11 recognized procedure
   requests have `ordered_instruction_block_missing`. V451-02-a1 and03-a1 current
   guides explicitly introduce an ordinary routine followed by four ordered
   imperative sentences. The frozen binding path requires a recognized ordered
   or unnumbered-block shape (`requirement_binding.py:1118-1123`); these natural
   source routines are missed. Do not remedy this by adding numbering to labels
   or source bytes in the exposed set.
3. **Whole-scope role scan hits a workspace cap.** Nine positives have
   `role_scope_document_budget_exceeded`, with65 captured document records and
   limit64; examples01-a1,01-a6,03-a6,04-a6,06-a6,14-a6,17-a6,18-a6,19-a6.
   `role_scope_inspection.py:225-275` queries all authorized published documents
   before contextual role inspection and returns incomplete when65 are present.
   Three additional role requirements report session scope not interpretable.
   The budget is a conservative control, but this set demonstrates its present
   user-visible false-refusal boundary; increasing it alone does not fix parser
   or binding failures.
4. **Correct reader spans fail proposition binding before model support.**
   V451-01-a2 reads `26` from the26-letter wheel sentence and01-a3 reads
   `7 minutes`, but rejects `subject_missing_from_selected_clause` with no
   hypothesis.01-a4 reads the complete prohibition yet returns
   `unsupported_negative_boolean`.01-a5 reads `silver pointer` from the
   reversed-alphabet condition but rejects requested relation binding. The
   question asks a conditional property, not a generic role or a new source
   authority. Correct raw spans are not final answers, but these examples locate
   the rejection before NLI, rather than demonstrating an inadequate model.
5. **Equivalent literal proposals spuriously conflict.** V451-05-a2 has supported
   values `3` and `3 footstep surfaces`, with the identical hypothesis
   `Tangle Lane reel contains 3 footstep surfaces`, same current source and
   same NLI scores.10-a2 similarly has `8` and `8 beats`, with identical
   `Pulse Grove pattern has 8 beats` hypotheses. Source31
   `requirement_answers.py:1842-1857` compares raw `w.value` strings for non-role
   requirements and marks more than one value conflicting. These are two spans
   of one supported quantity, not incompatible facts. See
   `proposal-equivalence.json`. Both requests also have an unsupported location
   requirement, so fixing this alone would not turn either into a complete pass.

All120 positive labels' required facts/steps are independently grounded in their
declared current authorized sources in this audit. Both source contributions are
needed for40 positives; the20 routine cases request complete actions and role
facts. Label review458 has200 reviewed entries, no corrections, and binds the
same raw corpus. The17 nonrefused candidate reranked answers are short current
source extracts matching the requested fact; no concrete unsupported extra claim
or label/scorer disagreement was found in those answers. The103 observed
refusals are genuine failures under the agreed request contract, not evidence
that all103 source-backed labels should be relaxed.

The sole baseline negative failure09-z1 outputs an untrusted exhibit, including
its warning that the copied instruction is not approved fact. This is a
nonrefusal failure under the frozen contract. It does **not by itself prove the
baseline accepted the embedded instruction as authority**. Candidate refusal80/80
also does not prove specific stale/conflict/injection reasoning: some refusals
arise from unsupported parsing/binding, with conflict assessments empty.

## Opposition source-provenance conclusion

Reviewer458 sidecar has exactly200 lists, ten nonempty two-source lists and190
empty lists. Preparation472 changes the field alias while keeping `cases`
identical; both sidecar hashes remain bound by499's pair seal. All40 candidate
required rows have2/2 current source identities and hashes in explicit inspection
provenance, plus conflict inclusion decisions for both. This is not a retrieval
rank inference. Source31 `requirement_answers.py:774-949` calls curated group
inspection, validates additional current members, adds them to inspected sources,
and emits the generic/boolean `source_scope_decisions` records. The helper's
procedure-only collection omits that supported source shape.

Keep `opposition.json` unchanged. Recommended separate follow-up is a read-only
supplement/helper contract test accepting both source-proven generic and
procedure shapes, rejecting ranks-only/wrong-version/wrong-hash observations.
Do not conflate complete source inspection with successful semantic contradiction
classification; this pair demonstrates the former and fails to establish the
latter.

## Replay portability, commands and limitations

From repository root:

`& '.tmp/groundtruth-coverage-20261024/delivery-worktree/.venv/Scripts/python.exe' -X utf8 -B '.tmp/groundtruth-coverage-20261024/quality-v6/first-blind-independent-v519/audit.py'`

Final exit0. This calls unchanged frozen `load_views` and `compare_reports` on
the same1600 observations; result exactly equals499/comparison.json. It does not
invoke evaluator HTTP execution. A namespace package shim for `app.services`
loads the exact frozen pure submodules without executing services/__init__.py,
which eagerly instantiates unrelated services. No scorer function is replaced.
Model imports and network/child-process execution are blocked. Imported module
inventory is in `result.json`. This establishes pure portable replay of frozen
logic; it is not a fresh test of the literal original CLI packaging on a bare
interpreter.

Two earlier invocations of the same audit command exited1 before replay while
the strict sandbox blocker rejected Windows platform discovery through eager
SQLAlchemy import: first socket.gethostname, then platform's subprocess ver
fallback. The final wrapper avoids those unrelated imports. These were audit
harness portability failures, not new application/model executions or additional
quality measurements. No sealed input was changed.

`python -X utf8 -B '.tmp/groundtruth-coverage-20261024/quality-v6/first-blind-independent-v519/source_binding.py'`

Initial raw comparison exit1; follow-up exact-content/modulo-CRLF classification
exit0. Both invoke `git -C W cat-file --batch`, exit0, using only the explicitly
named source manifest paths. Results retained in git-source-binding.json and
git-source-normalized-binding.json.

Recommended next mechanism checks: independently authored small regression
counterexamples for request decomposition, unnumbered complete routines,
subject/relation binding and negative/conditional facts; role-scope discovery at
65+ authorized documents; literal-equivalence reconciliation; and generic
opposition-source provenance. Do not tune only to these exposed200 questions.
Any repaired production candidate requires a new freeze and genuinely new
independently authored/reviewed blind set. Preserve both complete499 first
reports and partial487. No acceptance, human validation, universal conflict
detection, capacity, hosted CI, or release certification is claimed. Root owns
the next development decision. QUIET.
