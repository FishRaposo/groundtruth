# First sealed source27 development failure

Observed 2026-10-25. **Development qualification FAILED: 45/48 complete positive
answers and 32/32 correct negatives, below the required 46/48 positives.** Three
ordinary-procedure requests were falsely refused as curated conflicts. The raw
observations are retained without correcting failures. Execution errors,
unauthorized source exposures, citation errors and span errors are each zero.
The eight required opposing-source identities across four conflict requests are
separately present in the observed inspection records; see the
[author audit](development-audit.json). This presence check does not assert that
all source-relevance decisions are correct.

This is the exposed, synthetic, agent-authored DEV80 corpus: 48 answerable,
16 unanswerable, 8 conflicting/stale and 8 adversarial requests; 56 documents and
76 versions. It is development/regression evidence, without human validation.
No model-quality acceptance, blind acceptance, owner promotion or independent
export review is claimed. Root owns a separate independent export review.

Six actual condition-exclusion NLI decisions remained neutral and unsupported,
with entailment margins from -2.66998 to -2.40057, despite whole authoritative
premises and 278–279 pair tokens. Exact actual hypotheses, complete premises,
logits, margins and settings are in [actual NLI observations](actual-condition-nli-observations.json)
and [the preserved failure records](actual-failure-records.json). No threshold or
model change is asserted. Root semantic-overbreadth diagnosis is ongoing and is
not a passing quality mechanism or blind claim.

The source/scorer archive also includes root engineering fixture
`scripts/tests/fixtures/procedure-copy-v3-cover-v2-r1.json` and its new
`scripts/tests/test_retained_query_scoring.py` regression. Such engineering
fixtures use doubled external model boundaries; their passing tests are distinct
from this real cached-model HTTP report, and do not establish actual model quality.

The actual report measured **reranked retrieval only**, QA threshold **4**, NLI
margin **0**, composite proposals `qa_plus_source_patterns_v1`, activity role scope
`ordinary_session_activity_v1`, and combined procedure profile
`source_declared_procedure_copy_v1`. It used authenticated local HTTP, SQLite,
inline ingestion, local cached CPU models, reader selection and extractive
generation. [Exact settings](execution-settings.json) and [commands](commands.json)
preserve the measured configuration; other methods/margins remain unmeasured here.

All timing in this observation overlapped package builds and UI checks. It is not a performance claim or a controlled performance benchmark.

## Portable evidence

- [Exact full report, lossless gzip](report.json.gz), raw SHA256 `935346f5bf705a4705c98ac41eccf7733efe8dcdf1cc63743aaa25aff8f4528b`,
  39,607,386 uncompressed bytes.
- [Frozen source and scorer](frozen-source.zip): all 226 exact files, bound by the
  [source manifest](source-manifest.json).
- [Frozen candidate corpus](frozen-candidate-corpus.zip): four exact files including
  corpus hashes, source/label provenance and representation lineage.
- [Canonical source snapshot observations](source-snapshots.json) are checked by
  replay against the frozen corpus; they are not independent source authority.
- [Original seal](original-run-seal.json) binds 94 closed run files and the
  [preservation registry](original-preservation-registry.json) binds 95 files.
- [Input checks](input-checks.json), [result](result.json), and
  [closed process status](cleanup.json) preserve the recorded lifecycle.
- Dependency metadata [before](runtime-before.json), [after](runtime-after.json),
  and [stability comparison](runtime-stability.json); [model hashes](model-bindings.json).
- [Exclusions and synthetic provenance](export-exclusions.json),
  [manifest](manifest.json), and [checksums](checksums.sha256).

The frozen scorer replay verifies 80 report rows and their aggregate. Its runtime
verification remains `historical_unrecorded_or_report_claims_only`; matching report
settings, controller hashes and local metadata do not independently attest to a
historical running process. The 16-package before/after capture checks interpreter
and distribution version/RECORD metadata, not all installed binaries. Model file
hashes, raw report, frozen source/corpus, sealed data snapshots and prior exported
failure bundles were checked before and after this export. All remained unchanged.
Four actual throwaway runtime keys were read only for a nonprinting byte scan of
every public member and decompressed report. No database or private seed manifest
is exported. Model binaries are separately required for reproduction.

## Reproduction without erasing this failure

Inspect [the exact original launch argv](original-launch.json) and [frozen
controller](controller.py). The recorded argv uses local absolute paths and is
historical evidence, not a portable one-click execution claim. On a prepared host,
extract the two archives into fresh SOURCE/CORPUS directories, verify their hashes,
provide the pinned runtime/model assets, and call `controller.py` with those paths,
the source/corpus/common manifest pins, QA4/NLI0 composite/activity/combined settings
and a **new nonexistent output directory**. Keep the original report/outputs intact.
The exact original commands in `commands.json` show migration, authenticated
seeding and evaluation. Seeding creates fresh private keys locally. Do not copy
private seed artifacts into this evidence directory. This export launches none of
those commands and performs no inference, service, browser, installation or build.

The unchanged qualification gate is >=46/48 positives, 32/32 negatives, eight
required inspection identities and zero execution/access/citation/span errors,
then a qualified frozen candidate and fresh independently authored/reviewed blind
200 with >=114/120 positives and 80/80 negatives. These exposed DEV cases cannot
replace that blind acceptance.

Handoff: packet F / FTH-016 / GT-05–GT-07 support only; no opportunity or experiment
ledger change. Cash unknown, no receipt assessed. Next action: root separately
reviews this export and continues repair/requalification from a new source freeze.
