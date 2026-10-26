# Direct frontend gate observations

On2026-10-26 an independent context ran the actual current TypeScript and ESLint
commands. Both exited0. Exact argv, UTC times, runtime metadata, output hashes and
process exits are retained in [RESULT.json](RESULT.json) and the individual
invocation/result files. All232 frozen frontend inputs and the818-file
[engineering packet](../quality-repair-engineering-v30/README.md) remained unchanged.

This closes the earlier empty-log observation gap without rewriting historical407
or the v30 packet. [OBSERVATION.md](OBSERVATION.md) records the direct checks and
limits. The retained original run.py has host-specific provenance paths; it is
not presented as a fresh-clone launcher. Reproduce the native commands from
apps/web after installing its declared dependencies and generating Next types
through the normal build workflow.

Run `python -X utf8 -B check.py` here or from another directory to check the copied
observations using only the standard library. This checks retained evidence; it
does not rerun native commands. No model, API, browser, build or service was
launched by this export. Unseen answer-quality acceptance remains open.
