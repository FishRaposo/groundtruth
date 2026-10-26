# D481 single diagnostic outage run — CLOSED0 / QUIET

2026-10-26. The single authorized diagnostic run passed the unchanged protocol.
The old466 four unexpected request failures did not reproduce and remain
unexplained. No classification, assertion, app or scorer change was made; this
is not evidence that the old root cause was fixed. User quality work remains OPEN.

8401/3506 were explicitly released to root after coordinator cleanup and a
separate reviewed listener check returned both empty. No further port/network
operation occurred after that release.

## Exact preparation and ownership scope

NEW481 browser differs from466 only by adding existing sanitized state.issues,
state.apiFailures, state.apiResponses and state.requests to catch-time contexts.
All classification/expectation/assertion code is text-identical. The coordinator
diff is only its new481 public API record path; wrapper diff is only new481
command/process-record suffixes. Preparation source reads/writes explicitly use UTF-8. Original
two loading ellipses, snapshot/key matching and PID/cfg/binary/birth/mtime/full-argv/
listener rechecks remain unchanged. The venv binding is identical.

Before launch,1758 readable regular files under old466 were hashed, including
all source, actual failure JSON/logs/PNGs and staging files. After closure the
same file set and every hash match (`preservation-before.json` / `-after.json`).
No old failure output was changed or replaced.

Reviewed listener queries confirmed8401/3506 free. The owned481 bootstrap API
passed the complete central346 pinned readiness/runtime gate. During the initial
guarded stop, recorded venv launcher22260 had the strict known immediate base
serving child15444. Only15444 was explicitly stopped; no initial tree/name/port
fallback was used. Launcher exited naturally. The bootstrap wrapper session
ended−1 due that authorized forced child stop, not an application gate failure.
The coordinator restarted the API once, recorded its actual binding, validated
runtime again, and cleaned the newly owned API/frontend trees through unchanged
guards. Browser/coordinator exit0; cleanup says both ports closed. Independent
post-run listener query also returned8401=[] and3506=[] before release.

## Actual recorded results

All three390/768/1440 contexts completed local saved-read Retry recovery without
reload or a new query POST, provider Retry, separate persistence reload, all six
routes, explicit sample and cross-owner denial/restore. All three recovered saved
DTOs equal their respective baseline DTOs, not just answer text.36 PNGs and all
three final browser observations exist. `browser-done.json` and result.json exist;
no browser-error.json or catch occurred. The passing run therefore did not need
the new catch diagnostic arrays; existing final per-context observations retain
issues, request_failures and api_responses.

Actual failure events in this run:

| Phase | Error | Paths | Count |
|---|---|---|---:|
| outage | net::ERR_CONNECTION_REFUSED | saved query GET and identity/documents/queries/conversations/health, each viewport |18|
| retry-down | net::ERR_CONNECTION_REFUSED | each viewport's same saved query GET |3|
| identity-connect | net::ERR_ABORTED | /api/queries,768 and1440 only |2|

All23 were already classified expected by the unchanged harness. Each context
also recorded10 already-expected console issues and zero unexpected issues;
unexpected request failures are0 at every viewport. Full safe phase/path entries
are in diagnostic-result.json and final-analysis.log.

The21 connection-refused events are concrete real transport failures during the
intentional guarded API outage, including each local Retry, followed by actual
recovery GET200 and identical recorded DTOs. The two ERR_ABORTED query-list reads
occur during identity-connect. PortfolioProvider clear/invalidateRefresh and
ConnectedClient.close explicitly abort obsolete refresh clients during that
transition; subsequent identity/workspace/source/restore assertions pass. These
two observed aborts are consistent with that existing cancellation behavior and
already covered by the original predicate. They are not evidence identifying
old466's four unseen failures: old466 lacks their paths/types/phases and the new
run cannot reconstruct them.

No classification repair is justified by this one pass. Keep the added diagnostic
capture for a future independently authorized reproduction; do not blanket-allow
aborts, suppress transport failures, erase466 or call its root cause repaired.
If it recurs, origin/method/request-generation/timing metadata may be needed to
distinguish same-path requests; current failure records retain phase/path/type but
not request IDs/timestamps. No extra run was attempted.

## Commands, artifacts and hashes

Working directory:
`C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024/delivery-worktree`.

1. `.venv/Scripts/python.exe -B ../quality-v6/typed-restart-outage-v481/prepare.py`
   — exit0; diagnostic-only source diff and original preservation.
2. `node --check ../quality-v6/typed-restart-outage-v481/browser.mjs` — exit0.
3. Pure import of unchanged coordinator listener_pids for8401/3506 — exit0,
   ports-before.json. No owner8400/3505 or DEV8402 inspection/action.
4. `.venv/Scripts/python.exe -B ../quality-v6/typed_runtime_recovery_v481.py serve --margin 2`
   — owned initial API startup; later controlled stop ends wrapper−1.
5. Unchanged wait_ready(API+'/api/health/ready') + check_runtime — exit0,
   initial-readiness.json/readiness.log.
6. With GROUNDTRUTH_SEED_MANIFEST set only for the execution process to the fixed
   restricted378 seed path:
   `.venv/Scripts/python.exe -B ../quality-v6/typed-restart-outage-v481/coordinator.py --execute --frontend-build apps/web/.next-context-v430 --expected-api-record-sha256 <actual481-record-SHA256> --reviews-complete --stop-recorded-root-api --run-label first`
   — exit0, execute.log and runs/first/. Single execution only.
7. Reviewed post-run listener queries — exit0, ports-after.json;
   `.venv/Scripts/python.exe -B ../quality-v6/typed-restart-outage-v481/close_evidence.py`
   — exit0, original preservation and full saved-result checks, no network.

Startup/readiness/execution used tool-approved escalation for the explicitly
authorized disposable services and guarded stop; no approval rejection. The
private seed was read only by the unchanged browser at execution. Keys/headers
were neither printed nor recorded; the unchanged browser credential scans pass.
No private-key table/seed manual read, new seed/identity/document, app/scorer/model
edit, fresh-blind/corpus/author/evaluation operation or owner service action.

Source SHA256 values:

- coordinator481 `26ea53dcd6448081e13078544a38820884f5161c67f1bf5c00fd1c98cb4d00c2`
- browser481 `acc8db5b1ba359ee80b0fb36bf003673b0c9653e5ea197f9c8850bea336ae53a`
- wrapper481 `72502d71013cccf3fd7c8aa2481876edec5b39cf9b94923e2af7d3d12bdaef6b`
- venv binding `91bc41a78f9eda227e7b23dea7e1bfebe540e2b25b8d8fdd98412a99f66c22eb`

artifact-hashes.json binds public preparation/run outputs (including all36 PNGs),
the new wrapper and public command/PID records. Staging/node_modules are excluded
from this public-output manifest; build430/preflight bindings are retained.
It excludes its own hash. No screenshot/DTO independent review is claimed here;
root can commission that separately against these frozen observations.

Root owns subsequent work and quality gates. This current observation is valid
bounded engineering evidence; old466 remains an unresolved failed observation.
Sources checked locally2026-10-26; FTH-016 support, cash unknown; no shared
handoff/ledger edit. All owned processes closed;8401/3506 released. QUIET.
