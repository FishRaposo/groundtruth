# E510 direct current frontend type/lint gates — QUIET

2026-10-26. **Both actual current gates pass with independently captured process exit0.** This closes E506's missing direct current type/lint observation. It does not retroactively establish historical407 exit codes or change the immutable818-file engineering packet. Quality remains OPEN; unseen NOT accepted.

Only new Q/`frontend-direct-gates-v510` files were written. W is `C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024/delivery-worktree`; Q is its sibling `quality-v6`. Parent owns integration and shared handoff. FTH-016 support; no opportunity/experiment/cash record change; cash unknown.

## Actual sequential commands

Both commands ran from W/`apps/web`, using the existing local executable `C:/Program Files/nodejs/node.exe` and local tool entrypoints directly, without npm/npx or installation:

| Command after node.exe | UTC start | UTC finish | Actual exit | stdout / stderr |
| --- | --- | --- | ---: | --- |
| `W/apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false` |22:12:43.079397Z|22:13:05.918512Z|0|0bytes /0bytes|
| `W/apps/web/node_modules/eslint/bin/eslint.js . --max-warnings=0 --no-cache` |22:13:05.919512Z|22:14:23.153074Z|0|0bytes /0bytes|

`typescript-invocation.json`/`typescript-result.json` and `eslint-invocation.json`/`eslint-result.json` record exact absolute argv, cwd, UTC boundaries, observed subprocess returncode, duration and stdout/stderr byte lengths/hashes. The four exact log files are empty because the commands produced no output; **success is established by actual exit records, not inferred from empty logs**. `RESULT.json` consolidates the observed results and preservation checks. The wrapper itself exits0 with no intermediate failed attempt.

Node runtime query also exits0. `runtime.json` and raw `node-runtime.stdout.log` identify **Node v24.21.0,win32,x64; TypeScript5.9.3; ESLint9.39.5**, along with the Node binary and tool-entrypoint SHA256s. These are local runtime/version observations; no package/version lookup or external research was performed. Concurrent CPU activity makes these durations unsuitable as performance benchmarks.

## Frozen configuration and preservation

Before either gate, all **232 current frontend source inputs** matched the exact restored430 manifest pinned by freeze446: `39e835a9dfa0a282a5f3632dd7dc30cbb5469b231b09e73286e7442b4bc56d30`. Current canonical next-env and tsconfig were used as-is:

- `next-env.d.ts`: `1862ac4bbbc5192d4bf562161df66ea547ed3e67173100656ab606ae9797db2b`
- `tsconfig.json`: `7d2589ecab6695ab0c070f5f0b6377d1ab1fbf9c81523aaaad83ade32d02ba01`

Both canonical next-env references already existed: `.next/types/routes.d.ts` and `.next/types/root-params.d.ts`. Their exact hashes are recorded before/after in `generated-prerequisites-before.json`/`generated-prerequisites-after.json`; both remain unchanged. No type generation, build, source/config repair or temporary config substitution was needed.

After both commands, **232/232 source hashes still equal the before map and frozen manifest**, with zero source changes. All **818 engineering packet file hashes** remain equal before/after, including manifest SHA `99d849a0a53cc454e1096d7da666fbafad9d66ba1ff15db1025ae2788b0bbe57`.

- `source-before.json` = `source-after.json`, SHA256 `eb34f39ac92d11be0b53cd17796259a82659a023d970199029537fbbc1ffae11`
- `bundle-before.json` = `bundle-after.json`, SHA256 `40d0370247b19a86b83d9565dd66941817e674e631b0f80f021829556071ef26`
- `RESULT.json` SHA256 `0b68c3801f396afc749e4bcd47fc30c4a771796b46d7ccb049adc6c38fdb341e`

## Scope and handoff

No full862-unit rerun, build/typegen, browser, API/model/service action, network operation, npm install, port/PID/CIM query, private seed/database access, fresh author/label/pair directory or outcome read, staging/commit or existing packet rewrite occurred. Historical407's integrator-reported status remains preserved as historical evidence; this is a separate direct supplement bound to the unchanged current frozen232 input set. Passing type/lint does not establish unseen answer quality, release readiness, hosted CI or runtime behavior.

Reproduction wrapper: `W/.venv/Scripts/python.exe -S -X utf8 -B Q/frontend-direct-gates-v510/run.py` from this new review directory, final exit0. The wrapper captures exits and exact logs sequentially and stops without repairing code/config on any missing prerequisite or gate error.

Next owner: parent may append this direct type/lint supplement separately, preserving the818-file bundle and E506 historical limitation. All owned subprocesses have completed. **QUIET.**
