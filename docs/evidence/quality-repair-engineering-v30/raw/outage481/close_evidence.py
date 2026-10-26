"""File-only closure; never query released ports or read restricted seed."""
import collections
import hashlib
import json
from pathlib import Path

H=Path(__file__).resolve().parent; Q=H.parent; OLD=Q/'typed-restart-outage-v466'; R=H/'runs/first'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
old_before=read(H/'preservation-before.json')
old_after={str(p):sha(p) for p in OLD.rglob('*') if p.is_file()}
assert old_before==old_after
with (H/'preservation-after.json').open('x',encoding='utf-8') as f:json.dump(old_after,f,indent=2)
prepared=read(H/'preparation.json'); assert all(sha(H/name)==value for name,value in prepared['files'].items())
assert sha(Q/'typed_runtime_recovery_v481.py')==prepared['wrapper_sha256']
assert read(H/'ports-before.json')==read(H/'ports-after.json')=={'8401':[],'3506':[]}
cleanup=read(R/'cleanup.json'); assert cleanup['api_port_closed'] and cleanup['frontend_port_closed']
assert cleanup['owned_processes']==[{'process':'browser','already_exited':True,'exit':0},{'process':'api-restarted','stopped':True},{'process':'frontend','stopped':True}]
assert (R/'browser-done.json').is_file() and not (R/'browser-error.json').exists()
rows=[]; groups=collections.Counter(); summary=[]
for p in sorted(R.glob('browser-observation-*.json')):
    d=read(p); width=d['viewport']['width']; baseline=read(R/f'baseline-{width}.json')['record']; recovered=read(R/f'recovered-{width}.json')
    assert baseline==recovered['actual_saved_get']
    assert recovered['local_retry_without_reload'] is True and recovered['retry_query_post_count']==0
    assert d['known_query_id']==baseline['id'] and d['stable_routes']==6 and d['local_retry_no_reload'] and d['identity_scope_denied']
    assert all(row['expected'] for row in d['issues']) and all(row['expected'] for row in d['request_failures'])
    for row in d['request_failures']:
        groups[(row['phase'],row['error'])]+=1; rows.append({'width':width,**row})
    assert any(x['phase']=='recovery' and x['path']=='/api/queries/'+baseline['id'] and x['status']==200 and x['method']=='GET' for x in d['api_responses'])
    summary.append({'width':width,'query_id':baseline['id'],'failures':len(d['request_failures']),'unexpected':0,'issues':len(d['issues']),'unexpected_issues':0})
assert len(summary)==3 and len(list((R/'screenshots').glob('*.png')))==36
result={'scope':'Single unchanged diagnostic protocol observation, not quality acceptance or original failure root cause','coordinator_exit':0,'browser_exit':0,'viewports':summary,'request_failure_groups':[{'phase':phase,'error':error,'count':count} for (phase,error),count in sorted(groups.items())],'request_failures':rows,'old466_unexpected_four_reproduced':False,'old466_failure_root_cause_resolved':False,'classification_or_assertion_changes':False,'ports_released':True,'preserved_old466_regular_files':len(old_after),'screenshots':36,'source_hashes':prepared['files'],'wrapper_sha256':prepared['wrapper_sha256']}
with (H/'diagnostic-result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
# Public actual outputs only; no staging/node_modules or private files are copied.
paths=[p for p in H.iterdir() if p.is_file() and p.name not in {'artifact-hashes.json','close.log'}]
paths += [p for p in R.iterdir() if p.is_file()]+list((R/'screenshots').glob('*.png'))+[Q/'typed_runtime_recovery_v481.py',Q/'typed-connected-live-v378/api-outage-retry-v481-process.json',Q/'typed-connected-live-v378/serve-outage-retry-v481-command.json']
manifest={str(p.relative_to(Q)):sha(p) for p in paths}
with (H/'artifact-hashes.json').open('x',encoding='utf-8') as f:json.dump(manifest,f,indent=2)
print(json.dumps({'coordinator_exit':0,'browser_exit':0,'diagnostic_failure_counts':result['request_failure_groups'],'viewports':summary,'old466_preserved':len(old_after),'public_hashed_files':len(manifest),'ports_released':True},indent=2))
