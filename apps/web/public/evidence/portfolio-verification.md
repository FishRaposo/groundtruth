# Project 05: portable application verification

Observed 2026-10-24 on Windows, Python 3.12.14 and Node 24.21.0. Base source:
`a8dc3570e3e66320b716d31a4791e957f14d7cfa`; branch `feat/groundtruth-portfolio`.
The owner explicitly authorized continuing without WSL. This verifies SQLite,
canonical inline ingestion, cached CPU semantic embeddings and extractive answers.
It does **not** complete the deferred PostgreSQL/Redis acceptance criteria.

## Fresh gates and their scope

Run Python commands from the repository root with `.venv` activated. For tests,
set `PYTHONPATH=apps/api`, `DATABASE_URL=sqlite+aiosqlite:///:memory:`,
`APP_ENV=test`, `EMBEDDING_MODE=legacy`, `GENERATION_MODE=legacy`, an empty
`OPENAI_API_KEY`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. Explicit legacy
settings preserve historical library fixtures; authenticated connected HTTP
execution rejects that profile and uses the separately configured local mode.

| Command / observation | Result |
| --- | --- |
| `python -m pytest apps/api/tests -q -p no:cacheprovider --basetemp=.tmp/parent-frozen-pytest --cov=app --cov-report=term --cov-report=json:.tmp/parent-frozen-coverage.json` | 331 passed, 1 infrastructure skip; 114.48 seconds; 64% statement coverage |
| `ruff check apps/api/app apps/api/tests examples scripts` | Exit 0 |
| `ruff format --check apps/api/app apps/api/tests examples scripts` | Exit 0; 192 files |
| `pyright --pythonpath .venv/Scripts/python.exe apps/api/app` | 0 errors, 0 warnings |
| `python scripts/portfolio_demo.py` and `python scripts/verify_portfolio_evidence.py` | Both exit 0; original golden fixture preserved |
| `python scripts/check_forbidden_dependencies.py` | Exit 0 |
| `python -m build apps/api` and `python scripts/check_wheel_contents.py` | Source/wheel builds and packaged vendor/corpus closure exit 0 |
| `python scripts/verify_isolated_wheel.py` | Exit 0 in a fresh environment outside the checkout: packaged 100-case corpus, deterministic 384-vector, actual text upload/query/saved history; no sentence-transformers/PDF extras installed |
| `npm test -- --maxWorkers=2` in `apps/web` | Parent fresh 62 passed / 19 files, 14.39 seconds |
| `npm run lint` and `npx tsc --noEmit` | Exit 0 |
| `npm run build` | Production build exit 0; Next 16.4.2, API origin 8400, demo mode false |
| Separate production offline and connected Playwright suites | Three viewports each; see the checksummed browser observation below |
| Real HTTP workflow plus same-database process restart | 10 workflow checks and 2 restart checks; exit 0 |

Coverage is measured, not comprehensive. The remaining untested server/worker and
provider paths are not certified by a 64% report. Hosted CI execution was not
observed. The CI infrastructure job provisions PostgreSQL/pgvector/Redis and runs
the opt-in live test on ordinary relevant runs; configuration is not execution.

Pyright initially could not spawn its Python import-discovery process inside the
tool sandbox and reported false missing imports. The identical check with that
process boundary permitted completed with zero errors. Initial pytest working
directory, SSE harness vocabulary and PDF update-format mistakes were corrected
as harness defects, separately from application regression evidence.

## Actual connected proof

The acceptance processes use a disposable SQLite database, cleared provider
credentials, offline model loading, two CPU threads, loopback binding and explicit
3505 browser origins. The acceptance limiter is disabled to permit concurrency
probes; the documented review helper enables the normal limiter. No owner database
or sibling service is used. The pinned model produced actual 384-dimensional CPU
vectors with a 256-token limit; safetensors SHA-256 is
`53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`.

`scripts/verify_connected_workflow.py` sends real requests against FastAPI. It
checks normal/SSE citation agreement, 20 overlapping requests with isolated
traces, source version 2, owner/workspace history exclusions, empty/private scope
refusal, conversation isolation and source numbering, real PDF parsing/update/
restore to version 3, malformed-PDF durable failure, reader/admin denial and a
persisted terminal SSE refusal. Its restart mode reads the exact same historical
source snapshot and restored version after replacing only the task-owned API
process. There is no tool redispatch or fabricated success.

