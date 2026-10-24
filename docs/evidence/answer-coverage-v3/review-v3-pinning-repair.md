# Pinning repair — independent bounded recheck

2026-10-24, isolated delivery-worktree only. No source/service/assets/profile/corpus mutation, inference, quality evaluation or download by reviewer. Original probe_unmanifested_tokenizer.py and its failing log remain unchanged. New probe_unmanifested_tokenizer_repaired.py tests the repaired contract. Source binding: reviewed-pinning-repair-hashes.json.

The earlier P2 unmanifested-tokenizer preference defect is repaired for the exercised boundary. No further material defect found in this bounded patch. Directory inspection now rejects unlisted regular files before importing Transformers, while permitting the explicit runtime assets and inert README/license/download/runtime manifests. Ordinary cache directories do not override this root-file allowlist.

Independent command:

`<original>/.venv/Scripts/python.exe <review>/probe_unmanifested_tokenizer_repaired.py`

Exit0; log unmanifested-tokenizer-repaired.log. Uses the exact original scratch directory whose tokenizer.json was actually preferred by Transformers in the RED probe. The declared manifest/file digests still match. `_load` now rejects clearly with `Reader directory contains unverified files; use a clean setup directory.` before any model/tokenizer import (recorded imports=[]). The async select boundary fails as an execution error with no fallback and readiness=error. No actual model selection or inference occurs.

The same probe checks both actual approved MiniLM and RoBERTa cache roots: real directory inventory, manifest identity/file set, path containment and content digests pass the new guard. Transformer/tokenizer/model construction is substituted only at the boundary, so this confirms directory/hash compatibility rather than fresh real-model loading. Both caches include only their expected assets plus permitted README and manifests. No cache files were changed.

`<original>/.venv/Scripts/python.exe <review>/check_catalog_failure_metadata.py`

Exit0; catalog-failure-metadata-after-pin-fix.log. Unknown revision, wrong manifest model, wrong manifest revision and missing required file-set cases still produce execution errors/readiness error, preserving selected/unknown identity without fallback. Original venv supplies interpreter only; PYTHONPATH points to isolated apps/api and bytecode writes are disabled.

Earlier independent10 boundary assertions and51 catalog/model-selection/answer-reader tests passed before this narrowly scoped guard repair. Parent separately reports its86 affected checks passing after repair; that86 count was not rerun by this reviewer and is not represented as independent evidence here.

The interrupted grid and first complete development report are parent-owned evidence. This review did not inspect/replace/re-score them, resume a grid or make a new model-quality/unseen-validation claim. Parent owns source refreeze and fresh comparable development grids.
