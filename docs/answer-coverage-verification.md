# GroundTruth answer-coverage verification

Observed locally on Windows, 2026-10-24. This continuation uses SQLite, inline
ingestion and cached CPU models, without WSL, Docker, providers or generated
answers. The original quality failure remains preserved.

The [later development cycle](answer-coverage-development-v3.md) is separate from
this frozen comparison. Its new corpus is development material, and its reader
changes do not rewrite the observations below or establish release acceptance.

## Pre-blind candidate freeze

Application/scorer candidate: `eee951a91dad03f95d62600a5b35dea9e92927f5`.
Freeze-record commit: `bce1111`. The
[checksummed freeze](evidence/answer-coverage-v2/candidate-freeze.json) records
UTC `2026-10-24T04:53:05.715465+00:00`, model hashes, source fingerprints,
configuration and the development result before the independent blind author
started. The freeze is immutable; later observations are separate artifacts.

The declared grid selected -8 with 37/48 correct development answers and 32/32
correct negatives. A subsequent all-method development run reproduced those
counts for keyword, vector, hybrid and reranked retrieval. These are development
results, not an unseen quality pass. See the
[seven raw reports and selection rule](evidence/answer-coverage-v2/README.md).

## Observed engineering gates

Run Python commands from the repository root in the isolated `.venv` with
`PYTHONPATH=apps/api`, SQLite memory DB, explicit legacy embedding/generation and
lexical selection for historical unit fixtures, empty provider key, offline
Hugging Face/Transformers flags, and two CPU threads. Connected tests select
their own real/local profiles. These unit defaults do not describe the connected
reader runtime.

| Command or observation | Observed result |
| --- | --- |
| `python -m pytest apps/api/tests scripts/tests -q -p no:cacheprovider --cov=app --cov-report=term` with a dedicated temporary directory | 421 passed, 1 infrastructure skip; 202.81 seconds; 66% statement coverage |
| `ruff check apps/api/app apps/api/tests examples scripts` | Exit 0 |
| `ruff format --check apps/api/app apps/api/tests examples scripts` | Exit 0; 199 files |
| `pyright apps/api/app --pythonpath <absolute project interpreter>` | Exit 0; 0 errors/warnings |
| Historical `verify_connected_evidence.py --source-revision e19006c`, original golden verifier and forbidden-dependency scan | Exit 0; historical quality gate still FAILED |
| Source/wheel build and wheel-content check | Exit 0; packaged original/development assets and reader modules; no weights |
| Fresh base-wheel installation outside checkout | Real upload → query → saved history passed with no Torch, Transformers, semantic model or parser extras installed |
| Fresh CPU reader-wheel installation outside checkout | Actual cached reader selected Anika's source passage with exact offsets; isolated import came from installed site-packages; downloads disabled |
| Fresh installed-reader `pip check` | Exit 0; no broken requirements |
| Frontend unit/lint/types refreeze checks | 72 tests in 20 files; lint/type exits 0 |

The Windows sandbox initially denied build/pytest temporary files and Pyright's
interpreter probe. The same gates passed with normal local process permissions;
these harness failures are retained in the execution ledger. The first installed
reader probe omitted the documented SQLite environment and inherited the optional
PostgreSQL default; correcting that harness environment produced the passing
outside-checkout proof. No application fix is attributed to those corrections.
Two unexpected pooler-tensor warnings from QA weight loading remain recorded.

Full coverage reporting is 66%, not complete coverage. A configured CI recipe is
not observed hosted execution. Native PostgreSQL/Redis/indexed performance,
human validation, provider quality, public hosting and publication remain
deferred or outside scope.

## Boundaries checked in the repair

Recorded regressions cover exact Unicode spans and tokenizer windows, missing or
corrupted assets, null decisions, concurrent reader isolation, cancellation,
saved evidence, normal/SSE behavior and revocation during streaming. The reader
never turns a missing configured model into lexical success. Selection evidence
is redacted when source access is revoked. History keeps its recorded method or
explicit unknown state.

Independent review identified and rechecked stream revocation, abbreviation and
negation loss, scorer exposure authority, overbroad absence checks and procedural
question rewrites. Multiple-document support remains, including its existing
three-citation presentation cap. Reader scores and the bounded surface absence
check do not establish entity/attribute entailment. Nearby wrong facts and
unrelated curated-group positives remain known quality risks for blind testing.

