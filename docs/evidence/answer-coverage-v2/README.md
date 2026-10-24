# Answer-coverage repair evidence, version 2

This directory is separate from `../portfolio`, whose failed reports and golden
evidence retain their original bytes. The repair starts at
`e19006c9e8f1a11ef4930e24ed88128e765b6bf5`. No WSL, provider or generated-answer trial
is included. Labels are synthetic and agent-authored, without human validation.

## Development selection

All 80 development cases were run through the actual authenticated HTTP API,
SQLite, inline-ingested immutable source snapshots, cached semantic embeddings
and pinned CPU reader. Seven thresholds were declared before measurement.
`development-source-before.json` and `development-source-after.json` agree.

| Null threshold | Correct answers /48 | Correct negatives /32 |
| --- | ---: | ---: |
| -12 | 21 | 32 |
| -8 | 37 | 32 |
| -4 | 44 | 31 |
| 0 | 44 | 29 |
| 4 | 45 | 25 |
| 8 | 45 | 17 |
| 12 | 44 | 18 |

The predeclared rule selects -8: maximize correct answers with zero negative
failures, then choose the more refusal-prone threshold on ties.
`development-selection.json` records this decision and the measured report hash.
The seven `development-threshold-*.json` files retain exact answers, immutable
citations, span offsets, traces and authored-case scores. No execution errors,
unauthorized exposure or citation/span integrity failure occurred in this grid.
It does not establish blind acceptance.

`reader-assets.json` records the configured model/revision and runtime file hashes.
Weights are not distributed here. `reader-error-observation.json` records an
actual HTTP503 and durable error caused by a deliberately missing configured
reader directory; this is fault injection, not an unsupported-question refusal.
`preserved-original-hashes.json` lists the original files that must remain intact.

Earlier development experiments remain in the operation workspace's ignored
`.tmp/groundtruth-coverage-20261024` ledger. Source/scorer repairs during those
experiments make them unsuitable as frozen selection evidence; they are retained,
not relabeled as unseen validation.

## Validation boundary

The 200-case blind author may start only after a recorded candidate freeze.
The first complete baseline/candidate results must be sealed before case-level
failures are inspected. The default reranked acceptance gate is at least 114/120
correct answers, strict improvement over baseline, all 80 negatives correct and
no access/citation/span integrity failures. A failed gate stays failed.

Known limits remain: the QA model can associate a nearby fact with the wrong
attribute, ambiguous phrasing can produce a null answer, and a false-positive
reader span in an unrelated curated group can cause conservative refusal.
The surface absence check is not semantic entailment. Multiple supported
documents remain available under the existing three-citation presentation cap.
See the [protocol](../../answer-coverage-baseline.md) and
[actual workflow](../../portfolio-connected.md).

## First blind result — FAILED

Both complete reports were sealed before case-level failure inspection:
[baseline](first-baseline-canonical-v3.json),
[reader](first-candidate-canonical-v3.json),
[seal](first-comparison-seal.json),
[concurrent-editor qualification](concurrent-edit-qualification.json).
The on-disk source-after assertion failed because another editor changed
version/pagination files while the non-reloading test processes ran. Their
read-only version/pagination probes retained frozen behavior; QA/retrieval/scorer
files were unchanged. This qualification is retained, not described as a clean
passing source-integrity gate.

| Method | Baseline answers /120 | Reader answers /120 | Baseline negatives /80 | Reader negatives /80 |
| --- | ---: | ---: | ---: | ---: |
| Keyword | 30 | 52 | 68 | 77 |
| Vector | 30 | 55 | 68 | 77 |
| Hybrid | 30 | 55 | 68 | 77 |
| Reranked (default) | 30 | 55 | 68 | 77 |

The portable verifier independently re-scores all 800 rows per arm against the
packaged canonical corpus and exits **1, failed**. Default answer coverage remains
55/120 rather than the required114/120, with three missed negative contracts.
Recorded execution errors, unauthorized source exposures and citation/span
integrity failures are zero. Structural integrity does not establish relevance.
An independent literal-assembly audit also checked every emitted answer; the
bounded scorer is not a general entailment detector. See the full
[verification and limits](../../answer-coverage-verification.md).

The [blind input protocol](blind-input-protocol.md) explains the preserved schema
and whitespace preflight failures, source review and clean-context boundary.
No evaluation case was run until canonical v3 was frozen and bound. All cases
are now exposed and cannot become a fresh unseen test through rerunning.

The [browser record](browser-observations.md) retains the full final connected
suite's rollback failure at all three widths. The separate diagnostic and offline
sample passes do not erase it. [Screenshots](screenshots/README.md) show the
actual failure, reader source spans, fault-injected error and sample labels.
