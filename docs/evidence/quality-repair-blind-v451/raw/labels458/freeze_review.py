"""Freeze reviewer-owned evidence or verify it without writing. Standard library only."""
from pathlib import Path
import hashlib
import json
import sys

OUT = Path(__file__).resolve().parent
AUTHOR = OUT.parent / 'fresh-blind-author-v451'
CONTRACT = OUT.parent / 'fresh-blind-contract-v383'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

if '--verify' in sys.argv:
    f=read(OUT/'final-checksums.json')
    assert sha(OUT/'final-checksums.json')==(OUT/'FROZEN.sha256').read_text().split()[0]
    assert all(sha(OUT/n)==h for n,h in f['files'].items())
    assert sha(AUTHOR/'manifest.json')==f['author_manifest_sha256']==f['reviewed_manifest_sha256']
    assert sha(AUTHOR/'final-checksums.json')==f['author_checksum_inventory_sha256']
    a=read(AUTHOR/'final-checksums.json')
    assert all(sha(AUTHOR/n)==h for n,h in a['files'].items())
    assert all(sha(CONTRACT/n)==h for n,h in f['contract_files'].items())
    exp=read(OUT/'inspection-expectations.json')
    assert exp['corpus_manifest_sha256']==f['reviewed_manifest_sha256']
    cases=read(AUTHOR/'cases.json')
    assert set(exp['cases'])=={c['id'] for c in cases}
    assert read(OUT/'check-report.json')['passed'] is True
    print(json.dumps({'freeze_verified':True,'review_files':len(f['files']),'author_manifest_sha256':f['author_manifest_sha256'],'author_checksum_inventory_sha256':f['author_checksum_inventory_sha256'],'label_checksum_inventory_sha256':sha(OUT/'final-checksums.json'),'inspection_expectations_sha256':sha(OUT/'inspection-expectations.json')}))
    raise SystemExit(0)

