# Blind input preparation and preserved preflights

The implementation/scorer candidate was committed as `eee951a91dad03f95d62600a5b35dea9e92927f5`
and frozen at **2026-10-24 04:53:05.715465 UTC**. The isolated author began at
04:55:27 UTC with only the product/schema contract and excluded family/topic
inventory. They received no application, model identity/settings, previous cases,
development results or threshold. Labels are synthetic and agent-authored.

The authored set contains 200 cases (120 answerable, 40 unanswerable, 20
conflicting/stale and 20 adversarial), 40 fresh families, 70 documents and 90
snapshots. Forty positive cases require two documents; twenty require ordered
procedures. Multiple-document execution was retained as the owner requested.

Two input preflights failed **before any question was submitted for evaluation**:

1. Raw v1 manifest `bc5617e2e9cc0ddd3d42ac7f3bf3a0e2e3ee6862a59ad564350f4044d1d5c76c`
   omitted required fact groups on twenty ordered cases. The existing schema
   required both those groups and expected sources. V2 adds source-exact fact
   groups without changing questions, source facts, steps or permissions.
2. Raw v2 manifest `5a5d4e0f1d1d14114d4ce522438286cd75bc57136fb364a65841d3a000303360`
   used multiline source fingerprints. Both actual ingestion APIs normalize
   whitespace, so the first ingested document failed the immutable-source hash
   check. This format requirement was absent from the original author brief.

Both exact inputs, their then-current reviews/binding and rejection observations
are retained in [v1](preflight-rejected-corpus-v1.zip),
[v2](preflight-rejected-corpus-v2.zip), [rejection v1](preflight-rejection-v1.json)
and [rejection v2](preflight-rejection-v2.json). Their partial databases remain in
the ignored operation ledger. Each contains one declared historical compatibility
query fixture created before uploads, rather than zero total query rows. Neither
contains measured case answers. No failed quality results were discarded here.

Canonical v3 applies **all whitespace runs → one ASCII space, then strip** to
source/quote/span/fact/step strings and recomputes dependent hashes. Twenty of
ninety source strings change. All 200 questions, semantic facts, ordering, source
families, permissions and operational profile settings remain unchanged.
Its manifest is
`cbb9ebc3b48d18ba59ab40a344f7f64a2e01b691fe1a3fef0968144be38a6bc3`,
frozen at **05:20:25.799834 UTC**. No model-answer feedback informed the transform.

The first canonicalization reviewer approved the complete draft, then accidentally
saw an unrelated frontend status via agent inventory while awaiting final bytes.
Their [report](blind-canonicalization-review.json) explicitly limits its
clean-context attestation; no semantic edit followed that exposure and the author
was not contacted. A **fresh isolated verifier** therefore independently checked
all 200 labels/90 snapshots, raw-to-canonical preservation and final hashes:
[final report](blind-independent-review.json), 9,907 checks, no findings,
SHA-256 `41907c95bf3d8bdf8ceaecb25ec0496caff38063af5cecabd00e442770bb9653`.
That verifier had no implementation/model/development/results/inventory access.
These are independent agent source reviews, not human validation.

[The final corpus attestation](blind-corpus-freeze.json) and
[validation binding](validation-binding.json) link the frozen input to the earlier
candidate and unchanged development-selected settings. Both arms then use fresh
disposable SQLite databases, real authenticated ingestion/version APIs and all
four HTTP retrieval methods. Complete first reports must both be checksummed and
sealed before case-level failure inspection. Later auditing or reused cases must
never be described as fresh unseen validation.
