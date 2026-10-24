# Answer coverage: continued development, not release acceptance

Status on 2026-10-24: **OPEN**. This continuation preserves the
[first failed blind comparison](answer-coverage-verification.md) and all original
golden evidence. The 200 exposed cases are not a new unseen set. No replacement
blind corpus has been authored during this development cycle.

The owner confirmed that another editor owns the original checkout. These changes
are isolated on `feat/groundtruth-answer-coverage-delivery`; version, pagination,
dependency, CI and accessibility maintenance in that checkout is preserved.
The original review database and services remain separate from disposable tests.

## Current post-integration development

The current `reader-parts-v5` development repair keeps multi-document evidence
and adds local topic-sentence binding for inline procedures, bounded continuation
markers and named time/session-window recognition. Quantity questions mentioning
a window remain non-temporal. A retained review found two such false temporal
matches; their repairs and the subsequently restored named-window positive are
recorded separately. The final bounded review passed 35 executions with inspected
source unchanged. These grammar/format checks are not general entailment.

The latest matched v7 grids used identical application/evaluator/corpus source,
with unchanged model/source fingerprints and all seven predeclared thresholds:

| Threshold | MiniLM correct /48 | MiniLM negative /32 | RoBERTa correct /48 | RoBERTa negative /32 |
| --- | ---: | ---: | ---: | ---: |
| -12 | 11 | 32 | 0 | 32 |
| -8 | 25 | 32 | 10 | 32 |
| -4 | 36 | 31 | 30 | 32 |
| 0 | 44 | 29 | 43 | 32 |
| 4 | 47 | 29 | 47 | 32 |
| 8 | 47 | 26 | 48 | 25 |
| 12 | 47 | 24 | 48 | 24 |

The unchanged zero-negative-error rule selects **RoBERTa at 4: 47/48 answers and
32/32 negatives**, with one false refusal. Threshold8 accepts seven negatives,
so its higher answer coverage is ineligible. All rows report zero execution,
evidence-integrity and unauthorized-exposure errors. These are exposed
development observations; the required fresh blind gate remains pending.
See [v7 comparison](evidence/answer-coverage-v3/matched-readers-v7.json).

The local launcher now selects this development profile, using a separate
`reader-roberta` cache. Explicit `--reader-model minilm` retains MiniLM's revision,
legacy `reader` cache and threshold-8; library/setup defaults remain unchanged.
The three dispatch-level launcher tests passed, and independent bounded review
passed19 checks; real process/browser acceptance is recorded separately when run.
The current combined API/script suite passed **533 tests, one infrastructure
skip, 68% coverage**. No review-instance promotion follows from these counts.

The actual default launcher (no model/threshold overrides, explicit existing
cache path) reproduced47/48+32/32 for **all four retrieval methods**, with
unchanged source. Its evaluator correctly exits1. The fresh V7 browser journey
now answers the original rollback but reveals another false refusal on the
uploaded fixture: “What must be paused before restoring the staging snapshot?”
The model selects “deployment queue”; the later-topic heuristic rejects the
adjacent next instruction. This remains a **pre-freeze blocker**, not a passing
connected suite. V7 evidence is retained before a separate adjacent-step repair.

### Preserved earlier checkpoints

The matched v5 measurements below belong to historical checkpoint
`d6e9ed834d1d1723952a15a7244db4ffbd5bde78`, retained in the local
`evidence/groundtruth-reader-v5-d6e9ed8` ref. Its source-binding record distinguishes
exact observed Windows bytes from canonical Git LF source. No archived results
are changed to match later code.

The isolated branch now includes the other editor's committed main maintenance
at `e73d1d8`, with the reader checkpoint replayed as `b1e8dac`. The original main
checkout and its untracked work are preserved. This integration requires fresh
verification; earlier v5 gates do not certify the integrated source.

The integrated `reader-parts-v4` checkpoint records selected source-sequence
formatting as a ranking prior among already accepted witnesses for an explicitly
procedural question. Raw offsets must belong to that sequence and named topics
must occur in its local heading. Unmarked/unknown sequences retain margin behavior.
Formatting does not establish factual applicability. Exact clock intervals are
also distinguished from counts, retaining When-question support.

