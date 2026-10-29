# First sealed source29 development failure

Observed **2026-10-26**. **Development qualification FAILED: 45/48 complete
positive answers and 32/32 correct negatives**, below the required 46/48
positives. Three ordinary procedure requests were falsely refused as curated
conflicts. The report retains those failures unchanged. Execution errors,
unauthorized source exposures, citation errors and span errors are each zero.
The eight required opposing identities across four conflict requests are present
in the actual inspection records; [development-audit.json](development-audit.json)
records that presence check. Presence does not prove sound semantic relevance or
a completed comparison.

This is the exposed, synthetic, agent-authored DEV80 corpus: 48 answerable,
16 unanswerable, eight conflicting/stale and eight adversarial requests;
56 documents and 76 source versions. It has no human validation. This packet is
failed development evidence, with **no blind acceptance, qualification, default
promotion, owner review refresh, hosted acceptance or quality success claim**.
It preserves the first result and does not replace earlier failed observations.
Root obtains a separate independent export review before linking this packet.

## Actual failure and selected configuration

The three false refusals are `dev70-01-procedure`, `dev70-03-procedure` and
`dev70-04-procedure`. Across their six opposing note checks, each actual
`card_reference_identity` NLI assessment is neutral and unsupported; the other
22 mandatory semantic checks per note are supported. The six complete check
sets, exact premises, hypotheses, logits, margins, ranges and settings are in
[actual-context-nli-observations.json](actual-context-nli-observations.json).
Their premise slices were checked against the frozen corpus bodies. See also
[actual-failure-records.json](actual-failure-records.json) and the root's original
[compact diagnosis](original-compact-diagnosis.json). These are recorded local
model observations, without inference reruns, threshold changes or repair claims.

The actual run used authenticated local HTTP, SQLite, inline ingestion and cached
CPU models; reranked retrieval, top-k five, refusal threshold 0.35, QA null
threshold four, NLI margin zero, reader selection and extractive generation.
The selected profiles were `qa_plus_source_patterns_v1`,
`ordinary_session_activity_v1`, `source_declared_procedure_copy_v1`, and opt-in
`scoped_note_context_v1`. That last policy uses the note's stated context and
discloses the adopted interpretation; it does not make source entailment or a
universal scope claim. No later source or diagnostic is substituted here.
[execution-settings.json](execution-settings.json) retains the exact recorded
configuration. This observation is not a controlled performance benchmark.

## Portable evidence and limits

- [Full original report, lossless gzip](report.json.gz): raw SHA256
  `7d2104064d64fc1fd4cc645fe586f68616e8c79381cfc6ff65cc77f1b1f88b0e`,
  41,390,203 uncompressed bytes.
- [Frozen source and scorer](frozen-source.zip): all 229 exact source29 files,
  bound by [source-manifest.json](source-manifest.json), SHA256
  `0798ee3fe2127d726577c9cb280ed1764a408604473cecb7897dcbff949cd58a`.
- [Unchanged candidate corpus](frozen-candidate-corpus.zip): four exact files;
  corpus manifest SHA256
  `22c7cf7ccbc229d641b26ea359bdb74420c313b411505734681c843a7ba54cf4`.
  Its manifest retains authored-label provenance and lossless representation
  lineage. These exposed DEV cases cannot serve as fresh blind cases.
- [Source snapshot observations](source-snapshots.json) are report observations,
  checked against the frozen corpus by canonical scorer replay. They are not an
  independent source of authority.
- [Original run seal](original-run-seal.json) binds 94 closed run files;
  [preservation registry](original-preservation-registry.json) binds 99 original
  inputs. Hashes/path metadata may reference excluded private artifacts; their
  contents are not exported. [Input checks](input-checks.json),
  [result](result.json) and [cleanup](cleanup.json) retain the recorded lifecycle.
- [Pre-run runtime metadata](runtime-before.json) records 16 distribution
  versions and RECORD hashes. There is no post-run package capture in this
  packet, no all-binary or fresh-install attestation, and no independent
  attestation of a historical running process. [Model bindings](model-bindings.json)
  retain model revisions and file hashes; assets were rehashed during packaging
  without loading them. Model binaries are not exported.
- [Exclusions](export-exclusions.json), [manifest](manifest.json) and
  [checksums](checksums.sha256) make byte and scope boundaries explicit. The
  report gzip and copied historical JSON are raw-byte exact. Extracted JSON
  objects have fresh LF serialization and preserve structural equality. No
  answer, identity, quote, model assessment or certificate field was rewritten.

The source ZIP includes engineering tests and fixture doubles. Such tests are
distinct from the real HTTP/cache/CPU report and do not measure model quality.
No database, uploads directory, private seed manifest, credentials or model
weights are included. Complete known credential values from all 44 captured
direct run seed manifests, including DEV29, were read only into memory for
nonprinting scans of every public member and decompressed report/archive.
All 172 distinct captured values were absent. Actual observation JSON was also
checked for populated sensitive credential fields. This is a bounded scan of
known captured credentials, not proof against every possible unknown secret.

## Replay and reproduction

Run the included standalone integrity checker using any compatible Python:

```powershell
python -B replay.py
```

For canonical score reconstruction, use a prepared Python environment with the
API dependencies recorded in the frozen source/runtime metadata. Supply a **new
nonexistent** scratch path outside the immutable bundle:

```powershell
python -B replay.py --canonical --scratch-dir C:\scratch\dev29-replay-new
```

This checks closed file membership and hashes, extracts only the frozen source
and corpus into that new directory, then runs the frozen scorer against the
unchanged report. The scratch files remain for inspection. It does not use
current working source, load model libraries, query a database, call HTTP or run
inference. [Canonical replay observation](canonical-replay-observation.json)
holds the observed 80-row audit. Its integrity count describes the payload before
that observation was appended; the final expanded inventory was checked again.
Its historical runtime verification remains
`historical_unrecorded_or_report_claims_only`.

A new real model reproduction is separate. Inspect [original launch argv](original-launch.json),
[recorded commands and exits](commands.json), [controller](controller.py) and
[original launcher](original-launcher.py). Historical argv uses local absolute
paths and is not a portable one-click claim. On a prepared host, use fresh source,
corpus and model paths, the manifest pins and exact selected profiles above, and
a new nonexistent controller output directory. Seeding creates new local private
keys; keep its artifacts outside this packet. This export ran no reproduction,
inference, API, browser, package installation or build.

The unchanged gate is at least 46/48 positives, 32/32 negatives, all eight
required opposing inspections and zero execution/access/citation/span errors;
then a qualified frozen candidate and fresh independently authored/reviewed blind
200 with at least 114/120 positives and 80/80 negatives. No new quality result or
default change follows from packaging this failed report.

Handoff: FTH-016 / packet F / GT-05–GT-07 support only. No opportunity or
experiment ledger changed; cash unknown, no receipt assessed. Next action:
root obtains a fresh independent export review, then continues repair from a
separate source freeze. Author commands, exits, input preservation and limitations
are recorded in `Q/public-dev29-export-v343/REPORT.md` and `result.json`.