All 16 original evidence/golden files still match their preserved raw SHA-256
hashes. Git attributes retain measured corpus/report bytes, including the frozen
development manifest's CRLF form. New blind authoring requires UTF-8/LF. This
prevents newline normalization from silently changing a recorded corpus identity.

## First blind comparison: acceptance FAILED

The clean-context author produced 200 synthetic cases in 40 new families, with
70 documents and 90 snapshots. A fresh independent source verifier checked all
200 labels and canonical input preservation. See the
[input/preflight record](evidence/answer-coverage-v2/blind-input-protocol.md),
[corpus freeze](evidence/answer-coverage-v2/blind-corpus-freeze.json) and
[candidate binding](evidence/answer-coverage-v2/validation-binding.json).
Source ingestion and version publication used real authenticated HTTP in separate
disposable SQLite databases. Each arm then made 800 requests: 200 cases × four
retrieval methods. No provider, WSL or generative model was used.

| Method | Baseline correct answers /120 | Reader correct answers /120 | Baseline correct negatives /80 | Reader correct negatives /80 | Reader recall@5 | Reader MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Keyword | 30 | 52 | 68 | 77 | 0.9708 | 0.9653 |
| Vector | 30 | 55 | 68 | 77 | 0.9833 | 0.9135 |
| Hybrid | 30 | 55 | 68 | 77 | 0.9958 | 0.9389 |
| Hybrid + heuristic reranking (default) | 30 | 55 | 68 | 77 | 1.0000 | 0.9833 |

The default improved from 25.0% to 45.8% correct-answer coverage, but remains far
below **114/120 (95%)** and misses three required refusals. It has 46 false
refusals; the other 19 incorrect positive cases are attempted answers that miss
an authored fact, ordered step or required source. Retrieval recall is not answer
coverage. Default source/version correctness is 55/120 across all positive cases,
including refusals. Both arms recorded zero execution errors and zero observed
unauthorized source exposures or citation-integrity failures; candidate spans
were structurally exact. This does not establish general access/security coverage.

Both complete first reports and their raw response snapshots were
[sealed](evidence/answer-coverage-v2/first-comparison-seal.json) before failure
inspection. The portable verifier re-scored all 1,600 observed rows against the
canonical corpus and **exited 1, gate failed**. The
[baseline](evidence/answer-coverage-v2/first-baseline-canonical-v3.json) and
[candidate](evidence/answer-coverage-v2/first-candidate-canonical-v3.json) reports
are immutable. These cases are now exposed; no rerun can become fresh validation.

### Concurrent-editor integrity qualification

The original controller's final on-disk source hash assertion **failed** after
both reports completed: another editor changed six version/pagination modules
during measurement. The owner confirmed concurrent work. Those edits were
preserved. The dedicated APIs started before those writes, with hot reload off;
subsequent root/version and pagination probes retained the frozen behavior.
QA, retrieval and scorer files were unchanged. Nevertheless, the on-disk
source-after check did not pass. The
[qualification](evidence/answer-coverage-v2/concurrent-edit-qualification.json)
records this deviation; it is not silently converted into a clean protocol pass.
The controller lost its child exit-code metadata when that assertion raised;
complete reports/stdout survive, and the independent re-score exit1 was observed.

An isolated delivery worktree was created from `bce1111`, preserving the active
editor's checkout. All 135 frozen source fingerprints initially matched there
after restoring eight files' recorded newline bytes. The post-measurement privacy
repair below is separate from the measured candidate; it earns no new unseen
quality claim. Delivery worktree/branch are recorded in the handoff.

### Evidence limits and independent review

The bounded scoring contract checks authored required facts/steps and source
identity, quotes and offsets. Independent review demonstrated that it is **not**
a general entailment checker: a fabricated response can append unsupported prose
while retaining required facts and an unrelated valid span. The frozen scorer
was not changed after measurement. A separate audit checked every nonempty
recorded answer: all 168 baseline and 306 candidate answers exactly reproduce
their recorded quote/span assembly plus citation markers; no generated extra
prose appeared in these observations. That audit does not establish relevance or
complete factual support, which already fail the authored contract.

