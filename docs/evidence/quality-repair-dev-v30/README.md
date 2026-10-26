# Source30 exposed development observations

Checked 2026-10-26. This portable evidence packet retains all five first sealed
margin0..4 reranked reports and the first selected margin2 all-method report.
Every report contains the complete actual retained HTTP responses and provenance;
gzip preserves its original bytes. No failed result was removed or rewritten.
These are **80 exposed synthetic development cases with agent-authored labels**,
not human validation, fresh blind evidence, general model quality, release
acceptance, publication approval or a final quality-gate claim.

| Run | Method | Correct positives | Correct negatives | Execution/access/citation/span errors | Recorded evaluator/controller exit |
| --- | --- | --- | --- | --- | --- |
| margin0-reranked | reranked | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin1-reranked | reranked | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin2-reranked | reranked | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin3-reranked | reranked | 30/48 | 32/32 | 0/0/0/0 | 1 |
| margin4-reranked | reranked | 3/48 | 32/32 | 0/0/0/0 | 1 |
| margin2-all | keyword | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin2-all | vector | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin2-all | hybrid | 48/48 | 32/32 | 0/0/0/0 | 0 |
| margin2-all | reranked | 48/48 | 32/32 | 0/0/0/0 | 0 |

The predeclared selection maximizes reranked positives, requires at least46/48,
32/32 negatives, eight required opposing document/version/hash identities and
zero execution/access/citation/span errors, then breaks ties toward the higher
margin. Margins0/1/2 tie; margin2 wins. Margins3 and4 remain here, including their
insufficient positive results and exit1 records. This is exposed development
selection, not an unbiased performance estimate. The selected all-method run
contains keyword, vector, hybrid and reranked observations in the same report.

[Independent margin0 audit Q362](independent-audit-v362.zip) includes the saved
history/typed-reference/NLI/replay checks and its corrected checker attempt.
[Independent grid audit D373](independent-audit-v373.zip) includes all400 grid
rescores, eight required opponent identities per run, five readiness/400 response
runtime checks, model/package metadata bindings and the preserved failed checker
attempt. Their scopes remain those stated by their authors; packaging does not
rerun persisted SQL/history checks. [Predeclared grid](grid-declaration.zip)
retains the original commands, completion records and logs. Independent review
of this newly assembled export remains a separate root-owned task.

- [margin0-reranked complete raw report](margin0-reranked-report.json.gz); [explicit settings](margin0-reranked-execution-settings.json); [closed seal](margin0-reranked-SEALED.json); [first-result preservation](margin0-reranked-preservation.json).
- [margin1-reranked complete raw report](margin1-reranked-report.json.gz); [explicit settings](margin1-reranked-execution-settings.json); [closed seal](margin1-reranked-SEALED.json); [first-result preservation](margin1-reranked-preservation.json).
- [margin2-reranked complete raw report](margin2-reranked-report.json.gz); [explicit settings](margin2-reranked-execution-settings.json); [closed seal](margin2-reranked-SEALED.json); [first-result preservation](margin2-reranked-preservation.json).
- [margin3-reranked complete raw report](margin3-reranked-report.json.gz); [explicit settings](margin3-reranked-execution-settings.json); [closed seal](margin3-reranked-SEALED.json); [first-result preservation](margin3-reranked-preservation.json).
- [margin4-reranked complete raw report](margin4-reranked-report.json.gz); [explicit settings](margin4-reranked-execution-settings.json); [closed seal](margin4-reranked-SEALED.json); [first-result preservation](margin4-reranked-preservation.json).
- [margin2-all complete raw report](margin2-all-report.json.gz); [explicit settings](margin2-all-execution-settings.json); [closed seal](margin2-all-SEALED.json); [first-result preservation](margin2-all-preservation.json).

The [observations inventory](observations.json), [manifest](manifest.json) and
[checksums](checksums.sha256) enumerate all runs and files. Per-run commands,
readiness, input checks, process, result and cleanup records are copied exactly
beside each report. They record the historical closed process; no present port
or process was inspected. Original seals/registries include path/hash metadata
for excluded private files, never their contents.

## Portable replay

Copy this **entire directory** outside a checkout. Standard-library integrity:

```powershell
python -B replay.py
```

Canonical model-free rescoring needs an existing compatible API dependency
environment (Pydantic and the frozen source's normal API dependencies), without
model packages or model weights. Use a new scratch path outside this directory:

```powershell
python -B replay.py --canonical --scratch-dir ../source30-replay-scratch
```

The [replay script](replay.py) checks a closed checksum inventory, pinned raw
reports and authoritative metadata, exact source231/corpus4 archives, then
extracts them only into new scratch. It imports the frozen scorer, rebuilds
source observations, reconstructs every saved case score and full summary,
and records the eight required opposing identities per method (including any
missing observations). Multiple inspected chunks for the same required identity
are valid. Model-library imports are blocked. No API, model, subprocess, SQL,
provider, build, install or evaluation launch occurs in portable replay.
The [saved author replay observation](canonical-replay-observation.json) records
successful outside-checkout canonical rescoring of all720 saved rows across nine
method observations, with eight required opposing identities present in each.
This is author replay, not a separate independent review of this export.
Scratch remains available for inspection. The final runtime-selection verifier
stays false because these development reports have no final frozen selection
artifact. Rescoring saved responses does not reproduce inference.

[Frozen source](frozen-source.zip) contains the full231-file source30 authority,
bound by [its original manifest](source-manifest.json). [Frozen corpus](frozen-candidate-corpus.zip)
contains exactly cases/documents/manifest/profile. Case labels and inputs are
unchanged; third-party source content and human validation are absent.
The [original controller](controller.py), [original launcher](original-launcher.py)
and recorded commands document how the historical runs were made. They contain
original local paths and are provenance, not turnkey portable inference commands.

## Runtime and limits

Recorded source30 runs use reader QA null threshold4, local NLI at each explicitly
listed margin, composite proposals, ordinary-session activity scope,
source-declared copying and scoped_note_context_v2/evidence-profile-v4. Typed
exact reference checks remain separate from22 NLI obligations. Opposing sources
are retained and inspected; ordinary/factual gates and scorer labels are intact.

[Model bindings](model-bindings.json) retain three model revisions/manifests and
24 file hashes; no model or tokenizer binaries are bundled. The [locked runtime
capture](runtime-before.json) records16 package versions and RECORD hashes.
Independent audits compare the saved model/package bindings without importing
models. Distribution metadata is not all-binary or independently attested
historical process verification.

[Current-tool distinction](current-tool-distinction.json) records that the later
launcher375 has measured bare-serving defaults while all185 application files
still equal source30. The observations use frozen source30 and explicit settings;
their meaning does not depend on current checkout defaults. Portable replay
always imports the extracted source30 authority.

[Exclusions](export-exclusions.json) record bounded credential scanning: complete
known captured key values were scanned through every public/decompressed member,
with counts recorded and key values excluded. Databases, private seed manifests,
uploads, model weights and unrelated private material are excluded. Logical
document IDs and original non-sensitive local evidence paths remain for replay.
Earlier failed bundles, including source29, remain separate and unchanged.

FTH-016 / Project05. Cash status unknown. Root owns independent export review,
shared links, later candidate freeze and any fresh blind qualification.
