"""Bounded direct TypeScript/ESLint gate observation. No source/config repair."""
import datetime,hashlib,json,re,subprocess,sys,time
from pathlib import Path

H=Path(__file__).resolve().parent;Q=H.parent;W=Q.parent/'delivery-worktree';WEB=W/'apps/web';B=W/'docs/evidence/quality-repair-engineering-v30'
NODE=Path('C:/Program Files/nodejs/node.exe')
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
write=lambda name,obj:(H/name).write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
expected=read(B/'raw/gates/build430/source-restored.json')['files'];assert len(expected)==232
source=lambda:{n:sha((WEB/n).read_bytes()) for n in expected}
bundle=lambda:{p.relative_to(B).as_posix():sha(p.read_bytes()) for p in B.rglob('*') if p.is_file()}
before=source();bundle_before=bundle();write('source-before.json',before);write('bundle-before.json',bundle_before)
record={'schema':'direct-frontend-gates-v510','started_utc':now(),'cwd':str(WEB),'source_inventory':232,'source_manifest_sha256':sha((B/'raw/gates/build430/source-restored.json').read_bytes()),'quality_gate':'OPEN','unseen_accepted':False,'commands':[]}
def finish(exit_code,reason):
    after=source();bundle_after=bundle();write('source-after.json',after);write('bundle-after.json',bundle_after)
    record.update({'finished_utc':now(),'wrapper_exit':exit_code,'outcome':reason,'source_before_after_equal':before==after,'source_after_equals_frozen232':after==expected,'bundle818_before_after_equal':bundle_before==bundle_after,'source_changes':[n for n in before if before[n]!=after[n]],'staging_or_commit':False,'build_typegen_browser_model_API_services_install_network':False})
    write('RESULT.json',record)
    print(json.dumps(record,indent=2),flush=True)
    return exit_code
if before!=expected:
    sys.exit(finish(2,'STOP: current232 source hashes differ from frozen430/446; no gate or repair attempted'))
assert sha((B/'raw/gates/build430/source-restored.json').read_bytes())==read(B/'bindings/freeze446/freeze.json')['frontend_manifest_sha256']
record['canonical_next_env_sha256']=before['next-env.d.ts'];record['canonical_tsconfig_sha256']=before['tsconfig.json']
generated={}
for ref in re.findall(r'^import\s+"(\./[^\"]+)";', (WEB/'next-env.d.ts').read_text(),re.MULTILINE):
    p=WEB/ref
    if not p.is_file():
        record['missing_generated_type']=ref
        sys.exit(finish(2,'STOP: canonical next-env generated type prerequisite missing; no typegen/config repair attempted'))
    generated[ref]=sha(p.read_bytes())
write('generated-prerequisites-before.json',generated)
tool_paths={'typescript':WEB/'node_modules/typescript/bin/tsc','eslint':WEB/'node_modules/eslint/bin/eslint.js'}
if not NODE.is_file() or not all(p.is_file() for p in tool_paths.values()):
    sys.exit(finish(2,'STOP: expected local Node/tool entrypoint unavailable'))
runtime_cmd=[str(NODE),'-p','JSON.stringify({execPath:process.execPath,version:process.version,versions:process.versions,arch:process.arch,platform:process.platform})']
rt_started=now();rt=subprocess.run(runtime_cmd,cwd=WEB,capture_output=True)
(H/'node-runtime.stdout.log').write_bytes(rt.stdout);(H/'node-runtime.stderr.log').write_bytes(rt.stderr)
assert rt.returncode==0
runtime={'argv':runtime_cmd,'started_utc':rt_started,'finished_utc':now(),'exit':rt.returncode,'runtime':json.loads(rt.stdout),'node_executable_sha256':sha(NODE.read_bytes()),'tools':{name:{'entrypoint':str(p),'entrypoint_sha256':sha(p.read_bytes()),'version':read(WEB/f'node_modules/{name}/package.json')['version']} for name,p in tool_paths.items()}}
write('runtime.json',runtime);record['runtime_record_sha256']=sha((H/'runtime.json').read_bytes())
for name,args in [('typescript',['--noEmit','--incremental','false']),('eslint',['.','--max-warnings=0','--no-cache'])]:
    argv=[str(NODE),str(tool_paths[name]),*args];started=now();start=time.monotonic()
    invocation={'gate':name,'argv':argv,'cwd':str(WEB),'started_utc':started,'no_cache_or_emit':True}
    write(name+'-invocation.json',invocation)
    print(json.dumps({'gate':name,'started_utc':started,'argv':argv}),flush=True)
    result=subprocess.run(argv,cwd=WEB,capture_output=True)
    duration=time.monotonic()-start;finished=now()
    (H/(name+'.stdout.log')).write_bytes(result.stdout);(H/(name+'.stderr.log')).write_bytes(result.stderr)
    outcome={**invocation,'finished_utc':finished,'duration_seconds':duration,'exit':result.returncode,'stdout_bytes':len(result.stdout),'stderr_bytes':len(result.stderr),'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)}
    write(name+'-result.json',outcome);record['commands'].append(outcome)
    if result.returncode:
        sys.exit(finish(1,'STOP: actual '+name+' gate failed; source/config untouched, no repair or further gate attempted'))
generated_after={ref:sha((WEB/ref).read_bytes()) for ref in generated};write('generated-prerequisites-after.json',generated_after)
assert generated==generated_after
record['generated_type_prerequisites_unchanged']=True
sys.exit(finish(0,'PASS: direct current TypeScript and ESLint gates both exit0 with explicit process exit records'))
