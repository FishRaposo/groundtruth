"""Canonical stdlib-only portable engineering packet verification; no services."""
from __future__ import annotations
import argparse,base64,csv,gzip,hashlib,io,json,re,struct,tarfile,zipfile
from collections import Counter
from pathlib import Path
from uuid import UUID

MAX_STORED=64*1024*1024;MAX_DECODED=64*1024*1024;MAX_TOTAL=2*1024*1024*1024
sha=lambda b:hashlib.sha256(b).hexdigest()
def load_json(data):return json.loads(data.decode('utf-8-sig'))
def bounded_gzip(data,limit):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        result=stream.read(limit+1)
        if len(result)>limit or stream.read(1):raise ValueError('Decoded gzip exceeds bound')
        return result

def check(root):
    root=root.resolve(strict=True);manifest=load_json((root/'manifest.json').read_bytes());assert manifest['schema']=='source-bound-engineering-bundle-v498'
    assert manifest['quality_gate']=='OPEN' and manifest['unseen_accepted']is False
    expected={}
    for line in (root/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        value,name=line.split('  ',1);assert name not in expected;expected[name]=value
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    assert actual==set(expected)|{'SHA256SUMS'} and set(manifest['files'])==actual-{'manifest.json','SHA256SUMS'}
    logical={};decoded={};total=0;pattern=re.compile(rb'gt_[0-9a-fA-F]{48}')
    for name,pin in manifest['files'].items():
        path=(root/name).resolve(strict=True);assert path.is_relative_to(root) and path.stat().st_size<=MAX_STORED
        stored=path.read_bytes();assert len(stored)==pin['bytes'] and sha(stored)==pin['sha256']==expected[name]
        raw=bounded_gzip(stored,MAX_DECODED) if pin['encoding']=='gzip' else stored
        assert len(raw)==pin['decoded_bytes'] and sha(raw)==pin['decoded_sha256'] and len(raw)<=MAX_DECODED
        assert not pattern.search(raw),'Credential pattern in packet'
        total+=len(raw);assert total<=MAX_TOTAL
        assert pin['logical_path'] not in logical;logical[pin['logical_path']]=name;decoded[name]=raw
        assert Path(name).suffix not in {'.sqlite','.db'} and '/private/' not in '/'+name
    for name,value in expected.items():
        assert sha((root/name).read_bytes())==value
    def data(name):return decoded[logical[name]]
    def obj(name):return load_json(data(name))
    bindings=obj('SOURCE-BINDINGS.json');source=obj(bindings['source31_manifest'])['files'];front=obj('raw/gates/build430/source-restored.json')['files'];freeze=obj('bindings/freeze446/freeze.json')
    assert len(source)==232 and len(front)==232
    assert sha(data('raw/gates/build430/source-restored.json'))==freeze['frontend_manifest_sha256']
    assert sha(data('bindings/source31-manifest.json'))==freeze['source_manifest_sha256']
    assert sha(data('bindings/freeze446/runtime.json'))==freeze['runtime_sha256']
    for relative,name in bindings['source31_copied'].items():assert sha(data(name.removesuffix('.gz')))==source[relative] if name.endswith('.gz') else sha(decoded[name])==source[relative]
    assert len(bindings['source31_copied'])+len(bindings['source31_test_omissions'])==232
    for relative,name in bindings['frontend430_copied'].items():assert sha(decoded[name])==front[relative]
    assert len(bindings['frontend430_copied'])==232
    assert data('raw/gates/build430/build-exit.txt').strip()==b'0'
    assert '2806 passed, 1 skipped' in data('raw/gates/python385/python-0.log').decode('utf-8')
    coverage=obj('raw/gates/python385/coverage.json')['totals'];assert round(coverage['percent_covered'],2)==82.72
    assert all(x['exit']==0 for x in obj('raw/gates/python385/python-results.json')+obj('raw/gates/python385/static-results.json'))
    assert '862 passed (862)' in data('raw/gates/frontend407/units-all-final.log').decode('utf-8')
    assert obj('raw/gates/frontend408-historical-failure/result.json')['types']==2
    assert data('raw/gates/frontend407/types-final.log')==data('raw/gates/frontend407/lint-final.log')==b''
    assert obj('RESULTS.json')['quality_gate']=='OPEN' and obj('RESULTS.json')['unseen_accepted']is False
    assert obj('RESULTS.json')['concurrency423']['reviewed']is False
    assert obj('raw/historical/preservation-checkpoint462.json')['mismatches']==[]
    # Both archives are local and bounded; inspect members without extraction.
    wheel_name=next(n for n in logical if n.endswith('.whl'));sdist_name=next(n for n in logical if n.endswith('.tar.gz'))
    wheel=zipfile.ZipFile(io.BytesIO(data(wheel_name)));infos=wheel.infolist();assert len(infos)==len({i.filename for i in infos})
    for item in infos:
        assert item.file_size<=MAX_DECODED
        if not item.is_dir():assert not pattern.search(wheel.read(item))
    app_members={i.filename:wheel.read(i) for i in infos if not i.is_dir() and i.filename.startswith('app/')};assert len(app_members)==191
    for relative,name in bindings['source31_copied'].items():
        if relative.startswith('apps/api/app/'):
            member=relative.removeprefix('apps/api/');assert sha(app_members[member])==source[relative]
    record=next(i.filename for i in infos if i.filename.endswith('.dist-info/RECORD'));record_rows=list(csv.reader(io.StringIO(wheel.read(record).decode('utf-8'))));assert len(record_rows)==196
    for name,digest,size in record_rows:
        raw=wheel.read(name)
        if digest:
            assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=') and int(size)==len(raw)
    with tarfile.open(fileobj=io.BytesIO(data(sdist_name)),mode='r:gz') as archive:
        members={}
        for item in archive:
            if item.isfile():
                assert item.size<=MAX_DECODED;raw=archive.extractfile(item).read();assert not pattern.search(raw)
                relative=item.name.split('/',1)[1]
                if relative.startswith('app/'):members[relative]=raw
        assert members==app_members
    # Concrete retained report and screenshot metadata. No native metrics invented.
    def tests(report):
        result=[]
        def walk(suite):
            for spec in suite.get('specs',[]):result.extend(spec['tests'])
            for child in suite.get('suites',[]):walk(child)
        for suite in report['suites']:walk(suite)
        return result
    for path,count in [('raw/combined456/browser-report.json',3),('raw/offline485/browser-report.json',21)]:
        report=obj(path);assert (report['stats']['expected'],report['stats']['unexpected'],report['stats']['skipped'],report['stats']['flaky'])==(count,0,0,0) and not report['errors']
        assert len(tests(report))==count and all(t['status']=='expected' and len(t['results'])==1 and t['results'][0]['status']=='passed' for t in tests(report))
    pngs=Counter()
    for name,pin in manifest['files'].items():
        if pin['kind']=='PNG':
            raw=decoded[name];assert raw[:8]==b'\x89PNG\r\n\x1a\n';width,height=struct.unpack('>II',raw[16:24]);assert width in (390,768,1440) and height>0
            pngs[pin['logical_path'].split('/')[1]]+=1
    assert pngs=={'combined456':21,'outage481':36,'offline485':9}
    # Portable selected persisted observations: bind exact rich response fields,
    # authoritative source bodies/chunks, and answer spans without using API keys.
    sql=obj('raw/scoped-engineering-records.json');query_rows=[obj(name) for name in sql['query_row_files']];rows={str(UUID(r['id'])):r for r in query_rows};versions={(str(UUID(r['document_id'])),r['version_number']):r for r in sql['document_version_rows']}
    for version in versions.values():assert sha(version['normalized_content'].encode())==version['content_hash']
    dtos=[]
    for name in logical:
        if name.endswith('.json') and (name.startswith('raw/http388-before-restart/') or name.startswith('raw/concurrency420/response-') or name.startswith('raw/concurrency423/response-') or name=='raw/http400/sse-saved.json' or name=='raw/http400/early-disconnect.json' or re.fullmatch(r'raw/outage481/runs/first/(?:baseline|recovered)-\d+\.json',name)):
            item=obj(name);item=item.get('record',item.get('actual_saved_get',item))
            if 'question' in item:dtos.append(item)
    clean=lambda xs:[{k:v for k,v in x.items() if k!='source_status'} for x in xs]
    for dto in dtos:
        row=rows[dto['id']];assert row['question']==dto['question'] and row['answer']==dto['answer'] and row['outcome']==dto['outcome'] and bool(row['refused'])==dto['refused']
        assert json.loads(row['provenance'])==dto['provenance'] and (json.loads(row['retrieval_trace']) if row['retrieval_trace'] is not None else None)==dto['retrieval_trace']
        assert clean(json.loads(row['sources']))==clean(dto['sources'])
    for row in rows.values():
        for citation in json.loads(row['sources']):
            version=versions[(citation['document_id'],citation['document_version'])];assert citation['content_hash']==version['content_hash'] and citation['quoted_text'] in version['normalized_content']
            for span in citation.get('answer_spans',[]):assert type(span['start'])is int and type(span['end'])is int and citation['quoted_text'][span['start']:span['end']]==span['text']
    events=obj('raw/http400/sse-events.json');saved=obj('raw/http400/sse-saved.json');done=[v for v in events if v['type']=='done'];assert len(done)==1 and events[-1]['type']=='done' and {k:v for k,v in done[0].items() if k!='type'}==saved
    assert ''.join(v['content'] for v in events if v['type']=='token')==saved['answer']
    early=obj('raw/http400/early-disconnect.json');assert early['outcome']=='interrupted' and early['answer']is None and early['sources']==[]
    for width in (390,768,1440):
        baseline=obj(f'raw/outage481/runs/first/baseline-{width}.json');recovered=obj(f'raw/outage481/runs/first/recovered-{width}.json')
        assert baseline['record']==recovered['actual_saved_get'] and recovered['local_retry_without_reload']is True and recovered['retry_query_post_count']==0 and recovered['session_key_retained']is True
    cleanup=obj('raw/offline485/frontend-cleanup.json');assert cleanup['port3506_closed']is True and cleanup['api8401_untouched']is True
    return {'status':'PASS bounded packet integrity/source/metadata checks','files_checked':len(actual),'stored_bytes':sum((root/name).stat().st_size for name in actual),'decoded_bytes_checked':total,'source31_runtime_tool_files':len(bindings['source31_copied']),'frontend_inputs':232,'wheel_app_members':191,'wheel_RECORD_entries':196,'PNG_counts':dict(pngs),'rich_DTOs_bound_to_scoped_rows':len(dtos),'scoped_query_rows':len(rows),'immutable_versions':len(versions),'full_gt_hex48_matches':0,'quality_gate':'OPEN','unseen_accepted':False,'native_gate_or_model_rerun':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--result',type=Path);args=parser.parse_args()
    try:result=check(args.root)
    except Exception as failure:
        # Error type only: never echo possible offending credentials/raw values.
        print(json.dumps({'status':'FAILED packet check','error_type':type(failure).__name__}));return 1
    if args.result:args.result.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
