# New blind comparison: first complete results failed

This is a separate validation set. The earlier failed 100-case evaluation and
first 200-case reader comparison remain unchanged; the exposed 80-case continued
development set selected the configuration and is not reused as unseen data.

Application/scorer candidate: `82b2c77c3031253edcbc8ff8326314a3e00d88a4`.
Freeze-record commit: `8f49632442f614b190acd8ab1d009461e3dd0922`.
Input commit: `75e652fa90b72710c481636694823976f635f513`.
Baseline: `e19006c9e8f1a11ef4930e24ed88128e765b6bf5`.

The [candidate freeze](candidate-freeze.json) predates clean-context authoring and
binds 279 source/configuration/test files, model assets, scoring code, selected
settings and source-bound development evidence. Its SHA256 is
`aea96f10e3d8c693914bce6171157dc3b367e0b666af1006937f8d85cc59cba4`.
No application, scorer, configuration or test changes are permitted before both
first complete reports are sealed.

| Evidence | Scope |
| --- | --- |
| [Raw author inputs](blind-author-inputs-v1.zip) | Four original corpus files, source authoring/check scripts, own checks and dated freeze; no implementation or results were available to the author |
| [Independent label review](blind-independent-review.zip) | Separate clean-context source review of all 200 labels; 17,593 reproducible checks, no material discrepancies; agent review, not human validation |
| [Corpus freeze](blind-corpus-freeze.json) | 200 cases: 120 answerable/40 unanswerable/20 conflicting-stale/20 adversarial; 20 fresh semantic families, 100 documents/120 snapshots; 40 multi-document positives/20 ordered procedures |
| [Validation binding](validation-binding.json) | Later blind data bound to the earlier frozen development-only settings; author source/case bytes unchanged, only operational profile/manifest identity derived |
| [Packaged source manifest](../../../apps/api/app/portfolio/assets/coverage-blind-v4/manifest.json) | Frozen derived manifest SHA256 `01bcb22f6da6c3c3d4e801624d203bdc98e3823e111dfaf94d60355849fe9b21` |
| [Baseline source binding](baseline-source-binding.json) | 127 extracted Python files verified against baseline Git source; 125 Windows CRLF/LF representation differences recorded, no baseline source rewriting |
| [Execution profile](execution-profile.json) | Separate SQLite/inline/local-model/authenticated APIs on 8401/8402; uniform comparison-only limiter disable; actual default helper was separately verified with limiter enabled |

Both APIs received identical snapshots through actual upload/version routes. No
successful response mocks, provider requests, WSL or generative model are used.
Each first report covers 200 cases Ãƒâ€” four methods. Both complete byte streams and
their hashes must be sealed before implementation authors inspect failures.
Incomplete/error attempts must also be retained.

Acceptance requires the default reranked path to answer at least 114/120, improve
on the baseline, refuse all 80 negatives and have zero evidence/access errors.
The first complete comparison is **FAILED** (verifier exit 1). Both reports were
sealed before failure inspection. All 279 candidate files, 127 baseline source
files, corpus inputs, dependency versions and model assets remained unchanged.
The set is now exposed; subsequent experiments on it are development only.

| Retrieval | Baseline answers / 120 | Candidate answers / 120 | Baseline refusals / 80 | Candidate refusals / 80 |
| --- | ---: | ---: | ---: | ---: |
| Keyword | 19 | 49 | 77 | 75 |
| Vector | 21 | 51 | 77 | 75 |
| Hybrid | 19 | 51 | 77 | 75 |
| Reranked (default) | 19 | 51 | 77 | 75 |

The candidate improves answer coverage but misses the 114/120 and 80/80 gates.
The default path has 53 false refusals, 16 incomplete/wrong answers and five
incorrect negative-case answers. Retrieval recall@5 is 0.995833; this is mainly
an answer-selection failure rather than absent retrieved documents. All methods
had zero execution errors, unauthorized-source exposures, citation-integrity
failures and span-integrity failures. Exact quotations alone do not establish
that the requested facts were answered.

- [First baseline report](first-baseline-blind-v4.json), 800 real HTTP observations.
- [First candidate report](first-candidate-blind-v4.json), 800 real HTTP observations.
- [Seal and chronology](first-comparison-seal.json), SHA256
  `787ed5101e35aea4e583b150adc279592494ee06f1ffb0fc76c50043dddc5388`.
- [Independent first-result review](first-comparison-independent-review.zip):
  all 1,600 rows re-scored, frozen source/assets checked, and 12 failures
  inspected; no scoring or label defect explains the sampled misses.
- [Portable re-scoring and acceptance](first-comparison-gate.json): both 800-row
  reports independently re-scored against the frozen source contracts.

The review application on 8400/3505 was not promoted. Another acceptance attempt
requires a new frozen candidate and separately authored unseen cases; this failed
comparison will never be replaced or relabeled as unseen.

These measurements concern synthetic agent-authored source contracts, not human
validation, arbitrary factual entailment, production capacity or provider quality.
Observed HTTP timings are not a benchmark. The original 8400/3505 review instance
and its database remain unchanged. See the [development record](../../answer-coverage-development-v3.md).
