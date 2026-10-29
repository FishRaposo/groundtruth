# Answer coverage: preserved baseline and evaluation protocol

Started 2026-10-24 from clean `e19006c9e8f1a11ef4930e24ed88128e765b6bf5`
on `feat/groundtruth-answer-coverage`. The previous application/recruiter milestone
remains recorded in [its verification](portfolio-verification.md). No WSL,
Docker, paid provider, generative model or public publication is included.

## Evidence that must not change

The original golden files and the entire first observed evidence bundle retain
their exact bytes. The first held-out quality command failed: 37/80 per method,
42 false refusals and one missed refusal. That result is not repaired retroactively.
Its source fingerprints describe an earlier snapshot, not the current reader.
The later baseline commit already includes the independent compound-word repair;
a new baseline/candidate comparison must name that commit explicitly.

The execution ledger saved hashes for all 16 original golden/observed files and
an archive of the baseline source before edits. Historical verification now
supports an explicit source revision:

```powershell
python scripts/verify_connected_evidence.py --source-revision e19006c
```

The verifier reads local Git blobs without checking out files or changing the
old bundle. Its successful exit verifies integrity while still printing that the
original quality gate failed. An unavailable revision fails explicitly.

## What changes and what remains evidence

The application retains SQLite, canonical inline ingestion, pinned local semantic
embeddings and source-extractive answers. The optional CPU reader selects exact
source passages; it does not generate new factual prose. Reader errors remain
errors rather than lexical fallbacks or successful refusals. Lexical/library
compatibility remains explicitly selectable.

The new development corpus contains 80 synthetic agent-authored cases with
48/16/8/8 answerable/unanswerable/conflicting-stale/adversarial distribution,
20 documents, 24 versions and 18 fresh source families. Its manifest is
`bb345eb5854cd900a7195cdfff045220518b5998d36442748c2567f15f5de5fd`.
An independent agent checked every label against source text and permissions;
this does not constitute human validation. Original and development families are
disjoint. No development case is subsequently called unseen validation.

Threshold selection uses the declared grid -12/-8/-4/0/4/8/12, maximizing correct
development answers subject to zero negative failures, with conservative ties.
Source and scoring repairs during development invalidate earlier measurements
as final selection evidence. Keep those observations, then rerun current code.

The final unchanged-source development grid selected **-8**: 37/48 correct
answers and 32/32 correct negative outcomes. Threshold -12 answered 21/48 with
all negatives correct; every more permissive setting missed at least one
negative. At -4, 44/48 answers were correct but only 31/32 negatives were correct,
so it was ineligible. All seven raw reports are preserved in the separate
[coverage evidence directory](evidence/answer-coverage-v2/README.md). These are
development observations, not blind acceptance or a 95% quality claim.

Only after code, model hashes, scorer, development results and configuration are
frozen may a fresh author produce the 200-case blind corpus. The author receives
only product/schema requirements, without implementation, earlier questions,
development results or thresholds. Source families must be new and disjoint.
Independent label checking precedes freezing the blind bytes and any evaluation.

Baseline and candidate then use the same question contracts and actual HTTP
application path, in separate disposable databases. Candidate span integrity is
an additional requirement, not a different answer-quality judge. First complete
reports for both arms are retained before case-level failures are inspected.
No selective rerun or replacement of a failed set earns an unseen claim.

Acceptance for the default reranked path is at least 114/120 correct answers,
strict improvement over the frozen baseline, all 80 negative cases correct,
and no access/citation/span integrity failures. All four methods are reported.
Synthetic authored expectations do not establish general model quality, human
agreement or production capacity. PostgreSQL/Redis and indexed-scale checks
remain separately deferred.