assert not (OUT/'final-checksums.json').exists(), 'Preserve existing freeze; create a new revision rather than overwrite it.'
r=read(OUT/'check-report.json')
assert r['passed'] is True and r['cases_reviewed']==200 and r['material_issue_count']==0
manifest_hash=r['reviewed_manifest_sha256']
notes='''# Independent clean label review

All 200 cases, all 110 logical sources and all 130 source snapshots were read within the permitted frozen author packet. Review used only CONTRACT.md, its 175-family exclusion inventory, and fresh-blind-author-v451 files. No repository onboarding, memory, earlier corpus contents, implementation, models, APIs, network, scorer, thresholds, measurements, chats or other agent work were inspected. No author files were executed or modified. No delegation occurred.

The independent semantic read confirms the whole request for each of 120 positives: ordinary-scoped routines include all four ordered action sentences and separate activity-default lead/deputy; quantity/location pairs need two logical documents; durations keep units and current identity; negations retain the prohibited action; applicability-qualified exceptions retain conditions, substitutions and exclusions; special-session lead requests use the specific assignment. Five private coordination documents have owner-authorized positive coverage. Generic local phrasing is resolved by the explicit source activity and uniquely relevant question object, consistently with the product context policy.

All 80 negatives request unavailable current facts or an unresolved current conflict for the whole request. Ten owner-private and ten other-workspace facts cannot be accessed by their case principals. Ten missing budget attributes and ten separate East Annex entities have no current authorized support. Ten current incompatible pairs share an explicit group and impose retain/open versus discard/close under exactly the same violet flag condition; ordinary sessions do not invoke that condition. Ten present-tense acceptance-phrase questions are supported only by superseded versions. Ten copied-instruction cases ask for an unsupported operating value, rather than an answerable quotation about malicious text; ten question self-promotion cases cannot change private permissions. Authorized untrusted exhibits are not falsely forbidden.

Every necessary expected source is current and authorized. Every quote and acceptable span is an exact substring. Every required alternative is literal and bounded in an expected quotation; facts are full discriminating grounded sentences with entities or clear scoped objects, units, conditions and negation, never bare arbitrary numbers. Ordered steps cover the complete contiguous routine. All forbidden versions are stale or unauthorized. Semantic review was combined with a separately written stdlib-only checker rather than imported project or author validation code. case-review.json records all 200 review entries; family-review.json records all 20 subject judgments.

No material label, source or question issue was identified. No corrections or corpus copies were necessary. The immutable author corpus remains the reviewed corpus; correction-inventory.json records zero changes and the same author/reviewed manifest identity. Author files and the preserved authored-r1 bytes were checked before and after review.

inspection-expectations.json covers all 200 IDs: ten lists contain both current authorized opposing documents; 190 lists are empty. Selection uses question condition, source subject, current versions and permissions, independent of labels, expected behavior or any implementation. Both sides must be inspected to recognize the relevant curated incompatibility. This is frozen supplementary engineering evidence; it changes no label or scorer.

Twenty distinct operation subjects satisfy the required fresh family count against the 175 excluded family/title inventory. Related settings were considered, including puppet size comparison versus pinhole screen alignment, stage Foley versus keyboard-switch sound comparison, and body count-in versus digital MIDI quantization. Those share broad domains but differ in objects and operations. Earlier excluded source contents were not accessed. Subject disjointness is an agent judgment, not automatic proof.

Natural source and positive-question wording varies across the 20 activities and includes imperative/interrogative forms, paraphrases, quantities, durations, negation and conditions. Administrative negative stems, conflict disposition templates and balanced per-family allocation repeat. The corpus is therefore synthetic and not a representative distribution estimate. Review is source-backed engineering evidence, not human validation, universal contradiction detection, factual-entailment certification or evidence of real professional correctness. GroundTruth project ownership, MIT and synthetic authorship are recorded by the frozen manifest.
'''
(OUT/'LABEL_REVIEW_NOTES.md').write_text(notes,encoding='utf-8',newline='\n')
handoff=f'''# Frozen independent label-review handoff

Owned output: `{OUT}`.
Reviewed corpus: `{AUTHOR}`; immutable author corpus accepted with zero corrections.
Status: independent source/label audit complete and frozen before any application/API/model execution by this reviewer.

- 200 held_out/blind cases: 120 answerable, 40 unanswerable, 20 conflicting_stale, 20 adversarial.
- 20 fresh source subjects, compared with the 175 excluded family/title entries.
- 110 logical documents; 130 snapshots, including all 20 superseded versions.
- 40 necessary two-document positive requests; 20 complete four-step procedure requests.
- Three visibility classes, two workspaces, three principals; five owner-private coordination sources with authorized positive coverage.
- Ten curated opposing current instruction pairs; ten stale-only current claims.
- 200 opposition expectation mappings: ten nonempty lists containing two current opposing sources each, 190 empty lists.
- Zero material issues, zero corrections; exact empty inventory in correction-inventory.json. No corrected copy needed.

Author manifest SHA256: `{manifest_hash}`.
Author checksum inventory SHA256: `{r['author_checksum_inventory_sha256']}`.
Reviewed manifest SHA256: `{manifest_hash}`.
The label freeze inventory final-checksums.json hashes every reviewer artifact except itself and its external FROZEN.sha256 pointer; that pointer holds its SHA256. Its inventory separately binds the author freeze, contract inputs and opposition expectations.

Exact checks:

1. `python "{OUT / 'check_review.py'}"` — exit 0; 30 aggregate checks and 200 individual semantic/authority/coverage reviews, 40 necessary multidocument and 20 complete procedure confirmations. No project imports, author script execution or measurement.
2. `python "{OUT / 'freeze_review.py'}"` — expected exit 0 when this handoff and final inventories are frozen. Existing freezes cannot be overwritten.
3. `python "{OUT / 'freeze_review.py'}" --verify` — read-only post-freeze verification command; the integration handoff reports its observed exit. Verifies every reviewer file hash, author frozen bytes, corpus identity and all contract bindings.

Detailed evidence: check-report.json, case-review.json, family-review.json, LABEL_REVIEW_NOTES.md, inspection-expectations.json and correction-inventory.json.

Limits: independently reviewed synthetic agent labels, not human validated; semantic subject disjointness is reviewer judgment; repeated negative stems and administrative templates limit representativeness; supplementary opposition lists are engineering evidence, not a scorer alteration. No app/model/API/network measurement was performed. Cash status not applicable. No unresolved review blocker.

Next action owner: integration owner, preserve both final freezes and all original corpus bytes before separately supplied execution configuration or API execution. Do not treat this artifact/label acceptance as application accuracy or release certification.
'''
(OUT/'LABEL_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
files={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in {'final-checksums.json','FROZEN.sha256'}}
write('final-checksums.json',{'schema':'independent-label-freeze-v1','review_id':'fresh-blind-label-review-v458','authorship':'independent source/label review; synthetic not human validated','frozen_before_measurement':True,'author_manifest_sha256':manifest_hash,'reviewed_manifest_sha256':manifest_hash,'author_checksum_inventory_sha256':r['author_checksum_inventory_sha256'],'contract_files':{n:sha(CONTRACT/n) for n in ('CONTRACT.md','excluded-families.json')},'correction_count':0,'inspection_expectations_sha256':sha(OUT/'inspection-expectations.json'),'files':files})
freeze_hash=sha(OUT/'final-checksums.json')
(OUT/'FROZEN.sha256').write_text(freeze_hash+'  final-checksums.json\n',encoding='utf-8',newline='\n')
print(json.dumps({'frozen':True,'review_files':len(files),'label_checksum_inventory_sha256':freeze_hash,'inspection_expectations_sha256':sha(OUT/'inspection-expectations.json')}))
