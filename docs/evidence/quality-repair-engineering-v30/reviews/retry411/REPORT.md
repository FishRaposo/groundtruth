# F411 independent saved-answer Retry review

2026-10-26. Bounded result: no actionable finding in root407's saved GET Retry repair. This is source review plus isolated mocked unit verification, not browser outage acceptance or overall readiness.

## Evidence and behavior

Compared current `apps/web/src/components/PortfolioChat.tsx` with preserved root407 `PortfolioChat-before.tsx` (`component.diff`). The change records the failed saved ID only inside the current activity generation's non-abort failure branch. Retry calls `load(id)`, which encodes the ID, constructs an owned ConnectedClient with the current key/epoch, cancels any preceding active request, clears the prior failed target, and only publishes current-generation results/errors. Cleanup clears `activeRequest` only when it still owns that slot. Cancellation increments the generation and aborts that owned request; late failure cannot recreate the failed target.

Context invalidation clears the ref/error on source, provider client, epoch and conversation changes. PortfolioProvider memoizes its ConnectedClient on key/epoch, so a real key change also changes the invalidation dependency. Starting another saved load, asking a new question, inspecting a source, and creating a conversation clear the failed saved target. New-conversation draft and stale-creation behavior retain their existing guards. API authorization/identity behavior was not modified: all 185 API source paths still hash-identically to the prior frozen source30 comparison.

Fresh exact supplied regression: **8/8 PASS**, 3.48s. Fresh independent probes: **9/9 PASS**, 1.86s. All fetches are stubbed, including the fallback unexpected-network path; tests import the actual W component and actual ConnectedClient while mocking PortfolioProvider. Cases cover:

- A failed ID containing slash, space, question mark, hash and Unicode is reissued with the exact encoded URL and current API-key header; no provider refresh replaces that GET.
- Pending Retry owns an abortable request. Cancellation followed by a late rejected GET cannot select a result or restore the saved target.
- An old identity's late rejected GET cannot replace the new identity's failure or retry ID; the successful retry uses the new key and ID.
- Epoch, conversation and source changes drop the old target.
- A subsequent POST failure, source-inspection failure or conversation-creation failure cannot accidentally retry the earlier saved ID.

Other local error Retry actions still invoke provider refresh. This review does **not** claim POST or source-inspection replay was implemented. Their existing refresh behavior is explicitly tested.

## Recorded regression and tool limits

Root407 `red.log` fails the new saved Retry assertion because fetch remained at one call; seven other tests passed. Its `green-final.log` records eight passes. Root408 records 862 unit passes and lint exit 0, but its original type exit was 2 because the test supplied unsupported `exact` to `getByRole`. Current supplied test removes that option; root407 final lint/types logs are empty and parent reports their corrected exit 0. Those historical statuses are distinct from the fresh 17 passing tests here; full units/build remain the parent's next verification.

Review harness startup attempts are retained transparently: runner config loading failed with `require is not defined`; native loading initially found no files because Windows backslashes were used in absolute include globs; corrected native loading then hit sandbox `spawn EPERM` for fork workers. None executed tests. Native config with thread workers ran both final suites successfully. Only the new Q configuration was adjusted.

## Preservation and scope

`hashes-before.json` and `hashes-after.json` preserve 12/12 input files identically. Current component SHA-256: `09f7f0a529f7329de30e0f57d3e70c56013bd914307ae5e3c3cc2a0a54481042`. Current supplied lifecycle test: `a2bca165fa4cee8c64e87a18b1bc83398f9e28c754866865bd43914dd3b0c8b3`. Original component: `6e4d552c4493b5c67d71b0f7e97825449a2ce5b23b9d4f242d95c620e8fcc707`.

Changed paths are confined to new `Q/saved-retry-independent-v411/` (review scripts, independent tests/config, logs, results, hash inventories, this report, and isolated `.vite` cache). No W or old Q edits. No API requests, browser, server, model, build, install or seeding actions. No credentials or private manifests read. `commands-and-results.json` records exact verification commands/exits; `preservation-result.json` summarizes both suites and preservation. No opportunity/experiment/cash records were involved; cash status unknown. Shared handoff files were left to the parent integrator under this new-Q-only scope.

Next owner: parent runs final full frontend units/build, then the actual three-viewport saved-read outage proof. That live acceptance remains pending and is not inferred from these unit results. **QUIET.**
