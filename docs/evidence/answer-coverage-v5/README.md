# Post-failure development: coverage acceptance remains open

2026-10-24. This is **exposed development**, not another unseen trial. The
[first blind-v4 reports and failed gate](../answer-coverage-v4/README.md) remain
unchanged in commit `57e4128`. Earlier failed evaluations and golden evidence
also remain intact. No review application was promoted.

The revised implementation uses the same pinned RoBERTa CPU reader and threshold
4, cached semantic embeddings, SQLite and inline ingestion. Its selection
contract is `reader-parts-v7`. No additional model download, provider, generation
model, WSL, Docker or publication was used for this development step.

Repairs retain multiple documents and canonical source offsets. They separate
explicit requested noun lists and second questions, stop treating grammatical
prefaces or capitalized command words as document names, reject time/count
evidence for explicit payment requests, distinguish an until-deadline occurrence
from an identical actual duration, and honor narrowly explicit procedural scope
exclusions. Curated conflict checks still run before choosing the citation cover.
These are bounded preparation/rejection rules, not factual entailment.

| Observation | Answers | Correct negatives | Qualification |
| --- | ---: | ---: | --- |
| Original fresh blind-v4 candidate | 51/120 | 75/80 | Failed, sealed before failure inspection |
| Later exposed development, default reranked | 83/120 | 80/80 | Same now-exposed cases; not an acceptance result |
| Earlier 80 development cases, all four methods | 46/48 | 32/32 | One additional false refusal versus the preceding 47/48 checkpoint |

The exposed 200-case run retains 29 false refusals and eight incomplete/wrong
positive answers. Its recall@5 is 0.995833. All 520 observations in this step
have zero recorded execution errors, unauthorized-source exposure and
citation/span-integrity failures. Exact quotations still do not establish the
requested fact or completeness.

The 80-case regression has a demonstrated cause: a declarative opening sentence
was incorrectly prepared as a separate required question. Remaining 200-case
failures include compound intent confused with an entity named "sequence",
weak procedural selection, incomplete attributes and unrelated exception-group
refusals. Those are pending repairs, not passing acceptance criteria.

## Reproducible records

- [Checkpoint and source hashes](v9-checkpoint.json) binds 155 files before and
  after real HTTP execution. Source and original database digests stayed equal.
- [HTTP observations and runner](v9-exposed-development-observations.zip): both
  complete reports, integrity re-scoring, readiness, API logs, exact measured
  source/tests and orchestration. Every archive payload has a SHA256 manifest.
  The original authored `split` labels remain for source/case identity; the
  explicit `evaluation_visibility` is **EXPOSED DEVELOPMENT ONLY** and there is
  no frozen selection hash. The 200-case report has only reranked retrieval.
  It cannot satisfy the blind-comparison verifier.
- [Independent review](v9-independent-review.zip): seven material counterexamples
  retained and repaired, 17 final pure-module assertions passing with unchanged
  source hashes. This supplies no model or unseen-quality verdict.
- [Independent checkpoint audit](v9-checkpoint-independent-audit.zip): all 520
  rows re-scored, 90 preceding archive payloads and 155 staged/source bindings
  checked; failed blind-v4 bytes unchanged. No material discrepancy found.
- [Engineering observations](v9-engineering-observations.zip): red/green logs,
  corrected-fixture and sandbox failures, full API/script checks and coverage.

The runner makes disposable read-only SQLite backups of already API-ingested
datasets, then starts its own loopback API on 8410. Its requests use the real
reader/retrieval pipeline, and the original scorer rebuilds results from saved
responses. It disables the request limiter for this comparative workload,
clears provider credentials, and loads model assets locally. HTTP timings are
not benchmarks. Private seed manifests and databases are excluded from archives.

The API suite passed 552 tests with one infrastructure skip; a separate script
suite passed 20 tests. Combined coverage is 4,919/7,184 statements (68.4716%,
displayed 68%). Ruff and five-file formatting passed. Final configured Pyright
reported zero errors; failed sandbox dependency discovery is preserved as an
environmental observation. Current frontend/package/browser gates have not been
repeated for this checkpoint. Their earlier observations retain their original
scope and are not new quality evidence.

Next: repair the demonstrated regressions, measure stable source on development
data, then freeze a new candidate before another clean-context unseen set is
authored. The required gate remains at least 114/120 correct default-path
answers, improvement over baseline, all 80 negative contracts and no evidence or
access violation. No human validation or general model-quality claim is made.
