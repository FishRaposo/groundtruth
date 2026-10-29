# Independent cancellation/preparation repair review (2026-10-24)

Two material findings remain. Existing active-SELECT lock reproduction and ordinary transport/yield cleanup tests now pass; this is not a release or model-quality verdict.

## 1. Direct cancellation can interrupt the last response finalizer

Production references: `apps/api/app/services/query_stream.py:20-30`, specifically the finalizer await at30 inside AnyIO CancelScope; `apps/api/app/api/queries.py:309-314` finalization closure. AnyIO cancellation shielding does not protect an await against a direct `asyncio.Task.cancel()`.

Reproducer: `test_independent_cancellation_repair.py::test_direct_cancellation_during_response_finalizer_saves_status`. Real disposable SQLite/stream_query response, ASGI2.4 send raises OSError before the generator starts, response finally calls fail_query. Scratch seam pauses fail_query before its first write; a direct cancel of that response task interrupts the finalizer. After releasing the seam and awaiting the CancelledError, the DB record remains outcome `processing` (answer null), rather than `interrupted`. There is no later owner for that finalizer. This differs from an ordinary AnyIO disconnect, which the new shield handles.

Expected scope: drain/own final cleanup even if the response task is directly canceled while cleaning up; propagate cancellation after cleanup, as complete_read already does for in-flight reads. Keep completed/error/refused terminal outcomes intact and avoid broad CPU/model/network shielding. The scratch pause only makes a real awaited finalizer boundary deterministic. Do not treat replacing the assertion with processing or relying on a later GC finalization as a repair.

## 2. Possessive elapsed time can borrow a start clock

Production references: `apps/api/app/services/reader_support.py:16-23` asks_elapsed does not include explicit `elapsed time`; the broadened `temporal_question` pattern at33-35 now accepts any possessive attribute ending `time`. `reader_questions.py:159-166` protects elapsed requests only when asks_elapsed matches.

Exact seam: `mismatch_reason('Regarding Nova, What is its elapsed time?', 'Nova viewing starts at 14:20.', 23, 28)` returns None. The expected existing start-clock/elapsed-duration boundary is `start_clock_is_not_elapsed_duration`. The same viewing-time form correctly accepts the clock; ordered-procedure normalization and shared postposed qualified location controls pass. Retained `test_independent_preparation.py::test_possessive_elapsed_time_does_not_borrow_start_clock`.

This is a concrete surface-rejection regression caused by the broadened time classification, not proof a model generated this answer in a grid, and not a request to expand arbitrary grammar/entailment rules. Preserve the legitimate viewing-time clock control while recognizing explicit elapsed intent.

## What passed

- Original uninstrumented ASGI2.3 disconnect regression now passes.
- Owned authorization-read, generator-close/yield, ASGI2.4 send-start/token/done tests pass.
- Independent repeated direct cancellation drains an unfinished read, including a read that later raises, without canceling/orphaning the child or masking the outer CancelledError.
- Independent level-triggered AnyIO cancellation drains the read before returning.
- Independent real native SQLite SELECT pause, twice-canceled caller, release, then interrupted-status commit passes; raw cursor read finishes before cleanup touches its session.
- Independent full middleware ASGI2.4 send errors at start/token/citations/done persist interrupted before completion or completed after final application commit as designed.
- Existing preparation7 plus independent explicit ordered negation/qualifiers, shared qualified location and possessive viewing clock controls pass.

## Commands and evidence

Original interpreter `C:/Projects/operation-fan-the-hammer/portfolio/groundtruth/.venv/Scripts/python.exe`; workdir isolated `delivery-worktree/apps/api`; explicit isolated PYTHONPATH; PYTHONDONTWRITEBYTECODE=1; legacy import defaults with ANSWER_SELECTION_MODE=lexical, blank OPENAI_API_KEY, offline HF/Transformers. Fixture-only deterministic/extractive modes and dedicated scratch SQLite. No model/server/ownerDB.

1. `python -m pytest <this-dir>/test_independent_cancellation_repair.py tests/test_query_cancellation.py tests/test_connected_contract.py::test_stream_disconnect_does_not_save_completed_answer tests/test_reader_preparation_boundaries.py -c pyproject.toml -q --basetemp=<this-dir>/probe-temp-1 -o cache_dir=<this-dir>/cache`
   Exit1: **1 failed,21 passed in7.20s**, exact output `probes-1.log`. Only independent direct-cancel-during-finalizer assertion failed.
2. `python -m pytest <this-dir>/test_independent_preparation.py -c pyproject.toml -q -p no:cacheprovider`
   Exit1: **1 failed,4 passed in0.90s**, exact output `preparation-1.log`. Only explicit possessive elapsed-time assertion failed.

Read-only review included db/cancellation.py, query_stream.py, API closures, connected read wrappers, SQLite retrieval read wrapper, nominal list parser, ordered QA normalization, temporal support classifier, and corresponding tests. Source hash capture attempted before the first run used paths relative to the wrong workdir and emitted read errors; no valid pre-run hash claim is made. Correct `source-observed-during.json` and `source-after.json` contain the eight inspected source SHA256s and match exactly. No reviewer app/test/evidence/source writes. All writes confined to this scratch directory.

Limits: focused disposable-SQLite and in-process ASGI checks; no full suite, model/grid/new blind/latency measurements, PostgreSQL or arbitrary cancellation schedule proof. complete_read intentionally waits for reads to finish, so it cannot by itself promise bounded cancellation latency for a genuinely stalled driver. Raw support checks remain bounded rejection heuristics rather than general entailment. No more grammar scope expansion performed.