The final unchanged connected browser suite failed at all three sizes on the
original rollback false refusal. Sample browser checks passed 3/3 without backend
or external calls. A separately labeled diagnostic passed 3/3 for an actual scoped
Anika upload, reader JSON/SSE answer, immutable highlighting/reload, historical
reader failure, refusal, outage/retry and route layout. It does not replace the
failed original journey or its unexecuted downstream workflow/version checks.
See the [browser observations](evidence/answer-coverage-v2/browser-observations.md)
and [inspected screenshots](evidence/answer-coverage-v2/screenshots/README.md).

The original 8400/3505 review app and database remain unchanged. PostgreSQL/Redis,
indexed-scale performance, human validation and hosted execution remain deferred.
Acceptance stays open; a later repair requires another separately authored,
frozen unseen set rather than replacing this failed comparison.

## Post-measurement privacy repair

Independent disposable-fixture review found that a refused/null candidate or an
uncited candidate could retain a revoked document UUID in saved diagnostics.
Source text was not exposed in the reproduced case. Authorization previously
checked only selected citations, so an empty citation list bypassed the diagnostic
check. Four repository regressions recorded this failure before the repair.

`source_access` now checks cited documents **and every saved retrieval candidate**.
Reader diagnostic chunk IDs must resolve through the saved trace's document
mapping; malformed or missing mappings fail closed. Current chunk rows cannot
establish historical identity after reindexing, so they are not used as a fallback.
Saved-query/conversation presentation, per-yield SSE and recent memory share the
same check. Raw immutable records remain stored, but restricted answers, citations,
traces and provenance are withheld. This conservatively withholds the whole
record even when only an uncited candidate lost access; it does not narrow the
authorized multi-document answer workflow.

The same four failing scenarios passed after repair. Additional checks cover
malformed IDs, absent trace and unmapped chunk IDs. Independent post-fix validation
passed 52 tests, including its own history/SSE probes, existing reader tests and
the repository privacy tests. Missing-model failures retain safe model identity
when no candidate evidence exists. This is an authorization repair after the
sealed evaluation, not a new blind answer-quality result.

Fresh isolated post-repair checks observed **428 passed, 1 infrastructure skip**
in419.42s, with66% Python statement coverage. Ruff passes, formatting checks200
files, and Pyright reports zero errors/warnings. Frontend units pass72 tests in20
files; lint and TypeScript exit0. Source/wheel builds and wheel closure pass; a
new base environment outside the checkout performs upload → query → history and
loads all100 original,80 development and200 canonical validation cases without
Torch/Transformers/semantic/parser extras. The original historical verifier exits0
for integrity while preserving its FAILED quality outcome. The deterministic
golden verifier passes against the explicit preserved original bundle; an initial
isolated invocation only failed because that ignored bundle was absent from the
new worktree. No golden bytes were regenerated.

The isolated locked `npm ci` reports three moderate dependency findings and one
unapproved `unrs-resolver` postinstall script under the host's npm policy. No
dependency or script-approval workaround was applied. The other editor's version,
dependency, pagination, CI and accessibility changes remain in their original
checkout and are outside this delivery commit.

The final wheel was also reinstalled into the separate CPU-reader environment
created during this milestone. With `-I`, outside-checkout imports, SQLite and
downloads disabled, the installed application performed real ASGI upload →
cached semantic ingestion → reader answer → saved history → source inspection.
It selected Anika's exact [0,76) source span and loaded all100/80/200 packaged
case sets. This is the actual installed API, not a direct model-only probe or
a new blind-quality measurement. Restarting the disposable browser database under
the privacy repair preserved the exact saved answer/provenance/source hashes and
document/chunk/query counts; no duplicated ingestion/query effect was observed.

After the privacy repair, a fresh isolated production build exited0 (Next16.4.2;
React18 deprecation remains). With builds stopped, fresh sample3/3 (27.4s) and
separate real-reader diagnostic3/3 (27.6s) passed at all three widths. The sample
again asserts zero backend/provider/external requests; the connected diagnostic
uses successful real API responses, not mocks. New source/error screenshots were
inspected for meaningful content, wrapping and focus. These are affected
integration checks, **not** a rerun or passing replacement of the known-failing
complete original journey. See the appended browser record for exact commands.

## Later independently frozen comparison and bounded repair

This original record remains historical. A later larger-reader
[fresh200 comparison](evidence/answer-coverage-v8/README.md) also FAILED69/120+62/80
versus39/120+75/80 baseline. A subsequent source-title parser
[repair and engineering verification](evidence/answer-coverage-v9/README.md) is
separate exposed development, not a replacement for any failed result.
