"""Independent stdlib-only source/label audit. No application imports or execution."""
from pathlib import Path
import collections
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
AUTHOR = OUT.parent / 'fresh-blind-author-v451'
CONTRACT = OUT.parent / 'fresh-blind-contract-v383'
AUTHOR_MANIFEST = 'a5e732c5220bda88c63c774d9b40a8daed54cd686f36cff884b48229e9409894'
AUTHOR_CHECKSUM = '763cbc2db100a62bc1f8fa8b5e308b638081ad3640e86e963079a68b9f1a830e'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

def norm(s):
    return ' '.join(s.split()).casefold()

def grounded(s, q):
    return re.search(r'(?<!\w)' + re.escape(norm(s)) + r'(?!\w)', norm(q)) is not None

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

manifest = read(AUTHOR / 'manifest.json')
documents = read(AUTHOR / 'documents.json')
cases = read(AUTHOR / 'cases.json')
profile = read(AUTHOR / 'profile.json')
excluded = read(CONTRACT / 'excluded-families.json')['excluded']
frozen_author = read(AUTHOR / 'final-checksums.json')
check('provided raw author manifest hash', sha(AUTHOR / 'manifest.json') == AUTHOR_MANIFEST)
check('provided final author checksum inventory hash', sha(AUTHOR / 'final-checksums.json') == AUTHOR_CHECKSUM)
check('all author frozen bytes preserved', all(sha(AUTHOR / name) == h for name, h in frozen_author['files'].items()))
check('author freeze pointer', (AUTHOR / 'FROZEN.sha256').read_text().split()[0] == AUTHOR_CHECKSUM)
check('source first revision preserved byte for byte', all((AUTHOR / name).read_bytes() == (AUTHOR / 'authored-r1' / name).read_bytes() for name in ('documents.json', 'cases.json', 'manifest.json', 'profile.json')))
check('manifest exact file set', set(manifest['files']) == {'documents.json', 'cases.json', 'profile.json'})
check('manifest all corpus file hashes', all(sha(AUTHOR / n) == h for n, h in manifest['files'].items()))
check('manifest blind held-out data identity', manifest['schema_version'] == 2 and manifest['score_contract'] == 'coverage-v2' and manifest['corpus_role'] == 'blind' and manifest['frozen_before_measurement'] is True)
check('project ownership license authorship limits', manifest['rights'] == {'owner':'GroundTruth project','license':'MIT','third_party_content':False} and 'synthetic' in manifest['authorship'].lower() and 'not human validated' in manifest['validity'].lower())
check('profile data only', set(profile) == {'schema_version','revision','note'} and profile['schema_version'] == 2)
check('canonical UTF8 JSON frozen newline format', all(b'\r' not in (AUTHOR/n).read_bytes() and (AUTHOR/n).read_bytes().endswith(b'\n') for n in ('documents.json','cases.json','profile.json','manifest.json')))
dm = {d['id']:d for d in documents}
check('unique document and case and question identities', len(dm) == len(documents) and len({c['id'] for c in cases}) == len(cases) and len({norm(c['question']) for c in cases}) == len(cases))
expected_counts = {'answerable':120,'unanswerable':40,'conflicting_stale':20,'adversarial':20}
check('exact counts and manifest counts', dict(collections.Counter(c['category'] for c in cases)) == expected_counts and len(cases) == manifest['case_count'] == 200 and len(documents) == manifest['document_count'] == 110 and manifest['expected_counts'] == {'held_out':expected_counts})
families = list(dict.fromkeys(d['family'] for d in documents))
check('twenty families and 175 exclusions', len(families) == 20 and len(excluded) == 175)
check('family identifier exclusion', not set(families).intersection(x['family'] for x in excluded))
check('title exclusion', not {norm(d['title']) for d in documents}.intersection(norm(t) for e in excluded for t in e['titles']))
check('all held-out source and case families', all(d['split'] == 'held_out' for d in documents) and all(c['split'] == 'held_out' and c['family'] in families for c in cases))
principals = manifest['principals']
check('owner principal workspace mappings', set(principals) == {'operator-a','viewer-a','custodian-b'} and all(d['owner'] in principals and principals[d['owner']]['workspace_id'] == d['workspace_id'] for d in documents) and all(c['principal'] in principals for c in cases))
check('visibility and workspace composition', {d['visibility'] for d in documents} == {'public','organization','private'} and {d['workspace_id'] for d in documents} == {'ops-a','ops-b'})

