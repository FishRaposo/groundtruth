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
replace failed reports. The 37 archived measurement reports contain 2,960 case
rows; a portable re-score against the packaged development corpus matches their
recorded fields and summaries. Quality results remain failed/unselected.

Runtime model weights, private API-key manifests and owner databases are excluded.
New comparable model grids and any later blind validation are separate artifacts;
they must not overwrite these observations or be described as earlier results.
