# Two-reader catalog integration — bounded independent review

Reviewed 2026-10-24, isolated delivery-worktree only, source diff against dfdc0e4. Read-only. No source/profile/corpus/runtime/service mutation or quality evaluation. Original checkout untouched. Source hashes recorded in reviewed-catalog-source-hashes.json. New model quality was not evaluated by this reviewer.

## Material finding: P2/high confidence — Unmanifested tokenizer asset overrides verified catalog files

Location: apps/api/app/services/answer_reader.py:160-177; catalog file sets in apps/api/app/reader_catalog.py.

The loader verifies that the manifest names exactly the catalog files, validates those files, then gives the whole directory to AutoTokenizer.from_pretrained. Both approved specs omit tokenizer.json. If such a file exists beside the verified files, the real fast-tokenizer loader can prefer it over the checked vocab/merges assets. Runtime then reports the approved identity and ready state despite loading unverified tokenizer content. A stale file from another setup is sufficient; no browser-selected model path or remote code is needed.

Independent reproducer probe_unmanifested_tokenizer.py builds a scratch directory from the official locally downloaded RoBERTa tokenizer files. It writes a manifest matching all six declared files, then adds an unmanifested tokenizer.json with one extra vocabulary marker. Actual offline AutoTokenizer loading returns that marker; LocalReader metadata says ready. The model weight boundary alone is mocked (scratch placeholder weights), avoiding model inference; tokenizer selection, filesystem and manifest hashing are real. Expected-safe assertion fails, exit1. Exact output unmanifested-tokenizer.log shows marker_loaded=true/readiness=ready. No official/model-runtime directory was modified.

This finding does not establish that the current worker asset directory or running model grid used an extra file. Parent reports that actual root has the six downloaded assets plus README/manifests/cache and no known tokenizer.json. Preserve that distinction and any grid qualification. Smallest mitigation is to reject or explicitly pin every extra tokenizer/model-affecting asset before from_pretrained can consume it, rather than validating only a subset of a directory. Reproducing a failure in scratch does not authorize mutation of frozen measurement source.

## Independently verified checks

All Python commands use original .venv interpreter only, PYTHONPATH=isolated delivery-worktree/apps/api, PYTHONDONTWRITEBYTECODE=1. No external network; actual tokenizer probe also sets Hugging Face/Transformers offline flags.

- Original10 independent review assertions unchanged: `python -m pytest <review>/test_independent_question_boundaries.py <review>/test_independent_added_guard_boundaries.py -q -s -p no:cacheprovider`: exit0, **10 passed in 3.94s**, independent-ten-final.log. Previous qualifier, temporal, currency and relationship cases are repaired for those exact boundaries.
- `python -m pytest apps/api/tests/test_reader_catalog.py apps/api/tests/test_reader_model_selection.py apps/api/tests/test_answer_reader.py -q -p no:cacheprovider --basetemp <review>/catalog-integration-tests-tmp`: normal local permissions, exit0, **51 passed in 16.76s**, catalog-integration-tests.log. Includes catalog immutability, explicit downloads/CLI selection via mocked external hub seam, runtime selected identity/local-only loading, cancellation/errors, Unicode offsets/windows and canonical span validation. Existing Windows sandbox temp-ACL limitation justifies the dedicated normal-permission run; no service used.
- `python <review>/check_catalog_failure_metadata.py`: exit0. Independent unknown revision, wrong manifest model, wrong manifest revision, and missing required file-set cases all fail as execution errors with readiness error, without fallback. Unknown revision reports model=null; recognized but bad assets retain configured RoBERTa identity alongside error status. Log catalog-failure-metadata.log.
- `python <review>/probe_unmanifested_tokenizer.py`: exit1 at the deliberate safety assertion, as detailed above. Real local tokenizer, mocked model boundary, no inference/download.
- `git diff --check --` reviewed production files: exit0, only reader_setup.py CRLF normalization warning.

## Other inspected boundaries and limits

Catalog resolves only two exact revisions, returning frozen dataclass specs with immutable file tuples; unknown aliases do not select MiniLM fallback. Runtime validates identity/file sets and path containment, loads local safetensors with remote code disabled, sends model to CPU and keeps inference lock/request-local features. Existing source offset bounds and SourceCitation canonical quote validation remain. No new material issue found in those inspected paths beyond unmanifested asset selection.

The tested assertion count is not a quality score, completeness/entailment guarantee, production capacity result or release approval. No blind validation occurred in this review. Parent owns any later loader repair, source refreeze and comparable development/model measurement, preserving interrupted or exposed observations honestly.
