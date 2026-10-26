# Frozen independent author handoff

Output: `C:\Projects\operation-fan-the-hammer\.tmp\groundtruth-coverage-20261024\quality-v6\fresh-blind-author-v451`.
Revision: fresh-blind-author-v451-r1-20261026.
Status: authored and frozen before any measurement; ready for a separate label reviewer.

## Counts and composition

- Exactly 200 held_out/blind cases: 120 answerable, 40 unanswerable, 20 conflicting_stale, 20 adversarial.
- Exactly 20 fresh semantic source families; six positives and four negatives per family.
- 110 logical documents, 130 immutable snapshots, 20 superseded snapshots retained.
- 40 answerable questions necessarily use two logical documents.
- 20 complete ordinary procedures, each with all four ordered action sentences.
- 10 curated incompatible-current conflict groups and 10 stale-only current claims.
- Unanswerable: 10 owner-private, 10 cross-workspace, 10 missing attributes, 10 wrong entities.
- Adversarial: 10 untrusted copied-instruction authority attempts, 10 question self-promotion/private-access attempts.
- Public, organization, and private sources; two principals in ops-a and one source owner in ops-b. Five private coordination documents also have owner-authorized positive coverage.
- Normal search scope is document_ids null in all 200 cases. No positive expected-document filter was supplied.

## Exact execution record

1. `python "C:\Projects\operation-fan-the-hammer\.tmp\groundtruth-coverage-20261024\quality-v6\fresh-blind-author-v451\generate.py"` — exit 0; wrote the first and only authored revision and preserved it in authored-r1.
2. `python "C:\Projects\operation-fan-the-hammer\.tmp\groundtruth-coverage-20261024\quality-v6\fresh-blind-author-v451\check_author.py"` — exit 0; PASS 25 aggregate checks and 200 per-case author audits. See check-report.json and label-audit.json.
3. `python "C:\Projects\operation-fan-the-hammer\.tmp\groundtruth-coverage-20261024\quality-v6\fresh-blind-author-v451\freeze_author.py"` — exit 0 on success; writes this handoff, the author review notes, final-checksums.json and FROZEN.sha256 without changing corpus bytes.

## Exact successful checks

- exact category counts: PASS.
- unique document IDs: PASS.
- unique case IDs and questions: PASS.
- 20 source families: PASS.
- family identifiers absent from exclusion packet: PASS.
- all source titles differ from excluded titles: PASS.
- all source and case splits held_out: PASS.
- all case families exist: PASS.
- all source owners are mapped aliases: PASS.
- all principal aliases and workspace mappings valid: PASS.
- all three visibility classes and two workspaces present: PASS.
- all 130 snapshots contiguous, canonical and hash-correct: PASS.
- all 120 answerable labels current-authorized and text-grounded: PASS.
- all 80 negative labels demand whole-request refusal or review: PASS.
- at least 30 necessary multi-document requests: PASS.
- at least 20 complete ordered procedures: PASS.
- forbidden versions only stale or unauthorized: PASS.
- 20 curated conflict documents in 10 incompatible pairs: PASS.
- manifest exact file set: PASS.
- manifest exact SHA256 values: PASS.
- manifest identity/counts/rights: PASS.
- profile contains no execution settings: PASS.
- UTF8 JSON serialization LF and terminal newline: PASS.
- preserved first authored bytes match final root artifacts: PASS.
- per-family category allocation: PASS.

The script checks all required fact and step alternatives as literal grounded phrases with normalized word boundaries, every quote/span, every necessary source contribution, whole ordered-routine coverage, current visibility and version authority, and all referenced forbidden versions. Author review additionally covers the semantic exclusion boundary and all negative-case meanings. The check suite imports no project code or validator.

## Identity and evidence

Raw author manifest SHA256: `a5e732c5220bda88c63c774d9b40a8daed54cd686f36cff884b48229e9409894`.
The manifest maps exactly documents.json, cases.json and profile.json to their SHA256 hashes. final-checksums.json inventories all preserved author files except itself and its external FROZEN.sha256 pointer. Source files and labels are frozen. authored-r1 retains the initial bytes. No corpus corrections or discarded source versions exist.

## Limits and next owner

Synthetic source-backed authored expectations; agent authorship; GroundTruth project / MIT; no borrowed content, human validation, model measurement or general factual-entailment certification. Semantic freshness was reviewed against the excluded subject inventory but remains an author judgment. The balanced family template is a deliberate synthetic composition, not a representative frequency estimate. This author check is not the separate label review.

Next action owner: integration owner, to dispatch the separate clean label reviewer using only the frozen corpus and permitted contract. Do not score until that review is resolved. The integration owner supplies execution settings separately and retains the raw author manifest. No application, scorer, settings, shared ledger, or outside directory was changed. Cash status is not applicable to this data authoring task.
