# Final-v2 frontend validation — retained failure plus separate diagnostic

Date: 2026-10-24. Parent-designated frozen candidate code eee951a / freeze record bce1111; actual API8402, final reader null threshold -8. No model/evaluator/corpus/application logic changes. No blind corpus access or services8401/8403 calls. No commits or public actions. Cash unknown; existing GT-01–GT-07 / FTH-016 context only.

## Main outcome: full final live acceptance FAILED
The unchanged production connected.spec.ts suite failed at ALL THREE viewports (1440x900,390x844,768x1024), EXIT1, frontend-live-final-v2.log. Existing supported question: How do I roll back the staging deployment? Actual response: refused, no sources, message The local reader found no supported answer in the selected current authorized sources. Recorded selector is local reader, reader-span-v1, threshold -8. The subsequent source-card focus timed out at120000ms because no citation exists. This is a legitimate expected-answer regression, not a locator defect. No original assertion was weakened and no frozen logic was changed.

Complete original failure contexts retained BEFORE diagnostic test output replaced local test-results:
frontend-final-v2-failures/connected-actual-ingestion-596d5-sions-identity-and-recovery-chromium.md
frontend-final-v2-failures/connected-actual-ingestion-596d5-sions-identity-and-recovery-mobile-chromium.md
frontend-final-v2-failures/connected-actual-ingestion-596d5-sions-identity-and-recovery-tablet-chromium.md
Also frontend-final-v2-desktop-error-context.md.

The actual persisted missing-reader503 row was successfully opened before this failure at each viewport. It shows Reader failed, decision error, no citations and no refusal styling. Its historical recorded threshold0 remains0 rather than inheriting current -8. Screens: connected-reader-error-{1440,390,768}.png. Existing downstream original-suite current-answer/source, streaming, upload, version/workflow actions and recovery stages were NOT reached in this final suite. Earlier pre-freeze3/3 live success remains separate evidence and cannot establish final acceptance.

## Other final gates actually run
- GROUNDTRUTH_BUILD_DIR=.next-coverage NEXT_PUBLIC_API_URL=http://127.0.0.1:8402 NEXT_PUBLIC_DEMO_MODE=false npm run build: EXIT0; frontend-build-final-v2.log. Next16.4.2 compile6.6s, TypeScript4.3s. Existing React18 deprecation warning remains. Generated next-env restored to HEAD/default references afterwards; no application source changed.
- Same build directory, PLAYWRIGHT_PORT=3506, GROUNDTRUTH_SCREENSHOTS=<S>/frontend-final-v2-screenshots npm run test:e2e:sample: EXIT0,3/3 (15.7s), frontend-sample-final-v2.log. Zero API/external requests, all route/keyboard/contrast/overlay/error checks pass.
- Default .next BUILD_ID and prerender-manifest SHA256 unchanged before build, after build, after ALL browsers. Records frontend-review-final-v2-{before,after-build,after-browsers}.json.
- npm run lint and npx tsc --noEmit after authorized diagnostic harness addition: EXIT0; frontend-diagnostic-{lint,types}.log. git diff --check -- apps/web: EXIT0.
- Test-owned3506 server ended normally after each suite. Final TCP probe confirms3506 NOT listening. Review3505/default.next preserved; API8402 left parent-owned. No other service touched.

## Separately authorized supplemental diagnostic
Parent explicitly authorized a separate browser-only factual thin slice after retaining all three original failures. Added ONLY these test harness files:
apps/web/e2e/coverage-diagnostic.spec.ts
apps/web/playwright.diagnostic.config.ts
No edits to original connected.spec.ts, application sources, frozen model/scorer/corpus, or parent-owned public evidence docs during final-v2 validation.

Command: GROUNDTRUTH_BUILD_DIR=.next-coverage PLAYWRIGHT_PORT=3506 GROUNDTRUTH_SEED_MANIFEST=<same private S>/frontend-seed-manifest.json GROUNDTRUTH_SCREENSHOTS=<S>/frontend-final-v2-screenshots npx playwright test --config=playwright.diagnostic.config.ts
Result: EXIT0,3/3 (22.5s), frontend-diagnostic-final-v2.log.

All operations used the real browser/UI/API boundary. No successful API mocks, direct model calls, provider calls or external browser requests. Each viewport uploads a distinct synthetic TXT with an emoji and the factual statement Anika authorizes bridge repairs, selects only that document, and asks Who authorizes bridge repairs? Actual JSON and SSE answers include Anika. Source opening shows the complete canonical quote, recorded span, content hash and codepoint offsets; reload reproduces the same hash and selected span. The actual recorded span here is the full205-codepoint paragraph [0,205), NOT a narrow Anika-only highlight. UI preserves that exact recorded support rather than fabricating a narrower span. The Unicode-nonzero-offset unit tests remain the separate evidence for narrower codepoint conversion.

Additional actual checks: scoped CEO-salary refusal with no source cards; previously persisted actual503 reader-error row displayed as error rather than refusal; network-aborted API outage displays failure without sample fallback; explicit retry restores documents; all six routes render, fit width and have no framework overlays/page errors. Network failure is the only deliberately intercepted response; no successful API result is mocked.

This diagnostic PASS DOES NOT ERASE the original rollback failure, pass full final acceptance, or establish general answer quality, benchmark quality or release readiness.

