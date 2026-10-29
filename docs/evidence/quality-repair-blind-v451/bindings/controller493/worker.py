"""Explicit-execution helper. No app/model/process action on import.

This helper validates unchanged frozen selection APIs and records an additional
post-seal opposing-source observation; it never modifies the frozen scorer.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.abc
import importlib.metadata
import json
from pathlib import Path
import sys

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','transformers','sentence_transformers'}:raise ImportError('Model imports forbidden in pure validation worker')

def runtime_check(path):
    expected=read(path)
    if sys.version!=expected['python'] or Path(sys.executable).resolve()!=Path(expected['executable']).resolve():raise ValueError('Actual Python differs from frozen runtime')
    actual={dist.metadata['Name'].lower().replace('_','-'):dist for dist in importlib.metadata.distributions()}
    required={d['name'].lower().replace('_','-'):d for d in expected['distributions']}
    if set(actual)!=set(required):raise ValueError('Installed distribution inventory differs')
    for name,row in required.items():
        # Freeze446 hashes the owning distribution's RECORD bytes. Reading it
        # as text normalizes CRLF on Windows and changes the frozen identity.
        # Do not scan dist.files: that can include vendored RECORD entries.
        dist=actual[name];record_path=Path(dist._path)/'RECORD';record_hash=digest(record_path) if record_path.is_file() else None
        if dist.version!=row['version'] or record_hash!=row['record_sha256']:raise ValueError('Installed distribution version/RECORD differs')
    return {'runtime_packages_verified':len(required),'model_imports':False}

def validate_selection(source,raw,selection):
    sys.meta_path.insert(0,NoModels());sys.path.insert(0,str(Path(source)/'apps/api'))
    from app.portfolio import load_corpus
    from app.portfolio.comparison import read_selection
    corpus=load_corpus(Path(raw));selected=read_selection('held_out',Path(selection),corpus['manifest']['manifest_sha256'])
    if selected is None or selected.get('schema_version')!=2:raise ValueError('Version-two selection required')
    return {'selection_validated_by_frozen_source':True,'model_imports':False}

def inspected_opponents(response):
    """Require explicit conflict/condition inspection evidence, never ranks alone."""
    selection=(response.get('provenance') or {}).get('answer_selection') or {};found=set()
    for conflict in selection.get('conflicts',[]):
        for extent in conflict.get('source_extent_checks',[]):
            if isinstance(extent,dict) and extent.get('document_id') and type(extent.get('document_version'))is int and isinstance(extent.get('content_hash'),str):found.add((extent['document_id'],extent['document_version'],extent['content_hash']))
    for requirement in selection.get('requirements',[]):
        proof=requirement.get('procedure_completeness') or {}
        for excluded in (proof.get('condition_exclusion_inventory') or {}).get('exclusions',[]):
            source=excluded.get('source_identity') or {}
            if source.get('document_id') and type(source.get('document_version'))is int and isinstance(source.get('content_hash'),str):found.add((source['document_id'],source['document_version'],source['content_hash']))
    return found

def opposition(pair,expectations):
    pair=Path(pair);seal=read(pair/'PAIR-SEALED.json')
    if seal.get('inspection_allowed')is not True or set(seal.get('arm_seals',{}))!={'baseline','candidate'}:raise ValueError('Both first reports must be sealed before inspection')
    for arm,expected in seal['arm_seals'].items():
        root=pair/arm
        if digest(root/'SEALED.json')!=expected:raise ValueError('Arm seal changed')
        arm_seal=read(root/'SEALED.json')
        if not arm_seal.get('children_closed') or not arm_seal.get('structurally_complete'):raise ValueError('Arm not complete/closed')
        for name,value in arm_seal['files'].items():
            target=(root/name).resolve()
            if not target.is_relative_to(root.resolve()) or digest(target)!=value:raise ValueError('Arm evidence changed after seal')
    value=read(expectations)
    if digest(expectations)!=seal['opposition_expectations_sha256'] or value['raw_manifest_sha256']!=seal['raw_manifest_sha256']:raise ValueError('Opposition sidecar changed')
    observations={};missing=0
    for arm in ('baseline','candidate'):
        report=read(pair/arm/'report.json');docs={d['id']:d for d in read(pair/arm/'corpus/documents.json')};mapping=report['source_document_ids'];rows=[]
        for method,method_report in report['results'].items():
            for row in method_report['cases']:
                expected=value['cases'][row['case_id']];seen=inspected_opponents(row.get('observed_response') or {})
                absent=[]
                for source in expected:
                    logical=source['document_id'];number=source['version_number'];body=docs[logical]['versions'][number-1]
                    if (mapping[logical],number,body['content_hash']) not in seen:absent.append(source)
                if arm=='candidate':missing+=len(absent)
                rows.append({'case_id':row['case_id'],'method':method,'required':len(expected),'missing':absent})
        observations[arm]=rows
    return {'scope':'Supplementary engineering inspection, separate from unchanged frozen score/gate','candidate_required_opposing_inspections_missing':missing,'acceptance_blocked_by_missing_required_inspection':bool(missing),'baseline_structured_inspection_not_required_for_acceptance':True,'observations':observations}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('runtime-check','validate-selection','opposition'))
    for name in ('source','raw','selection','frozen-runtime','pair','expectations'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    try:
        if args.action=='runtime-check':result=runtime_check(args.frozen_runtime)
        elif args.action=='validate-selection':result=validate_selection(args.source,args.raw,args.selection)
        else:result=opposition(args.pair,args.expectations)
    except (ImportError,OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'status':'unavailable','error_detail_suppressed':True}));return 2
    print(json.dumps(result,indent=2));return int(bool(result.get('acceptance_blocked_by_missing_required_inspection')))

if __name__=='__main__':raise SystemExit(main())
