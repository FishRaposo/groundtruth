# Final bounded cancellation/preparation recheck (2026-10-24)

No remaining material defect found within this repair's inspected and exercised boundaries. The two exact retained independent assertions from `review.md` now pass. Prior RED evidence is preserved and the earlier review is not rewritten.

`complete_cleanup` and `complete_read` share `_complete`; it owns the child operation through direct/repeated asyncio cancellation and level-triggered AnyIO cancellation, observes a child failure, and propagates the caller cancellation after draining. QueryStreamingResponse now closes its iterator and runs its finalizer through that cleanup boundary before the request DB lifetime ends. Its scope shields DB read/finalization operations, not model/CPU/provider/network work. The inspected API closure keeps already persisted completed/refused/error outcomes terminal. Explicit `elapsed time` now triggers the existing duration guard; explicitly labeled elapsed-clock source text and legitimate viewing-clock requests remain accepted.

## Exact command and result

Original GroundTruth venv interpreter, isolated delivery-worktree/apps/api PYTHONPATH, PYTHONDONTWRITEBYTECODE=1, offline HF/Transformers, blank provider key, legacy import defaults and ANSWER_SELECTION_MODE=lexical. Fixtures use deterministic/extractive generation and dedicated scratch SQLite, no model or live server/ownerDB.

`python -m pytest <this-dir>/test_independent_cancellation_repair.py <this-dir>/test_independent_preparation.py tests/test_query_cancellation.py tests/test_connected_contract.py::test_stream_disconnect_does_not_save_completed_answer tests/test_reader_preparation_boundaries.py -c pyproject.toml -q --basetemp=<this-dir>/recheck-temp-1 -o cache_dir=<this-dir>/cache`

Exit0: **30 passed in6.81s** (`recheck-1.log`). Nine independent cancellation cases, five independent preparation controls, six owned cancellation cases, nine owned preparation cases, and the original ASGI2.3 disconnect case. These cover the original active-native-SELECT lock, twice-canceled caller, child read failure without orphan/cancel masking, level-triggered AnyIO read cancellation, iterator close at yield, direct cancellation during finalization, full middleware ASGI2.4 send failures at start/token/citations/done, persisted completed outcome after execution, ordered restrictions, shared qualified location, viewing clock, elapsed-time wrong-clock rejection and explicit elapsed-clock acceptance.

`recheck-source-before.json` and `recheck-source-after.json` record identical SHA256s for eight inspected application files. All reviewer writes remain scratch-only; no application/repository tests/evidence/assets/services changed by reviewer.

Remaining limits: targeted disposable SQLite and in-process ASGI evidence only. No full suite/model/grid/new blind/latency/performance/release conclusion, PostgreSQL validation, arbitrary transport/cancellation schedule proof, or general answer entailment guarantee. Draining a genuinely stalled DB operation can delay cancellation until the operation returns; no bounded-latency claim was tested. The parent's older full-v5 run predates these latest changes and is not certified by this focused review. Comparative model measurements remain a separate pending gate.
