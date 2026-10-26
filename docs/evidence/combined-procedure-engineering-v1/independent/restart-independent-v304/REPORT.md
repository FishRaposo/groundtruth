# Independent clone-restart evidence review R304

Checked 2026-10-25. Final state: QUIET. Contract confirmed within the tested SQLite clone / absent support-assets / repaired cached-assets scenario. No material finding in the inspected assertions, HTTP/SSE artifacts and independent read-only database comparisons. This is not general NLI/model quality, DEV/blind, full restore/fresh install, PostgreSQL/Redis or browser-error-UI acceptance.

## Independent result

The root probe's missing/repaired exit files are 0 and its logs report both phases passed. This review independently checked the actual response/event payloads and immutable SQLite rows rather than accepting those success flags alone.

| Observed boundary | Missing support directory | Valid cached support assets after API restart |
| --- | --- | --- |
| Historical DTOs / source responses | All 12 / 9 structurally unchanged | All 12 / 9 structurally unchanged |
| Before/after-history runtime | Support and reader report not_loaded | Support and reader report not_loaded |
| Readiness | HTTP 503; support:error; reader/embeddings:ok | HTTP 200; support/reader/embeddings:ok |
| New normal query | HTTP 503; no substituted answer | HTTP 200; original exact Cedar answer/sources |
| New SSE query | HTTP 200, one error event, no token/citations/done | Three tokens, citations, one done; no error |
| Durable new rows | Two outcome:error, refused=false, answer=null, sources=[] | Two outcome:completed with the returned output |

The repaired token contents concatenate exactly to the done answer and normal answer. The citations event's sources and retrieval_trace equal the done record. Both repaired outputs reproduce the original Cedar answer/sources and verified cover-v1 certificate. Normal/SSE output records are present in the clone DB; the missing-phase errors also remain present after repair. This distinguishes execution failure from a factual refusal or a lexical/sample answer fallback.

## Actual isolation and preservation

All 94 sealed entries in Q/live-combined-v297-first-result-preservation.json match before and after this review, including source DB/seed/uploads/logs and Q298 evidence. clone-initial.json records the same source DB hash that currently matches that sealed original. The actual current clone retains all 13 original stored query rows exactly; it adds only four new queries. All 23 original immutable document_versions, 18 documents and 18 chunks remain exactly equal. All 24 non-DB source-data files, including uploaded bytes and private seed, equal their clone counterparts. Original and clone DB hashes stay unchanged during this read-only inspection.

The retained valid clone launch array differs from the original297 array only in --data-dir. Missing and repaired arrays differ only in --support-dir: missing uses an empty directory (zero files), repaired uses the configured cached pinned NLI assets. Distinct actual server startup IDs appear in the two API logs; both have startup completion. No process lifecycle was performed by this reviewer. These artifacts support the described two API starts on one clone, not a machine reboot or a new installed environment.

Both phases' twelve saved history DTOs and nine saved source responses equal the Q298 originals as parsed JSON, including exact answer/quote/source literal strings. The serialized files are **not byte-identical** (zero of 21 raw file comparisons match in each phase) because capture serialization differs. The preserved claim is structural DTO equality plus exact literal/stored-row preservation; identical raw HTTP or JSON-file bytes are not asserted. serialization-scope.json records that distinction.

## Probe/assertion and fault-scope audit

Read actual probe.py, both retained argument arrays, raw readiness/normal/stream/history/error records, result files and relevant API log summaries. probe.py imports an HTTP client and sends real requests; it neither loads QA/NLI nor mocks responses. The root's actual API process performed readiness/model use. It brackets historical reads with health snapshots, verifies every old DTO and source, then tests readiness and both new-query transports. It checks durable failure records and rechecks original records after query execution. Existing phase folders were not rewritten.

The saved data show the fault is support-specific in this case: reader and embeddings readiness remain ok while evidence_support errors; the support path is empty. Historical runtime state reports support/reader not_loaded before and after read-only history. This is a bounded model-readiness observation, not proof every Python dependency or OS memory mapping is absent. Readiness later loads assets by design. No malformed-checkpoint, missing-reader, optional-package, OOM, general provider failure or every possible asset error is claimed.

The SSE evidence preserves parsed data-event payloads, not arbitrary network packet timing or client cancellation behavior. Both normal and streaming endpoint semantics are verified for the captured request; no browser was involved in this restart probe. Its support-failure behavior must not be confused with semantic NLI neutral/contradiction handling or used as general answer-quality evidence. All documents are synthetic public engineering examples; completed certificates here are cover-v1.

## Fresh independent checks executed

From W, no network/model invocation:
`python -B ../quality-v6/restart-independent-v304/compare_artifacts.py`

comparison.log / independent-comparison.json: exit0. Opens original/clone SQLite through mode=ro&immutable=1, compares all original query/version/document/chunk rows, copied data files, all 21 parsed history/source artifacts per phase, exact status/event/error branches and complete known credential-value absence in non-private artifacts. No credentials/header values were exported. API logs contain their normal truncated key-prefix metadata; that is not a full credential or authentication header and is not reproduced in this report. The known complete-value scan is bounded, not an exhaustive secret detector.

Additional direct read-only artifact check in stream-persistence-checks.json verifies exact token concatenation, citations/trace parity and presence/equality of all four new durable rows. An initial inspection compared the citations event with an object omitting its legitimate retrieval_trace field; it was corrected to compare actual sources and trace separately. That harness mistake is not a product finding.

Pure canonical replay command from W:
`$env:PYTHONPATH='apps/api'; $env:DATABASE_URL='sqlite+aiosqlite:///:memory:'; .venv/Scripts/python.exe -B ../quality-v6/restart-independent-v304/verify_repaired.py`

repaired-canonical-replay.log / .json: exit0. Both repaired normal/done certificates pass actual verify_output against independently loaded immutable clone versions and actual retained trace. Two changed-certificate and two changed-actual-answer controls are rejected. DB hash remains unchanged; no model inference/API call is used.

The runtime-after addendum was added outside the phase folders during review. It is byte-equal to the preceding297 interpreter/sixteen-package-RECORD manifest. That does not attest every installed binary or model asset. COMMANDS.md is explicitly after-transcribed; it supplies readable command provenance without a contemporaneous argv claim. Both addenda are hashed in runtime-and-addenda-checks.json. All 70 current non-private inputs pass the known complete-credential-value scan.

## Integrity, limits and handoff

initial-hashes.json binds 68 initial non-private restart inputs; every one remains unchanged. The 94 sealed original hashes still match. RESULT.json additionally binds all 70 current non-private files, including the two new outside-phase addenda, and records original/clone DB hashes. No original Q294/R290/R299 review, W file, sealed source, response log, phase data, process, API, browser, build, model, dependency, installation or commit was changed. Only NEW Q/restart-independent-v304 output was written. All command sessions ended; QUIET.

Outcome/artifacts: bounded restart/model-assets-failure/repair evidence accepted with no material finding; REPORT.md, RESULT.json, initial-hashes.json, independent-comparison.json, stream-persistence-checks.json, serialization-scope.json, runtime-and-addenda-checks.json, final-hash-and-process-evidence.json and pure replay scripts/logs. Sources/date: actual300 probe/arguments/two-phase responses/logs, sealed297 registry and read-only original/clone DB rows, 2026-10-25. Opportunity/experiment IDs: none. Cash: unknown. Blockers within this review: none. Next owner/action: root integrates the bounded result with separate production-browser, product-scope and model-quality decisions, preserving both originals and this evidence.