Two independently reproduced API failures (canonical numbering and unrelated
sequence preference) and a residual canonical-bullet failure were repaired. The
final independent bounded recheck passed 29 executions with four source hashes
unchanged. An earlier long Windows scratch path failed before upload/answer
assertions; the same selection passed with a shorter scratch path. Both logs remain.

The fresh matched v6 comparison used identical application/evaluator/corpus source
for both readers; each full seven-threshold grid retained unchanged model/source
fingerprints. These are the same **exposed development cases**, not unseen data:

| Threshold | MiniLM correct /48 | MiniLM negative /32 | RoBERTa correct /48 | RoBERTa negative /32 |
| --- | ---: | ---: | ---: | ---: |
| -12 | 11 | 32 | 0 | 32 |
| -8 | 24 | 32 | 10 | 32 |
| -4 | 34 | 31 | 28 | 32 |
| 0 | 42 | 29 | 39 | 32 |
| 4 | 45 | 29 | 43 | 32 |
| 8 | 45 | 26 | 45 | 25 |
| 12 | 45 | 24 | 45 | 24 |

The predeclared zero-negative-error rule selects RoBERTa at 4 for this comparison:
**43/48 answers and 32/32 negatives**. It remains inadequate for a blind candidate
freeze. At this setting there are three wrong/incomplete procedural answers and
two false refusals. All grid rows record zero execution, citation/span-integrity
and unauthorized-exposure errors; those structural results are not answer quality.
See [comparison and rule](evidence/answer-coverage-v3/matched-readers-v6.json).

Fresh engineering checks passed 502 backend tests, with one infrastructure skip
and 68% coverage; Ruff/format, Pyright, 72 frontend units, lint/types, production
build, source/wheel closure and fresh outside-checkout base API installation.
The offline production run passed three zero-network full journeys at all three
viewports, plus ten actual axe scans. Eight additional axe test cases return
before scanning by existing viewport selection; **21 reported passes do not mean
18 scans**. Three representative screenshots were visually inspected and archived.
Current connected-reader browser verification remains pending. Subsequently,
both models passed real cached inference and upload/query/history/source checks
in a fresh outside-checkout installed-wheel environment, with dependency
consistency confirmed. These thin functional checks are not corpus-quality
acceptance; see the [supplement](evidence/answer-coverage-v3/v6-installed-reader-checks.json).
Details and exact logs are in the
[V6 engineering record](evidence/answer-coverage-v3/v6-engineering-checks.json).

The initial full-suite attempts intercepted an obsolete Celery `.delay` seam and
blocked on real Redis retries. A diagnostic stack identifies configured
`send_task`; correcting only the test mock produced a focused pass and the final
full pass above. Both interrupted logs remain and are not passing results.

Further development has recorded failing fixtures for a sequence following its
immediate topic sentence, ordinary Begin/After/Finish wording, and a valid
session-window interval. Their repairs and new measurements follow this preserved
checkpoint; they do not rewrite v6 observations. The original 200-case failure
and all earlier development evidence remain immutable. No new blind set or review
promotion has occurred.

## Engineering changes under measurement

The optional reader now prepares bounded explicit compound questions and noun
lists. Named topic qualifiers remain attached to their applicable parts, including
pronoun continuations and postposed list qualifiers. Separate requested entities
can use separate documents. There is no primary-document restriction.

Each recognized part needs a non-null reader selection. Citation selection finds
a cover within the existing three-citation cap after inspecting curated conflicts.
An incomplete cover refuses instead of silently displaying a successful subset.
Prepared questions, coverage, missing parts, scores and decisions are recorded
under `reader-parts-v3` in the v5 checkpoint (the earlier grids used
`reader-parts-v2`). Raw candidate text is removed recursively from saved
diagnostics; approved answer spans retain exact immutable source offsets.

These are bounded preparation and mismatch checks, **not general entailment**.
Unrecognized grammar remains the original question. A recognized-part coverage
ledger does not prove every factual obligation in arbitrary prose was understood.
The quality gate remains separate from span integrity and runtime readiness.

