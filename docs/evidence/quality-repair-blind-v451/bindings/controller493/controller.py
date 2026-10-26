"""Prepared paired blind controller. Import/preflight perform file operations only.

Only --stage execute crosses process/loopback boundaries. Both original arm
reports are sealed with closed children before any quality summary is inspected.
No compiler, evaluator, corpus profile, source code or score rule is patched.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent
Q=HERE.parent
METHODS=('keyword','vector','hybrid','reranked')
ARMS=(('baseline',8401,'legacy-flat-v1'),('candidate',8402,'connected-paragraphs-v1'))
RAW_FILES={'documents.json','cases.json','profile.json'}
EXPECTED_COUNTS={'answerable':120,'unanswerable':40,'conflicting_stale':20,'adversarial':20}

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def save(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')

def checked_child(root,name):
    if not isinstance(name,str):raise ValueError('Manifest path must be text')
    root=Path(root).resolve(strict=True);path=(root/name).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Manifest path escaped root')
    return path

def check_files(root,files):
    if not isinstance(files,dict) or not files:raise ValueError('Empty file inventory')
    for name,expected in files.items():
        if not isinstance(expected,str) or len(expected)!=64 or digest(checked_child(root,name))!=expected:raise ValueError('Immutable file hash mismatch')
    return dict(files)

def check_source(root,files):
    check_files(root,files)
    actual={p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts}
    expected={name for name in files if Path(name).suffix in ('.py','.json')}
    if actual!=expected:raise ValueError('Frozen source contains unmanifested or missing import/data files')

def same_setting(actual,expected):
    if type(actual) in (int,float) and type(expected) in (int,float):return math.isfinite(actual) and math.isfinite(expected) and actual==expected
    return type(actual) is type(expected) and actual==expected

def raw_inventory(root,manifest_sha256,*,expected_counts=None):
    """Structural preflight; no labels/metrics printed. Tests may use tiny counts."""
    root=Path(root).resolve(strict=True);manifest=read(root/'manifest.json')
    if digest(root/'manifest.json')!=manifest_sha256:raise ValueError('Raw manifest differs from independently supplied pin')
    if manifest.get('schema_version')!=2 or manifest.get('corpus_role')!='blind' or manifest.get('score_contract')!='coverage-v2' or 'comparison_representation' in manifest:raise ValueError('Requires unprojected blind coverage-v2 raw corpus')
    if set(manifest.get('files',{}))!=RAW_FILES:raise ValueError('Unexpected raw file contract')
    check_files(root,manifest['files'])
    counts=expected_counts if expected_counts is not None else EXPECTED_COUNTS
    documents=read(root/'documents.json');cases=read(root/'cases.json');profile=read(root/'profile.json')
    if not isinstance(documents,list) or not documents or not isinstance(cases,list) or not isinstance(profile,dict):raise ValueError('Raw payload shape differs')
    if Counter(c.get('category') for c in cases)!=counts or any(c.get('split')!='held_out' for c in cases):raise ValueError('Requires full held_out 200/120+80 category inventory')
    if manifest.get('case_count')!=len(cases) or manifest.get('document_count')!=len(documents) or manifest.get('expected_counts')!={'held_out':counts}:raise ValueError('Raw declared counts differ')
    doc_ids={d['id'] for d in documents};ids={c['id'] for c in cases}
    if len(doc_ids)!=len(documents) or len(ids)!=len(cases) or any(not isinstance(i,str) or not i for i in doc_ids|ids):raise ValueError('Raw identities must be unique nonempty strings')
    principals=manifest.get('principals')
    if not isinstance(principals,dict) or not principals:raise ValueError('Raw principals missing')
    # Frozen seeder adds a workflow-only admin-a; never silently replace author identity.
    if 'admin-a' in principals and principals['admin-a']!={'workspace_id':'ops-a','role':'admin'}:raise ValueError('Author principal collides with frozen seeder workflow-only admin-a')
    families={}
    for document in documents:
        if document.get('owner') not in principals or document.get('split')!='held_out' or not isinstance(document.get('family'),str):raise ValueError('Document owner/family/split invalid')
        families[document['family']]='held_out'
        if document.get('workspace_id')!=principals[document['owner']].get('workspace_id'):raise ValueError('Document owner/workspace differ')
        versions=document['versions']
        if not versions or [v['version_number'] for v in versions]!=list(range(1,len(versions)+1)):raise ValueError('Version sequence invalid')
        if document.get('current_version_number')!=len(versions):raise ValueError('Current version differs from latest immutable body')
        for version in versions:
            if hashlib.sha256(version['content'].encode('utf-8')).hexdigest()!=version['content_hash']:raise ValueError('Raw source hash mismatch')
            if 'input_content' in version or 'input_sha256' in version:raise ValueError('Raw inputs must not already declare arm-specific uploads')
    for case in cases:
        if case.get('principal') not in principals or case.get('family') not in families:raise ValueError('Case principal/family invalid')
        if case.get('document_ids') is not None and not set(case['document_ids'])<=doc_ids:raise ValueError('Case document scope invalid')
    return {'manifest':manifest,'cases':cases,'documents':documents,'files':{'manifest.json':manifest_sha256,**manifest['files']},'case_categories':{c['id']:c['category'] for c in cases}}

def opposition_inventory(path,pin,raw):
    if not path or not pin:raise ValueError('Execution requires independently frozen opposition expectations and hash')
    if digest(path)!=pin:raise ValueError('Opposition sidecar hash differs')
    value=read(path)
    if value.get('schema')!='blind-opposition-expectations-v1' or value.get('raw_manifest_sha256')!=raw['files']['manifest.json']:raise ValueError('Opposition sidecar raw binding differs')
    cases=value.get('cases');catalog={d['id']:d for d in raw['documents']}
    if not isinstance(cases,dict) or set(cases)!=set(raw['case_categories']):raise ValueError('Opposition sidecar must explicitly cover every case, empty lists included')
    for expectations in cases.values():
        if not isinstance(expectations,list):raise ValueError('Opposition expectations must be lists')
        seen=set()
        for expected in expectations:
            if not isinstance(expected,dict) or set(expected)!={'document_id','version_number'}:raise ValueError('Opposition identity must name logical document/version only')
            doc=catalog.get(expected['document_id']);number=expected['version_number'];identity=(expected['document_id'],number)
            if doc is None or type(number)is not int or not 1<=number<=len(doc['versions']) or identity in seen:raise ValueError('Unknown/duplicate opposing source version')
            seen.add(identity)
    return value

def frozen_inputs():
    pins=read(HERE/'frozen-inputs.json')
    for relative,expected in pins['files'].items():
        if digest(checked_child(Q,relative))!=expected:raise ValueError('Frozen controller dependency drift')
    freeze=read(Q/'candidate-freeze-v446/freeze.json');projection=read(Q/'candidate-selection-v455/selection-compatible-freeze.json')
    if projection['parent_freeze_sha256']!=pins['files']['candidate-freeze-v446/freeze.json'] or projection['frozen_at']!=freeze['frozen_at']:raise ValueError('Projection parent/date differs')
    for key,value in freeze['settings'].items():
        if not same_setting(projection['settings'].get(key),value):raise ValueError('Projection changes frozen runtime setting')
    check_source(Q/freeze['source_snapshot'],read(Q/'requirements-source-v31.json')['files'])
    baseline=read(Q/'baseline-freeze-v417/source-manifest.json')
    check_source(Q/'baseline-freeze-v417/source',baseline['extracted_runtime_subset'])
    if baseline['commit']!=freeze['baseline_commit'] or baseline['archive_sha256']!=freeze['baseline_archive_sha256']:raise ValueError('Original baseline commit/archive differs')
    return pins,freeze,projection

def selection_binding(path,pin,raw,projection):
    if not path or not pin or digest(path)!=pin:raise ValueError('Frozen selection and its independent hash required')
    selection=read(path)
    if selection.get('schema_version')!=2 or selection.get('selection_basis')!='development_only' or selection.get('validation_corpus_manifest_sha256')!=raw['files']['manifest.json']:raise ValueError('Selection validation binding differs')
    if selection.get('settings')!=projection['settings'] or selection.get('frozen_at')!=projection['frozen_at']:raise ValueError('Selection reselected frozen settings/date')
    for prefix,expected_path in [('candidate_freeze',Q/'candidate-selection-v455/selection-compatible-freeze.json'),('development_report',Path(projection['development_report_path']))]:
        target=Path(selection[prefix+'_path']);target=target if target.is_absolute() else Path(path).parent/target
        if target.resolve()!=expected_path.resolve() or digest(target)!=selection[prefix+'_sha256']:raise ValueError('Selection evidence path/hash differs')
    if selection.get('development_corpus_manifest_sha256')!=projection['development_corpus_manifest_sha256']:raise ValueError('Selection development corpus differs')
    return selection

def approval(path,pin):
    if not path or not pin or digest(path)!=pin:raise ValueError('Independent controller review approval and hash required')
    value=read(path)
    if value.get('verdict')!='approved' or value.get('scope')!='blind-pair-controller-v476':raise ValueError('Review approval scope/verdict differs')
    expected={name:digest(HERE/name) for name in ('controller.py','worker.py','frozen-inputs.json')}
    if value.get('reviewed_files')!=expected:raise ValueError('Controller changed since independent review')

def disjoint_output(output,protected):
    output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(Q.resolve()):raise ValueError('Output must be a new Q directory')
    for root in protected:
        root=Path(root).resolve()
        if output.is_relative_to(root) or root.is_relative_to(output):raise ValueError('Output overlaps immutable input')
    return output

def preflight(args):
    pins,freeze,projection=frozen_inputs()
    raw=raw_inventory(args.raw_corpus,args.raw_manifest_sha256)
    selection=selection_binding(args.selection,args.selection_sha256,raw,projection) if args.selection else None
    opposition=opposition_inventory(args.opposition_expectations,args.opposition_expectations_sha256,raw) if args.opposition_expectations else None
    python=Path(read(Q/'candidate-freeze-v446/runtime.json')['executable']).resolve(strict=True)
    if args.python and Path(args.python).resolve()!=python:raise ValueError('Python differs from frozen measured executable')
    protected=[args.raw_corpus,Q/'requirements-source-v31',Q/'baseline-freeze-v417',Q/'candidate-freeze-v446',Q/'candidate-selection-v455',HERE,*[Path(v['root']) for v in freeze['model_bindings'].values()]]
    for item in (args.selection,args.opposition_expectations,args.review_approval):
        if item:protected.append(Path(item).resolve().parent)
    output=disjoint_output(args.output,protected)
    return {'pins':pins,'freeze':freeze,'projection':projection,'raw':raw,'selection':selection,'opposition':opposition,'python':python,'output':output}

def port_free(port):
    with socket.socket() as stream:
        if os.name=='nt':stream.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try:stream.bind(('127.0.0.1',port));return True
        except OSError:return False

def environment(ctx,arm,root):
    path=Q/'development-controller-v346/controller.py';spec=importlib.util.spec_from_file_location('_frozen_env346',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    freeze=ctx['freeze'];source=Q/('baseline-freeze-v417/source' if arm=='baseline' else 'requirements-source-v31')
    models=freeze['model_bindings'];settings=freeze['settings']
    config=SimpleNamespace(source=source,output=root,embedding=Path(models['embedding']['root']),reader=Path(models['reader']['root']),support=Path(models['support']['root']),margin=settings['support_min_margin'],proposal_profile=settings['answer_proposal_profile'],role_scope_policy=settings['role_scope_policy'],procedure_profile=settings['procedure_verification_profile'],source_context_policy=settings['source_context_policy'])
    env=module.environment(config)
    for key in list(env):
        if key.upper() in {'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'}:del env[key]
    env['NO_PROXY']='127.0.0.1,localhost,::1';env['no_proxy']=env['NO_PROXY']
    if arm=='baseline':env.update(ANSWER_SELECTION_MODE='lexical',ANSWER_SUPPORT_MODE='disabled',SOURCE_CONTEXT_POLICY='explicit_target_v1',PROCEDURE_VERIFICATION_PROFILE='all_units_nli_v1')
    return env,source,module

def tool_environment(api_env,arm):
    """Source31 tools need a valid profile even while serving original417.

    Copy only: baseline API/migration environment and candidate measured profile
    remain unchanged. The same tool environment drives bootstrap and evaluation.
    """
    env={**api_env,'PYTHONPATH':str(Q/'requirements-source-v31/apps/api')}
    if arm=='baseline':
        env.update(ANSWER_SELECTION_MODE='lexical',ANSWER_SUPPORT_MODE='disabled',ANSWER_PROPOSAL_PROFILE='qa_only_v1',ROLE_SCOPE_POLICY='literal_v1',PROCEDURE_VERIFICATION_PROFILE='all_units_nli_v1',SOURCE_CONTEXT_POLICY='explicit_target_v1')
    return env

class ProcessBoundary:
    """Only explicitly executed, owned local processes; no shell, WSL or installs."""
    def start(self,argv,cwd,env,log):
        with Path(log).open('xb') as stream:
            return subprocess.Popen(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def stop(self,process):
        if process.poll() is None:
            if os.name=='nt':
                result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
                if result.returncode!=0 and process.poll() is None:raise RuntimeError('Owned PID tree stop failed')
            else:process.terminate()
            process.wait(timeout=30)
        return process.returncode
    def run(self,argv,cwd,env,log,timeout,*,server=None):
        process=self.start(argv,cwd,env,log);deadline=time.monotonic()+timeout
        try:
            while process.poll() is None:
                if server is not None and server.poll() is not None:raise RuntimeError('Owned API exited during command')
                if time.monotonic()>deadline:raise TimeoutError('Owned child command deadline exceeded')
                time.sleep(.2)
            return process.returncode
        finally:
            if process.poll() is None:self.stop(process)
    def health(self,port):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/health/ready',timeout=30) as response:return response.status,json.loads(response.read())

def verify_models(ctx):
    for binding in ctx['freeze']['model_bindings'].values():
        root=Path(binding['root'])
        if digest(root/binding['manifest'])!=binding['manifest_sha256']:raise ValueError('Model manifest drift')
        check_files(root,binding['files'])

def seal(root,**metadata):
    files={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file() and p!=root/'SEALED.json'}
    save(root/'SEALED.json',{'created_at':datetime.now(UTC).isoformat(),'files':files,**metadata})
    return digest(root/'SEALED.json')

def structural_report(path,arm,raw,selection_pin):
    """Only completeness metadata. Do not read/summarize quality before pair seal."""
    report=read(path)
    if report.get('execution_arm')!=arm or report.get('split')!='held_out' or report.get('selection_sha256')!=selection_pin or report.get('common_corpus_manifest_sha256')!=raw['files']['manifest.json'] or set(report.get('results',{}))!=set(METHODS):raise ValueError('Report metadata/method inventory incomplete')
    for method in METHODS:
        rows=report['results'][method].get('cases',[])
        if len(rows)!=len(raw['case_categories']) or {row['case_id']:row['category'] for row in rows}!=raw['case_categories']:raise ValueError('Report exact case inventory incomplete')
    return {'report_sha256':digest(path),'methods':list(METHODS),'cases_per_method':len(raw['case_categories'])}

def execute(args,ctx,boundary=None):
    if not ctx['selection'] or not ctx['opposition']:raise ValueError('Explicit execution needs selection and opposition sidecar')
    approval(args.review_approval,args.review_approval_sha256)
    if any(not port_free(port) for _,port,_ in ARMS):raise ValueError('Dedicated port occupied; no existing process stopped')
    verify_models(ctx)
    system=boundary or ProcessBoundary();output=ctx['output'];output.mkdir(parents=True,exist_ok=False)
    save(output/'execution-plan.json',public_plan(args,ctx));commands=[];arm_seals={};status='infrastructure_partial';error=None
    try:
        # Compiler/evaluator/seed tooling are frozen31 for both arms. Server and
        # migration imports use each arm's own frozen source independently.
        for arm,port,profile in ARMS:
            root=output/arm;root.mkdir();(root/'data').mkdir();private=root/'private';private.mkdir()
            os.chmod(private,0o700)
            if os.name=='nt':
                account=os.environ.get('USERDOMAIN','')+'\\'+os.environ['USERNAME']
                acl=subprocess.run(['icacls',str(private),'/inheritance:r','/grant:r',account+':(OI)(CI)F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
                if acl.returncode:raise RuntimeError('Private seed ACL setup failed')
            env,source,authority=environment(ctx,arm,root);tools_env=tool_environment(env,arm);python=str(ctx['python']);process=None;closed=True;complete=False;info=None;api_entry=None
            def unchanged():
                frozen_inputs();check_files(args.raw_corpus,ctx['raw']['files'])
                if digest(args.selection)!=args.selection_sha256 or digest(args.opposition_expectations)!=args.opposition_expectations_sha256:raise ValueError('Selected inputs changed')
            def run(argv,stage,tool=False,allow_quality=False):
                unchanged();entry={'arm':arm,'stage':stage,'argv':argv,'cwd':str(source),'exit':None};commands.append(entry)
                code=system.run(argv,source,tools_env if tool else env,root/(stage+'.log'),args.command_timeout,server=process)
                entry['exit']=code;unchanged()
                if code not in ((0,1) if allow_quality else (0,)):raise RuntimeError('Infrastructure child failed: '+stage)
                return code
            try:
                if not port_free(port):raise ValueError('Dedicated port occupied before own arm startup')
                run([python,'-B',str(HERE/'worker.py'),'runtime-check','--frozen-runtime',str(Q/'candidate-freeze-v446/runtime.json')],'runtime',tool=True)
                run([python,'-B',str(Q/'requirements-source-v31/scripts/compile_corpus_representation.py'),str(args.raw_corpus),str(root/'corpus'),'--profile',profile],'compile',tool=True)
                run([python,'-B',str(HERE/'worker.py'),'validate-selection','--source',str(Q/'requirements-source-v31'),'--raw',str(args.raw_corpus),'--selection',str(args.selection)],'selection',tool=True)
                run([python,'-B','-m','app.db.migrate'],'migrate')
                argv=[python,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log']
                api_entry={'arm':arm,'stage':'api','argv':argv,'cwd':str(source),'exit':None};commands.append(api_entry)
                process=system.start(argv,source,env,root/'api.log');closed=False
                save(root/'process.json',{'owned_pid':process.pid,'port':port,'runtime_source':str(source),'argv':argv})
                deadline=time.monotonic()+args.readiness_timeout
                while True:
                    if process.poll() is not None:raise RuntimeError('Owned API exited before readiness')
                    try:
                        code,ready=system.health(port)
                        if code==200 and ready.get('status')=='ready':break
                    except (urllib.error.URLError,TimeoutError,OSError):pass
                    if time.monotonic()>deadline:raise TimeoutError('Readiness deadline exceeded')
                    time.sleep(.2)
                save(root/'readiness.json',ready)
                expected=authority.expected_runtime(SimpleNamespace(margin=ctx['freeze']['settings']['support_min_margin'],proposal_profile=ctx['freeze']['settings']['answer_proposal_profile'],role_scope_policy=ctx['freeze']['settings']['role_scope_policy'],procedure_profile=ctx['freeze']['settings']['procedure_verification_profile'],source_context_policy=ctx['freeze']['settings']['source_context_policy'])) if arm=='candidate' else {'embedding':{'mode':'local','revision':ctx['freeze']['model_bindings']['embedding']['revision'],'dimension':384},'generation_mode':'extractive','ingestion_mode':'inline','persistence':'sqlite','authentication':'api-key'}
                if not authority.includes(ready.get('runtime'),expected) or ready.get('checks',{}).get('database')!='ok' or ready.get('checks',{}).get('embeddings')!='ok':raise ValueError('Actual readiness/runtime differs from frozen arm')
                run([python,'-B',str(Q/'requirements-source-v31/scripts/seed_portfolio.py'),'--api-url',f'http://127.0.0.1:{port}','--manifest',str(private/'seed.json'),'--corpus-dir',str(root/'corpus'),'--confirm-disposable-database'],'seed',tool=True)
                run([python,'-B',str(Q/'requirements-source-v31/scripts/evaluate_portfolio_retrieval.py'),'--seed-manifest',str(private/'seed.json'),'--corpus-dir',str(root/'corpus'),'--output',str(root/'report.json'),'--split','held_out','--method','all','--execution-arm',arm,'--selection',str(args.selection)]+(['--require-answer-spans'] if arm=='candidate' else []),'evaluate',tool=True,allow_quality=True)
                info=structural_report(root/'report.json',arm,ctx['raw'],args.selection_sha256);complete=True
            finally:
                if process is not None:
                    stop_exit=system.stop(process);api_entry['exit']=stop_exit;deadline=time.monotonic()+30
                    while time.monotonic()<deadline and not port_free(port):time.sleep(.1)
                    closed=process.poll() is not None and port_free(port)
                    save(root/'cleanup.json',{'owned_pid':process.pid,'exit':stop_exit,'children_closed':closed,'port_closed':port_free(port)})
                unchanged()
                save(root/'controller-state.json',{'report_structurally_complete':complete,'children_closed':closed,'structural_binding':info})
                arm_seals[arm]=seal(root,children_closed=closed,structurally_complete=complete,inspection_allowed=False)
                if not closed:raise RuntimeError('Owned arm process/port did not close')
            # A quality exit1 never prevents the next arm. Infrastructure exit2
            # stops here, preserves partial arm evidence, and never opens scores.
        verify_models(ctx);frozen_inputs();check_files(args.raw_corpus,ctx['raw']['files'])
        save(output/'PAIR-SEALED.json',{'arm_seals':arm_seals,'both_structurally_complete':True,'both_children_closed':True,'raw_manifest_sha256':args.raw_manifest_sha256,'selection_sha256':args.selection_sha256,'opposition_expectations_sha256':args.opposition_expectations_sha256,'inspection_allowed':True,'created_at':datetime.now(UTC).isoformat()})
        # Only after the durable pair seal may any frozen score or extra
        # engineering opposition observation be read by a child/reviewer.
        tools_env['PYTHONPATH']=str(Q/'requirements-source-v31/apps/api')
        comparison_argv=[str(ctx['python']),'-B',str(Q/'requirements-source-v31/scripts/verify_answer_coverage_delivery.py'),'--baseline',str(output/'baseline/report.json'),'--candidate',str(output/'candidate/report.json'),'--corpus-dir',str(args.raw_corpus),'--baseline-corpus-dir',str(output/'baseline/corpus'),'--candidate-corpus-dir',str(output/'candidate/corpus'),'--selection',str(args.selection)]
        comparison_entry={'arm':'pair','stage':'postseal_comparison','argv':comparison_argv,'cwd':str(Q/'requirements-source-v31'),'exit':None};commands.append(comparison_entry)
        comparison=system.run(comparison_argv,Q/'requirements-source-v31',tools_env,output/'comparison.json',args.command_timeout);comparison_entry['exit']=comparison
        if comparison not in (0,1):raise RuntimeError('Frozen portable comparison unavailable')
        opposition_argv=[str(ctx['python']),'-B',str(HERE/'worker.py'),'opposition','--source',str(Q/'requirements-source-v31'),'--pair',str(output),'--expectations',str(args.opposition_expectations)]
        opposition_entry={'arm':'pair','stage':'postseal_opposition','argv':opposition_argv,'cwd':str(Q/'requirements-source-v31'),'exit':None};commands.append(opposition_entry)
        opposition=system.run(opposition_argv,Q/'requirements-source-v31',tools_env,output/'opposition.json',args.command_timeout);opposition_entry['exit']=opposition
        if opposition not in (0,1):raise RuntimeError('Postseal opposition inspection unavailable')
        status='sealed_pair_inspected';save(output/'postseal-status.json',{'comparison_exit':comparison,'supplementary_opposition_exit':opposition,'acceptance_claimed':False,'note':'Frozen gate and supplementary engineering obligations remain separately reviewable; exit0 is not autonomous acceptance'})
        return max(comparison,opposition)
    except BaseException as exc:
        # Do not serialize exception text: source/HTTP libraries could include keys.
        error=type(exc).__name__;return 2
    finally:
        save(output/'commands.json',commands);save(output/'controller-result.json',{'status':status,'error_type':error,'quality_or_blind_acceptance_claimed':False,'pair_seal_exists':(output/'PAIR-SEALED.json').is_file()})
        seal(output,inspection_allowed=(output/'PAIR-SEALED.json').is_file(),status=status)

def public_plan(args,ctx):
    return {'stage':args.stage,'raw_manifest_sha256':args.raw_manifest_sha256,'settings':ctx['freeze']['settings'],'candidate_commit':ctx['freeze']['candidate_commit'],'baseline_commit':ctx['freeze']['baseline_commit'],'python':str(ctx['python']),'methods':list(METHODS),'case_count':len(ctx['raw']['case_categories']),'arms':[{'arm':arm,'port':port,'profile':profile,'database':str(ctx['output']/arm/'data/groundtruth.sqlite')} for arm,port,profile in ARMS],'selection_bound':ctx['selection'] is not None,'opposition_expectations_bound':ctx['opposition'] is not None,'execute_requires_independent_review':True,'execution_performed':False,'provider_credentials_included':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('preflight','execute'),required=True)
    for key in ('raw-corpus','output'):parser.add_argument('--'+key,type=lambda x:Path(x).resolve(),required=True)
    parser.add_argument('--raw-manifest-sha256',required=True)
    for key in ('selection','opposition-expectations','review-approval','python'):parser.add_argument('--'+key,type=lambda x:Path(x).resolve())
    for key in ('selection','opposition-expectations','review-approval'):parser.add_argument('--'+key+'-sha256')
    parser.add_argument('--readiness-timeout',type=float,default=600)
    parser.add_argument('--command-timeout',type=float,default=21600)
    args=parser.parse_args()
    try:
        if args.readiness_timeout<=0 or args.command_timeout<=0:raise ValueError('Timeout must be positive')
        ctx=preflight(args)
        if args.stage=='preflight':
            ctx['output'].mkdir(parents=True,exist_ok=False);save(ctx['output']/'preflight.json',public_plan(args,ctx));print(json.dumps({'stage':'preflight','execution_performed':False,'plan':str(ctx['output']/'preflight.json')}));return 0
        code=execute(args,ctx);print(json.dumps({'stage':'execute','controller_exit':code,'evidence':str(ctx['output']),'pair_seal_exists':(ctx['output']/'PAIR-SEALED.json').is_file(),'acceptance_claimed':False}));return code
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'preflight_or_setup_unavailable','error_type':type(exc).__name__,'execution_not_claimed':True}));return 2

if __name__=='__main__':raise SystemExit(main())
