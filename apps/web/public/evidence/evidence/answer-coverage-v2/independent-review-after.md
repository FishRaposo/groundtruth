# GroundTruth bounded review — sealed evidence and privacy mitigation addendum

Read-only review on 2026-10-24 of isolated worktree C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024/delivery-worktree. No source, application, blind corpus, scoring, or public evidence edits by reviewer. The original checkout belongs to an active other editor and was not touched after parent directed isolation.

## Verdicts

Contract/privacy mitigation: **confirmed within the exercised boundary**. The P2 candidate-metadata revocation finding in review-pre-mitigation.md is repaired by the isolated source_access patch. No remaining material defect found in this bounded patch review. The patch reauthorizes all cited and traced document identities, requires every saved reader candidate chunk to have a valid immutable trace/document mapping, fails closed on missing/malformed mapping, and preserves raw snapshots while redacting presentation. Its conservative policy withholds the entire answer if any retained candidate becomes inaccessible. Existing error identity, cancellation, spans and multiple-document behavior remain exercised.

Whole answer-coverage acceptance: **failed**. Sealed reranked candidate has55/120 correct answerable cases and77/80 correct negatives; required114/120 and80/80 are unmet. Baseline is30/120 and68/80. Candidate keyword52/120, vector/hybrid/reranked55/120; all candidate negative totals77/80. All four methods retained. The original final connected browser acceptance also failed all three viewports on supported rollback false refusal. Neither a diagnostic thin slice nor the privacy repair closes those failures.

Evidence protocol: **qualified**. first-comparison-seal.json truthfully records source-after FAILED from another editor's six version/pagination writes after APIs started without reload. Process-behavior probes and unchanged QA/scorer support attribution, but this reviewer did not re-run those live process probes and does not convert the failed on-disk source-after gate into a pass. First results are retained; no repeat is called unseen.

## Independent sealed-artifact checks

Parent first confirmed both complete reports sealed before granting blind-result access. Only then did this reviewer read/re-score their portable observed evidence.

- `python scripts/verify_answer_coverage_delivery.py --baseline docs/evidence/answer-coverage-v2/first-baseline-canonical-v3.json --candidate docs/evidence/answer-coverage-v2/first-candidate-canonical-v3.json --corpus-dir apps/api/app/portfolio/assets/coverage-blind-canonical-v3`: **exit1**, correctly reports failed gate; independently re-scores800 rows per arm against canonical70-document corpus. Both report summaries match all recomputed fields. Zero recorded execution errors, unauthorized source exposures, citation-integrity failures or candidate span-integrity failures. Log sealed-portable-audit.log.
- `python <review>/audit_sealed_observations.py`: **exit0**. Seal SHA25670fdc603fb911e714e480a1ab9c87e9f9fff521224a52fcf3f0fd81bc8b28be4. Raw report hashes, sidecars and seal's freeze/binding/qualification hashes all match. Reports contain all4 methods ×200 rows. Every nonempty answer is byte-exact assembly of the recorded quotes (baseline168 responses) or selected spans (candidate306 responses), plus fixed prefix/citation labels: zero assembly mismatches. Log sealed-observations-audit.log.
- `python <review>/check_postprivacy_scope.py`: **exit0**. Imports resolve to isolated worktree apps/api, not original editable checkout.134/135 frozen raw source files still match; sole changed frozen source is apps/api/app/services/connected_query.py (postpatch SHA25615897711352e4a273d4cce4a8a315ae63a4e659e6973355cc409bf3cb981fddc). Log postprivacy-scope.log.

All Python commands use original checkout's .venv interpreter with PYTHONPATH explicitly set to isolated worktree apps/api and PYTHONDONTWRITEBYTECODE=1. No HTTP measurement or model inference was rerun.

## Independent postpatch behavioral check

Command from isolated worktree, normal local permissions due previously reproduced Windows pytest tmp ACL limitation:

`<original>/.venv/Scripts/python.exe -m pytest <review>/test_revocation_surfaces.py <review>/test_independent_boundaries.py::test_revocation_of_null_candidate_restricts_its_saved_reader_evidence apps/api/tests/test_answer_reader.py apps/api/tests/test_reader_evidence_access.py -q -s -p no:cacheprovider -o asyncio_mode=auto --basetemp <review>/postprivacy-tests-tmp`

**Exit0,52 passed in53.52s**; postprivacy-tests.log. Real isolated SQLite/upload/query/presentation paths; only external reader inference boundary is substituted. No listening service or original database. Own four revocation assertions that failed before patch now pass for refused/mixed saved history, conversation, and revocation during refused SSE. Scratch diagnostic prints were made None-safe after redaction, with behavioral assertions unchanged; original failing files retained as *.preprivacy.py. Existing reader regression tests cover configured-reader errors as errors rather than refusals, safe persisted model identity, cancellation, concurrency, Unicode/window offsets and real multiple-document support. Parent-added privacy tests cover conflicting/null/mixed candidates and missing/malformed saved mappings, plus recent-memory assertions. `git diff --check -- apps/api/app/services/connected_query.py` exits0.

## Scorer limitation, bounded by observed-answer audit

The frozen scorer's request-specific literal fact/order checks plus source-relative offset checks do not alone establish that every answer character came from its selected spans. An independent forged-response probe passes required fact substrings while adding an invented instruction and recording an unrelated exact source span. This remains a limitation, not a claim of fabricated prose in measured outputs. The independent literal assembly audit above found zero such mismatches in all474 emitted observed answers across both arms. No frozen scorer was changed and no failed measurement was replaced.

## Scope and remaining action

This review does not prove human agreement, general entailment, hosted CI, production capacity, PostgreSQL/Redis or new postpatch model quality. Full prefreeze Python log was inspected (421 passed/1 skip/66% coverage); this reviewer reran only the recorded targeted suites. Browser claims rely on inspected final packet with retained failure, not a fresh independent browser run. No commercial messages/publication/receipt; cash unknown; GT-01–GT-07/FTH-016 context only. Parent owns final documentation/integration and should retain failed acceptance, source-after qualification, independent privacy repair attribution, and the rule that exposed cases cannot earn a later unseen claim.
