# Combined procedure verification — local engineering checkpoint

Observed2026-10-25 on Windows using SQLite, inline ingestion and cached CPU
models. **Answer-quality acceptance remains open:45/48 development positives,
32/32 negatives.** No new blind set, default promotion or release is claimed.

The [portable engineering evidence](evidence/combined-procedure-engineering-v1/README.md)
has independently reviewed captured answers, immutable snapshots, source/runtime
bindings, screenshots and a model-free replay. Its source27 implementation is
bundled and pinned, so later working-file changes do not rewrite that observation.
The [failed development report](evidence/quality-repair-dev-v27/README.md) remains
a separate immutable result.

## Observed checks

| Check | Result | Boundary |
| --- | --- | --- |
| Full Python277 | 2676 passed,1 service skip;82.50% statement coverage | PostgreSQL/Redis opt-in skip; local Windows only |
| Python CI lint/format, Pyright, forbidden scan | Pass | Application/test/example/script CI scope; historical reproducer bytes preserved |
| Frontend after metadata and guard repairs | 590 unit tests; types and full lint pass | Includes unit doubles; separate from real API/browser checks |
| Production build296 | Pass,9 routes |212 inputs captured; only generated type/config references changed and were restored |
| Real connected browser297 |3/3 at390×844,768×1024,1440×900 |Real uploads, cached models, normal/SSE answers, refusal, update/diff and historical source inspection; no successful API mocks |
| Independent connected replay299 |9 completed records,9 source responses;18 tamper rejections |Output-cover-v1 examples; no live conditional-cover-v2 claim |
| Real cloned-database restart300 |12 historical DTOs/9 sources preserved; missing-model errors and restored normal/SSE answers pass |Only the support assets were deliberately absent; structured JSON equality, exact answer/source strings and stored rows |
| Independent restart replay304 |2 repaired certificates pass;4 tamper controls rejected |Original13 query rows,23 versions,18 documents and18 chunks preserved |
| Offline production310 |21/21 at all3 viewports; no attempted backend/provider/external connections observed |Reviewed origin/API/write/WebSocket guards within Page observation windows; no whole-machine network capture |
| Base wheel269 outside checkout |Pass, actual upload/query/history |No external shared_core/Torch/parser import; fresh optional-model installation remains unverified |

The590-test frontend includes47 request-guard tests added after build296. Only
two offline specs and two new test-harness files changed:210 of the212 earlier
inputs remain identical, and all runtime application inputs are unchanged.
The214 current inputs are recorded separately; they were not all built by296.
The stronger offline run uses that reviewed harness against the unchanged
production application. Earlier303 passes retain their loopback-guard limitation.

Detailed local records are in the operation workspace's
`.tmp/groundtruth-coverage-20261024/quality-v6/`: `full-verification-v277`,
`frontend-metadata-authority-repair-v294`, `current-frontend-checks-v312`,
`offline-network-guard-repair-v307`, `offline-independent-v305/review-v310`,
`connected-browser-review-v299`, and `restart-independent-v304`. These local
records supplement the portable connected/restart bundle; they are not published
hosted CI results.

## Repairs and actual workflow

Procedure expansion preserves a reader's original raw proposal lineage while
copying the full source-declared instruction interval. The UI now checks those
recorded raw candidates rather than equating them with the expanded interval.
Malformed modern diagnostics cannot silently enter legacy span-only compatibility;
the recorded profile and retained capture determine the applicable contract.

The [public engineering inputs](../apps/api/app/portfolio/assets/procedure-copy-demo/README.md)
provide a numbered Cedar procedure and a counted-paragraph Juniper procedure.
Actual acceptance uploaded their TXT files, inspected NLI-supported subject/
applicability separately from exact instruction/output coverage, rejected an
unsupported qualifier, replaced Juniper's content and reopened its superseded
immutable evidence. The package README's original NOT RUN note records its
authoring checkpoint; execution is recorded in the evidence bundle above.

On a database clone, saved evidence remained readable with support not_loaded.
Missing support assets produced readiness503, normal-query503 and an SSE error
without factual tokens; two durable rows recorded errors rather than refusals.
After valid assets were restored, normal/SSE answers, citations and traces agreed.
Historical answers were checked from stored evidence without rerunning NLI.

All examples and labels are synthetic and agent-authored. Local model execution
is real; no generative model, paid provider, WSL, Docker or public hosting is used.
The observations do not establish human validation or general model quality.

## Remaining acceptance

On2026-10-26 the owner approved reading bare commands in an explicitly scoped
audit note within that note's stated context, with the interpretation disclosed.
A separately versioned, opt-in policy is being implemented and reviewed. This
decision does not change the preserved source27 score, qualify the candidate or
retroactively certify historical evidence. Unsupported scope changes and grammar
remain unresolved; strict legacy/library defaults remain explicit.

The independently audited [source29 run](evidence/quality-repair-dev-v29/README.md)
now records that context policy with real cached CPU models. Coverage remains
45/48+32/32: all6 affected notes pass22 NLI checks and fail the same generated
card-reference identity check. Its complete first result is preserved. A new
typed-reference verification contract is being implemented; it is not yet a
qualified configuration. No failed assessment is relabeled as entailment.

Qualification still requires at least46/48 positives,32/32 negatives, required
opposing-source inspection and zero evidence/access errors, followed by the
predeclared margin grid/all retrieval methods and a frozen candidate. Only then
may an independent author/reviewer create another fresh200-case blind set.
The unchanged gate is114/120 positives,80/80 negatives, improvement over the
original baseline and zero authorization/citation/span errors.

Conditional-cover-v2 live acceptance, final changed-source gates, fresh optional-
model installation and the remaining full connected-route/failure checks remain
distinct. PostgreSQL/Redis/indexed-scale and hosted/human/provider claims remain
deferred. Owner review8400/3505 has not been refreshed; both endpoints were
unavailable at the latest liveness check, with no initial-state/cause attribution.
