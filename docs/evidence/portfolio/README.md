# Connected observations: preserve the failed result

These are observed local results, separate from the original golden fixture in
`data/golden/`. The corpus manifest is
`0be7e127c84aabf048d69edae3e5cc430e7a65114f45ca93fd27365723c3315f`.
Sources/cases are synthetic and agent-authored, without human/model validation.

- `development-final.json`:20 development cases for each of four real HTTP
  retrieval methods after the development-only support repair.
- `selection-final.json`:settings, source fingerprints and development checksum,
  frozen before the first held-out request at2026-10-24T02:53:24.162705+00:00.
- `held-out-final.json`:the **first, failed**80-case-per-method held-out result;
  exit1,37/80 passed per method,42 false refusals and1 missed refusal. Retrieval
  recall@5=1.0, with zero observed unauthorized exposure/execution errors.

The source fingerprints describe an intermediate development snapshot using
`extractive-coverage-v1`. The final application subsequently repaired an
independently prepared live “roll back” question and usesv1.1. The earlier source
fingerprints are historical evidence, not a claim that the final source is byte
identical. Do not report another run on these exposed cases as new unseen
held-out validation, and do not replace the failed report with later success.

The [case study](../../portfolio-case-study.md) interprets retrieval, source/version
correctness and refusal denominators. The [verification record](../../portfolio-verification.md)
describes current connected checks, independent review, packaging and browser
evidence. Local SQLite/inline behavior does not verify PostgreSQL/Redis or the
large indexed benchmark. Raw credentials and owner data are excluded.

## Current portable proof and inspected screenshots

`connected-workflow.json` records ten real HTTP checks including 20 overlapping
requests; `restart.json` reads their exact sources after process restart.
`frontend-gates.json` retains author gates plus the independent parent rerun:
62 units, three offline and three real connected production journeys. The
`manifest.json` verifies artifact bytes and 216 current source fingerprints
(normalized UTF-8/LF for cross-platform source checkout). The frozen selection
file retains its original CRLF bytes; Git must not normalize this historical
report. A deliberately tampered copy is rejected with exit 1.

Representative final parent browser captures:

- [Sample opening](sample-overview-1440.png):1440×900, guided/free choice.
- [Sample version comparison](sample-versions-768.png):768×1024, keyboard focus.
- [Sample source](sample-source-390.png):390×844, readable mobile evidence.
- [Actual source drawer](connected-source-390.png):immutable passage/version/hash.
- [Actual answer](connected-answer-1440.png):extractive mode and stored citation.
- [Actual documents](connected-documents-768.png):real upload/version surface.
- [Loaded actual audit/usage](connected-admin-1440.png):unknown pricing remains unknown.
- [Legacy history](connected-legacy-390.png):unverified provenance stays unknown.

All visible content is synthetic. These screenshots show local application
behavior, not customer usage or model-quality validation. No video was recorded.
