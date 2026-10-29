"""Portable frozen DEV29 evidence audit; never performs inference, HTTP or SQL."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parent
PINNED_REPORT='7d2104064d64fc1fd4cc645fe586f68616e8c79381cfc6ff65cc77f1b1f88b0e'
PINNED_SOURCE_MANIFEST='0798ee3fe2127d726577c9cb280ed1764a408604473cecb7897dcbff949cd58a'
PINNED_CORPUS_MANIFEST='22c7cf7ccbc229d641b26ea359bdb74420c313b411505734681c843a7ba54cf4'
sha=lambda b: hashlib.sha256(b).hexdigest()
read=lambda p: json.loads(p.read_text(encoding='utf-8-sig'))

def safe_name(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe evidence path')
    return p

def integrity():
    listed={}
    for line in (ROOT/'checksums.sha256').read_text().splitlines():
        digest,name=line.split('  ',1)
        safe_name(name)
        if name in listed: raise ValueError('Duplicate checksum path')
        listed[name]=digest
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'checksums.sha256'}
    if actual!=set(listed): raise ValueError('Checksum inventory is not closed')
    for name,digest in listed.items():
        if sha((ROOT/name).read_bytes())!=digest: raise ValueError('Changed export: '+name)
    m=read(ROOT/'manifest.json')
    if set(m['files'])!=actual-{'manifest.json'}: raise ValueError('Manifest inventory differs')
    for name,record in m['files'].items():
        data=(ROOT/name).read_bytes()
        if record!={'sha256':sha(data),'bytes':len(data)}: raise ValueError('Changed inventory record: '+name)
    if sha((ROOT/'source-manifest.json').read_bytes())!=PINNED_SOURCE_MANIFEST: raise ValueError('Changed source authority')
    source=read(ROOT/'source-manifest.json')['files']
    with zipfile.ZipFile(ROOT/'frozen-source.zip') as z:
        if len(z.namelist())!=229 or len(set(z.namelist()))!=229 or set(z.namelist())!=set(source): raise ValueError('Source member set differs')
        for n,d in source.items():
            safe_name(n)
            if sha(z.read(n))!=d: raise ValueError('Frozen source differs: '+n)
    with zipfile.ZipFile(ROOT/'frozen-candidate-corpus.zip') as z:
        if set(z.namelist())!={'cases.json','documents.json','manifest.json','profile.json'} or len(z.namelist())!=4: raise ValueError('Corpus member set differs')
        for n in z.namelist(): safe_name(n)
        if sha(z.read('manifest.json'))!=PINNED_CORPUS_MANIFEST: raise ValueError('Changed corpus authority')
        corpus_manifest=json.loads(z.read('manifest.json'))
        for n,d in corpus_manifest['files'].items():
            if sha(z.read(n))!=d: raise ValueError('Frozen corpus differs: '+n)
    raw=gzip.decompress((ROOT/'report.json.gz').read_bytes())
    if sha(raw)!=PINNED_REPORT or len(raw)!=41390203: raise ValueError('Changed raw first report')
    r=json.loads(raw)
    if r['results']['reranked']['summary']!=m['summary']: raise ValueError('Summary differs')
    if read(ROOT/'source-snapshots.json')!=r['source_manifest']: raise ValueError('Source observations differ')
    failures=[x for x in r['results']['reranked']['cases'] if not x['passed']]
    if read(ROOT/'actual-failure-records.json')['cases']!=failures: raise ValueError('Failure objects differ')
    pairs={}
    for row in failures:
        for c in row['observed_response']['provenance']['answer_selection']['conflicts']:
            for extent in c.get('source_extent_checks',[]):
                if 'condition_scope' in extent:
                    pairs[(row['case_id'],extent['document_id'])]=extent['condition_scope']
    observations=read(ROOT/'actual-context-nli-observations.json')['observations']
    if len(observations)!=6 or len(pairs)!=6: raise ValueError('Actual note observations differ')
    for item in observations:
        if item['condition_scope']!=pairs[(item['case_id'],item['actual_document_id'])]: raise ValueError('Actual NLI observation differs')
    return r,{'export_files_hashed':len(listed),'source_files_hashed':229,'corpus_files_hashed':4,'raw_report_sha256':sha(raw),'raw_report_bytes':len(raw),'actual_note_observations':6,'development_qualified':False,'blind_acceptance':False}

def canonical(report,scratch):
    scratch=scratch.resolve()
    if scratch.exists(): raise ValueError('Canonical replay requires a new nonexistent scratch directory')
    if scratch==ROOT or scratch.is_relative_to(ROOT): raise ValueError('Scratch must be outside immutable export')
    scratch.mkdir(parents=True)
    for archive_name,folder in [('frozen-source.zip','source'),('frozen-candidate-corpus.zip','corpus')]:
        base=scratch/folder
        base.mkdir()
        with zipfile.ZipFile(ROOT/archive_name) as z:
            for name in z.namelist():
                safe_name(name)
                target=(base/name).resolve()
                if not target.is_relative_to(base): raise ValueError('Unsafe archive member')
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as f: f.write(z.read(name))
    source=scratch/'source'
    sys.path.insert(0,str(source/'apps/api'))
    sys.dont_write_bytecode=True
    os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
    from app.portfolio import load_corpus
    if not Path(sys.modules['app.portfolio'].__file__).resolve().is_relative_to(source): raise ValueError('Wrong app source imported')
    corpus=load_corpus(scratch/'corpus',expected_representation_profile='connected-paragraphs-v1',expected_common_manifest_sha256=read(ROOT/'execution-settings.json')['common_manifest_sha256'])
    spec=importlib.util.spec_from_file_location('frozen_dev29_audit',source/'scripts/verify_answer_coverage_delivery.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    result=verifier.audit_report(report,corpus)
    if not result['verified'] or result['case_rows']!=80: raise ValueError('Frozen scorer rejected report')
    if 'torch' in sys.modules or 'transformers' in sys.modules: raise ValueError('Model library imported unexpectedly')
    if result['runtime_verification']['verified']: raise ValueError('Unexpected historical runtime attestation')
    return {'frozen_scorer_audit':result,'model_libraries_imported':False,'inference_performed':False,'scratch_retained_for_inspection':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--canonical',action='store_true',help='Use frozen scorer; needs existing API Python dependencies, no models')
    p.add_argument('--scratch-dir',type=Path,help='New path outside export; extracted source and corpus retained')
    a=p.parse_args()
    report,result=integrity()
    if a.canonical:
        if a.scratch_dir is None: p.error('--canonical requires --scratch-dir')
        result.update(canonical(report,a.scratch_dir))
    result['scope']='Author evidence replay; not a model run, independent export review or quality acceptance'
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
