# GroundTruth engineering evidence — v30

**Quality OPEN. Unseen NOT accepted.** This bundle preserves dated local synthetic engineering evidence; it is not a release, general-quality or capacity verdict.

| Retained gate / observation | Bounded result |
| --- | --- |
| Python385 | 2806 passed,1 PostgreSQL-only skip;82.72% coverage |
| Frontend407 / build430 | 862 unit passes; final type/lint exit0 recorded; build exit0 |
| Package367 + selected390 | Isolated archive/install/ASGI evidence; margin0 historical vs margin2 selected |
| HTTP400 / concurrency420 | Restart,SSE,cancel; three overlapping isolated positive requests |
| Concurrency423 | Producer capture only; independent review absent |
| Combined456 / outage481 / offline485 | Reviewed engineering observations;21 +36 +9 current screenshots |

Run `python -X utf8 -B check_bundle.py` from any directory. It uses only the standard library and this bundle: hashes, bounded gzip, immutable source/package members, selected persisted-record bindings, gate counts and PNG dimensions. It performs no API/model/browser/service operation or gate rerun. [RESULTS.json](RESULTS.json) keeps qualifications and current counts explicit; [SOURCE-BINDINGS.json](SOURCE-BINDINGS.json) resolves copied code locally.

Raw observations in `raw/` and exact independent reports in `reviews/` are immutable copies; large originals use deterministic gzip with decoded hashes/lengths in [manifest.json](manifest.json). Historical host paths inside originals are provenance, not replay dependencies. Private keys/manifests, SQLite files, models and installed environments are excluded. Source31 runtime/tool code and all232 frontend430 input files are copied; omitted source31 test-only files remain listed rather than implied present.

The old466 outage failure remains unexplained;485 closes the fresh offline screenshot gap but not every visual state. Root463 governance checks failed separately. No fresh blind labels/source/cases or pending pair directories were read:487's setup failure before API/models/queries is integrator-reported and yields no quality report.493 protocol/metadata work is outside this engineering packet. No provider,WSL,PostgreSQL,hosted-CI,human or capacity acceptance is claimed.
