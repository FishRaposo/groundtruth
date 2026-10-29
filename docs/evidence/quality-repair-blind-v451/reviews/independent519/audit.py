"""Read-only frozen observation audit. Writes only this new audit directory."""
from pathlib import Path
import collections, hashlib, importlib.abc, importlib.util, json, re, sys
HERE=Path(__file__).resolve().parent
Q=HERE.parent
PAIR=Q/'blind-pair-v499'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def save(name,obj):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n')
checks=[]
def check(name,ok,detail=None):
 checks.append({'check':name,'passed':bool(ok),'detail':detail})
 if not ok:raise ValueError(name)
def inventory(root,files,name):
 failures=[]
 for rel,pin in files.items():
  p=(root/rel).resolve()
  if not p.is_relative_to(root.resolve()) or not p.is_file() or digest(p)!=pin:failures.append(rel)
 check(name,not failures,{'files':len(files),'mismatches':failures})
class NoModels(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','transformers','sentence_transformers','onnxruntime','tensorflow'}:raise ImportError('Model execution forbidden')
sys.meta_path.insert(0,NoModels())
def security(event,args):
 if (event.startswith('socket.') and event!='socket.gethostname') or event.startswith('subprocess.') or event in ('os.system','os.spawn'):raise RuntimeError('Network/process forbidden')
sys.addaudithook(security)
pins={}
for rel in ['QUALITY_REVIEW_PACKET_V518.md','candidate-freeze-v446/freeze.json','candidate-freeze-v446/runtime.json','requirements-source-v31.json','baseline-freeze-v417/source-manifest.json','blind-pair-controller-v493/controller.py','blind-pair-controller-v493/worker.py','blind-pair-controller-v493/frozen-inputs.json','blind-runtime-independent-v496/review-approval.json','blind-selection-v479/selection.json','blind-corpus-arm-preparation-v472/opposition-expectations.json','fresh-blind-label-review-v458/inspection-expectations.json','fresh-blind-author-v451/manifest.json','fresh-blind-author-v451/final-checksums.json','fresh-blind-label-review-v458/final-checksums.json','blind-pair-v499/PAIR-SEALED.json']:
 pins[rel]=digest(Q/rel)
before=dict(pins)
for arm in ['baseline','candidate']:
 seal=read(PAIR/arm/'SEALED.json');inventory(PAIR/arm,seal['files'],arm+' sealed bytes')
 check(arm+' closed complete',seal['children_closed'] and seal['structurally_complete'])
 check(arm+' seal pin',digest(PAIR/arm/'SEALED.json')==read(PAIR/'PAIR-SEALED.json')['arm_seals'][arm])
 pins[f'blind-pair-v499/{arm}/SEALED.json']=digest(PAIR/arm/'SEALED.json')
 pins[f'blind-pair-v499/{arm}/report.json']=digest(PAIR/arm/'report.json')
inventory(PAIR,read(PAIR/'SEALED.json')['files'],'pair sealed bytes')
for root in ['fresh-blind-author-v451','fresh-blind-label-review-v458']:
 inv=read(Q/root/'final-checksums.json');inventory(Q/root,inv['files'],root+' freeze files')
 check(root+' freeze pointer',digest(Q/root/'final-checksums.json')==(Q/root/'FROZEN.sha256').read_text().split()[0])
freeze=read(Q/'candidate-freeze-v446/freeze.json')
check('source31 manifest freeze pin',digest(Q/'requirements-source-v31.json')==freeze['source_manifest_sha256'])
inventory(Q/'requirements-source-v31',read(Q/'requirements-source-v31.json')['files'],'source31 manifest files')
baseline=read(Q/'baseline-freeze-v417/source-manifest.json')
inventory(Q/'baseline-freeze-v417/source',baseline['extracted_runtime_subset'],'original417 source bytes')
check('baseline archive',digest(Q/'baseline-freeze-v417/source.zip')==freeze['baseline_archive_sha256'])
inventory(Q/'requirements-source-v31',freeze['scorer_sha256'],'frozen scorer files')
for name,model in freeze['model_bindings'].items():
 root=Path(model['root']);check(name+' model manifest',digest(root/model['manifest'])==model['manifest_sha256']);inventory(root,model['files'],name+' model bytes')
check('runtime metadata pin',digest(Q/'candidate-freeze-v446/runtime.json')==freeze['runtime_sha256'])
approval=read(Q/'blind-runtime-independent-v496/review-approval.json')
inventory(Q/'blind-pair-controller-v493',approval['reviewed_files'],'496 approved493 files')
check('approval496 correct',approval['verdict']=='approved' and approval['scope']=='blind-pair-controller-v476')
inventory(Q,read(Q/'blind-pair-controller-v493/frozen-inputs.json')['files'],'493 dependency pins')
side=read(Q/'fresh-blind-label-review-v458/inspection-expectations.json');opp=read(Q/'blind-corpus-arm-preparation-v472/opposition-expectations.json')
check('sidecar unchanged cases',opp['cases']==side['cases'])
raw=Q/'fresh-blind-author-v451';cases=read(raw/'cases.json');docs={d['id']:d for d in read(raw/'documents.json')};case_map={c['id']:c for c in cases}
check('raw manifest exact',digest(raw/'manifest.json')=='a5e732c5220bda88c63c774d9b40a8daed54cd686f36cff884b48229e9409894')
check('200 explicit opposition lists',set(opp['cases'])==set(case_map) and all(type(v)is list for v in opp['cases'].values()))
check('ten opponent pairs',sum(bool(v) for v in opp['cases'].values())==10 and sum(map(len,opp['cases'].values()))==20)
labels=[]
def norm(t):return ' '.join(re.findall(r'\w+',t.casefold()))
for c in cases:
 grounded=[]
 for s in c['expected_sources']:
  d=docs[s['document_id']];v=d['versions'][s['version_number']-1]
  check(c['id']+' source hash '+s['document_id'],v['content_hash']==hashlib.sha256(v['content'].encode()).hexdigest() and s.get('content_hash',v['content_hash'])==v['content_hash'])
  check(c['id']+' quote '+s['document_id'],s['quoted_text'] in v['content'])
  if c['category']=='answerable':
   principal=read(raw/'manifest.json')['principals'][c['principal']]
   check(c['id']+' current source '+s['document_id'],d['current_version_number']==s['version_number'])
   check(c['id']+' authorized source '+s['document_id'],d['workspace_id']==principal['workspace_id'] and (d['visibility']!='private' or d['owner']==c['principal']))
  grounded.append(v['content'])
 if c['category']=='answerable':
  body=norm(' '.join(grounded));facts=c['required_facts'];steps=c.get('ordered_steps',[])
  check(c['id']+' every required fact grounded',all(any(norm(a) in body for a in alternatives) for alternatives in facts))
  check(c['id']+' every ordered step grounded',all(any(norm(a) in body for a in alternatives) for alternatives in steps))
 labels.append({'case_id':c['id'],'category':c['category'],'question':c['question'],'expected_sources':[{'document_id':s['document_id'],'version_number':s['version_number']} for s in c['expected_sources']],'required_facts':c.get('required_facts',[]),'ordered_steps':c.get('ordered_steps',[]),'rationale':c.get('label_rationale')})
reports={a:read(PAIR/a/'report.json') for a in ['baseline','candidate']}
timeline={}
for a,r in reports.items():
 timeline[a]={'report_created_at':r['created_at'],'report_mtime_utc':__import__('datetime').datetime.fromtimestamp((PAIR/a/'report.json').stat().st_mtime,__import__('datetime').timezone.utc).isoformat(),'seal_created_at':read(PAIR/a/'SEALED.json')['created_at'],'cleanup':read(PAIR/a/'cleanup.json'),'runtime':read(PAIR/a/'readiness.json')['runtime']}
 check(a+'800 exact cases',set(r['results'])=={'keyword','vector','hybrid','reranked'} and all(len(v['cases'])==200 and {x['case_id'] for x in v['cases']}==set(case_map) for v in r['results'].values()))
check('arm sequential seal order',timeline['baseline']['seal_created_at']<timeline['candidate']['report_created_at']<timeline['candidate']['seal_created_at']<read(PAIR/'PAIR-SEALED.json')['created_at'])
for root in ['fresh-blind-author-v451','fresh-blind-label-review-v458']:
 check(root+' freeze precedes predictions', (Q/root/'FROZEN.sha256').stat().st_mtime < (PAIR/'baseline/report.json').stat().st_mtime)
sys.path.insert(0,str(Q/'requirements-source-v31/apps/api'))
# The services package initializer eagerly instantiates unrelated services.
# A namespace package loads the exact frozen pure submodules without executing
# that initializer; no scorer function or source byte is replaced.
from types import ModuleType
services=ModuleType('app.services');services.__path__=[str(Q/'requirements-source-v31/apps/api/app/services')]
sys.modules['app.services']=services
path=Q/'requirements-source-v31/scripts/verify_answer_coverage_delivery.py'
spec=importlib.util.spec_from_file_location('frozen_portable_scorer',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from app.portfolio.comparison import load_views
corpus,b,c=load_views(raw,PAIR/'baseline/corpus',PAIR/'candidate/corpus')
comparison=m.compare_reports(reports['baseline'],reports['candidate'],corpus=corpus,baseline_corpus=b,candidate_corpus=c,selection_path=Q/'blind-selection-v479/selection.json')
check('portable replay equals original comparison',comparison==read(PAIR/'comparison.json'))
save('portable-replay.json',comparison)
mechanisms=[];opposition=[];answers=[]
for arm,r in reports.items():
 reverse={v:k for k,v in r['source_document_ids'].items()};arm_docs={d['id']:d for d in read(PAIR/arm/'corpus/documents.json')}
 for method,result in r['results'].items():
  for row in result['cases']:
   c=case_map[row['case_id']];response=row['observed_response'];sel=response.get('provenance',{}).get('answer_selection') or {}
   if arm=='candidate' and c['category']=='answerable':
    mechanisms.append({'case_id':c['id'],'method':method,'passed':row['answer_quality_passed'],'refused':row['refused'],'recall_at_5':row['recall_at_5'],'requirements':[{'id':x['id'],'kind':x['kind'],'text':x['original_text'],'status':x['status'],'reason':x.get('reason')} for x in sel.get('requirements',[])],'candidate_decisions':dict(collections.Counter(x.get('decision') for x in sel.get('candidates',[]))),'role_read_set_reason':(sel.get('role_scope_read_set') or {}).get('reason'),'role_read_set_documents':len((sel.get('role_scope_read_set') or {}).get('documents',[]))})
   if method=='reranked' and not row['refused']:
    answers.append({'arm':arm,'case_id':c['id'],'category':c['category'],'passed':row['answer_quality_passed'],'answer':response.get('answer'),'sources':response.get('sources'),'required_facts':c.get('required_facts'),'ordered_steps':c.get('ordered_steps')})
   expected=opp['cases'][c['id']]
   if not expected:continue
   source_decisions=[s for conflict in sel.get('conflicts',[]) for s in conflict.get('source_scope_decisions',[])]
   extent_checks=[s for conflict in sel.get('conflicts',[]) for s in conflict.get('source_extent_checks',[])]
   inspected=sel.get('inspected_sources',[])
   def identities(entries):return {(s.get('document_id'),s.get('document_version'),s.get('content_hash')) for s in entries}
   target={(r['source_document_ids'][s['document_id']],s['version_number'],arm_docs[s['document_id']]['versions'][s['version_number']-1]['content_hash']) for s in expected}
   opposition.append({'arm':arm,'method':method,'case_id':c['id'],'required':len(target),'present_inspected_sources':len(target & identities(inspected)),'present_source_scope_decisions':len(target & identities(source_decisions)),'present_source_extent_checks':len(target & identities(extent_checks)),'included_source_scope_decisions':len(target & identities([s for s in source_decisions if s.get('included')])),'matching_conflicts':[{'requirement_id':x['requirement_id'],'outcome':x.get('outcome'),'relevant':x.get('relevant'),'inspection_complete':x.get('inspection_complete'),'assessments':len(x.get('assessments',[]))} for x in sel.get('conflicts',[]) if target & identities(x.get('source_scope_decisions',[]))]})
for rel,pin in before.items():check('post-audit unchanged '+rel,digest(Q/rel)==pin)
save('input-hashes.json',pins);save('checks.json',checks);save('timeline-runtime.json',timeline);save('label-grounding.json',labels);save('positive-mechanisms.json',mechanisms);save('opposition-shapes.json',opposition);save('reranked-nonrefused-answers.json',answers)
summary={'checks':len(checks),'all_passed':all(x['passed'] for x in checks),'replay_gate':comparison['gate'],'pure_imported_modules':sorted(x for x in sys.modules if x.startswith('app.')),'candidate_opposition_rows':len([x for x in opposition if x['arm']=='candidate']),'candidate_opposition_sources_recorded':sum(x['present_source_scope_decisions'] for x in opposition if x['arm']=='candidate'),'candidate_helper_shape_sources_recorded':sum(x['present_source_extent_checks'] for x in opposition if x['arm']=='candidate'),'candidate_positive_refusals_by_method':{method:sum(x['refused'] for x in mechanisms if x['method']==method) for method in reports['candidate']['results']}}
save('result.json',summary);print(json.dumps(summary,indent=2))
