# R496 independent metadata repair review — approved / QUIET

2026-10-26. No material finding in the narrow493 runtime-record repair. It now
matches freeze446's own-distribution raw RECORD byte collector. A new exact-file
review approval is provided; this is controller repair review, not paired
execution, model-quality, fresh-blind or release acceptance.

## Verified repair

Controller493 and frozen-inputs.json are byte-identical to reviewed476. The only
worker change is within runtime_check: normalized Distribution.read_text(RECORD)
encoding is replaced with `Path(dist._path)/'RECORD'` raw bytes through digest.
The original exact Python version/executable, normalized package inventory,
package version and RECORD-hash comparisons remain. All other worker function/
class ASTs are identical. Freeze446's collector uses exactly the same owning
metadata directory/RECORD/raw-byte rule. No dist.files traversal, vendored RECORD
search or permissive substitution was introduced. This review did not modify
source/scorer/settings/models, frozen inputs, labels or493/487 files.

Direct canonical L metadata-only execution passes92 packages under Python3.12.14.
The same runtime is rejected by the old476 worker. Actual inventory and all92
versions and owning raw RECORD hashes equal freeze446; every one of the92 text
read/encode hashes differs from its raw hash under universal-newline conversion.
This independently confirms the collector/checker representation mismatch, not a
changed installation. Only owning distribution metadata/RECORD bytes were read;
no model assets or installed package binaries were hashed or imported.

Twelve fresh pure canaries pass: raw CRLF acceptance; LF-only changed bytes
rejected; modified owner despite matching vendored record rejected; changed
version; missing and extra inventory; missing hashed owner record despite a valid
vendor; changed vendor irrelevant when owner is intact; changed Python,
executable, frozen hash and frozen version rejected. Fixtures make dist.files
and dist.read_text raise if accessed, proving the new path does not use them.
The tests write only new496 fixture files.

## Approval and checks

`review-approval.json` uses the476 ROOT-RECIPE shape and required scope
`blind-pair-controller-v476`, because the byte-identical493 controller still
requires that scope. Its reviewed_files hashes bind exactly the493 controller,
new493 worker and493 pins. A literal scope493 would be rejected; this is tested.
The exact current controller approval function accepts this approval and rejects
wrong scope, old worker hash, wrong verdict and incorrect approval-file checksum.
No controller preflight/execute or fresh binding/selection data was read.

Approval SHA256:
`e56719dd3467f9cc28abaeede580df5b8a7595cd62168c4ae47171792d1f06c9`.

From W=`C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024/delivery-worktree`:

- `.venv/Scripts/python.exe -X utf8 -B ../quality-v6/blind-runtime-independent-v496/review.py`
  — exit0;12 pure canaries, exact controller/pin preservation, worker AST checks.
- `../quality-v6/context-package-v329/optional-env/Scripts/python.exe -X utf8 -B ../quality-v6/blind-runtime-independent-v496/review.py --canonical`
  — exit0; actual92-package scan/new acceptance/old rejection. Explicit app/model
  import blockers and network/subprocess audit blockers remain active. Tool-
  approved escalation permits existing L metadata reads; no approval rejection.
- `.venv/Scripts/python.exe -X utf8 -B ../quality-v6/blind-runtime-independent-v496/check_approval.py`
  — exit0; current approval accepts and four incorrect approvals reject.
- Read-only git diff --no-index — exit1 for the intended worker difference;
  Windows newline warnings do not represent another semantic edit. Initial
  guessed worker.diff filename was absent; actual source comparison succeeded.

`hashes-before.json` equals `hashes-after.json` across17 review inputs. Final
rehash is recorded in final-hashes.log. Actual L rows are in canonical-L-records.json;
canonical-L-result.json/pure-result.json and logs retain exact results. The root
supplied RED2/GREEN0 logs and diagnosis491 agree with this independent scan.

Exact reviewed493 hashes:

- controller `7a05c53ce67bafc0b81373818f68c75cc5c19fb21756c6e86ade154ec8fba45e`
- worker `0bf5535ee726aab3ffabf979ed431f538adcc24a38923bb10dec1037a3243835`
- pins `4c06c7ca8a364aea822369be41747dd4276b19b229f60051fb98604640097e77`

## Limits and next action

No app/model imports, network, child services, API, port/process actions, seed,
evaluator/scorer execution or fresh case/author/corpus/label inspection. This did
not inspect or rerun487's sealed partial directory or create predictions/reports.
Its supplied first-runtime-check failure remains preserved. Broader controller
behavior inherits the unchanged reviewed476 bytes; this is not a new full review
of that protocol. RECORD metadata binding is not all-binary attestation.

Root owns a new explicitly authorized paired retry using these exact reviewed
files and the separate frozen bindings; original failed outputs must remain.
User quality task remains open until actual gates are met. Sources checked
locally2026-10-26; FTH-016 support, cash unknown; no shared handoff/ledger edits.
All metadata/pure commands closed. QUIET.
