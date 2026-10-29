"""Verify exposed failed-pair bytes and replay frozen1600-row scoring; no inference."""
from __future__ import annotations
import argparse,base64,gzip,hashlib,importlib.abc,importlib.util,io,json,re,sys
from collections import Counter
from pathlib import Path
from types import ModuleType
MAX_STORED=64*1024*1024;MAX_DECODED=300*1024*1024;MAX_TOTAL=2*1024*1024*1024
sha=lambda b:hashlib.sha256(b).hexdigest()
json_bytes=lambda b:json.loads(b.decode('utf-8-sig'))

def check(root):
    root=root.resolve(strict=True);manifest=json_bytes((root/'manifest.json').read_bytes())
    assert manifest['schema']=='first-failed-blind-portable-v524' and manifest['quality_gate']=='FAILED' and manifest['unseen_accepted']is False and manifest['exposed_regression_only']is True
    sums={}
    for line in (root/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        pin,name=line.split('  ',1);assert name not in sums;sums[name]=pin
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    assert actual==set(sums)|{'SHA256SUMS'} and set(manifest['files'])==actual-{'manifest.json','SHA256SUMS'}
    logical={};total=0;pattern=re.compile(rb'gt_[0-9a-fA-F]{48}')
    for name,pin in manifest['files'].items():
        p=(root/name).resolve(strict=True);assert p.is_relative_to(root) and not p.is_symlink() and p.stat().st_size<=MAX_STORED
        assert not re.search(r'(?i)(^|/)(private|data|node_modules|\.venv|__pycache__)(/|$)|\.(db|sqlite3?|pyc)$',name)
        raw=p.read_bytes();assert len(raw)==pin['bytes'] and sha(raw)==pin['sha256']==sums[name]
        stream=gzip.GzipFile(fileobj=io.BytesIO(raw)) if pin['encoding']=='gzip' else io.BytesIO(raw)
        if pin['encoding']=='gzip':assert raw[4:8]==b'\0\0\0\0'
        decoded_hash=hashlib.sha256();size=0;tail=b''
        with stream:
            while block:=stream.read(1024*1024):
                size+=len(block);assert size<=MAX_DECODED
                assert not pattern.search(tail+block),'Full credential pattern in packet'
                decoded_hash.update(block);tail=block[-64:]
        assert size==pin['decoded_bytes'] and decoded_hash.hexdigest()==pin['decoded_sha256']
        total+=size;assert total<=MAX_TOTAL
        assert pin['logical_path']not in logical;logical[pin['logical_path']]=(name,pin)
    for name,pin in sums.items():assert sha((root/name).read_bytes())==pin
    for name in ('manifest.json','SHA256SUMS'):assert not pattern.search((root/name).read_bytes())
    def data(name):
        physical,pin=logical[name];raw=(root/physical).read_bytes()
        return gzip.decompress(raw) if pin['encoding']=='gzip' else raw
    def obj(name):return json_bytes(data(name))
    def pin(name):return logical[name][1]['decoded_sha256']
    def safe_public(name):return not set(Path(name).parts)&{'private','data','__pycache__'} and Path(name).suffix not in ('.db','.sqlite','.sqlite3','.pyc')
    preserved=obj('bindings/failed-blind-v499-preservation.json');assert len(preserved['files'])==309 and preserved['unseen_accepted']is False
    public_preserved=0
    for name,value in preserved['files'].items():
        if not safe_public(name):continue
        relative=name.removeprefix('blind-pair-v499/')
        target='raw/first-pair/controller.log' if name=='blind-pair-v499.controller.log' else 'raw/first-pair/'+relative
        assert pin(target)==value;public_preserved+=1
    pair=obj('raw/first-pair/PAIR-SEALED.json')
    assert pair['both_structurally_complete'] and pair['both_children_closed'] and pair['inspection_allowed']
    for arm in ('baseline','candidate'):
        seal=obj(f'raw/first-pair/{arm}/SEALED.json')
        assert pin(f'raw/first-pair/{arm}/SEALED.json')==pair['arm_seals'][arm]
        assert seal['children_closed'] and seal['structurally_complete']
        for name,value in seal['files'].items():
            if safe_public(name):assert pin(f'raw/first-pair/{arm}/{name}')==value
        assert data(f'raw/first-pair/{arm}/report.json.sha256').decode().strip()==pin(f'raw/first-pair/{arm}/report.json')
    for name,value in obj('raw/first-pair/SEALED.json')['files'].items():
        if safe_public(name):assert pin('raw/first-pair/'+name)==value
    for folder in ('author451','labels458'):
        inv=obj(f'raw/{folder}/final-checksums.json')
        assert data(f'raw/{folder}/FROZEN.sha256').decode().split()[0]==pin(f'raw/{folder}/final-checksums.json')
        for name,value in inv['files'].items():
            if safe_public(name):assert pin(f'raw/{folder}/{name}')==value
    labels=obj('raw/labels458/final-checksums.json');assert labels['correction_count']==0 and labels['authorship']=='independent source/label review; synthetic not human validated'
    for name,value in labels['contract_files'].items():assert pin('bindings/author-contract383/'+name)==value
    assert obj('raw/labels458/inspection-expectations.json')['cases']==obj('bindings/arm-preparation472/opposition-expectations.json')['cases']
    bindings=obj('SOURCE-BINDINGS.json');source31=obj(bindings['source31_manifest'])['files'];base=obj(bindings['source417_manifest'])['extracted_runtime_subset']
    assert len(source31)==232 and len(base)==215
    assert set(bindings['source31_copied'])|set(bindings['source31_explicit_test_omissions'])==set(source31)
    assert not set(bindings['source31_copied'])&set(bindings['source31_explicit_test_omissions'])
    for rel,name in bindings['source31_copied'].items():assert pin(name)==source31[rel]
    for rel,name in bindings['source417_copied'].items():assert pin(name)==base[rel]
    assert len(bindings['source31_copied'])==213 and len(bindings['source31_explicit_test_omissions'])==19 and len(bindings['source417_copied'])==215
    freeze=obj('bindings/freeze446/freeze.json')
    assert pin(bindings['source31_manifest'])==freeze['source_manifest_sha256'] and pin('bindings/freeze446/runtime.json')==freeze['runtime_sha256']
    for rel,value in freeze['scorer_sha256'].items():assert source31[rel]==value
    assert pin('bindings/selection479/selection.json')==pair['selection_sha256']
    assert pair['raw_manifest_sha256']==pin('raw/author451/manifest.json')
    assert pin('bindings/arm-preparation472/opposition-expectations.json')==pair['opposition_expectations_sha256']
    approval=obj('reviews/runtime496/review-approval.json');assert approval['verdict']=='approved'
    for name,value in approval['reviewed_files'].items():assert pin('bindings/controller493/'+name)==value
    git=obj('reviews/independent519/git-source-normalized-binding.json')
    assert all(git[arm]['all_equal_modulo_CRLF'] and not git[arm]['semantic_mismatches'] for arm in ('baseline','candidate'))
    results=obj('RESULTS.json');assert results['quality_gate']=='FAILED' and results['unseen_accepted']is False
    # Guard execution before loading the exact frozen pure modules. This shim
    # bypasses only app.services' eager initializer, as independently reviewed519.
    allowed={'app','app.evidence_policy','app.portfolio','app.portfolio.comparison','app.portfolio.coverage','app.portfolio.evaluation','app.portfolio.representation','app.services','app.services.document','app.services.document.source_context','app.services.procedure_output','app.services.requirement_contract'}
    class PureOnly(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.startswith('app.') and fullname not in allowed:raise ImportError('Non-pure app import forbidden')
            if fullname.split('.')[0] in {'torch','transformers','sentence_transformers','tensorflow','onnxruntime','sqlalchemy','pydantic'}:raise ImportError('Runtime/model dependency forbidden')
    sys.meta_path.insert(0,PureOnly())
    def guard(event,args):
        if event.startswith('socket.') or event.startswith('subprocess.') or event in ('os.system','os.spawn'):raise RuntimeError('Network/process operation forbidden')
    sys.addaudithook(guard)
    api=root/'source/frozen31/apps/api';sys.path.insert(0,str(api))
    services=ModuleType('app.services');services.__path__=[str(api/'app/services')];sys.modules['app.services']=services
    scorer_path=root/'source/frozen31/scripts/verify_answer_coverage_delivery.py'
    spec=importlib.util.spec_from_file_location('frozen_portable_scorer',scorer_path);scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)
    from app.portfolio.comparison import load_views
    corpus,baseline_corpus,candidate_corpus=load_views(root/'raw/author451',root/'raw/first-pair/baseline/corpus',root/'raw/first-pair/candidate/corpus')
    baseline=obj('raw/first-pair/baseline/report.json');candidate=obj('raw/first-pair/candidate/report.json')
    for arm,report in (('baseline',baseline),('candidate',candidate)):
        public=obj(f'raw/first-pair/{arm}/seed-public-bindings.json')
        assert public['report_sha256']==pin(f'raw/first-pair/{arm}/report.json')
        assert public['bindings']=={key:report[key] for key in ('profile','source_document_ids','source_manifest','source_manifest_sha256','source_identity_scope')}
    comparison=scorer.compare_reports(baseline,candidate,corpus=corpus,baseline_corpus=baseline_corpus,candidate_corpus=candidate_corpus,selection_path=root/'bindings/selection479/selection.json')
    assert comparison==obj('raw/first-pair/comparison.json') and comparison['gate']=='failed' and comparison['methods']==results['methods']
    # Recount actual authored fact/step coverage and complete200-case/method rows
    # through the unmodified frozen scorer above, then retain shape distinctions.
    side=obj('bindings/arm-preparation472/opposition-expectations.json')['cases'];docs={d['id']:d for d in candidate_corpus['documents']}
    opposition_rows=0;expected_count=0;inspected_count=0;scope_count=0;assessments=0;outcomes=Counter();refusals={}
    identity=lambda entries:{(s.get('document_id'),s.get('document_version'),s.get('content_hash')) for s in entries}
    for method,value in candidate['results'].items():
        refusals[method]=sum(row['refused'] for row in value['cases'] if row['category']=='answerable')
        assert len(value['cases'])==200 and refusals[method]==103
        for row in value['cases']:
            targets=side[row['case_id']]
            if not targets:continue
            selection=row['observed_response']['provenance']['answer_selection']
            target={(candidate['source_document_ids'][s['document_id']],s['version_number'],docs[s['document_id']]['versions'][s['version_number']-1]['content_hash']) for s in targets}
            conflicts=selection.get('conflicts',[]);decisions=[s for c in conflicts for s in c.get('source_scope_decisions',[]) if s.get('included')]
            inspected=identity(selection.get('inspected_sources',[]));included=identity(decisions)
            assert target<=inspected and target<=included
            opposition_rows+=1;expected_count+=len(target);inspected_count+=len(target&inspected);scope_count+=len(target&included)
            for c in conflicts:
                if target&identity(c.get('source_scope_decisions',[])):assessments+=len(c.get('assessments',[]));outcomes[c.get('outcome')]+=1
    assert (opposition_rows,expected_count,inspected_count,scope_count)==(40,80,80,80)
    assert assessments==0 and set(outcomes)=={'not_relevant'}
    original_opposition=obj('raw/first-pair/opposition.json');assert original_opposition['candidate_required_opposing_inspections_missing']==80 and original_opposition['acceptance_blocked_by_missing_required_inspection']is True
    return {'packet_integrity':'PASS','frozen_pure_replay':'PASS all1600 rows; exact original comparison equality','quality_gate':'FAILED','unseen_accepted':False,'exposed_regression_only':True,'files_checked':len(actual),'stored_bytes':sum((root/n).stat().st_size for n in actual),'decoded_payload_bytes':total,'original309_public_preservation_entries_bound':public_preserved,'candidate_runtime_tool_files':213,'candidate_test_omissions':19,'baseline_source_files':215,'all_method_metrics':comparison['methods'],'candidate_positive_refusals_by_method':refusals,'opposition_actual_rows':opposition_rows,'opposition_actual_required_sources':expected_count,'opposition_actual_inspected_and_included':scope_count,'original_helper_missing80_preserved':True,'semantic_contradiction_assessments':assessments,'semantic_conflict_outcomes':dict(outcomes),'no_new_prediction_or_inference':True,'pure_imported_app_modules':sorted(n for n in sys.modules if n=='app' or n.startswith('app.'))}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--result',type=Path);args=parser.parse_args()
    try:result=check(args.root)
    except Exception as failure:
        print(json.dumps({'packet_integrity':'FAILED CHECK','error_type':type(failure).__name__}));return 1
    if args.result:args.result.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
