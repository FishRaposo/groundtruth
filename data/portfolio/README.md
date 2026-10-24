# Frozen synthetic runbooks and authored evaluation

The single canonical corpus is packaged in
[`app/portfolio/assets`](../../apps/api/app/portfolio/assets). Load it with
`from app.portfolio import load_corpus`; execution never depends on this checkout
or a sibling project. The loader verifies file checksums, source content hashes,
source quotations, IDs, versions, counts and family-separated splits.

All prose, questions and labels are **agent-authored synthetic fixtures** owned by
this project and released under MIT. No human review, general model validation,
operational safety approval or real customer usage is claimed. Runbooks contain
invented test markers, not real credentials. Repeated paraphrases of the same
fact are correlated cases, not 100 independent real-world tasks.

## Frozen contract

- `documents.json`: 12 logical runbooks, immutable versions and declared
  ownership/workspace/visibility. Two rollback documents retain a retired and
  current version. Two pairs carry explicitly curated contradictory procedures;
  this does not establish general contradiction detection.
- `cases.json`: 100 labeled questions. Development: 12 answerable, four
  unanswerable, two conflicting/stale and two adversarial. Held-out: 48/16/8/8.
  Related document/version families stay within one split.
- `profile.json`: initial top-k five and refusal threshold 0.35, declared before
  measurement and **not empirically selected**. Keep held-out results closed
  while selecting settings from development evidence.
- `manifest.json`: authorship, license, expected counts, revision and SHA-256
  checksums of the three assets. v2 manifest hash:
  `0be7e127c84aabf048d69edae3e5cc430e7a65114f45ca93fd27365723c3315f`.

Freeze correction before any measurement: v1 restricted ordinary answerable
questions to their target document, which would trivialize recall. v2 searches
all authorized corpus documents for every ordinary answerable case. Only
permission, conflict and unsupported-question contracts retain explicit filters.
The execution ledger preserves v1 and its checksum. No held-out measurement
informed this correction.

## Real HTTP evaluation

Install the actual API package first. The owner-operated seeder writes an ignored
JSON manifest; never commit API keys or pass them as command-line arguments.

```powershell
python scripts/evaluate_portfolio_retrieval.py --seed-manifest .tmp/seed.json --split development --output .tmp/development.json
python scripts/evaluate_portfolio_retrieval.py --seed-manifest .tmp/seed.json --split held_out --selection .tmp/selection.json --output .tmp/held-out.json
```

The seed manifest has `schema_version: 1`, loopback `api_url`, runtime `profile`,
`principals` mapping aliases to `{api_key}`, and `documents` mapping logical IDs
to `{document_id, versions: {"1": {content_hash}}}`. Uploads must contain the exact
frozen version text. The evaluator checks supplied hashes against the packaged
snapshots before requests; source content supplied in an API response cannot
establish its own truth.

The held-out selection artifact must contain `selection_basis:
"development_only"`, `corpus_manifest_sha256`, `development_report_path`,
`development_report_sha256`, `settings: {top_k: 5, refusal_threshold: ...}` and
`frozen_at`. Relative development-report paths resolve against the selection
file. Changing settings requires new development evidence and a new frozen
selection before measuring held-out cases. The server must actually apply the
selected settings; the client does not grant itself a threshold override.

The four methods are keyword, vector, hybrid RRF and heuristic-reranked hybrid.
Reports retain per-case ranks, HTTP latency, provenance, search scope and errors.
Recall@5/MRR use source **and version** identity from ordered retrieval evidence;
unknown versions do not count as hits. Citation correctness additionally checks
content hashes, an exact authoritative passage and its authored fact in the
extractive answer. Refusals/denials do not receive fabricated retrieval scores.
Exit 0 means every declared fixture contract passed, 1 means observed contract
failures, and 2 means invalid input or execution errors. These are fixture checks,
not an automated certification of general answer quality.

## Measurements and deferred indexed matrix

`scripts/benchmark_portfolio_retrieval.py` queries the actual HTTP application and
independently counts chunks through `GROUNDTRUTH_BENCHMARK_DATABASE_URL`.
Credentials stay in environment/ignored manifests. Preseed datasets under
`benchmark.datasets` with `chunk_count`, actual UUID `document_ids`, `questions`
and optional principal alias. The script does not invent an indexed corpus.

The full PostgreSQL matrix requires actual 1k/10k/100k chunk datasets, pgvector,
HNSW/GIN indexes and separately captured natural, unforced application query-plan
evidence. It uses four methods, concurrency 1/10, three repeats, 20 warm-ups and
100 measured requests per condition. `--portable` explicitly measures a small
nonindexed SQLite smoke profile: four methods, concurrency one, one repeat, two
warm-ups and ten measurements per method. It cannot satisfy indexed acceptance.

```powershell
python scripts/benchmark_portfolio_retrieval.py --seed-manifest .tmp/seed.json --portable --output .tmp/portable-benchmark.json
```

Raw observations, actual chunk counts, runtime/model metadata and checksums
accompany results. Retrieval timing is null when the API supplies no distinct
retrieval duration; full HTTP latency must not be relabeled retrieval latency.
Warm runs do not establish cold OS-cache performance. WSL/PostgreSQL/Redis and the
indexed matrix remain deferred while development proceeds without WSL.
