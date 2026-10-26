# Failed source21 development observation

Observed 2026-10-25. **Development qualification failed: 3/48 correct complete
answers; 32/32 correct negatives.** This is the same frozen 80-case synthetic,
agent-authored development corpus used for source20. These exposed cases are
development/regression material, not a fresh unseen or blind validation.

| Observation | Result |
| --- | ---: |
| Complete answerable cases | 3/48 |
| Correct negative outcomes | 32/32 |
| False refusals on answerable cases | 45 |
| Incomplete emitted answers | 0 |
| Authored-source recall@5 / MRR | 1.000000 / 0.968750 |
| Complete source/version coverage | 3/48 |
| Unauthorized source exposures | 0 |
| Citation / span integrity failures | 0 / 0 |
| Execution errors | 0 |
| Required opposing-source inspection identities present | 8/8 |

The actual HTTP run used SQLite, inline ingestion and cached CPU semantic
embeddings, RoBERTa QA threshold4, NLI margin0, composite proposals and disclosed
activity-role scope. Its recorded settings identify the precise profiles and
model revisions. Seeding published56 documents and76 immutable versions. The
complete run, database and logs were closed and sealed before case failures were
inspected. Raw observations and prior failed evidence remain unchanged in the
isolated operation evidence. No owner review instance was promoted.

The three complete positives and45 false refusals do not satisfy the development
gate. Only reranked retrieval and margin0 were measured for this snapshot. These
results are not human calibration, a blind baseline comparison, general answer
quality validation or production readiness. HTTP timings were collected while
regression tests also ran; they are not a controlled performance benchmark.

## Inspect the complete evidence

- [Manifest and exact byte hashes](manifest.json)
- [Full public report, gzip](report.json.gz)
- [Frozen Python/JSON source archive](frozen-source.zip) and [source hashes](source-manifest.json)
- [Exact compiled candidate corpus](frozen-candidate-corpus.zip)
- [Frozen scorer replay and opposing-source inspection checks](development-audit.json)
- [Dependency metadata before](runtime-before.json), [after](runtime-after.json) and [comparison](runtime-stability.json)
- [Checksum list](checksums.sha256)

The report decompresses byte-for-byte to the first complete report, SHA-256
`fda800a1d4e04b6ddefa4a744fea92155a7cc607eeeae8b0124a63b6c5c0f7bf`.
Both archives contain exact frozen input bytes. Runtime keys, databases, private
seed manifests and model binaries are excluded from this bundle. Synthetic source
and case content are project-owned MIT fixtures, with provenance in the corpus.

Model assets, source and corpus were checked before and after execution. The
interpreter and16 distribution versions/RECORD files were captured before and
after, with identical metadata. This is metadata stability, not a rehash of every
installed binary. The portable scorer audit explicitly does not independently
attest to a historical running process; its runtime claim remains unverified.
The separate runtime snapshots and controller integrity checks retain their
bounded meaning. Reproduction requires the separately pinned cached model assets
and runtime dependencies described in [the active repair](../../answer-coverage-quality-repair.md).

The development gate remains at least46/48 complete positives and32/32 negatives,
with zero access/citation/span errors, followed by a frozen configuration and
fresh independently authored/reviewed blind200. The final gate remains114/120
complete positives and80/80 negatives. Overall quality acceptance remains open.
