# Failed source22 development observation

Observed 2026-10-25. **Development qualification failed: 32/48 correct complete
answers; 32/32 correct negatives.** This is the same frozen 80-case synthetic,
agent-authored development corpus used for source20 and source21. These exposed
cases are development/regression material, never a fresh unseen validation.

| Observation | Result |
| --- | ---: |
| Complete answerable cases | 32/48 |
| Correct negative outcomes | 32/32 |
| False refusals on answerable cases | 16 |
| Incomplete emitted answers | 0 |
| Authored-source recall@5 / MRR | 0.989583 / 0.979167 |
| Complete source/version coverage | 32/48 |
| Unauthorized source exposures | 0 |
| Citation / span integrity failures | 0 / 0 |
| Execution errors | 0 |
| Required opposing-source inspection identities present | 8/8 |

All 16 failed cases are procedure requests that the application refused. The
other 32 positive cases passed their authored complete-answer contracts. These
results improve exposed development coverage but remain below the required
46/48 development positives. No quality or blind acceptance is claimed.

The actual HTTP run used SQLite, inline ingestion and cached CPU semantic
embeddings, RoBERTa QA threshold 4, NLI margin 0, composite proposals and disclosed
activity-role scope. The recorded report settings preserve the precise profiles
and model revisions. Seeding published 56 documents and 76 immutable versions.
The complete run, database and logs were closed and sealed before case failures
were inspected. Raw observations and earlier failed evidence remain unchanged
in the isolated operation evidence. No owner review instance was promoted.

Only reranked retrieval and margin 0 were measured for this snapshot. This is
not human calibration, a blind baseline comparison, general model-quality
validation or production readiness. HTTP timings were collected while regression
tests also ran; they are not a controlled performance benchmark.

## Inspect the complete evidence

- [Manifest and exact byte hashes](manifest.json)
- [Full public report, gzip](report.json.gz)
- [Frozen Python/JSON source archive](frozen-source.zip) and [source hashes](source-manifest.json)
- [Exact compiled candidate corpus](frozen-candidate-corpus.zip)
- [Frozen scorer replay and opposing-source inspection checks](development-audit.json)
- [Dependency metadata before](runtime-before.json), [after](runtime-after.json) and [comparison](runtime-stability.json)
- [Checksum list](checksums.sha256)

The report decompresses byte-for-byte to the first complete report, SHA-256
`24887798558209005a81fda17922eb5fc2471ecea2cee59270ebfcfabb50c3d3`.
Both archives contain exact frozen input bytes. Runtime keys, databases, private
seed manifests and model binaries are excluded. Synthetic source and case
content are project-owned MIT fixtures, with provenance in the corpus.

Model assets, source and corpus were checked before and after execution. The
interpreter and 16 distribution versions/RECORD files were captured before and
after, with identical metadata. This proves metadata stability, not a rehash of
every installed binary. The portable scorer audit explicitly does not
independently attest to a historical running process; its runtime claim remains
unverified. Separate runtime snapshots and controller integrity checks retain
their bounded meaning. Reproduction requires the separately pinned cached model
assets and runtime dependencies described in [the active repair](../../answer-coverage-quality-repair.md).

The development gate remains at least 46/48 complete positives and 32/32 negatives,
with zero access/citation/span errors, followed by a frozen configuration and a
fresh independently authored/reviewed blind set of 200 cases. The final gate
remains 114/120 complete positives and 80/80 negatives. Quality acceptance is open.
