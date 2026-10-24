# Fresh validation of the reviewed local reader

**FAILED. GroundTruth answer-coverage acceptance remains OPEN.** The first
complete reports were [sealed together](first-comparison-seal.json) before
inspection. The frozen [gate](comparison-gate.json) exits1:

| Method | Baseline answers /120 | Baseline negatives /80 | Candidate answers /120 | Candidate negatives /80 |
| --- | --- | --- | --- | --- |
| Keyword |39|75|70|62|
| Vector |39|75|69|62|
| Hybrid |39|75|69|62|
| Hybrid + heuristic reranking (default) |39|75|69|62|

The default candidate improves answer coverage from32.5% to57.5% on this set,
but correct negative outcomes regress from93.75% to77.5%. Required: at least95%
and100% respectively. There are44 false refusals, seven wrong/incomplete positive
answers and18 answered negatives:13 unsupported questions and five stale/current
attribute questions. All20 adversarial cases pass their authored contracts.
These are synthetic authored expectations, not human-validated quality scores.

Default recall@5 is0.9916667 and MRR0.9555556. Most required sources were
retrieved; this does not imply that extracted passages answer every requested
fact. Execution errors, unauthorized source exposure, citation-byte and span
integrity failures are zero in the recorded comparison. Valid source bytes can
still accompany an unsupported or incomplete answer, as this trial demonstrates.

The [baseline](first-baseline-blind-v5.json),
[candidate](first-candidate-blind-v5.json),
[gate command](comparison-command.json) and
[durable-record check](durable-comparison-records.json) preserve all observations.
Each database retains105 documents,125 exact immutable snapshots and800 saved
case answers/refusal decisions/provenance matching its report, plus one explicit
seeded legacy-history row. Both dedicated APIs were stopped after sealing.
The owner review instance and original database were not promoted or changed.

All200 cases are now exposed. Later diagnostics or repairs must not replace this
result or reuse this set as unseen. Another quality claim needs a new candidate
freeze and a different independently authored corpus.

The [independent final audit](independent-final-audit.zip) re-scores all1,600
rows and confirms the failed gate, frozen source/assets/runtime and preservation
of original failed evidence. Its bounded source-backed sample finds no label or
scorer defect overturning the result. It reproduces a concrete parser defect:
sentence-head “Limit the answer…” becomes an entity constraint in five filtered
questions. It also documents missing second-document facts, irrelevant current
passages and overly broad relevance of adjacent exception conflict groups.
The audit did not independently repeat the parent's later SQLite durability check.

The [runtime archive](connected-comparison-runtime.zip) preserves migration,
actual API ingestion, both rejected preflight invocations, the administrative
correction, successful comparison controller and dedicated process cleanup.
The [operational corpus archive](frozen-operational-inputs.zip) contains the exact
four input files for reproduction. Extract it into a separate corpus directory;
pass that path to the existing `--corpus-dir` seed/evaluation CLIs. Regenerate
private seed manifests locally; they are deliberately absent from public evidence.
Archived Windows runner paths/configuration describe this host and need explicit
adaptation on another host. Model setup remains an explicit separate command.

At freeze, **quality acceptance is pending**. This record is separate from the
[failed first comparison](../answer-coverage-v4/README.md) and from
[exposed development](../answer-coverage-v7/README.md). Neither earlier failure
nor later exposed scores is replaced.

Candidate `bf7d28361f7f9445fe28d13c5d6ac3bd256c12ec` was frozen at
2026-10-24T13:08:19.922356Z before clean independent authoring. The
[freeze](candidate-freeze.json) binds286 application/test/tool/configuration
files, pinned model assets, scorer, runtime, fixed settings and development
evidence. RoBERTa threshold4, multiple-document extraction and all authorization
and source-version checks are retained. The embedded engineering snapshot was
created before its later packaging supplement; the separately bound supplement
records completed fresh base/optional-reader installations, both reader probes
and lint checks. No pending historical field implies that those later checks
were unavailable at freeze.

The clean author received only the product/schema contract and excluded semantic
families. The [contract archive](author-contract-and-freeze-runner.zip) and
[dispatch record](author-dispatch.json) document that boundary. Dispatch time is
a record written after the tool call, not a precise tool-start timestamp.
The [raw author archive](blind-author-inputs-v1.zip) freezes200 cases,20 fresh
families and105 logical documents. Its initial composition claims were rejected
by [independent preflight review](preflight-label-review-v1-failed.zip): five
procedure labels omitted necessary parameter values, and three questions did
not need every required source. The reviewer counted37 genuine multi-document
positives and15 complete procedure labels. No application/model case was run.
The original inputs/review remain immutable; corrections require a separate
version and another independent review before execution. Supplying the frozen
operational profile never permits silent source/question/label edits.

The [corrected author version](blind-author-inputs-v2.zip) changes eight labels,
with all200 question bodies and source-document bytes unchanged. The
[independent recheck](blind-independent-review.zip) passes6,612 checks, confirming
37 necessary multi-document positives,20 complete procedures and all80 negative
labels. The [corpus freeze](blind-corpus-freeze.json) binds the corrected raw
author input and the operational profile; the [selection binding](validation-binding.json)
ties it to the earlier candidate/configuration freeze. The original preflight
failure occurred before any model/application case execution.

A separate [binding preflight failure](preflight-binding-reference-failure.zip)
rejected both CLIs before case requests: the development summary was referenced
where the unchanged validator requires the full report. The
[reference correction](binding-reference-correction.json) points to the exact
full report already preserved in the pre-freeze archive. Candidate freeze,
source, scorer, settings, model hashes and all input labels remain unchanged.
Each seeded database held only its deliberately inserted legacy-history row,
not an evaluated case; the retry reuses the unchanged ingested snapshots.
Original preflight logs and binding are preserved. Only the first complete
reports count as this comparison's first results.

The [independent preflight audit](independent-preflight-audit.zip) verifies286
candidate paths,127 baseline files,21 pinned assets/manifests, runtime versions,
input/label chronology and the administrative correction. It inspected no
ongoing report outcomes or case answers. Its metadata verdict is separate from
the final quality gate and scoring audit.

Baseline `e19006c` and the candidate use separate disposable SQLite databases,
actual API ingestion/version publication, cached semantic embeddings and local
credential-free execution. Baseline retains lexical answer selection; candidate
uses the frozen CPU reader. Loopback APIs8401/8402 are independent of the owner's
8400/3505 review instance. Request limiting is disabled equally for this quality
comparison; these observations are not latency or capacity benchmarks.

Only after independent source/label review and frozen input binding may any
case execute. Both first complete all-method reports must be sealed before
failure inspection. Required default gate: at least114/120 correct answers,
improvement over baseline,80/80 correct negative outcomes and zero evidence/access
errors. If it fails, preserve the entire result and keep the milestone open.
No replacement or selectively rerun result may be called unseen.

All labels are synthetic and agent-authored, independently checked by another
agent, without human validation or general model-quality certification. No WSL,
Docker, paid provider, local generative model, publication or sibling integration
is used. PostgreSQL/Redis and indexed-scale local verification remain deferred.
