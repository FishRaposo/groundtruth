# Independent engineering evidence review E488

2026-10-26. Verdict: **PASS for the bounded D481 engineering observation**. No material inconsistency found in the reviewed source diff, saved records, final browser observations, screenshots or recorded cleanup. This establishes one successful actual browser engineering run; it does not establish blind-answer quality, a release gate, or the root cause of the earlier D466 failure. No approval for another live run is implied. Root owns next actions and the shared handoff; FTH-016 support, cash unknown.

## Independent findings

The source delta is exact and narrow (`independent.diff`). Coordinator466→481 changes only the run-specific initial API record filename. Browser466→481 changes only the catch DTO to include already sanitized issues/request failures/responses/request arrays. Wrapper464→481 changes only run-specific command/process record suffixes. The venv binding is byte-identical. Classifiers, expected-event predicates, assertions, origin checks, credential guards, key-matched provider snapshots, IPC, strict process identity/birth/mtime/listener checks and cleanup protocol are unchanged. The two current identity-connect ERR_ABORTED events are accepted by the **preexisting** predicate at browser lines170-172; no new exception was added.

Current D481 has all three final observations and browser-done, browser/coordinator exit0, exactly one guarded API restart and complete recorded cleanup. Saved baseline and recovered **entire DTOs** compare equal independently at390/768/1440; this includes the stored record and source/provenance data, beyond answer text. Each recovered DTO records local Retry without reload, zero query POSTs and session-key retention. Browser lines208-231 separately assert an actual GET200, equal answer/sources, unchanged document timeOrigin and unchanged POST count, before the later separate persistence reload. Provider Retry is separate. All six routes are asserted after recovery at lines233-257; admin usage/audit are real403, with explicit ordinary-user denial and no substituted audit data. Every width has the corresponding recorded403 events.

The saved event inventory independently recomputes to:

| Phase | Type | Count |
| --- | --- | ---: |
| outage | ERR_CONNECTION_REFUSED |18 |
| retry-down | ERR_CONNECTION_REFUSED |3 |
| identity-connect | ERR_ABORTED |2 |

There are23 recorded request failures, all classified expected, and30 console issues total, all classified expected; no unexpected issue or pageerror appears. Each viewport records recovery saved-query GET200 and cross-owner saved-query404. Explicit-sample observations contain no API response in that phase, and the unchanged browser asserts zero API requests after the explicit switch and absence of private document identities. Distinct private owners/workspaces and nine document identities are checked at browser lines128-131, and switched-identity document lists are checked at275-289. No private seed or SQLite read was needed for this independent review.

**D466 remains unresolved.** Its preserved browser-error records `Unexpected request failure: 4 !== 0` but only viewport/phase/URL in catch contexts; it has none of the per-event arrays required to identify the four failures. D481 does not reproduce them and did not enter its new catch branch. Its two observed cancellations cannot retrospectively identify those four unseen events. Neither this review nor D481 proves an old root cause was fixed or supports broadening a classifier.

## Visual evidence and limits

All36 PNGs have valid PNG headers and exact390×844,768×1024 or1440×900 dimensions. I visually inspected15 original PNGs: admin, local-retry-recovered, recovered-source, identity-denied and explicit-sample at every width.

- Admin images show the final ordinary-user privilege denial and no fabricated metrics. At768 the audit panel explicitly says no audit data was substituted; the narrower/top-of-page crops do not show every lower panel, which is independently covered by the browser assertions and recorded403 responses. No loading state appears in the inspected admin screenshots.
- Recovered-source dialogs show current/version2 synthetic typed engineering evidence at every width, without credential fields. The phone view is a narrow scrollable passage crop; the larger views show exact-source highlights. These are old typed378 engineering fixtures, not fresh blind corpus material.
- Explicit-sample images clearly display sample mode and synthetic data. Identity-denied images display query-not-found and no stale recovered answer. Some identity-denied images still show unrelated history-loading text, so they are not evidence of a fully settled history panel.
- The local-retry-recovered screenshots show the still-distinct provider failure notice at the top and can place the recovered answer below the viewport. Therefore those top crops alone do not demonstrate the recovered answer. The complete saved DTO equality, real GET200 and unchanged browser assertions supply that evidence; the subsequent source-dialog shots demonstrate source access after provider refresh.

I did not visually inspect the remaining21 PNGs; their hashes/dimensions and the six-route browser assertions were checked. This is a bounded verification, not an exhaustive visual/accessibility certification.

## Hash and cleanup scope

- coordinator481: `26ea53dcd6448081e13078544a38820884f5161c67f1bf5c00fd1c98cb4d00c2`
- browser481: `acc8db5b1ba359ee80b0fb36bf003673b0c9653e5ea197f9c8850bea336ae53a`
- wrapper481: `72502d71013cccf3fd7c8aa2481876edec5b39cf9b94923e2af7d3d12bdaef6b`
- executable binding: `91bc41a78f9eda227e7b23dea7e1bfebe540e2b25b8d8fdd98412a99f66c22eb`

All83 current public artifact-manifest entries match their hashes, including36 PNGs and the subsequently added D481 REPORT. The historical close log's82 count precedes that report entry. Both preservation inventories are equal and all1758 old466 files still match. No old failure was overwritten.

Build430 source-restored manifest is the exact232-file manifest pinned by freeze446, SHA `39e835a9dfa0a282a5f3632dd7dc30cbb5469b231b09e73286e7442b4bc56d30`; all232 current frontend source files match. Preflight build ID and standalone server hash match the original build and staged actual server. All232 frozen source31 files match their inventory. Saved initial/restarted readiness reports satisfy the pinned central346 expected runtime, including QA4/margin2/context2. These are file and stored-runtime checks, not a new readiness call or a remote attestation.

Recorded before/after port inventories both say8401=[] and3506=[]. Cleanup records the initial recorded API stop, browser already exited0, owned restarted API/frontend stopped and both ports closed. This review reads those historical artifacts only; it made no port/PID/CIM/HTTP query and does not assert the ports remain unused now. The strict ownership guards are preserved by exact diff.

Private seed bytes/keys were not opened by this reviewer. Public record key scans found no api_key/authorization/password/credential fields. The unchanged live browser compares actual private keys against its evidence/logs during the authorized run and forbids credential input fields in screenshots; those controls passed with the run. This is not an independent plaintext-secret-value scan against the restricted private seed.

## Commands and verification

Only base Python file/stdlib work and local image viewing were used. No API/browser/model/service/process-inspection command, source/scorer edit, fresh corpus read, SQLite operation or private-key read occurred.

`C:\Users\vinic\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -S -X utf8 -B <Q>\typed-outage-live-independent-v488\check_evidence.py`

First run exit1 (`checks.log`) was an independent review-harness count assumption: it expected the close-time82 manifest entries, while the completed current manifest also binds REPORT.md for83. I verified the added entry, changed the count check and retained that initial result. Final run **exit0,6 tests PASS,4.389s** (`checks-final.log`) verifies exact diffs, public/old artifact hashes, complete three-record recovery/event inventories, build/freeze/runtime metadata, PNG dimensions/key hygiene and recorded cleanup/old-failure limits.

An auxiliary hash-summary command wrote its initial binding file, then exited1 when printing a key with Windows versus POSIX separators. The initial file is preserved as `review-bindings-initial.json`; the final metadata-only command used POSIX keys and completed exit0. This formatting issue did not affect the passing evidence checks or reviewed inputs.

All writes are in this new E488 review directory. Next owner: root may use D481 as bounded browser engineering evidence while preserving D466's unexplained failure and keeping blind quality/release decisions separate. **QUIET.**
