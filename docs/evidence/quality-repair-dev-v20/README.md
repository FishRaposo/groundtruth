# Failed source20 development observation

Observed 2026-10-25. **Development qualification failed: 0/48 correct complete
answers; 32/32 correct negatives.** This is an 80-case agent-authored development
corpus, with source families separate from earlier evaluations. Later use of these
cases is exposed development/regression work, never another unseen result.

| Observation | Result |
| --- | ---: |
| Complete answerable cases | 0/48 |
| Correct negative outcomes | 32/32 |
| False refusals on answerable cases | 44 |
| Incomplete answers | 4 |
| Authored-source recall@5 / MRR | 0.989583 / 0.989583 |
| Complete source/version coverage | 0/48 |
| Unauthorized source exposures | 0 |
| Citation / span integrity failures | 0 / 0 |
| Execution errors | 0 |
| Required opposing-source inspection identities present | 8/8 |

The run used real HTTP, SQLite/inline ingestion and cached CPU semantic embedding,
RoBERTa QA threshold4, NLI margin0, composite proposals and disclosed activity-role
scope. Seeding published56 documents and76 immutable versions. The complete run,
database and logs were closed and sealed before case failures were inspected.
Original raw observations remain unchanged in the isolated operation evidence.

These results expose request-planning and binding failures, rather than a lack
of retrieved sources: coordinated attributes and owner consultation dependencies
were lost, and complete source-declared paragraph procedures never reached NLI
assessment. The four emitted answers omitted requested facts. Subsequent repairs
require new source snapshots and new reports; this result stays failed.

Only reranked retrieval and margin0 were measured for this snapshot. This is not
a blind validation, a baseline comparison, human calibration or a general model
quality claim. HTTP timings were collected while regression tests also ran and
do not constitute a controlled performance benchmark.

## Inspect the complete evidence

- [Manifest and exact byte hashes](manifest.json)
- [Full public report, gzip](report.json.gz)
- [Frozen Python/JSON source archive](frozen-source.zip) and [source file hashes](source-manifest.json)
- [Exact compiled candidate corpus](frozen-candidate-corpus.zip)
- [Portable scorer replay and extra inspection checks](development-audit.json)
- [Runtime dependency observation](runtime-after-only.json)

The gzip report decompresses byte-for-byte to the first complete report. Its raw
SHA-256 is `e751ff9c5ab3f31d848bb3ca26566eb61dd5ee729ff29c3cd598e952b2562317`.
Archives contain the exact frozen source/input bytes. Runtime keys, databases and
private seed manifests are retained separately and are excluded from this bundle.

Model assets, source and corpus were checked before/after execution. Runtime
package metadata was captured **after execution only**; this observation does not
establish dependency stability during the run. Reproduction requires the separately
pinned model assets and appropriate runtime dependencies described in
[the active repair](../../answer-coverage-quality-repair.md).

The development gate is at least46/48 complete positives and32/32 negatives with
zero integrity/access errors, followed by a frozen configuration and a fresh,
independently authored/reviewed blind200. The final target remains114/120 and80/80.
No owner review instance was promoted from this run.
