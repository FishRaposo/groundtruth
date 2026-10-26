# Runtime-byte check repair — V493

The first paired attempt487 stopped at its first runtime-check before API start, migration, ingestion or evaluation. It produced no quality report or predictions. The sealed partial directory is retained unchanged.

Freeze446 hashes owning distribution RECORD raw bytes. The old worker used Distribution.read_text, which normalizes CRLF on Windows; all92 versions/inventory and raw bytes still matched the freeze in the separate metadata-only diagnosis491. V493 changes only that comparison to the owning distribution's RECORD read_bytes; it never scans vendored RECORD entries or weakens version/inventory/Python checks. Controller and frozen-inputs bytes remain476-identical; source/scorer/settings/models/labels remain frozen.

Actual canonical optional interpreter command against new493worker runtime-check/frozen446: before repair exit2 (runtime-red.log); identical command after repair exit0, runtime_packages_verified92, model_importsfalse (runtime-green.log). Seven pure metadata canaries pass: CRLF raw acceptance; changed bytes, version, missing distribution, missing owning RECORD, unrelated vendored metadata and changed Python rejection. No application, model, API or network command ran. No candidate/blind acceptance is claimed.

Independent review is required before another execution. No existing493file should be overwritten; test fixtures are retained. Cash unknown, FTH-016 support; no publication/owner-instance refresh/WSL.
