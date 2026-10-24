# Continued answer-coverage development evidence

These are preserved development observations, **not an unseen acceptance pass**.
The [continuation record](../../answer-coverage-development-v3.md) explains scope,
source authorship, engineering limits and pending acceptance. Original failed and
golden evidence remains in its earlier directories, unchanged.

| Artifact | Meaning |
| --- | --- |
| [Author inputs](development-author-inputs.zip) | Exact source-author corpus/profile/manifest, independent label review and input contract; inner file hashes included |
| [Initial measurements](initial-development-observations.zip) | First threshold-0 failure and complete seven-threshold MiniLM development grid, raw responses, hashes and source fingerprints |
| [Interrupted RoBERTa observation](interrupted-roberta-observation.zip) | One complete threshold plus explicit interruption qualification, source-at-stop and model fingerprints; remaining grid did not complete |
| [Complete pinned RoBERTa grid](roberta-pinned-v3-observations.zip) | Seven completed thresholds with unchanged source/model hashes, before the later support-binding repair; quality failed |
| [Support-bound RoBERTa grid](roberta-binding-v4-observations.zip) | Seven fixed-source thresholds; best eligible result 36/48 answers and 32/32 negatives, still inadequate; predates later citation/cleanup repairs |
| [Matched RoBERTa v5 grid](roberta-witness-v5-observations.zip) | Seven completed thresholds with citation/cleanup repairs and source/model fingerprints; quality remains inadequate |
| [Matched MiniLM v5 grid](minilm-witness-v5-observations.zip) | Same application/evaluator/corpus source as RoBERTa; all seven raw reports retained |
| [Comparison](matched-readers-v5.json) · [predeclared rule](matched-readers-v5-rule.json) | Best eligible development result 40/48 answers and 32/32 negatives; not release acceptance |
| [Matched RoBERTa v6 grid](roberta-procedure-v6-observations.zip) · [MiniLM v6 grid](minilm-procedure-v6-observations.zip) | Integrated main0.2.0 plus sequence/interval repairs, all seven thresholds for each reader, unchanged model/source hashes |
| [V6 comparison](matched-readers-v6.json) · [rule](matched-readers-v6-rule.json) | Best eligible development43/48 answers+32/32 negatives, inadequate for blind freeze |
| [Matched RoBERTa v7 grid](roberta-continuation-v7-observations.zip) · [MiniLM v7 grid](minilm-continuation-v7-observations.zip) | All seven thresholds for each reader with identical application/evaluator/corpus and unchanged model/source hashes |
| [V7 comparison](matched-readers-v7.json) · [rule](matched-readers-v7-rule.json) | Selected RoBERTa4:47/48 answers+32/32 negatives; promising exposed development, not fresh blind acceptance |
| [V7 default launcher](v7-default-profile-observations.zip) | Actual helper without model/threshold overrides reproduces47/48+32/32 for all four retrieval methods; quality exit1 |
| [V7 engineering](v7-engineering-checks.json) · [raw checks](v7-engineering-observations.zip) · [bounded reviews](v7-review-observations.zip) | 533 combined Python passes/1infra skip/68%; installed reader probes pass; new connected uploaded-step false refusal prevents candidate freeze |
| [V7 connected failures](v7-connected-failures.zip) | All three connected journeys fail the uploaded-step answer; three diagnostics fail a stale contract expectation; actual same-database record/source/count restart check passes. Original rollback answers and screenshots retained, without a full-suite pass |
| [V8 functional checks](v8-engineering-checks.json) · [raw logs](v8-engineering-observations.zip) · [independent review](v8-review-observations.zip) | Repaired narrow adjacent-step guard, retained unsafe REDs and passing bounded recheck; functional/package checks remain distinct from blind quality |
| [V8 default launcher](v8-default-profile-observations.zip) · [portable development report](v8-development-all-methods.json) | Final reader source reproduces47/48+32/32 across all four methods, quality exit1; no retuning or relabeled V8 fourteen-cell grid |
| [V8 actual connected browser](v8-connected-observations.zip) | Full3/3 connected journeys+3/3 separate diagnostics at all three viewports, actual saved missing-assets error, restart equality, and36 screenshots (three inspected as named in checks) |
| [V8 final gates](v8-final-gates.json) · [exact final logs](v8-final-gates-observations.zip) | Final544 Python passes/1infra skip/69% displayed (68.521885%), source lint/format and repaired dependency scan; earlier543/540 logs retain their at-time scope |
| [V8 final audit](v8-final-review-observations.zip) · [source binding](v8-source-binding.json) | Independent stored-result/tooling audit, retained coverage-summary correction, scanner controls, and staged-source mapping; no blind acceptance verdict |
| [Procedure review](procedure-window-review-observations.zip) | Retained API/normalization failures, their repairs and final29-test bounded recheck |
| [V6 engineering](v6-engineering-checks.json) · [raw checks](v6-engineering-observations.zip) | Integrated502 backend passes/1infra skip/68%, frontend72, production offline journeys, packaging/base-wheel API; interrupted obsolete-mock runs retained |
| [V6 installed readers](v6-installed-reader-checks.json) · [raw probes](v6-installed-reader-observations.zip) | Subsequent fresh outside-checkout0.2.0wheel tests for both cached CPU readers, real upload/query/history/source and dependency consistency; functional only |
| [V6 source binding](v6-source-binding.json) | Observed Windows source mapped to the staged checkpoint; distinguishes Git newline representation |
| [Initial artifact hashes](initial-artifact-hashes.json) | Digests of the initial preserved archives and independent review notes |
| [Question-boundary review](review-v3-qualified-parts.md) | Retained material findings and independent regression evidence |
| [Catalog review](review-v3-reader-catalog.md) | Actual unmanifested-tokenizer defect and bounded passing checks |
| [Pinning repair recheck](review-v3-pinning-repair.md) | Independent rejection before imports and official-cache compatibility |
| [Support-binding review](review-support-binding.md) | Independently rechecked regression boundaries, multiple-document controls and explicit grammar/entailment limits |
| [Witness-cover review](review-witness-cover.md) | Stronger complementary evidence, ties, unknown scores, citation cap and retained permission boundaries |
| [Disconnect diagnosis](diagnosis-query-disconnect.md) | Reproduced active-cursor lock before the repair |
| [Cancellation findings](review-query-cancellation.md) · [final recheck](review-query-cancellation-final.md) | Preserved direct-finalizer/elapsed-time failures and their bounded passing recheck |
| [V5 engineering checks](v5-engineering-checks.json) · [raw checks](v5-engineering-observations.zip) | 504 Python tests, 72 frontend units, types/lint, packaging and both installed-reader probes; separate from failed quality |
| [V5 source binding](v5-source-binding.json) | Exact Windows observation hashes mapped to canonical Git blobs; Python CRLF/LF representation changes are explicit, corpus bytes unchanged |

Each ZIP has an adjacent `.sha256` file. Its `archive-file-hashes.json` verifies
every contained original byte stream. Do not normalize JSON line endings or
replace failed reports. The 67 archived measurement reports contain 5,840 case
rows; a portable re-score against the packaged development corpus matches their
recorded fields and summaries. No archived development result passes the fresh
blind release gate.

Runtime model weights, private API-key manifests and owner databases are excluded.
New comparable model grids and any later blind validation are separate artifacts;
they must not overwrite these observations or be described as earlier results.
