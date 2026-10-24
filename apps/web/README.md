# GroundTruth web

Next.js frontend for the GroundTruth portable application. Two data sources:

- **Sample** — interactive fixtures rendered without a backend or network calls;
  the source selector never substitutes sample data for connected errors.
- **Connected** — real requests against the local portable API
  (`NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8400`) with the disposable
  key from `scripts/portfolio_local.py seed`.

## Commands

```bash
npm ci                 # locked install (package-lock.json is authoritative)
npm test               # Vitest unit suite
npm run lint           # ESLint, zero warnings
npm run build          # production build into .next (standalone)
npm run check          # units + lint + build + sample/a11y Playwright suites

npm run test:e2e:chromium       # offline sample + axe suites (chromium + mobile-chromium)
npm run test:e2e:live           # connected suite; needs GROUNDTRUTH_SEED_MANIFEST
npx playwright test --config=playwright.diagnostic.config.ts  # supplemental reader evidence
```

The connected and diagnostic suites require a real seeded API. Use the
portable profile from the repository root:

```bash
python scripts/portfolio_local.py migrate
python scripts/portfolio_local.py serve   # http://127.0.0.1:8400
python scripts/portfolio_local.py seed    # writes .tmp/portfolio/seed-manifest.json
export GROUNDTRUTH_SEED_MANIFEST=.tmp/portfolio/seed-manifest.json
```

The diagnostic spec additionally expects `reader_error_query_id` in the
manifest — a durable error row produced by an actual request against an API
configured with a missing reader directory. Sample journeys assert zero
external/API requests; connected success uses actual application responses.