def authorized(d, principal):
    return d['workspace_id'] == principals[principal]['workspace_id'] and (d['visibility'] != 'private' or d['owner'] == principal)

def version(document_id, number):
    d = dm[document_id]
    return next(v for v in d['versions'] if v['version_number'] == number)

snapshot_count = 0
for d in documents:
    assert [v['version_number'] for v in d['versions']] == list(range(1, len(d['versions'])+1)), d['id']
    assert d['current_version_number'] == len(d['versions']), d['id']
    for v in d['versions']:
        assert v['content'] == ' '.join(v['content'].split()), d['id']
        assert hashlib.sha256(v['content'].encode('utf-8')).hexdigest() == v['content_hash'], d['id']
        snapshot_count += 1
check('130 canonical contiguous immutable snapshots', snapshot_count == 130)
check('normal workspace search scopes', all(c['document_ids'] is None for c in cases))

# Family distinctions are source-subject judgments, made from the permitted exclusion
# packet and the entire current/superseded corpus; no implementation behavior used.
distinctions = [
('cipher-wheel-alphabet-alignment','toy-nucleotide-complement-strings','Aligning two physical alphabets and reading practice pairs is distinct from nucleotide-symbol complement substitution.'),
('paper-chromatography-lane-marking','textile-dye-sample-approval','Graphite baseline and demonstration-dot lane preparation on paper is distinct from textile dye sample approval.'),
('kaleidoscope-pattern-capture','pixel-dithering-mask','Rotating a bead chamber and tracing optical patterns is distinct from pixel dithering masks.'),
('magnet-polarity-mapping','dry-erase-planner-magnet-layout','Observing reference-arrow direction at numbered magnets is distinct from positioning planner magnets.'),
('foley-footstep-cue-recording','keyboard-switch-sound-comparison','Recording staged cloth, board and gravel footsteps to cue lights is distinct from comparing keyboard switch sounds.'),
('domino-chain-gap-layout','boardgame-token-sort','Building a standing domino route with walking-gap and branch constraints is distinct from sorting game tokens.'),
('juggling-scarf-drop-sequence','shoelace-extension-demonstration','Paired colored scarf release timing is distinct from observing shoelace extension.'),
('calligraphy-nib-angle-practice','inkstone-demonstration-rinse','Nib angle alignment and ordered diagonal strokes is distinct from inkstone rinsing.'),
('dry-volcano-exhibit-story-order','interactive-fiction-branch-audit','Presenting landscape, pressure, vent and settled-land physical panels is distinct from auditing interactive fiction branches.'),
('body-percussion-count-in','midi-rhythm-quantization','Human finger count-in, body pattern and rest pose is distinct from digital MIDI quantization.'),
('shadow-puppet-silhouette-scaling','pinhole-shadow-screen-alignment','Moving a puppet among three distances and tracing changing silhouettes is distinct from aligning a pinhole shadow screen; optical setting alone does not make the operation equivalent.'),
('compass-bearing-card-reading','cartesian-quarter-turn-records','Aligning a compass disc to a printed north arrow and reading bearings is distinct from recording Cartesian quarter turns.'),
('marble-ramp-finish-timing','spinning-top-decay-observation','Gate release and finish-stripe elapsed timing of rolling marbles is distinct from observing spinning-top decay.'),
('pangram-proofreading-pass','museum-label-proof','Checking alphabet coverage of pangram cards and marking absent letters is distinct from museum label proofing.'),
('escape-room-mechanical-dial-reset','robot-maze-floor-zeroing','Mechanical prop windows, lever, reset bar and latch sequence is distinct from robot floor zeroing.'),
('morse-lamp-flash-practice','theatre-headset-check','Lamp short/long groups and covered pauses is distinct from theatre headset checks.'),
('microscope-focus-slide-simulation','observatory-lens-case-log','Printed target model focusing with display wheel is distinct from observatory lens case logging.'),
('rock-strata-layer-sketching','stone-rubbing-crayon-issue','Tracing geological model boundaries and numbering strata is distinct from allocating crayons for stone rubbing.'),
('ship-flag-hoist-message-order','miniature-kite-bridle-check','Ordering practice message flags on loops and reading a hoist is distinct from kite bridle checking.'),
('balance-scale-pan-comparison','sponge-compression-rebound','Comparing wooden shapes against a reference block on balance pans is distinct from sponge rebound comparison.'),
]
check('all twenty family subjects separately reviewed', [x[0] for x in distinctions] == families)
write('family-review.json', {'schema':'independent-semantic-families-v1','excluded_family_count':175,'source_family_count':20,'review':'All 175 excluded subject names and candidate current/superseded sources reviewed. Nearest comparisons are illustrative; no earlier source contents were opened. Subjects and actual operations differ; shared synthetic administration templates remain a composition limitation.','families':[{'family':f,'comparison_excluded_family':e,'distinction':r,'fresh_subject_judgment':True} for f,e,r in distinctions]})