Independent review reproduced and rechecked loss of subject qualifiers, future
entities contaminating earlier pronouns, wrong currency/temporal restrictions and
paragraph-anaphora handling. A later actual-tokenizer probe demonstrated that an
extra unmanifested `tokenizer.json` could override verified files. Runtime now
rejects unverified extra root files before loading a tokenizer or model. The
original failing probes are preserved; both official cache layouts remain valid.

A later independent diagnosis reproduced wrong-attribute spans, clock times used
as elapsed durations, spatial objects used as responsible people, and a sibling
topic's earlier fact used for a question about a later topic. The current contract
adds bounded rejection checks for those forms. Shared phrases only reject a
demonstrably later topic; they never certify support. These checks neither crop
model input nor retry alternative spans until one evades a checker. Four recorded
failing regressions now pass alongside their valid controls. Independent review
and fresh same-source model measurements remain necessary.

## Fresh development material

A clean-context source author produced **80 development cases**: 48 answerable,
16 unanswerable, eight conflicting/stale and eight adversarial. The positives
include 16 simple questions (eight ordered procedures), 16 single-document
multiple-fact requests and 16 genuinely requiring two documents. There are 24
fresh source families, 44 documents and 52 snapshots.

An independent source-only reviewer checked all labels with 2,061 checks. Neither
author nor label reviewer saw application code, models, settings or earlier
case-level results. Labels are synthetic and agent-authored, without human
validation. The raw author manifest is
`672e8a19e79a8667ce49d684983faeb11f7e2354619201d1a8355e9887050712`.

The parent added only operational profile fields: top_k=5, four retrieval methods
and the legacy refusal setting 0.35. Case/source bytes are unchanged. The derived
[packaged manifest](../apps/api/app/portfolio/assets/coverage-development-v3/manifest.json)
is `62071bb0298c0bf7322b26db9d74bd7e163bcb1d15a57caf95341cf5e0854e22`.
Documents and versions were seeded through real authenticated HTTP into disposable
SQLite. Evaluation reads actual responses and stored source identities.

## Preserved intermediate failures

The initial compound-reader experiment at threshold 0 scored **24/48 answers and
27/32 negatives**. A subsequent fixed-source MiniLM grid produced:

| Null threshold | Correct answers /48 | Correct negatives /32 |
| ---: | ---: | ---: |
| -12 | 11 | 31 |
| -8 | 18 | 29 |
| -4 | 21 | 28 |
| 0 | 27 | 27 |
| 4 | 30 | 27 |
| 8 | 31 | 24 |
| 12 | 31 | 21 |

No setting satisfied zero negative failures; none was selected. Source fingerprints
matched before and after that grid. Later boundary repairs make those observations
historical rather than evidence for the current source.

The first RoBERTa experiment completed threshold -12 with 0/48 answers and 32/32
negatives. The remaining grid was explicitly interrupted for the tokenizer-pinning
repair. At interruption, source and model hashes matched their before snapshots,
and the actual cache had no extra tokenizer. This is one completed development
observation, not a complete grid or deployment selection.

The complete, subsequent RoBERTa grid with the tokenizer-pinning repair produced:

| Null threshold | Correct answers /48 | Correct negatives /32 |
| ---: | ---: | ---: |
| -12 | 0 | 32 |
| -8 | 9 | 32 |
| -4 | 27 | 31 |
| 0 | 35 | 29 |
| 4 | 35 | 26 |
| 8 | 32 | 22 |
| 12 | 32 | 22 |

Source and model hashes matched before and after. Under the predeclared
zero-negative rule, -8 yields only 9/48 correct answers. This does not meet the
goal and is not a release configuration. The earlier MiniLM grid used different
source; these tables cannot isolate the model's contribution. Both predate the
current support-binding repair.

The next fixed-source RoBERTa grid added the bounded support checks:

