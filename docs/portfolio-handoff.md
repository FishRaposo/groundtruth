# GroundTruth portable milestone handoff

Observed 2026-10-24. Supports GT-01–GT-07 and existing FTH-016. No new opportunity,
experiment or cash record; cash status unknown. No push, publication or paid use.

Start with [verification](portfolio-verification.md), [actual setup](portfolio-connected.md),
[case study](portfolio-case-study.md), [walkthrough](portfolio-walkthrough.md),
[observed evidence](evidence/portfolio/README.md) and the operation's
[Project 05 plan](../../plans/groundtruth.md). The repository remains independently
installable; EvalForge/AgentTrace are optional artifact exchanges.

The owner explicitly continued without WSL. Delivered local behavior uses real
SQLite, canonical inline ingestion, cached pinned CPU semantic embeddings and
source-extractive answers. Strict authenticated scope flows through query/SSE,
history/conversations, documents/versions and sources. Ingestion has immutable
attempt fencing, renewable leases and atomic publication; workflow review/audit
and unknown pricing survive restart. Unknown legacy provenance remains unknown.
The source-independent recruiter tour is visibly simulated and works offline.

GT-01/02/04/06 and portable GT-07 acceptance have observed evidence. GT-03 includes
schema/index/query/CI implementation but live PostgreSQL/Redis remains unverified.
GT-05 corpus/evaluation is observed but its first quality gate failed and the large
indexed benchmark is deferred. Do not mark the complete original milestone done.

Delivery branch: `feat/groundtruth-portfolio`, original clean source
`a8dc3570e3e66320b716d31a4791e957f14d7cfa`, prerequisite-only checkpoint
`a1fd2df1060d6743dc1fdf1a68ffe3972fe40d16`. The local delivery commit is the latest
commit containing this handoff; inspect `git log -1` and the operation handoff for
its concrete SHA. No publication follows from that commit.

The separate review app listens on `http://127.0.0.1:3505`, API8400. Review data,
process ownership and disposable keys are recorded in the operation's ignored
`.tmp/groundtruth-20261023/review-v1` directory. Enter the admin key through
Connection; never put it in a URL or public evidence. It is seeded via actual
HTTP ingestion/version APIs, not copied from the acceptance database. Model cache
is outside the clone and explicitly configured. Preserve both databases.

Next owner action: inspect the real rollback/source/version/review flow and the
independent sample tour. Next agent action: address conservative answer coverage
using a new development cycle and genuinely unseen validation; retain the failed
37/80 first held-out report. When the owner chooses to resume infrastructure,
verify the pending Windows prerequisite explicitly, then run dedicated PG/Redis
acceptance and the full indexed benchmark. Never restart Windows automatically.