## Screens inspected
Directory: <S>/frontend-final-v2-screenshots, S=C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024.
- sample-source-{1440,768,390}.png inspected: canonical historical quote, explicit unknown selected-span metadata, identity wrapping and keyboard focus state.
- diagnostic-source-{1440,768,390}.png inspected: full canonical source + exact [0,205) selected span, immutable identity/hash, source/dialog wrapping. Mobile drawer scrolls to remaining identity fields; no horizontal clipping observed.
- diagnostic-answer-{1440,768,390}.png inspected: actual reader identity/revision/decision/threshold -8, answer/source cards and trace control fit. Mobile answer capture includes a visible keyboard-focused Skip to content control; this is a capture/focus-state artifact, while source/error/refusal captures are unobscured.
- diagnostic-reader-error-{1440,768,390}.png inspected: error styling/message, no citations, recorded historical threshold0, metadata wraps. This is a real stored503 outcome, not a fabricated response.
- diagnostic-refusal-390.png and diagnostic-outage-390.png inspected: distinct refusal versus operation failure, explicit absence of sample substitution, retry control.
Other recorded diagnostic screenshots at all three viewports remain available for refusal/outage.

## Remaining limits / next action
Main final live acceptance remains FAILED due to the reproducible rollback false refusal. Parent must keep this regression and milestone status visible and finish the independent frozen quality process; no claim here that quality gates pass. Final full version/workflow-action regression checks were blocked by the earlier legitimate answer failure. Parent may start the isolated3506 build later for review if desired; this agent left it stopped.

Current non-harness frontend diff includes parent-owned public/evidence/portfolio-connected.md; it was preserved without modification by this packet. No financial action, external communication, publication or receipt occurred.

## Representative original rollback refusal PNG added in granted capture window
Parent granted a bounded GET-only capture window before API8402 rotation. External scratch harness only: frontend-readonly-capture/playwright.config.cjs and capture-existing.spec.cjs. Existing isolated build was started through Playwright-managed3506; no build occurred. Command: GROUNDTRUTH_BUILD_DIR=.next-coverage npx playwright test --config=<S>/frontend-readonly-capture/playwright.config.cjs. EXIT0,1/1 (5.1s), frontend-original-rollback-capture.log. This check merely opened an existing failed query; it is NOT an answer-quality or acceptance pass.

Actual already-saved query identity b24409ea-2191-427c-95d8-05faedb5c9e6 was selected through the UI and fetched by GET. Proof verifies exact original rollback question, reader mode, recorded threshold-8, refused outcome/decision and sources[]. API non-GET operations were blocked; observed write attempts empty. No new query/model call/API write/source change. Proof: frontend-original-rollback-capture-proof.json (no key). Actual screenshot: frontend-final-v2-screenshots/original-rollback-refusal-1440.png, inspected readable. This is the actual original rollback refusal, not the diagnostic CEO refusal.

Playwright stopped its owned3506 process; a subsequent TCP probe confirmed3506 not listening. Parent notified immediately that8402 was released. No further service/browser/application work planned.

Parent-owned public evidence changes, including untracked answer-coverage-baseline.md and evidence/answer-coverage-v2 copies, were preserved without inspection of case contents or edits by this packet.

## Later isolated post-privacy integration check — parent observation

After both first comparison reports were sealed, another editor was confirmed
active in the original checkout. Parent created the isolated worktree
`C:/Projects/operation-fan-the-hammer/.tmp/groundtruth-coverage-20261024/delivery-worktree`,
branch `feat/groundtruth-answer-coverage-delivery`, from freeze-record commit
`bce1111`. It includes the separately reviewed diagnostic-authorization repair;
QA selection/scorer settings remain unchanged. Original8400/3505 was preserved.

Fresh isolated `npm ci`,72 units,lint/types and production build exited0.
Build command: `GROUNDTRUTH_BUILD_DIR=.next-coverage NEXT_PUBLIC_API_URL=http://127.0.0.1:8402 NEXT_PUBLIC_DEMO_MODE=false npm run build`.
No browser ran during that build. Then, from isolated `apps/web`:

- `GROUNDTRUTH_BUILD_DIR=.next-coverage PLAYWRIGHT_PORT=3506 GROUNDTRUTH_SCREENSHOTS=<S>/frontend-isolated-screenshots npm run test:e2e:sample`: exit0,3/3,27.4s.
- Same build/port/screenshots plus `GROUNDTRUTH_SEED_MANIFEST=<private S>/frontend-seed-manifest.json npx playwright test --config=playwright.diagnostic.config.ts`: exit0,3/3,27.6s.

All three standard widths, real reader-backed upload/JSON/SSE/history/source,
safe historical reader-error identity, refusal, explicit outage/retry, layouts,
keyboard and console assertions ran. Offline sample again asserts zero API or
external requests. Successful connected results were not mocked. Screens from
this later run are distinguished by the `postprivacy-` prefix in the evidence
directory. Parent inspected the mobile source highlight and desktop true error:
readable actual content, exact [0,205) full-paragraph highlight, historical error
threshold0 and no horizontal clipping in the inspected view.

These limited affected integration passes do not erase the original rollback
failure above. The full original suite was not rebranded or weakened. Its
downstream version/workflow stages remain unverified for the new reader profile.
