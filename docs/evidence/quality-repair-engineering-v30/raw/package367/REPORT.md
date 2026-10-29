# C367 independent source30 package gate — QUIET

Executed locally 2026-10-26. Final archive, fresh installation and ASGI package
workflow checks pass. Earlier failed attempts remain preserved. This is local
Windows/Python 3.12 package engineering, separate from DEV/blind quality, browser,
authorization, hosted services or release acceptance.

## Source and archives

Build used W's development interpreter D (Python 3.12.14) and standard isolated PEP517
(`python -m build`), producing an sdist and a wheel built from that sdist. Source
was staged only in NEW `Q/context-package-v367/staged-api`, so setuptools wrote
no W build/egg-info output. All 185 frozen app members match
`Q/requirements-source-v30` and its manifest (manifest SHA256
`fd0e693629aaae190d1d3759784d857a77bac0e45c4fa5b45a83d3efd1879772`).
Six explicit vendor-license/Cedar/Juniper package assets supplement that code
freeze. Both archives and both installed environments match all 191 app members,
including `source_context_references.py`, `source_context_scope.py` and the v2
evidence policy. The repository's current canonical closure check also passes.
No model weights or external `shared_core` namespace are packaged.

- Wheel: `dist/groundtruth-0.2.0-py3-none-any.whl`, SHA256
  `08621b6c5dec801108bc9a2200b730ed9762828c5e113e8191a60de2ceb39ecc`.
- Sdist: `dist/groundtruth-0.2.0.tar.gz`, SHA256
  `572270a6967fe282e88398b06732298ec2c40d48bad5833ca230ac9bf4643eec`.

`archive-check.json` and `stage-closure.json` contain exact file bindings.
This records the actual bytes; no deterministic timestamp/build-byte claim.

## Fresh installations and actual workflows

New `base-env` and `optional-env` are outside the checkout and exclude system
site packages. Current lock constraints were exported using the verified uv 0.8.17
executable against staged current pyproject/uv.lock. The 64 base and 115 optional
non-comment pin lines exactly match the prior locked pins, independently of
generated command comments. Both fresh installs and `pip check` exit0.

Installed closure/runtime records are separate: `base-installed-runtime.json`
contains 191 matching app files/63 distributions; `optional-installed-runtime.json`
contains 191 matching app files/92 distributions. GroundTruth 0.2.0 is imported
from each new environment's site-packages, with Python isolated mode and no
checkout PYTHONPATH. Actual versions include torch 2.14.1, transformers 5.20.2,
sentence-transformers 6.2.0 and safetensors 0.8.0. Distribution RECORD metadata is
captured; this does not claim full installed-binary hashing.

The base environment executed the unchanged current canonical smoke body from
`W/scripts/verify_isolated_wheel.py`: actual ASGI upload/query/saved history,
packaged corpus/demo integrity and visible missing reader/classifier failures.
Its child profile explicitly neutralizes inherited discovery/role/copy/context/
support settings exactly as that tool specifies. Result exit0; torch/transformers
remain absent in the base install.

The optional environment used exact existing cached CPU embedding/RoBERTa/NLI
assets from source30's recorded recipe, with offline model flags and new local
runtime-cache paths. It used activity scope, source-declared copy and
`scoped_note_context_v2` (profile v4); QA revision
`adc3b06f79f797d1c575d5479d6f5efe54a9e3b4`, threshold 4, support margin 0. The
approved configuration is explicit rather than inferred from health.

Final optional probe (`optional-workflow-2`) observes readiness 200, real upload 200,
completed query 200, actual saved GET 200 and immutable version GET 200/body hash.
Its exposed packaged Cedar case has no opposing inventory, so its source-
authoritative output certificate is exactly v1 while evidence profile is v4. This
does not exercise Lumen's 22+1 typed opposing-source journey. Explicitly missing
reader/support paths fail visibly even after real models loaded; observations
are in `optional-workflow-2/missing-assets.json`. Full safe DTOs are in its
`result.json`. No model download, successful mock, provider call or API port.
AUTH=false is a package smoke boundary, not authorization evidence.

## Preserved failures and limits

1. First isolated build failed on a Windows sandbox ACL when creating a temporary
   venv. `build.log`/result remain. The permission-scoped retry passed.
2. First archive inspection likewise encountered sandbox read permission; its
   failure record remains. The permission-scoped read-only retry passed.
3. First optional probe reached readiness/upload/completed query, then failed our
   overly strict scratch expectation of outputv4 for Cedar with no inventory.
   Frozen `procedure_output.py` explicitly selects v4 only for inventoryv3;
   no-inventory uses v1. Its log and original SQLite DB remain untouched. A NEW
   probe/output directory corrects only that exact no-inventory expectation and
   completes history/snapshot/missing-asset checks. No application fix was made.

All subprocess invocation/exit/log records are aggregated in
`commands-and-results.json`; raw per-phase records remain. `artifact-manifest.json`
hashes explicit outputs, not entire caches/environments as a public bundle.

## Upstream stability and handoff

`upstream-before.json`, `upstream-after.json`, additional asset hashes and
`upstream-stability.json` verify 464 read-only input records unchanged: frozen
source/current packaged app, current packaging/tooling inputs, exact cached model
files/manifests and prior constraints. D and old329 distribution version/RECORD
metadata are identical before/after. No W, old329 environment, owner P/L install,
original database, API port or browser/build process was changed by this gate.
Only NEW v367 scratch was mutated. No credentials entered public evidence.

Sources checked 2026-10-26: frozen source30/manifest, current packaging/canonical
wheel scripts and lock, prior329 build/export/install/base338/optional337 recipes,
cached model manifests and actual new installed source/runtime/ASGI observations.
FTH-016 support; no opportunity/experiment/ledger change; cash unknown.

Next/root: independently review this package evidence and keep the first failures
with the final result. Continue the separate typed browser, restart/outage/error,
quality/method/candidate/blind and other release gates. Combined no-inventory
browser expectations need the same source-authoritative v1 distinction; root was
notified, and this gate made no W test edit. All package processes are stopped.
No commit, publication, WSL or external action. QUIET.
