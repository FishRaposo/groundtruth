# GroundTruth: repairing the path between a question and its evidence

GroundTruth is a local knowledge application for operational runbooks. Its
portfolio value is the inspectable boundary between retrieval, authorization,
source versions and an answer/refusal, with a working connected application and
an independent visual sample. No customer, production adoption, human validation
or business-savings claim is made.

## Answer-coverage continuation

The later answer-coverage repair is tracked separately in the
[frozen protocol and evidence](answer-coverage-baseline.md). It adds a pinned CPU
extractive reader and exact highlighted source spans while preserving
multi-document answers. The first reader development grid selected threshold -8, with
37/48 correct answers and 32/32 correct negative cases across all four retrieval
methods. This development result is not blind acceptance or a 95% claim. The
first failed evidence below remains unchanged; adding a model does not erase it.

The first frozen 200-case reader comparison also **fails acceptance**. Default reader
coverage improved from 30/120 to 55/120 answers, with 77/80 correct negative cases
versus 68/80 baseline. It misses the 114/120 and 80/80 requirements. Keyword answers
52/120; the other three methods answer 55/120. Both first reports are preserved,
with a concurrent-editor source-integrity qualification. The final original
rollback browser journey also fails. The
[new verification](answer-coverage-verification.md) separates those failures from
working reader/source-highlight diagnostics and a later reviewed privacy repair.
The [continued development record](answer-coverage-development-v3.md) preserves
the approved larger-reader comparison and its separate source-bound results.
It does not relabel the earlier failed200 cases as unseen.

## The original failure

At `a8dc3570e3e66320b716d31a4791e957f14d7cfa`, the actual retrieval path did not
consistently carry its injected database session and filters. Singleton counters
could describe another request. Query/conversation rows lacked durable ownership;
old restoration did not regenerate embeddings; conversation text could displace
numbered evidence. The frontend replaced connected failures with sample success.
The untouched API baseline passed291 tests with62% statement coverage: passing
existing tests did not establish the missing application contract.

Recorded regressions, focused repairs and real HTTP checks now cover those
boundaries. SQL predicates use trusted key/workspace identity before candidate
limits. Normal and SSE requests share one request-local pipeline. Durable
citations retain exact passage, version and hash; current rights are rechecked on
historical reads. Updates publish atomically after successful embedding, keeping
the old version usable on failure. Restores create a new revision with compatible
vectors; reindexing preserves content identity.

Independent review also reproduced an administrative key workspace escape and a
startup routine that interrupted healthy jobs. Key operations now inherit and
respect trusted scope; durable worker claims use expiring renewable leases and
fenced publication. A later review found stale failure/retry ordering, documented
in the verification record. Real production-shaped denial probes caught detached
ORM logging that turned404 into500; logging now uses safe primitive snapshots.

## Real application and explicit preview

The connected application uses real SQLite, canonical inline parsing/ingestion,
the pinned CPU MiniLM model and source-extractive generation. Browser users can
upload documents, inspect jobs, ask scoped questions, open saved sources, update/
compare/restore versions, review documents and inspect durable audit/usage data.
Network/model failures remain errors. Hash-vector operation is a separately
selected deterministic mode. The shared visual components make both experiences
understandable without presenting sample interactions as live execution.

The recruiter tour follows a staging rollback citation into version history,
refusal, curated conflicting procedures and quarantined-file recovery. It is
labeled **Interactive sample data**, resets as one scenario and makes no backend,
provider or external-font requests. Keyboard/focus and three responsive layouts
are verified separately from the actual HTTP workflow.

## What the first frozen evaluation actually showed

Twelve project-owned synthetic runbooks and100 agent-authored cases were frozen
before measurement. The development split is12/4/2/2 and held-out48/16/8/8 across
answerable/unanswerable/conflicting-stale/adversarial categories. Related source
families stay within one split. These are correlated authored fixtures, not100
independent real-world tasks or human-calibrated labels.

The first development run found that topic overlap plus an RRF rank of1 could
accept questions about missing facts. After a **development-only** conservative
support repair, all20 development contracts passed for all four methods. Settings
were frozen at top-k5, refusal threshold0.35 and literal coverage0.75 before the
first held-out call. The manifest, source fingerprints, report hashes and freeze
timestamp are retained in the [first observation](evidence/portfolio/README.md).

| Method | Held-out pass | Recall@5 | MRR | False refusals | Missed refusals |
| --- | --- | --- | --- | --- | --- |
| Keyword | 37/80 | 1.000 | 0.9375 | 42 | 1 |
| Vector | 37/80 | 1.000 | 0.9861 | 42 | 1 |
| Hybrid RRF | 37/80 | 1.000 | 0.9653 | 42 | 1 |
| Hybrid + heuristic reranking | 37/80 | 1.000 | 0.9757 | 42 | 1 |

All four methods observed zero unauthorized-source exposure and zero execution
errors in this320-request held-out comparison. The reported source/version
correctness is0.125 against all48 expected answerable cases; refusing an answer
does not earn citation correctness. Retrieval success did **not** establish
answer coverage:42 of48 answerable questions were refused. The first evaluation
command exited1. This failed quality result is retained, not relabeled a passing
gate because the dashboard worked.

An independently prepared live walkthrough subsequently exposed “roll back” versus
“rollback” normalization. That generic regression was repaired and versioned as
`extractive-coverage-v1.1`. Later checks are exposed regression evidence, not new
unseen held-out validation. The original held-out report remains unchanged.
Literal coverage is deliberately conservative and is not semantic entailment;
broader paraphrase support remains a documented quality limitation requiring a
new development cycle and genuinely unseen validation before quality claims.

## Engineering evidence and practical limits

Real HTTP verification exercised twenty overlapping requests, isolated traces,
normal/SSE parity, PDF ingestion, updates/restoration, source inspection and
ordinary-user denials. Restart checks read the same saved source snapshot and
restored versions. Independent review probes use their own SQLite fixtures;
connected browser acceptance uses actual FastAPI/Next processes and no successful
API mocks. See [verification](portfolio-verification.md) for fresh gate counts,
screenshots, packaging and dependency findings.

The owner explicitly continued without WSL. PostgreSQL/pgvector and Redis-worker
support, migration/index code and ordinary CI contracts are included, but their
live service acceptance and the1k/10k/100k indexed benchmark remain outstanding.
Portable timings must not be extrapolated to indexed or production capacity.
Model/provider quality, hosted CI execution, public hosting and hosted multi-user
authentication remain unverified. In that original milestone the CPU model was
used for embeddings only. The subsequent optional CPU extractive reader selects
source spans; neither path produces local generative-model output. See the
[reader verification](answer-coverage-verification.md) for the separate frozen
candidate, new measurements and remaining acceptance failures.

This project supports an AI-app audit/fix sprint story: reproduce a defect in the
real path, define its authority boundary, preserve the failing evidence, repair
the mechanism and disclose what the measurements still do not support.

The [reviewed coverage checkpoint](evidence/answer-coverage-v7/README.md) reaches
116/120 answers and80/80 refusals on the exposed development cases after retaining
the failed blind comparison. Request intent, topic boundaries and selected-clause
ranking were repaired with failing regressions and independent review. Those
numbers are development evidence only; a newly frozen unseen comparison must
satisfy the acceptance gate before the review instance is promoted.