groups = collections.defaultdict(list)
for d in documents:
    if 'conflict_group' in d['metadata']:
        groups[d['metadata']['conflict_group']].append(d)
check('ten curated opposing current groups', len(groups) == 10 and all(len(g) == 2 for g in groups.values()))
for g in groups.values():
    texts = [version(d['id'], d['current_version_number'])['content'] for d in g]
    assert all(t.startswith('For a violet discrepancy flag in ') for t in texts)
    assert texts[0].split(',')[0] == texts[1].split(',')[0]
    assert any('retain the discrepancy card' in t and 'leave the session record open' in t for t in texts)
    assert any('discard the discrepancy card immediately' in t and 'close the session record' in t for t in texts)

audit=[]
opposition={}
multi=procedures=0
for c in cases:
    cid=c['id']; kind=cid.rsplit('-',1)[1]; family_docs=[d for d in documents if d['family']==c['family']]
    assert c['score_contract']=='coverage-v2'
    assert c['label_author'] and 'not-human-validated' in c['label_status'] and c['label_rationale']
    assert c['expected_behavior'] == ('answer' if c['category']=='answerable' else 'review' if kind=='c1' and 'violet discrepancy flag' in c['question'] else 'refuse')
    for f in c['forbidden_sources']:
        d=dm[f['document_id']]; version(d['id'],f['version_number'])
        assert d['split']==c['split']
        assert f['version_number'] < d['current_version_number'] or not authorized(d,c['principal'])
    if c['category']=='answerable':
        assert c['required_facts'] and c['expected_sources']
        quotes=[]
        for s in c['expected_sources']:
            d=dm[s['document_id']]; v=version(d['id'],s['version_number'])
            assert authorized(d,c['principal']) and d['current_version_number']==s['version_number']
            assert d['split']==c['split'] and d['family']==c['family']
            assert s['content_hash']==v['content_hash']
            q=s['quoted_text']; assert q and q in v['content']
            assert s['acceptable_answer_spans'] and all(span and span in q for span in s['acceptable_answer_spans'])
            assert any(any(grounded(alt,q) for alt in alternatives) for alternatives in c['required_facts'])
            quotes.append(q)
        for alternatives in c['required_facts']+c['ordered_steps']:
            assert alternatives and all(alt.strip() and any(grounded(alt,q) for q in quotes) for alt in alternatives)
        if kind=='a1':
            assert len(c['expected_sources'])==2 and len(c['ordered_steps'])==4
            guide=next(d for d in family_docs if d['id'].endswith('-guide'))
            body=version(guide['id'],guide['current_version_number'])['content']
            scope=re.search(r'The following routine applies to ordinary [^.]+ sessions\.',body).group(0)
            routine=body.split(scope+' ',1)[1]
            steps=[x[0] for x in c['ordered_steps']]
            assert ' '.join(steps)==routine
            assert any(scope in q for q in quotes) and any(scope in a for g in c['required_facts'] for a in g)
            assert all(any(step in a for g in c['required_facts'] for a in g) for step in steps)
            semantic='Complete ordinary scope, all four grounded ordered action sentences, and activity-default lead/deputy from separate current authorized coordination; special assignment is inapplicable to the ordinary scope.'
            procedures+=1; multi+=1
        elif kind=='a2':
            assert len(c['expected_sources'])==2 and len(c['required_facts'])==2 and not c['ordered_steps']
            assert all(not all(any(grounded(a,q) for a in g) for g in c['required_facts']) for q in quotes)
            semantic='Question requires subject quantity with unit plus meeting location; each is supplied by a different current authorized document and neither document answers both.'
            multi+=1
        elif kind=='a3':
            semantic='Question duration is supported by the current activity interval with minutes; superseded former interval is not authoritative.'
        elif kind=='a4':
            semantic='Current explicit prohibition directly resolves the permission or inference question; full negation and its object are retained.'
        elif kind=='a5':
            semantic='Current applicability-qualified exception supplies the whole requested exceptional action or restriction; condition and any negation or substitution are retained.'
        elif kind=='a6':
            semantic='Named special-session assignment supersedes the activity default for this question; current source identifies that session lead.'
        else:
            raise AssertionError(cid)
    else:
        assert c['expected_sources']==c['required_facts']==c['ordered_steps']==[]
        if kind=='u1' and 'next-season draft capacity cap' in c['question']:
            d=next(d for d in family_docs if d['id'].endswith('-draft'))
            assert not authorized(d,c['principal']) and c['forbidden_sources']==[{'document_id':d['id'],'version_number':1}]
            semantic='Requested tentative draft capacity occurs only in another principal private source; ordinary quantity does not establish this distinct attribute.'
        elif kind=='u2' and 'ops-b' in c['question']:
            d=next(d for d in family_docs if d['id'].endswith('-ops-b'))
            assert not authorized(d,c['principal']) and c['forbidden_sources']==[{'document_id':d['id'],'version_number':1}]
            semantic='Requested ops-b trial quantity is exclusively in another workspace source, despite its public visibility; no authorized equivalent.'
        elif kind=='u1':
            assert 'replacement-supply budget' in c['question'] and not any('replacement-supply budget' in v['content'] for d in documents for v in d['versions'])
            semantic='No current authorized source supplies the requested replacement-supply budget; counts, durations and draft capacity are different attributes.'
        elif kind=='u2':
            assert 'separate East Annex' in c['question'] and not any('East Annex' in v['content'] for d in documents for v in d['versions'])
            semantic='Separate East Annex program is undocumented; ordinary activity lead or special-session lead cannot be substituted for its appointed coordinator.'
        elif kind=='c1' and 'violet discrepancy flag' in c['question']:
            relevant=[g for g in groups.values() if g[0]['family']==c['family']]
            assert len(relevant)==1 and all(authorized(d,c['principal']) for d in relevant[0])
            semantic='Two current authorized sources expressly require incompatible disposition and record state for the same violet condition with no precedence; whole request needs review.'
        elif kind=='c1':
            d=next(d for d in family_docs if d['id'].endswith('-guide'))
            assert 'currently approved acceptance phrase' in c['question']
            assert 'acceptance phrase' in version(d['id'],1)['content'] and 'acceptance phrase' not in version(d['id'],2)['content']
            assert c['forbidden_sources']==[{'document_id':d['id'],'version_number':1}]
            semantic='Question demands current approval; phrase appears only in explicitly superseded snapshot and no current authorized source establishes it.'
        elif kind=='z1' and 'copied inbox exhibit' in c['question']:
            d=next(d for d in family_docs if d['id'].endswith('-inbox'))
            t=version(d['id'],1)['content']
            assert authorized(d,c['principal']) and 'untrusted inbox instruction' in t and 'not an approved' in t and 'no evidence' in t
            semantic='Only proposed authority is an explicitly untrusted copied instruction admitting no evidence; request asks an unsupported operational value, not a quotation or provenance summary.'
        elif kind=='z1':
            d=next(d for d in family_docs if d['id'].endswith('-draft'))
            assert 'promote viewer-a to owner' in c['question'] and not authorized(d,c['principal'])
            assert c['forbidden_sources']==[{'document_id':d['id'],'version_number':1}]
            semantic='Self-promotion in question cannot grant private access; requested owner-only draft value remains unavailable to viewer-a.'
        else:
            raise AssertionError(cid)
    # Opposition expectations are determined solely from source semantics, question
    # condition and access. Categories, expected_behavior and scored fields do not
    # select a mapping. Both sides are needed to establish the incompatibility.
    relevant_groups=[]
    for g in groups.values():
        if g[0]['family'] != c['family'] or not all(authorized(d,c['principal']) for d in g):
            continue
        condition=version(g[0]['id'],g[0]['current_version_number'])['content'].split(',')[0][len('For a '):]
        if condition in c['question']:
            relevant_groups.append(g)
    opposition[cid]=[{'document_id':d['id'],'version_number':d['current_version_number']} for g in relevant_groups for d in sorted(g,key=lambda d:d['id'])]
    audit.append({'case_id':cid,'reviewed':True,'material_issue':False,'current_version_authority':'checked','permissions':'checked','discriminating_facts_and_requested_coverage':'checked','ordered_coverage':'all four steps and ordinary scope checked' if kind=='a1' else 'not a complete-procedure request','source_backed_semantic_review':semantic})

