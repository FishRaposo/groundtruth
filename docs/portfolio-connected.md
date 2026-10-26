# GroundTruth: run the actual local application

This workflow uses real HTTP requests, stored documents, model embeddings,
conversation records and immutable source snapshots. The visual **Interactive
sample data** experience is independent and explicitly simulated. No provider
account or WSL is required for the portable profile.

The reader repair is **not accepted for answer quality**: the earlier frozen
MiniLM comparison reached55/120 answers and77/80 negatives, below the required
114/120 and80/80. Its original rollback browser journey also failed. Read
[reader verification](answer-coverage-verification.md) before interpreting runtime
readiness as quality. The existing8400/3505 review instance remains on its prior
version; the isolated follow-up uses8402/3506 and a separate disposable database.

## Install and prepare

From the repository root, use Python 3.11+ and Node 20.19+ (the observed Windows
environment used Python 3.12 and Node 24). Activate an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e "apps/api[dev,embeddings,reader,support]"
python -m app.model_setup --directory .tmp/models/minilm
python -m app.reader_setup --model roberta --directory .tmp/models/reader-roberta
python -m app.support_setup --directory .tmp/models/support
python scripts/portfolio_local.py migrate
```

The model download is explicit. It obtains the pinned
`sentence-transformers/all-MiniLM-L6-v2` revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, safetensors and tokenizer assets,
records SHA-256 hashes and the Apache-2.0 license. Runtime validates the local
manifest/files, loads CPU-only with remote code disabled and uses cached files.
Missing/broken assets produce errors; they never silently become hash vectors.
The model emits 384 dimensions and accepts at most 256 tokenizer tokens per
sequence; token-aware chunks retain exact source offsets.

Reader assets are a separate explicit download:
The current development launcher uses `deepset/roberta-base-squad2` at revision
`adc3b06f79f797d1c575d5479d6f5efe54a9e3b4`, licensed CC-BY-4.0.
Its selection comes from the predeclared development comparison, not a new blind
quality pass. To retain MiniLM, download with `python -m app.reader_setup --model
minilm --directory .tmp/models/reader` and pass `--reader-model minilm` to every
helper action. MiniLM revision remains
`934656cdda79824eabf503ed56e15c01ddbdbe3f`.
The setup command records asset hashes and attribution. Runtime validates that
manifest and loads safetensors on CPU with remote code and downloads disabled.
Installing the `reader` extra alone does not download weights. Missing or damaged
configured reader files produce a readiness/execution error; no lexical fallback
is substituted. See [third-party attribution](../THIRD_PARTY_NOTICES.md).

Reader serving also requires the explicitly prepared local support classifier,
`cross-encoder/nli-deberta-v3-small` revision
`70de96bd327ef95839a8bd9f6299875cae396433`. The support setup command records its
Apache-2.0 attribution and asset hashes. Inference uses cached CPU assets and
does not download during a request. Classifier scores remain uncalibrated.

The library retains `all_units_nli_v1`. After development qualification, bare
reader-serving through this helper selects the measured composite/activity/copy/
context-v2 recipe at QA4/NLI2. Explicit profile flags retain legacy defaults for
omitted peers; this preserves existing explicit legacy commands. To reproduce the
complete selected recipe rather than mix profiles, use all of these together:

```powershell
python scripts/portfolio_local.py serve --answer-selection reader --reader-model roberta --reader-threshold 4 --answer-support local_nli --support-margin 2 --answer-proposal-profile qa_plus_source_patterns_v1 --role-scope-policy ordinary_session_activity_v1 --procedure-verification-profile source_declared_procedure_copy_v1 --source-context-policy scoped_note_context_v2
```

The [complete DEV80 evidence](evidence/quality-repair-dev-v30/README.md) includes
every margin arm and all four retrieval methods. This is development qualification;
fresh blind acceptance remains open. The source-copy profile requires reader,
local NLI and extractive generation together. Subject,
applicability and independent factual answers still require NLI; recognized
source-declared instruction blocks additionally require complete ordered literal
coverage and a certificate checked against the actual rendered and saved answer.
Exact source-copy checks are not represented as model entailment. Unsupported
declarations, unresolved requirements, conflicts and invalid evidence refuse or
fail visibly. Selecting it does not establish
the separate answer-quality gate or promote the existing review instance.

In separate terminals, using the same activated environment:

```powershell
python scripts/portfolio_local.py serve
```

```powershell
python scripts/portfolio_local.py seed
```

The API binds to `127.0.0.1:8400`. The helper uses only
`.tmp/portfolio/groundtruth.sqlite` and `.tmp/portfolio/uploads`; it does not reset
existing databases. Seeding requires a new disposable database/manifest and sends
12 synthetic runbooks through the real ingestion and version APIs. Trusted local
fixture setup creates API identities and declared collection grants; it never
manufactures chunks or successful job results.

The private `.tmp/portfolio/seed-manifest.json` contains disposable keys. Enter
`principals.admin-a.api_key` through the browser's **Connection** dialog. Never
commit or publish that file. `viewer-a` and `custodian-b` exercise reader and
separate-workspace boundaries. The helper prints no key values.

Build once, then serve the frontend in another terminal:

```powershell
cd apps/web
npm ci
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8400"
$env:NEXT_PUBLIC_DEMO_MODE="false"
npm run build
npm run start -- --hostname 127.0.0.1 --port 3505
```

Open `http://127.0.0.1:3505`, choose **Connection**, enter the local key and select
**Connect application**. API keys remain in tab session storage, outside URLs,
bundles and public evidence. Source preference persists separately. Changing
identity/source aborts obsolete requests and clears incompatible private views.

