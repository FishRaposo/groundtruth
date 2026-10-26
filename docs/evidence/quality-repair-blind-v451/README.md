# GroundTruth first failed blind pair — v451

**QUALITY FAILED. Unseen NOT accepted. EXPOSED REGRESSION ONLY.** These synthetic agent-authored and agent-reviewed cases are now exposed. Any repaired candidate requires a new freeze and a genuinely new independently authored/reviewed blind set.

| Retrieval method | Original positives | Candidate positives | Original negatives | Candidate negatives |
| --- | ---: | ---: | ---: | ---: |
| keyword |69/120|17/120|79/80|80/80|
| vector |63/120|17/120|79/80|80/80|
| hybrid |70/120|17/120|79/80|80/80|
| reranked |69/120|17/120|79/80|80/80|

The frozen gate requires at least114/120 positives,80/80 negatives, improvement over the original baseline, and zero execution/access/citation/span errors. Candidate misses the positive and improvement gates. Its103 positive failures per method are whole-request refusals. Both complete first800-row reports, original comparison and opposition helper output are preserved exactly, with deterministic gzip for large observations. Both arms were complete and pair-sealed before inspection.

Run `python -S -X utf8 -B check_bundle.py` from any directory. The standard-library-only checker verifies local hashes/bounded gzip, frozen source/corpus/seal bindings, then uses unchanged frozen pure scorer functions and the actual authored facts/ordered steps to re-score all1600 observations. Exit0 means the **failed record is faithfully replayed**, not that quality passed. It performs no inference, HTTP/API/browser/service/model operation, installation or new measurement.

The [original opposition helper](raw/first-pair/opposition.json) reports80 missing inspections because it recognizes a procedure-only provenance shape. [Independent V519](reviews/independent519/REPORT.md) shows all40 required candidate case/method rows contain both opponents in inspected sources and included conflict source-scope decisions:80/80 identities. Its semantic assessments remain empty and outcomes `not_relevant`; complete source inspection does not establish contradiction recognition. The original failed helper result remains unchanged.

[RESULTS.json](RESULTS.json) records metrics and limits. [SOURCE-BINDINGS.json](SOURCE-BINDINGS.json), [manifest.json](manifest.json) and [SHA256SUMS](SHA256SUMS) bind frozen source31, baseline417, commit metadata, runtime446, selection479, controller493/approval496, raw author451/review458, both arm corpora and both first reports. Candidate commit is `de79a787d922b2ace0c5a9ee06c5a17a7a497730`; original baseline is `e19006c9e8f1a11ef4930e24ed88128e765b6bf5`. Frozen snapshots match Git contents modulo CRLF conversion; raw Git-blob byte equality is not claimed.

No full keys, private seed/SQLite payloads, model weights or installed environments are included. Hash-only references to excluded private files remain historical provenance. Runtime/HTTP observations and pure replay are not installed-binary attestation, human validation, general conflict detection, capacity, hosted-CI or release certification. Both arms share raw inputs with versioned arm-specific representations; this is an end-to-end comparison, not a reader-only improvement experiment.

Related retained packets: [engineering evidence](../quality-repair-engineering-v30/README.md) and [direct current frontend gates](../frontend-direct-v510/README.md). Those packets remain unchanged and are optional context, not replay dependencies. Historical paths inside exact copied records identify origins; they are not commands to execute.
