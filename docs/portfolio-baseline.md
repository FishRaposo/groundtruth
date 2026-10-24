# Project 05 baseline and environment prerequisite — 2026-10-23

Implementation branch: `feat/groundtruth-portfolio`. Application baseline:
`a8dc3570e3e66320b716d31a4791e957f14d7cfa`; the clone was clean before creating
the branch. This record currently covers environment preparation, not completed
GT-01–GT-07 acceptance. No application behavior has been changed.

## Confirmed milestone

Follow the owner's approved [GroundTruth plan](../../plans/groundtruth.md) and
[portfolio index](../../PORTFOLIO_PLAN.md): real scoped retrieval, PostgreSQL/
pgvector plus Redis worker, pinned local semantic embeddings, explicit portable
mode, durable ingestion/version/source evidence, connected application and
independent recruiter preview. Use ports 8400/3505/5545/6385 and new disposable
data. Preserve sibling projects and services. No paid providers/publication or
automatic Windows restart.

The approved embedding model is `sentence-transformers/all-MiniLM-L6-v2`, revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, with 384 dimensions. It has not yet
been downloaded or used in an evaluation. Corpus, benchmark and application
acceptance remain unperformed.

## Observed Windows prerequisite

Initial inspection found no Docker Desktop, PostgreSQL or Redis executable.
`winget list --id Microsoft.WSL --exact --disable-interactivity` reported a WSL
2.7.8 registration, but `wsl --status` returned `REGDB_E_CLASSNOTREG` and no WSL
service was present. The normal agent token is not an administrator;
`HypervisorPresent` is true. Inspecting Windows optional features requires UAC.

The prepared administrator script was launched through Windows UAC. It found
both `VirtualMachinePlatform` and `Microsoft-Windows-Subsystem-Linux` **Disabled**,
enabled them with `-NoRestart`, and recorded `restart_required: true`.
The official WSL 3.0.3 x64 MSI then installed with **exit 0**, using `/norestart`.
The helper's final status is `waiting_for_owner_restart`; no restart was issued.

Before execution the MSI's Microsoft signature was Valid and its SHA-256 matched
the official release digest:

`ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211`

The official Docker Desktop installer is version 4.96.3.244472; its Docker Inc
signature was Valid, with downloaded SHA-256:

`3d8adad4f6c86583e0b00ea19a76197c51ccf5c83437c9ed775b739756452507`

Per-user installation used `install --user --quiet --accept-license --backend=wsl-2`
and completed with **exit 0**. The installed CLI reports
`Docker version 29.9.2, build a82e528`. The engine was not launched; its readiness
and actual PostgreSQL/Redis operation remain separate checks after owner restart.

Sources checked 2026-10-23:
[Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/),
[official WSL 3.0.3 release](https://github.com/microsoft/WSL/releases/tag/3.0.3),
actual signature/hash checks, Windows feature results and MSI exit/log.
No project defect is inferred merely from an unavailable service.

## Baseline checks still required

Python 3.12.14 was selected for an isolated `.venv`; system Python 3.14 remains
unchanged. Declared API/dev/PostgreSQL/Redis dependency installation completed
with **exit 0**; `python -m pip check` reports no broken requirements. Locked
frontend `npm ci` completed
with **exit 0**: 587 packages added, 588 audited. Its audit inventory reports
12 findings (4 moderate, 7 high, 1 critical); runtime/development classification
and relevant repairs remain part of the baseline/implementation milestone.
An `unrs-resolver` install-script allowance warning is retained in the log.
Installation is not a passing test or package verification. Native local model
dependencies/download remain separate.

After restart, run and record the current full Python/coverage, Ruff/formatting,
Pyright, original golden evidence, forbidden scan, source/wheel/isolated install,
frontend units/lint/build and existing browser gates before application edits.
Read installed Next.js documentation before modifying framework behavior.

Then preserve real failing regressions for the inspected session/filter,
authorization/history, request-local trace, memory/citation and version-embedding
defects. No new regression, retrieval-quality result, benchmark, PostgreSQL query
plan, queue delivery or end-to-end success has been established yet.

## Resume

The durable state, prepared administrator script, verified installers, command
logs and JSON results are in
`C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-20261023` outside this clone.
Read `STATE.md` first. Keep the task branch and existing data; do not reset other
projects or reuse their databases. After the owner restarts Windows, verify WSL,
Docker engine, actual pgvector/Redis containers, then continue the saved milestone.

Supports existing FTH-016. No opportunity/experiment or cash ledger was changed;
cash status remains unknown. Owner supplies the required Windows restart; agent
owns the remaining authorized engineering and verification.
