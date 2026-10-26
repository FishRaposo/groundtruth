# E422 independent engineering evidence review

2026-10-26. Two separate bounded verdicts follow. No overall quality, unseen-evaluation, deployment or capacity approval is implied.

## A — Offline production sample browser gate: supported

Inspected the actual root421 Playwright report, invocation, process/stop records, final result, root414 build records, both executing specs, the network guard and all nine PNGs. The report contains **21 actual passed tests**, zero skipped/unexpected/flaky, no report errors, one attempt each, **97.023457 seconds**. The suite is three recruiter journeys plus six route axe scans at each of three viewport sizes. The journey asserts keyboard activation, focus trap/return, saved-answer and refusal selection, version comparison, reset, route overflow, selected contrast checks, and no page/console errors. This is retained execution evidence, not a new browser run by this reviewer.

All **232 root414 build inputs** match current W, including repaired root407 PortfolioChat SHA `09f7f0a529f7329de30e0f57d3e70c56013bd914307ae5e3c3cc2a0a54481042`. The restored source map equals the prebuild map and root421 invocation map. Build exit is 0; its log records successful compilation/types/static generation. Root421 starts that `.next-context-v414` output and records stopping its owned frontend PID in stop.log. Source binding is to the retained build recipe/maps/log, not an independently rebuilt bundle or cryptographic executable attestation.

Visually reviewed all overview, source and version-history PNGs at **390, 768 and 1440 px**. Sample labels are visible; overview content fits; source passage, version/hash metadata, comparison and focus indicators are readable in the captured viewports. Mobile dialogs intentionally capture their scrollable viewport, so lower content is not all visible in one PNG. These screenshots support their shown states, not every route state or connected outage behavior.

Both specs install the Page network guard before navigation and require an empty violation list. It records different origins (including API/provider origins), `/api` namespace attempts, writes, and WebSockets. Independent model-free guard probes passed: three permitted frontend cases, eight rejected API/provider/external/write cases, WebSocket classification and two recorded listener attempts. Thus the retained passing test supports **no Page-observed forbidden attempts** in these flows. The guard observes rather than blocks; this is not firewall, server-process, browser-worker or whole-machine egress monitoring. No raw all-request trace is retained to elevate that claim.

No actionable finding within this offline evidence scope.

## B — Three concurrent private HTTP requests: supported engineering check

Independently read all three retained root420 response DTOs, the executed controller script, its result/log, a captured prefix of API-restart.log and a read-only transactional SQLite snapshot. Did not read the private seed manifest or API-key table. Each DTO matches its persisted question, answer, outcome, refusal, source content, provenance and retrieval trace. Each conversation belongs to the same persisted owner/workspace; all **three owners, workspaces and conversations are distinct**. Each workspace contains exactly its own three source documents, owned by that owner; source IDs are disjoint across cohorts. Retrieval score IDs, inspected identities, final citations and condition opponents remain inside the correct workspace. The two opponents equal the own three-document set minus the primary procedure.

Final citations and procedure proof use the **current primary version 2**. All inspected source hashes/bodies match authoritative document-version snapshots and the current published version (opponent notes remain current version 1). Frozen source30 canonical output verification independently passes **3/3** against actual questions/answers/citations/trace/snapshots. Across six opponent-note readings, all **132 recorded NLI checks** validate, and each canonical typed exact-reference obligation/plan matches without NLI fields. Recorded reader is RoBERTa revision adc3b06f.../QA threshold 4. No model was rerun.

Actual restart log records one successful POST per workspace in the root420 interval, followed by GET200 of each exact retained query ID. POST durations are **33.11821, 50.99632 and 59.43548 seconds**. Completion timestamps and measured middleware durations imply at least **31.99632 seconds of common HTTP overlap**, allowing the worst case one-second timestamp-format uncertainty. This demonstrates overlapping in-flight HTTP requests, not parallel model computation, throughput, sustained load capacity or unseen correctness. POST matching uses unique workspace/time-window records; DTO `retrieval_trace.request_id` is the persisted query UUID by connected_query.py, not middleware's separate correlation UUID.

The original executed script asserts full POST/GET JSON equality. A separate raw saved-GET body was not retained. Independently confirmed exact persisted DTO equality plus matching GET200 logs corroborate the history claim; this limitation is explicit rather than treating producer success flags alone as proof.

No actionable finding within this three-positive-case engineering scope. Mixed round423 was not inspected.

## Preservation, commands and boundaries

`hashes-before.json` and `hashes-after.json` preserve **266/266 input paths**, including all 232 current web build inputs. All **185 API source paths** remain equal to the frozen source30 comparison. Retained API-restart log prefix: 14,271 bytes, SHA `388efa0cd429ef87bbc8dac808334fa6551f6d3bc225beef0c7688c43d61131f`. That prefix remains exact; the active log subsequently grew to 17,181 bytes. No whole-active-log immutability claim is made. `offline-result.json`, `http-result.json`, `guard-result.json` and `preservation-result.json` contain the independently checked facts; exact verification commands/exits and corrected review-harness errors are recorded in `commands-and-results.json`.

Only new `Q/final-portable-engineering-independent-v422/` files were created. No W/old Q edits, API/model/browser/server/CIM/build/install/seeding actions, credentials or private-manifest reads. SQL used URI `mode=ro`, `PRAGMA query_only=ON` and a transaction; only queries/conversations/documents/document_versions were read. The live database was not opened as immutable and was not hashed as a frozen file. No opportunity/experiment/cash record was involved; cash unknown. Shared handoff remains with the parent integrator under the new-Q-only scope.

Next owner: parent may use these two engineering verdicts within their stated limits and independently review later mixed/outage evidence after closure. **QUIET.**
