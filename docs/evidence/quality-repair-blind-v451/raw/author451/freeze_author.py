import json, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
report=json.loads((ROOT/'check-report.json').read_text(encoding='utf-8'))
MH=report['manifest_sha256']
notes='''# Author review notes

Revision: fresh-blind-author-v451-r1-20261026. Synthetic agent authorship, GroundTruth project ownership, MIT license, no third-party text, no human validation.

Only the assigned CONTRACT.md, its excluded-families.json, and this newly owned author directory were read. Candidate-freeze timing was supplied by the integration owner before authoring. No application, scorer, operational profile, previous question, result, threshold, model, memory, repository onboarding, agent inventory, chat, API, network, or external validator was consulted. No delegation occurred. Generation and artifact checks use the Python standard library. No execution setting was chosen.

## Semantic freshness review

The full exclusion family/title inventory was read before choosing these subjects. None is a renamed earlier activity. The new subject matters are: substitution-wheel alphabet alignment; paper chromatography lane preparation; kaleidoscope optical pattern capture; magnetic polarity mapping; Foley footstep cue recording; domino-chain route layout; juggling-scarf release sequencing; calligraphy diagonal nib practice; dry volcanic-landscape story panels; body-percussion count-ins; shadow projection scaling; compass-bearing card interpretation; marble-ramp finish timing; pangram alphabet proofreading; mechanical escape-room prop resets; Morse lamp flash practice; a printed microscope-focus simulator; geological strata profile sketching; maritime flag-hoist reading order; and balance-pan comparison of wooden shapes.

Some share broad educational, physical-demonstration, or creative settings with old families. The actual object, requested operation, applicability rules, and ordered actions are different. Exact family and title disjointness was also checked mechanically. Semantic freshness is an author judgment rather than a universal automatic similarity proof.

## Label review

Each family has six positive cases: an ordinary complete routine plus default lead/deputy from a separate assignment document; an activity quantity plus location from another document; duration; explicit negation; an applicability-qualified exception; and a special-session lead overriding the activity default. Positive labels use the current authorized versions and quote the full requested sentences. The ordinary routine quote includes its ordinary-session scope, and the role quote identifies the named activity. Four action sentences constitute each complete ordinary routine; each step has its own ordered literal group. No exception procedure is mislabeled as an ordinary complete routine.

Two positive cases per family require facts from two logical documents. No source alone answers both parts. Five assignment documents are private; their positive cases use their owner. Other positive cases include viewer-a in the same workspace. Public source visibility is not treated as cross-workspace permission.

The 40 unanswerable cases comprise 10 private owner-draft questions by viewer-a, 10 ops-b trial questions by an ops-a principal, 10 completely missing budget attributes, and 10 undocumented East Annex entities. Neighboring counts, durations, default roles, or draft values do not establish any requested missing fact. Private draft questions use an attribute different from the ordinary activity quantity.

The 20 conflicting_stale cases comprise 10 fully incompatible current instruction pairs and 10 present-tense claims supported only by superseded versions. Both current conflict documents share an exact conflict_group and impose opposite card-disposition and record-state instructions for the identical violet-flag condition. No precedence is given. Ordinary activities are outside that condition. Stale questions request current approval rather than historical inspection.

The 20 adversarial cases comprise 10 unsupported operational-value requests whose only proposed authority is a copied untrusted instruction that explicitly admits no evidence, and 10 self-promotion attempts to reveal another user's private draft. No case is negative merely because malicious text happens to be nearby. The authorized copied-message exhibits are not listed as forbidden sources. Permission and stale prohibitions name the actual unavailable versions. All 80 negatives request refusal or review for the whole question; none labels a supported partial request as a negative.

Every case includes an individual authored rationale. label-audit.json records the author check coverage for all 200 labels; check-report.json records the independent artifact re-read assertions. These remain the same author's checks, not a separate reviewer or human gold standard.

## Preservation and limitations

No authored corpus content was revised after generation. authored-r1 preserves the first authored documents, cases, profile, manifest, data source, and generator bytes. Superseded logical snapshots are fully present in documents.json. Root corpus files and the authored-r1 copies match byte-for-byte. Source content uses canonical one-space whitespace before hashing, and frozen JSON uses UTF-8 with LF newlines.

The corpus intentionally has balanced per-family allocation and recurring negative categories. It does not claim representativeness of all operational writing, universal contradiction detection, general entailment certification, human validation, or real professional correctness. No model or application behavior was measured. A separate label reviewer is still required before integration or scoring. The integration owner must supply any execution profile separately and preserve this raw author manifest and the source/question/label bytes.
'''
(ROOT/'AUTHOR_REVIEW_NOTES.md').write_text(notes,encoding='utf-8',newline='\n')
checks='\n'.join(f"- {c['check']}: PASS." for c in report['checks'])
handoff=f'''# Frozen independent author handoff

Output: `{ROOT}`.
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

1. `python "{ROOT / 'generate.py'}"` — exit 0; wrote the first and only authored revision and preserved it in authored-r1.
2. `python "{ROOT / 'check_author.py'}"` — exit 0; PASS 25 aggregate checks and 200 per-case author audits. See check-report.json and label-audit.json.
3. `python "{ROOT / 'freeze_author.py'}"` — exit 0 on success; writes this handoff, the author review notes, final-checksums.json and FROZEN.sha256 without changing corpus bytes.

## Exact successful checks

{checks}

The script checks all required fact and step alternatives as literal grounded phrases with normalized word boundaries, every quote/span, every necessary source contribution, whole ordered-routine coverage, current visibility and version authority, and all referenced forbidden versions. Author review additionally covers the semantic exclusion boundary and all negative-case meanings. The check suite imports no project code or validator.

## Identity and evidence

Raw author manifest SHA256: `{MH}`.
The manifest maps exactly documents.json, cases.json and profile.json to their SHA256 hashes. final-checksums.json inventories all preserved author files except itself and its external FROZEN.sha256 pointer. Source files and labels are frozen. authored-r1 retains the initial bytes. No corpus corrections or discarded source versions exist.

## Limits and next owner

Synthetic source-backed authored expectations; agent authorship; GroundTruth project / MIT; no borrowed content, human validation, model measurement or general factual-entailment certification. Semantic freshness was reviewed against the excluded subject inventory but remains an author judgment. The balanced family template is a deliberate synthetic composition, not a representative frequency estimate. This author check is not the separate label review.

Next action owner: integration owner, to dispatch the separate clean label reviewer using only the frozen corpus and permitted contract. Do not score until that review is resolved. The integration owner supplies execution settings separately and retains the raw author manifest. No application, scorer, settings, shared ledger, or outside directory was changed. Cash status is not applicable to this data authoring task.
'''
(ROOT/'AUTHOR_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
# Make every preserved byte inspectable, including the generation sources and cache.
files={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in {'final-checksums.json','FROZEN.sha256'}}
checksum={'schema_version':1,'revision':'fresh-blind-author-v451-r1-20261026','manifest_sha256':MH,'files':files}
p=ROOT/'final-checksums.json'; p.write_text(json.dumps(checksum,indent=2)+'\n',encoding='utf-8',newline='\n')
freezehash=hashlib.sha256(p.read_bytes()).hexdigest()
(ROOT/'FROZEN.sha256').write_text(freezehash+'  final-checksums.json\n',encoding='utf-8',newline='\n')
# Re-read final checksums once without changing any artifacts.
assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in files.items())
assert hashlib.sha256((ROOT/'manifest.json').read_bytes()).hexdigest()==MH
print(json.dumps({'freeze':'complete','inventoried_files':len(files),'manifest_sha256':MH,'final_checksums_sha256':freezehash,'exit_code':0}))
