# Recorded commands and their evidentiary limits

Logical aliases: W = GroundTruth source checkout, Q = captured evidence root,
P = actual cached-model interpreter, D = existing development interpreter,
WEB = W/apps/web. Ports were loopback API8402/frontend3506. This transcription
was prepared **after execution**, not captured as contemporaneous runtime argv.
The original API argument array is separately bound by digest in
`bindings/launch-arguments.logical.json`; its exported paths are logical aliases.

Production build296, from WEB with the captured build environment:

```powershell
$env:GROUNDTRUTH_BUILD_DIR='.next-quality-v296'
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8402'
$env:NEXT_TELEMETRY_DISABLED='1'
$env:NEXT_PUBLIC_DEMO_MODE='false'
npm.cmd run build
```

Migration/serve/seed297, from W using the actual retained argument array, with a
new disposable data directory replacing285's directory:

```powershell
& $P -B scripts/portfolio_local.py migrate @taskArgs
& $P -B scripts/portfolio_local.py serve @taskArgs
& $P -B scripts/portfolio_local.py seed @taskArgs
```

Serve was long-running; migration/seed exited0. The launcher clears provider
credentials and selects the recorded CPU/local/extractive profile. Generated
disposable keys stayed in private seed manifests.

Actual production browser297, after successful build and production start:

```powershell
$env:GROUNDTRUTH_BUILD_DIR='.next-quality-v296'
$env:NEXT_TELEMETRY_DISABLED='1'
npm.cmd run start -- --hostname 127.0.0.1 --port 3506
# Separate test process; no concurrent build:
$env:GROUNDTRUTH_SEED_MANIFEST='{PRIVATE297}/seed-manifest.json'
$env:GROUNDTRUTH_SCREENSHOTS='{Q297}/screenshots'
$env:PLAYWRIGHT_PORT='3506'
$env:PLAYWRIGHT_EXTERNAL_SERVER='1'
$env:CI='true'
npx.cmd playwright test --config=playwright.combined.config.ts --workers=1 --retries=0 --output='{Q297}/test-results'
```

Observed exit0: `3 passed (46.8s)`. The list reporter did not persist `info.attach`
observation buffers. Q298 separately ran its real read-only HTTP/browser capture:

```powershell
node '{Q298}/capture.mjs'
```

Capture exit0; nine completed, three refused, nine source-response DTOs and nine
focused screenshots. Twelve selected screenshots are exported across both packets.

Restart300 used a copy of sealed297 data. Actual missing/repaired API starts on
the clone differed by support-directory selection. The HTTP probe ran once for
each phase:

```powershell
& $D -B '{Q300}/probe.py' --phase missing
& $D -B '{Q300}/probe.py' --phase repaired
```

Both phase probes exited0. Raw saved normal/SSE/error/history records are exported
losslessly; request packet timing and a browser failure UI are not established.

Independent299/304 pure replays used their own read-only SQL snapshots and actual
retained trace; their saved reports/logs are included. This export's replay instead
uses the frozen API archive and the newly serialized authoritative public snapshot
subset, so future working code need not match historical code:

```powershell
& $D -B replay.py --canonical
```

That last command is the export validation, not another browser/API/model run.
Its observed result is recorded separately in `export-validation.json`.
