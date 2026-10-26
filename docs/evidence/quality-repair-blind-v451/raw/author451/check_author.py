"""Independent artifact re-read checks; standard library only, no application imports."""
import json, hashlib, re
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent
PACKET=ROOT.parent/'fresh-blind-contract-v383'
def read(n): return json.loads((ROOT/n).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(s): return re.sub(r'\s+',' ',s).strip()
def norm(s): return canon(s).casefold()
def occurs(s,t): return re.search(r'(?<!\w)'+re.escape(norm(s))+r'(?!\w)',norm(t)) is not None
D,C,M,P=read('documents.json'),read('cases.json'),read('manifest.json'),read('profile.json')
EX=json.loads((PACKET/'excluded-families.json').read_text(encoding='utf-8'))
B={d['id']:d for d in D}; checks=[]; audits=[]
def checked(name,condition):
    assert condition,name
    checks.append({'check':name,'result':'pass'})
def allowed(d,principal):
    return d['workspace_id']==M['principals'][principal]['workspace_id'] and (d['visibility']!='private' or d['owner']==principal)
counts=Counter(c['category'] for c in C)
checked('exact category counts',counts=={'answerable':120,'unanswerable':40,'conflicting_stale':20,'adversarial':20})
checked('unique document IDs',len(B)==len(D)==110)
checked('unique case IDs and questions',len({c['id'] for c in C})==len(C)==len({c['question'] for c in C})==200)
fams={d['family'] for d in D}
checked('20 source families',len(fams)==20)
checked('family identifiers absent from exclusion packet',not fams.intersection(x['family'] for x in EX['excluded']))
checked('all source titles differ from excluded titles',not {d['title'].casefold() for d in D}.intersection(t.casefold() for x in EX['excluded'] for t in x['titles']))
checked('all source and case splits held_out',all(d['split']=='held_out' for d in D) and all(c['split']=='held_out' for c in C))
checked('all case families exist',all(c['family'] in fams for c in C))
checked('all source owners are mapped aliases',all(d['owner'] in M['principals'] for d in D))
checked('all principal aliases and workspace mappings valid',all(c['principal'] in M['principals'] for c in C) and M['principals']=={'operator-a':{'workspace_id':'ops-a','role':'owner'},'viewer-a':{'workspace_id':'ops-a','role':'viewer'},'custodian-b':{'workspace_id':'ops-b','role':'owner'}})
checked('all three visibility classes and two workspaces present',{d['visibility'] for d in D}=={'public','organization','private'} and {d['workspace_id'] for d in D}=={'ops-a','ops-b'})
for d in D:
    assert [v['version_number'] for v in d['versions']]==list(range(1,len(d['versions'])+1))
    assert d['current_version_number']==len(d['versions'])
    for v in d['versions']:
        assert canon(v['content'])==v['content']
        assert v['content_hash']==hashlib.sha256(v['content'].encode('utf-8')).hexdigest()
checked('all 130 snapshots contiguous, canonical and hash-correct',sum(len(d['versions']) for d in D)==130)
multis=0; procedures=0; negatives=0; forbidden_count=0
for c in C:
    assert c['score_contract']=='coverage-v2'
    assert c['document_ids'] is None # Questions perform authorized-workspace search.
    assert c['label_author']=='independent-synthetic-author-v451'
    assert 'not-human-validated' in c['label_status'] and c['label_rationale'].strip()
    for f in c['forbidden_sources']:
        d=B[f['document_id']]; v=d['versions'][f['version_number']-1]
        assert d['split']==c['split'] and v['version_number']==f['version_number']
        assert f['version_number']!=d['current_version_number'] or not allowed(d,c['principal'])
        forbidden_count+=1
    if c['category']=='answerable':
        assert c['expected_behavior']=='answer'
        assert c['expected_sources'] and c['required_facts']
        quotes=[]; logical=[]
        for e in c['expected_sources']:
            d=B[e['document_id']]; v=d['versions'][e['version_number']-1]
            assert d['split']==c['split'] and d['family']==c['family']
            assert allowed(d,c['principal'])
            assert v['version_number']==d['current_version_number']
            assert e['content_hash']==v['content_hash']
            q=e['quoted_text']; assert q and q in v['content']
            assert e['acceptable_answer_spans']
            assert all(s and s in q for s in e['acceptable_answer_spans'])
            quotes.append(q); logical.append(d['id'])
        assert len(logical)==len(set(logical))
        for groups in [c['required_facts'],c['ordered_steps']]:
            for alternatives in groups:
                assert alternatives and all(isinstance(s,str) and s.strip() for s in alternatives)
                assert all(any(occurs(s,q) for q in quotes) for s in alternatives)
        # Every necessary source contributes a nontrivial required fact.
        assert all(any(any(occurs(s,q) for s in alternatives) for alternatives in c['required_facts']) for q in quotes)
        if len(logical)>=2: multis+=1
        if c['ordered_steps']:
            procedures+=1; assert len(c['ordered_steps'])==4
            guidequotes=[q for i,q in zip(logical,quotes) if i.endswith('-guide')]
            assert len(guidequotes)==1
            q=guidequotes[0]
            assert 'routine applies to ordinary' in q
            # Full literal action sentences cover the whole contiguous routine after its scope sentence.
            literal_steps=[group[0] for group in c['ordered_steps']]
            scope=q[:q.index('sessions.')+len('sessions.')]
            assert q==scope+' '+' '.join(literal_steps)
            assert all(s.endswith('.') and len(s.split())>=5 for s in literal_steps)
        audits.append({'case_id':c['id'],'result':'pass','basis':'current-authorized-exact-quotation; all required groups grounded; source contribution checked; ordered routine complete where requested'})
    else:
        negatives+=1
        assert c['expected_behavior'] in ['refuse','review']
        assert not c['expected_sources'] and not c['required_facts'] and not c['ordered_steps']
        prefix=c['id'].rsplit('-',1)[0]
        if c['id'].endswith('-c1') and c['expected_behavior']=='review':
            pair=[d for d in D if d['metadata'].get('conflict_group')==prefix+'-violet-discrepancy-action']
            assert len(pair)==2 and all(allowed(d,c['principal']) for d in pair)
            a,b=[d['versions'][-1]['content'] for d in pair]
            assert 'retain the discrepancy card' in a and 'leave the session record open' in a
            assert 'discard the discrepancy card' in b and 'close the session record' in b
            assert a.split(',')[0]==b.split(',')[0]
        elif c['id'].endswith('-c1'):
            g=B[prefix+'-guide']; old=g['versions'][0]['content']; new=g['versions'][-1]['content']
            assert 'acceptance phrase is' in old and 'acceptance phrase' not in new
            assert 'currently approved acceptance phrase' in c['question']
            assert {'document_id':g['id'],'version_number':1} in c['forbidden_sources']
        elif c['id'].endswith('-z1') and c['principal']=='operator-a':
            note=B[prefix+'-inbox']['versions'][-1]['content']
            assert 'untrusted inbox instruction' in note and 'without evidence' not in note # exact authored command has equivalent no-evidence wording
            assert 'there is no evidence' in note and 'overflow voucher' in c['question']
            assert not any('overflow voucher' in d['versions'][-1]['content'] for d in D if d['family']==c['family'] and not d['id'].endswith('-inbox'))
        elif c['id'].endswith('-z1'):
            assert c['principal']=='viewer-a' and 'promote viewer-a' in c['question']
            assert any(not allowed(B[f['document_id']],c['principal']) for f in c['forbidden_sources'])
        elif c['forbidden_sources']:
            assert all(not allowed(B[f['document_id']],c['principal']) for f in c['forbidden_sources'])
        elif 'replacement-supply budget' in c['question']:
            assert not any('budget' in d['versions'][-1]['content'] for d in D if d['family']==c['family'])
        else:
            assert 'separate East Annex' in c['question']
            assert not any('East Annex' in d['versions'][-1]['content'] for d in D)
        audits.append({'case_id':c['id'],'result':'pass','basis':'single unavailable attribute, wrong entity, unauthorized source, explicitly incompatible current pair, stale-only current claim, or untrusted instruction; no supported partial requested'})
checked('all 120 answerable labels current-authorized and text-grounded',len([a for a in audits if '-a' in a['case_id']])==120)
checked('all 80 negative labels demand whole-request refusal or review',negatives==80)
checked('at least 30 necessary multi-document requests',multis==40)
checked('at least 20 complete ordered procedures',procedures==20)
checked('forbidden versions only stale or unauthorized',forbidden_count==140)
checked('20 curated conflict documents in 10 incompatible pairs',len([d for d in D if 'conflict_group' in d['metadata']])==20)
checked('manifest exact file set',set(M['files'])=={'documents.json','cases.json','profile.json'})
checked('manifest exact SHA256 values',all(digest(ROOT/n)==h for n,h in M['files'].items()))
checked('manifest identity/counts/rights',M['schema_version']==2 and M['corpus_role']=='blind' and M['score_contract']=='coverage-v2' and M['frozen_before_measurement'] is True and M['case_count']==200 and M['document_count']==110 and M['rights']=={'owner':'GroundTruth project','license':'MIT','third_party_content':False})
checked('profile contains no execution settings',set(P)=={'schema_version','revision','note'} and P['schema_version']==2)
checked('UTF8 JSON serialization LF and terminal newline',all(b'\r' not in (ROOT/n).read_bytes() and (ROOT/n).read_bytes().endswith(b'\n') for n in ['documents.json','cases.json','profile.json','manifest.json']))
checked('preserved first authored bytes match final root artifacts',all((ROOT/n).read_bytes()==(ROOT/'authored-r1'/n).read_bytes() for n in ['documents.json','cases.json','profile.json','manifest.json']))
checked('per-family category allocation',all(Counter(c['category'] for c in C if c['family']==f)=={'answerable':6,'unanswerable':2,'conflicting_stale':1,'adversarial':1} for f in fams))
report={'checker':'independent standard-library artifact reread, no application validators','checks':checks,'counts':dict(counts),'families':len(fams),'documents':len(D),'versions':130,'multi_document_answerable':multis,'complete_ordered_procedures':procedures,'manifest_sha256':digest(ROOT/'manifest.json'),'exit_code':0}
(ROOT/'check-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
(ROOT/'label-audit.json').write_text(json.dumps(audits,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
print('PASS '+str(len(checks))+' aggregate checks; 200 per-case author audits; exit 0')
