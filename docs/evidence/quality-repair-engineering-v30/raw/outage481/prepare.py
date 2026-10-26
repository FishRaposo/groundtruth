"""Diagnostic-only capture successor. Preserves all old466 files before launch."""
import ast
import hashlib
import json
from pathlib import Path

H=Path(__file__).resolve().parent; Q=H.parent; OLD=Q/'typed-restart-outage-v466'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(OLD/'browser.mjs')=='10e3a8c55b5f0548e12d4e22602ea203aaffc93082e5c9bf5ff4992cade8192a'
assert sha(OLD/'coordinator.py')=='bbc57e6d367515a3721bf1a4db27d4900e218e702688ed18b0f8a1318faf4229'
preserved={str(p):sha(p) for p in OLD.rglob('*') if p.is_file()}
with (H/'preservation-before.json').open('x',encoding='utf-8') as f:json.dump(preserved,f,indent=2)
coordinator=(OLD/'coordinator.py').read_text(encoding='utf-8').replace('api-outage-retry-v464-process.json','api-outage-retry-v481-process.json')
browser=(OLD/'browser.mjs').read_text(encoding='utf-8')
prior='contexts:states.map(state=>({viewport:state.viewport,phase:state.phase,url:state.page.url()}))'
after='contexts:states.map(state=>({viewport:state.viewport,phase:state.phase,url:state.page.url(),issues:state.issues,apiFailures:state.apiFailures,apiResponses:state.apiResponses,requests:state.requests}))'
assert browser.count(prior)==1; browser=browser.replace(prior,after)
for name,value in [('coordinator.py',coordinator),('browser.mjs',browser)]:
    with (H/name).open('x',encoding='utf-8',newline='') as f:f.write(value)
with (H/'venv-executable-binding.json').open('xb') as f:f.write((OLD/'venv-executable-binding.json').read_bytes())
wrapper=(Q/'typed_runtime_recovery_v464.py').read_text(encoding='utf-8').replace('outage-retry-v464','outage-retry-v481')
with (Q/'typed_runtime_recovery_v481.py').open('x',encoding='utf-8',newline='') as f:f.write(wrapper)
# Semantic/diff checks: no ownership, classification, expectation or assertion edit.
assert coordinator.replace('api-outage-retry-v481-process.json','api-outage-retry-v464-process.json')==(OLD/'coordinator.py').read_text(encoding='utf-8')
assert browser.replace(after,prior)==(OLD/'browser.mjs').read_text(encoding='utf-8')
assert all(text in browser for text in ('Loading durable usage and audit history…','Loading recorded events…'))
result={'scope':'Diagnostic arrays only; unchanged protocol/classification/assertions/guards','preserved_old466_files':len(preserved),'files':{name:sha(H/name) for name in ('coordinator.py','browser.mjs','venv-executable-binding.json')},'wrapper_sha256':sha(Q/'typed_runtime_recovery_v481.py')}
with (H/'preparation.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
