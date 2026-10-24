# Qualified-parts repair recheck and added-guard review

Read-only review, 2026-10-24, isolated delivery-worktree. Application frozen during development-qualified-parts-v1 grid. No source/profile/corpus/service changes, quality evaluation, performance measurement, blind authoring, other-agent inventory or original-checkout interaction. Source identity retained in reviewed-qualified-parts-source-hashes.json. Parent acknowledged findings and will preserve current grid before any later repair; no quality-success claim.

## Original five regressions independently repaired

`<original>/.venv/Scripts/python.exe -m pytest <code-review>/test_independent_question_boundaries.py -q -s -p no:cacheprovider`

Exit0, **5 passed in 2.37s**. Log independent-boundaries-repaired.log. The preceding middle-pronoun/global-anchor bug, night/day qualifier loss, insured-value authority rejection, monetary hourly-rate rejection, and direct prior-sentence anaphora rejection all pass their original assertions unchanged. PYTHONPATH resolves isolated worktree apps/api; original venv supplies interpreter only; bytecode writes disabled.

## New material findings

### P2/high confidence — Nominal-list parser loses shared postposed subject qualifier

Location reader_questions.py:43-57,71-83,87-89.

`Give me the opening time and the closing time for Orion.` becomes `What is the opening time?` with empty anchors, plus `What is the closing time for Orion?`. The first part is identical for Vela, losing the explicitly requested entity before inference. An independent _parts model-boundary probe with only `Vela opens at ten.` and `Orion closes at seventeen.` returns both spans, treating Vela opening evidence as completing the missing Orion opening request. This is deterministic loss of request scope, not an unauthorized-data exposure or evidence of general model behavior.

Retain the shared qualified subject in each applicable nominal part. Do not fix this by globally requiring every later entity on every explicit interrogative; that would reintroduce the preceding future-anchor bug. Unrecognized grammar needs a truthful bounded policy.

### P2/high confidence — Temporal-token guards reject valid responsible parties and ordered procedures

Location reader_questions.py:108-121.

`Who approves Orion access?` with selected answer `The Monday shift supervisor` is rejected as schedule_is_not_a_responsible_party. A weekday can qualify a valid responsible party. Likewise, the complete valid procedure `At 09:00, isolate the line, inspect the valve, then record the result.` is rejected as appointment_is_not_a_procedure for a steps question. Presence of a clock in a genuine procedure does not turn it into an appointment-only answer.

Restrict a surface mismatch check to decisive temporal-only answers; preserve person/team phrases and actual instructions containing time qualifiers. Do not claim entity/attribute entailment from token presence.

### P2/high confidence — Currency guard still treats nonquantity what-questions as amount requests

Location reader_questions.py:122-130.

`What condition changes the price?` is supported by `Stock availability changes the price.` with selected answer `Stock availability`. The guard rejects it as currency_evidence_missing because it sees what plus price, although the requested answer is a cause/condition. The earlier who-question repair did not narrow the rule to monetary-quantity requests.

Only apply amount evidence restrictions when the request actually asks for an amount. Preserve ordinary policy/cause/authority questions mentioning a fee or price.

## Exact independent evidence

`<original>/.venv/Scripts/python.exe -m pytest <code-review>/test_independent_added_guard_boundaries.py -q -s -p no:cacheprovider`

First 4 added assertions: exit1, **4 failed in 3.33s**, independent-added-guards-red.log. Added a fifth assertion at the model boundary for the same nominal scope-loss issue: exit1, **5 failed in 1.93s**, independent-added-guards-red-v2.log. Source tests retained in test_independent_added_guard_boundaries.py. No live model, HTTP or services used. These deliberately failing code-boundary probes are not quality-grid measurements. No further scope expansion or tests after parent's freeze instruction.

The existing before-cover conflict check, full-part three-citation cover and recursive nested raw-span sanitation remain as inspected previously. These findings concern relevance/completeness and false refusals; source spans continue to be copied rather than factually generated. No completion verdict or later unseen-validation claim follows from the passing five original tests. Parent owns next repair wave and any fresh development measurement after source changes.