| Null threshold | Correct answers /48 | Correct negatives /32 |
| ---: | ---: | ---: |
| -12 | 0 | 32 |
| -8 | 8 | 32 |
| -4 | 25 | 32 |
| 0 | 36 | 32 |
| 4 | 36 | 31 |
| 8 | 32 | 25 |
| 12 | 32 | 24 |

Source and model fingerprints matched throughout. Threshold 0 is the eligible
development choice under the zero-negative rule, but 36/48 is inadequate. It is
not a release selection. Later diagnosis found compact citation choice could
discard stronger accepted complementary sources. The next repair preserves the
strongest per-part witnesses before minimizing citation count, retains legacy
unknown-score behavior, and refuses covers exceeding three sources. Raw margins
rank already accepted witnesses; they do not prove truth.

The full suite also exposed a streaming SQLite lock during cancellation. An
independent read-cursor diagnosis and new read/yield/send-failure regressions are
separate from quality measurement. New cleanup drains in-flight database reads
before rethrowing cancellation and owns stream finalization before the request
session closes. It does not shield model inference. All current-source gates and
model measurements must be rerun after these repairs.

The subsequent matched-source comparison includes the citation and cancellation
repairs. Both grids used identical application, evaluator and corpus fingerprints;
each model's asset hashes matched before and after:

| Threshold | MiniLM answers /48 | MiniLM negatives /32 | RoBERTa answers /48 | RoBERTa negatives /32 |
| ---: | ---: | ---: | ---: | ---: |
| -12 | 11 | 32 | 0 | 32 |
| -8 | 24 | 31 | 10 | 32 |
| -4 | 34 | 30 | 29 | 32 |
| 0 | 42 | 29 | 40 | 32 |
| 4 | 45 | 29 | 44 | 31 |
| 8 | 45 | 26 | 45 | 25 |
| 12 | 45 | 24 | 45 | 24 |

The rule saved before execution chooses RoBERTa at 0 with **40/48 answers and
32/32 negatives**. This is an eligible development configuration, not an adequate
release. A more permissive setting cannot win by accepting unsupported answers.
Three procedural questions selected a schedule/return-instruction paragraph over
the actual ordered procedure. One count question accepted a clock interval.
Those failures and the remaining refusals are retained for the next bounded
repair; no later repair may be credited to these measurements.

All 37 reports and 2,960 rows in the preserved intermediate archives were re-scored
against the authoritative packaged corpus: recorded scores and summaries match.
That is observation integrity, not a passing quality result. See
[archived evidence](evidence/answer-coverage-v3/README.md).

## Approved larger-reader comparison

The owner explicitly approved a larger CPU extractive-reader comparison after the
MiniLM failures. Both models remain available; legacy defaults remain MiniLM.

| Model | Immutable revision | License |
| --- | --- | --- |
| `deepset/minilm-uncased-squad2` | `934656cdda79824eabf503ed56e15c01ddbdbe3f` | CC-BY-4.0 |
| `deepset/roberta-base-squad2` | `adc3b06f79f797d1c575d5479d6f5efe54a9e3b4` | CC-BY-4.0 |