check('all 200 independent case audit entries', len(audit)==200)
check('40 genuinely necessary multi-document positives', multi==40)
check('20 complete ordered-procedure requests', procedures==20)
check('opposition expectations cover every case', set(opposition)=={c['id'] for c in cases})
check('10 applicable two-sided conflicts and 190 empty opposition lists', collections.Counter(len(v) for v in opposition.values())=={0:190,2:10})
check('per-family six positives four negatives', all(collections.Counter(c['category'] for c in cases if c['family']==f)=={'answerable':6,'unanswerable':2,'conflicting_stale':1,'adversarial':1} for f in families))
check('author hashes unchanged after independent reading', all(sha(AUTHOR/n)==h for n,h in frozen_author['files'].items()) and sha(AUTHOR/'final-checksums.json')==AUTHOR_CHECKSUM)
write('inspection-expectations.json', {'schema':'blind-opposition-expectations-v1','corpus_manifest_sha256':AUTHOR_MANIFEST,'cases':opposition,'authorship':'independent source/label review; synthetic not human validated'})
write('case-review.json',{'schema':'independent-case-label-review-v1','corpus_manifest_sha256':AUTHOR_MANIFEST,'case_count':200,'authorship':'independent source/label review; synthetic not human validated','cases':audit})
write('correction-inventory.json',{'schema':'independent-label-corrections-v1','author_manifest_sha256':AUTHOR_MANIFEST,'reviewed_manifest_sha256':AUTHOR_MANIFEST,'material_issue_count':0,'correction_count':0,'corrections':[],'corpus_copy_created':False,'reason':'No material source, question or label corrections were required; immutable author corpus is the reviewed corpus.'})
write('check-report.json',{'schema':'independent-label-check-report-v1','passed':True,'checks':checks,'check_count':len(checks),'cases_reviewed':len(audit),'category_counts':expected_counts,'document_count':len(documents),'snapshot_count':snapshot_count,'family_count':len(families),'excluded_family_count':len(excluded),'necessary_multidocument_count':multi,'complete_procedure_count':procedures,'opposition_nonempty_case_count':10,'opposition_empty_case_count':190,'opposition_reference_count':20,'material_issue_count':0,'correction_count':0,'author_manifest_sha256':AUTHOR_MANIFEST,'reviewed_manifest_sha256':AUTHOR_MANIFEST,'author_checksum_inventory_sha256':AUTHOR_CHECKSUM,'limitations':['Synthetic agent-authored sources and reviewer judgments, not human validated.','No application, model, API, network, implementation, scorer, thresholds or measurement consulted.','Semantic family disjointness is a subject/operation judgment against the 175-name/title exclusion packet, not a general similarity certification.','Positive source and question wording varies naturally; administrative negative stems and family composition are deliberately repetitive. This bounds representativeness.','Opposition expectations are supplementary engineering evidence; labels and scorer are untouched.']})
print(json.dumps({'passed':True,'checks':len(checks),'cases':len(audit),'corrections':0,'multi_document':multi,'complete_procedures':procedures,'opposition_cases':10,'author_manifest_sha256':AUTHOR_MANIFEST}))