## Actual investigation

1. Create a conversation and ask the staging rollback question. Answers are
   labeled **source extracts**, not model-generated reasoning.
2. Open a numbered citation. Inspect the exact passage, document version, content
   hash and current/superseded status. Reload the saved query URL.
3. Inspect retrieval candidates and method metadata. Keyword, vector, hybrid RRF
   and heuristic lexical reranking use the same authorized pipeline. Ranks are
   support/ranking signals, not calibrated probabilities.
4. Upload TXT/PDF/Markdown/HTML/DOCX; inspect the durable job. Submit replacement
   content, compare versions and restore a snapshot as a new content revision.
   Reindexing changes representation without inventing a content revision.
5. Ask a scoped question and inspect normal versus SSE results. Empty filters
   mean no documents; filters never expand the caller's permissions.
6. Start the seeded review and approve, reject or cancel it. Inspect real workflow
   events and administrator audit/usage records. Ordinary readers receive clear
   administrator restrictions.
7. Stop/restart the API with the same directory. History, versions, source
   snapshots and terminal jobs remain stored. Retry failed/interrupted work
   explicitly. A failed connected request remains an error with Retry and an
   explicit switch to sample mode.

New uploads are private to their key owner. Workspace identity comes from key
metadata, not a supplied workspace header. Public/organization collection read
access does not permit writes. Historical unowned evidence is unknown and
administrator restricted. Revocation is checked again when reading history,
conversation context and citations; old answers cannot bypass changed access.

## Explicit modes and limits

For portable deterministic operation, pass `--embedding deterministic` to every
helper action with a separate `--data-dir`. Hash embeddings are labeled and are
not semantic retrieval. Switching embedding representations requires explicit
reindexing; unknown/mismatched vectors are not padded, truncated or backfilled.
Library `legacy` defaults preserve original golden behavior; authenticated HTTP
must select connected modes and does not expose unscoped legacy execution.

The helper selects **Local extractive reader** with semantic embeddings. It uses
the pinned SQuAD2 QA model to locate answer offsets, compares span/null logits,
and copies the surrounding source passage. It generates no new factual prose.
Raw scores are uncalibrated; this is not an entailment or accuracy guarantee.
`--reader-dir`, `--reader-threshold` and `--answer-selection reader` make the
configuration explicit. The helper defaults to RoBERTa with null threshold **4**
and the separate `.tmp/models/reader-roberta` cache. Explicit `--reader-model
minilm` retains threshold **-8** and `.tmp/models/reader`. A direct server
deployment must set the matching `READER_MODEL_PATH`, `READER_MODEL_REVISION` and
`READER_NULL_THRESHOLD`; the low-level library defaults remain MiniLM and 0.
Do not change a frozen evaluation threshold after seeing
its held-out results. The current repair protocol and preserved failed gate are
documented in [the coverage baseline](answer-coverage-baseline.md).

For an explicitly selected portable lexical workflow, pass
`--answer-selection lexical` consistently to the helper. With deterministic
embeddings, the helper defaults to lexical selection. Its conservative literal
coverage can refuse useful paraphrases and does not establish entailment.
The [measured case study](portfolio-case-study.md) records the original failed
held-out gate. Curated conflicting procedure groups trigger
review/refusal; universal contradiction detection is not claimed. Conversation
memory remains context and never becomes numbered source authority.

New reader answers retain model/revision, selection contract, decision reasons
and exact Unicode-codepoint span offsets inside JSON provenance and citations.
The source drawer highlights those spans within the immutable canonical quote.
Historical answers retain their recorded selection method or show unknown;
changing runtime mode does not rewrite earlier evidence. The offline sample
experience does not load or require either local model.

Uploads are limited to five files and 10 MiB each. Storage uses generated names
inside the configured root. Failed updates retain the published version and a
safe quarantined job reason. Usage tokens are estimated, with unknown/illustrative
pricing disclosed. This is local API-key access control, not verified hosted
multi-user authentication.

## Deferred infrastructure profile

The owner explicitly deferred WSL. `infra/portfolio.compose.yml` reserves isolated
PostgreSQL/pgvector and Redis containers/volumes on loopback5545/6385. It has not
been run in this continuation. A future connected PostgreSQL deployment selects
queued ingestion, installs PostgreSQL/Redis extras and runs the canonical Celery
worker against the same database/storage root. Queue errors cannot silently
switch to inline execution. Jobs use durable claims, expiring leases and fenced
publication; queued work survives API restarts.

Live PostgreSQL SQL/index plans, Redis-worker delivery, scoped ANN recall and the
1k/10k/100k benchmark remain outstanding. Configured CI service tests are not
observed hosted execution. See [verification](portfolio-verification.md) and
[the baseline](portfolio-baseline.md) for exact evidence and environmental limits.