The [pinned RoBERTa model card](https://huggingface.co/deepset/roberta-base-squad2/blob/adc3b06f79f797d1c575d5479d6f5efe54a9e3b4/README.md)
identifies extractive SQuAD2 question answering. Its benchmark is not GroundTruth
validation. Its 496,254,442-byte safetensors file was checked against the upstream
object and has SHA-256
`ac5db66fdcfecb400345d09787b71009d60805ef9883451071669cf951b5e2c7`.
Weights remain outside Git, distributions and the recruiter preview.

Explicit setup, from an installed reader environment with `PYTHONPATH=apps/api`:

```powershell
$readerCache = Join-Path $env:LOCALAPPDATA 'GroundTruth/models/roberta-base-squad2--adc3b06f79f797d1c575d5479d6f5efe54a9e3b4'
python -m app.reader_setup --model roberta --directory $readerCache
$env:ANSWER_SELECTION_MODE = 'reader'
$env:READER_MODEL_PATH = $readerCache
$env:READER_MODEL_REVISION = 'adc3b06f79f797d1c575d5479d6f5efe54a9e3b4'
```

Set the path and revision together. No runtime request downloads assets. Unknown
revisions, mismatched manifests, damaged files or unverified extra model/tokenizer
files produce errors, not another model or successful lexical fallback. Runtime
uses CPU safetensors with remote code disabled. Existing `download(directory)` and
setup commands still select MiniLM unless another model is explicitly chosen.

The matched v5 grids are complete; their [raw comparison](evidence/answer-coverage-v3/matched-readers-v5.json)
remains failed for release purposes. Further repairs need new source-bound
measurements. The predeclared thresholds
remain -12,-8,-4,0,4,8,12; model input/stride/nbest/span settings remain
384/128/20/96. Current measurements are development only. The current launcher
profile follows the later v7 comparison above; no fresh unseen acceptance is
claimed here.

## Reviewed v5 engineering checkpoint

Before integrating the other editor's newer committed maintenance, the isolated
source passed 504 Python/API/script tests with one infrastructure skip and 68%
coverage; Ruff/217-file formatting and Pyright passed. Frontend 72 units, lint and
TypeScript passed. Source/wheel builds, wheel module/corpus closure and a fresh
outside-checkout base-wheel upload/query/history execution passed. These are
engineering checks, separate from the failed quality comparison. Browser checks
remain pending for this source. Fresh installed CPU-reader probes passed for both
models at threshold 0: actual upload, answer, exact spans, saved history and source
inspection, with all four packaged corpus sets available (100/80/200/80 cases).
These thin functional probes are not additional quality validation.

Independent review reproduced the active SQLite cursor lock and finalizer
cancellation defects before repairs. Final bounded recheck passed 30 test
executions, with inspected source hashes unchanged. Witness-cover review passed
27 executions, including discarded-candidate revocation checks. Counts include
named scopes and duplicate control executions, not a claim of unique independent
quality cases. See the [review records](evidence/answer-coverage-v3/README.md).

To reproduce a development evaluation, use a separate migrated/seeded SQLite
profile from the [actual workflow](portfolio-connected.md), the packaged
`apps/api/app/portfolio/assets/coverage-development-v3` corpus, and the explicit
reader cache/revision above. Run the server loopback-bound on an unused dedicated
port; do not point at the review database. `seed_portfolio.py` requires
`--confirm-disposable-database` and writes a private key manifest. Keep that file
outside Git. For the recorded comparison, the disposable API used
`RATE_LIMIT_ENABLED=false`, `EMBEDDING_MODE=local`, `GENERATION_MODE=extractive`,
`INGESTION_MODE=inline`, `AUTH_ENABLED=true` and offline cached model loading.

With that actual API on 8410 and its private seed manifest:

```powershell
python scripts/evaluate_portfolio_retrieval.py --seed-manifest .tmp/reader-comparison/seed-manifest.json --corpus-dir apps/api/app/portfolio/assets/coverage-development-v3 --output .tmp/reader-comparison/roberta-threshold-0.json --method reranked --execution-arm candidate --require-answer-spans --expected-reader-null-threshold 0 --expected-reader-model-revision adc3b06f79f797d1c575d5479d6f5efe54a9e3b4
```

The manifest supplies the actual API URL. Repeat with a restarted, explicitly
configured server for each of -12/-8/-4/0/4/8/12 and each model; use new output
paths. Freeze source/corpus/model hashes before the first request and check them
afterwards. A complete report may exit 1 because quality fails. Exit 0 from an
archive-integrity check does not change that result. The comparison contains no
latency or capacity claim.

## Remaining acceptance

Choose settings from development only, freeze source/scorer/model/settings, then
independently author and verify another 200-case blind set. Preserve both first
complete baseline/candidate reports before failure inspection. The required gate
remains at least 114/120 correct default-path answers, improvement over baseline,
all 80 negative contracts, and zero evidence/access violations.

Full current-source API/frontend/packaging/browser and installed-wheel gates must
be recorded after the final repair. Passing focused tests does not close that
acceptance. No WSL, Docker, generative model, paid provider, hosted CI observation,
public hosting, publication or human quality claim is included.
