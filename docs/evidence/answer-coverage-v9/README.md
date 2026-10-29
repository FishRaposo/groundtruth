# Post-seal scope-directive repair and functional verification

Observed locally on2026-10-24. **Answer-quality acceptance remains OPEN.** The
[sealed fresh comparison](../answer-coverage-v8/README.md) remains69/120 correct
answers and62/80 correct negatives for its frozen candidate, versus39/120 and75/80
for the baseline. Required:114/120, improvement over baseline and80/80. No new
unseen corpus or full-corpus quality measurement is claimed here.

## Concrete repair

The independent failed-trial audit reproduced an entity-parser error: the
sentence-head instruction “Limit the answer to the document titled…” became a
named subject. A source without the word “Limit” was therefore rejected before
the reader ran. The repair recognizes this bounded instruction prefix while
retaining its document-title anchor. Genuine names such as “Limit fixture” and
“Limit answer register” remain constraints. Original questions, explicit document
filters, authorization, current-source checks and multi-document extraction are
unchanged. Selection metadata now records `reader-parts-v14`.

The [retained regression sequence](engineering-commands-and-results.zip) includes
the initial failures, an incomplete uppercase repair and the final13 passing
tests. Independent review retained its22-pass/two-failure intermediate result;
the [final recheck](independent-scope-review.zip) passes those24 assertions,
21 additional case/title controls and the copied13 tests. This finite parser
check is not general entity recognition, semantic entailment or answer validity.

The [real HTTP regression](focused-exposed-http.zip) runs the five already
exposed, explicitly filtered questions against a new SQLite backup. All five
pass their authored answer/evidence contracts with default reranking, cached
semantic embeddings, CPU RoBERTa and unchanged threshold4. No negative cases
were measured. The161 [source fingerprints](current-source.json) before/after
match current files; original database bytes remain unchanged. **Do not add five
to the sealed score, infer74/120, infer better refusals or describe these cases
as unseen.** The archive also retains an earlier source version separately.

## Final-source engineering results

| Check | Observed result |
| --- | --- |
| Full API pytest |633 passed, one live-infrastructure skip|
| Evaluation/tool tests |20 passed|
| Combined statement coverage |5005/7303,68.53347939203067%;69% displayed|
| Ruff / formatting / configured Pyright |pass /231 files /zero errors|
| Frontend units / lint / TypeScript |72 passed /pass /pass|
| Real connected / reader-diagnostic production journeys |3/3 and3/3|
| Same-database restart |saved answer/source hashes and document/chunk/query counts unchanged|
| Separate offline production suite |21 reported passes: three zero-network journeys, ten actual axe scans, eight existing early returns|
| Source/wheel build / wheel closure |pass;137 packaged Python modules match current source|
| Fresh outside-checkout base installation |actual import/upload/query/history pass without model/PDF extras|
| Optional installed-reader environment |updated only GroundTruth in the previously fresh v14 graph; both cached MiniLM and RoBERTa API probes pass|
| Original golden / historical evidence |pass; historical source explicitly checked at `e19006c`|

Exact logs, coverage JSON and host-specific runners are in the
[engineering archive](engineering-commands-and-results.zip). The initial packaging
command named a nonexistent checker and exited2; the build itself succeeded.
The corrected `scripts/check_wheel_contents.py` passes. The historical verifier
first rejected changed working source, then passes with
`--source-revision e19006c9e8f1a11ef4930e24ed88128e765b6bf5`. Both unsuccessful
invocations are preserved. Earlier626-test/source observations predate the
final uppercase grammar and do not substitute for the final633-test run.

Commands use the declared test settings from the earlier verification record,
`PYTHONPATH=apps/api`, unique pytest temporary paths and the configured Python
interpreter. Main gates are `pytest apps/api/tests`, `pytest scripts/tests`,
`ruff check`, `ruff format --check`, `pyright --pythonpath`, frontend
`npm test -- --maxWorkers=2`, `npm run lint` and `tsc --noEmit`. Packaging uses
`python -m build apps/api`, `scripts/check_wheel_contents.py` and
`scripts/verify_isolated_wheel.py`. Archived runners preserve the actual dedicated
API commands, cleared provider credentials, offline settings and cleanup.

The production frontend is the unchanged `.next-v14` build completed before
browser execution. No frontend source changed after that build; no build overlaps
browser checks. Dedicated APIs8402/8410 and frontend3506 use disposable data,
actual requests and no successful API mocks. Viewports:390×844,768×1024,1440×900.
Browser timings are functional observations, not performance measurements.

The [browser archive](connected-browser-and-restart.zip) preserves all screenshots
and restart/error records. Inspected: [completed answer](diagnostic-answer-1440.png),
[mobile exact source](diagnostic-source-390.png),
[tablet document restoration](connected-documents-768.png). The archived general
answer screenshot captures an in-flight stream; it is not a terminal-state claim.
Checks cover focus, keyboard use, navigation, source highlighting, reloads,
identity switching, truthful reader/outage errors, Retry and explicit sample entry.

The [wheel binding](wheel-binding.json) distinguishes the fresh base install from
reuse of the previously fresh optional dependency graph. Both optional reader
smokes use deterministic embeddings and threshold0 for installation/functionality;
the focused HTTP regression and frozen quality comparison use local semantic
embeddings and threshold4. Those probe outcomes are not interchangeable.

## Preservation and next work

The [preservation record](preservation.json) verifies all16 original evidence
hashes,21 earlier blind-v4 files and45 fresh blind-v5 evidence files byte-for-byte
against their recorded commits. Current source snapshots are in
[current-source.zip](current-source.zip); settings/results and qualifications are
in [observations.json](observations.json). No original report, source snapshot,
label or failed gate is overwritten. The owner8400/3505 instance and original
checkout remain unpromoted; the other editor's work is preserved.

The failed trial still contains44 false refusals, seven wrong/incomplete positive
answers and18 answered negatives. High retrieval recall does not solve missing
second-document facts, wrong-attribute support or conflict relevance. The next
development cycle must address those mechanisms with separate development tests,
not relax negative-case gates or retune now-exposed labels. Only after a stronger
source/settings/scorer freeze may a new clean author and independent label reviewer
produce another unseen200. Seal both baseline/candidate first complete reports
before failure inspection. This repair has no new quality acceptance score.

All labels are synthetic and agent-authored; no human/model-quality validation is
claimed. PostgreSQL/Redis/indexed-scale local acceptance remains deferred. No WSL,
Docker, paid provider, generative model, publication, external action or sibling
change occurred. No hosted execution was reverified here.

The [independent final delivery audit](independent-delivery-audit.zip) verifies
all five original archive hashes,161 stable source bindings, the actual wheel
SHA/137 modules, five saved-row scores, recorded gate/browser counts and their
qualifications. It inspects the three linked screenshots and confirms original
16/earlier21/new45 evidence bytes remain unchanged. Its16-key exact scan finds
zero matches across354 expanded payloads. This is artifact/source inspection,
not another test/model/API run or quality pass. The initial direct-wheel read
permission limit and its successful byte-identical-copy resolution are retained.

The scoped local-link check reports197 references across14 changed/current
files with no new missing link; one inherited portfolio-context link resolves
from the owner clone rather than this worktree layout. Two older unrelated root
handoff ARIA link typos remain outside the new section. The canonical operation
overview guard passes. The broad root validator/unit fixture recursively copies
or traverses independent clones/generated trees, so it was not presented as a
passing workspace-wide check. Local owner8400/3505 health still responds200;
owned acceptance8401/8402/8410 APIs are stopped. Frontend3506 remains available,
without promoting the failed candidate or replacing the owner's review backend.