The production browser suite covers Home, Chat, Documents, Workflows, Admin and
the actual-workflow guide at 390×844, 768×1024 and 1440×900. Connected checks use
real HTTP, never successful API mocks: normal/streamed answers and refusals, saved
query URLs/reloads, source inspection, actual TXT upload/update/diff/restore,
approve/reject/cancel, loaded durable audit/usage, legacy unknown evidence,
identity/private-cache changes and deliberate outage → error → Retry recovery.
Offline checks cover guided/free exploration, version comparison, refusals,
curated conflict, simulated quarantine recovery, saved sample history and complete
reset; they assert zero API/provider/external requests. Keyboard Enter/Tab/
Shift+Tab/Escape, source-drawer focus return, reduced motion, readable contrast,
navigation clipping and unexplained console/page errors are checked.

## Recorded defects and independent review

Preserved RED/GREEN checks cover scope/session/counter leaks, memory displacing
source numbers, restore without compatible embeddings and connected fallback.
Actual integration/review also found and repaired workspace API-key escape,
denial logging using a detached ORM object, startup interruption of healthy jobs,
stale worker/dispatch failures overwriting retries, SSE refusals displayed as
errors, nullable usage-price crashes, saved-query URL races, incomplete reset,
drawer focus escape and legacy unverified content promoted into new citations.

A bounded independent reviewer used isolated in-memory HTTP/state probes. Final
recheck exit 0: 10 keyword/vector query cases rejected unpublished, missing,
invalid-hash or mutated snapshots and accepted valid immutable evidence; legacy
history remained explicitly unknown. Delayed dispatch and three stale worker
token/attempt combinations preserved current work; the valid current failure
transitioned to error. No material finding remained in that reviewed scope.
Local semantic execution is proven separately by the real-process acceptance;
the independent review used deterministic embeddings and did not test Redis/PG.

## Preserve the failed quality gate

The [first frozen reports](evidence/portfolio/README.md) contain 20 development
cases and 80 held-out cases per method. All 20 development contracts passed;
the **first held-out command exited 1, with 37/80 passed per method**, 42 false
refusals and one missed refusal. Recall@5 was 1.0 and unauthorized exposure was
zero in these authored fixtures. That is a failed answer-quality gate despite
successful retrieval. See the [case study](portfolio-case-study.md) for denominators
and the later independently prepared compound-word regression. No exposed-case
rerun is represented as new unseen validation.

`python scripts/verify_connected_evidence.py` verifies checksums, source
fingerprints, chronology, exclusive fixture identities, concurrency/restart and
browser metadata. Its own success means artifact integrity; it explicitly retains
the failed quality result. It does not turn the quality gate green.

## Inspectable artifacts and limitations

The committed [evidence directory](evidence/portfolio/README.md) contains raw
evaluation observations, workflow/restart/browser metadata, integrity manifest and
representative inspected PNGs. The local external execution ledger retains exact
commands/stdout/exits under `.tmp/groundtruth-20261023` in the operation workspace;
it also retains failed/historical attempts rather than overwrite them.

Runtime npm audit: zero findings. Full graph: three moderate development-only
Tailwind/postcss-nested/postcss-selector-parser findings remain. React 18 is still
supported by the installed Next version, with an announced Next 17 deprecation;
no incompatible forced upgrade is claimed. Browser color-environment warnings
and intentional test ErrorBoundary stderr are harness diagnostics.

Deferred: live PostgreSQL/pgvector/Redis worker execution, filtered ANN recall,
natural SQL plans, the 1k/10k/100k timing matrix and restart/cache measurements.
No performance/capacity claim is made. Model-generated answers, human validation,
paid providers, hosted multi-user authentication, formal accessibility
certification, hosted CI, public hosting/publication and recorded video remain
unverified or outside scope. Security redaction is not comprehensive PII detection.

The operation overview guard passes. Its broad legacy validator aborts with a
Windows text-decoding error while scanning nested dependency Markdown; the
copy-all root unit harness would duplicate every cloned repository/environment
for every test and was not run. Scoped changed-document links and the project
gates are checked separately; no passing broad operation gate is claimed.
