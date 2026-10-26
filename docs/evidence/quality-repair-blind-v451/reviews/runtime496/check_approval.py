"""Run exact approval function only; never controller preflight or execute."""
import ast
import copy
import hashlib
import json
from pathlib import Path
H=Path(__file__).resolve().parent;Q=H.parent;P=Q/'blind-pair-controller-v493'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tree=ast.parse((P/'controller.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='approval')
namespace={'HERE':P,'digest':sha,'read':lambda p:json.loads(p.read_text(encoding='utf-8'))}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<exact493 approval function>','exec'),namespace)
approval=H/'review-approval.json';namespace['approval'](approval,sha(approval))
good=json.loads(approval.read_text(encoding='utf-8'));rejected=[]
for name,mutate in [('wrong scope',lambda v:v.update(scope='blind-pair-controller-v493')),('old worker hash',lambda v:v['reviewed_files'].update({'worker.py':sha(Q/'blind-pair-controller-v476/worker.py')})),('wrong verdict',lambda v:v.update(verdict='not-approved'))]:
    value=copy.deepcopy(good);mutate(value);path=H/'fixtures'/('approval-'+name.replace(' ','-')+'.json');path.write_text(json.dumps(value),encoding='utf-8')
    try:namespace['approval'](path,sha(path))
    except ValueError:rejected.append(name)
    else:raise AssertionError(name)
try:namespace['approval'](approval,'0'*64)
except ValueError:rejected.append('wrong approval checksum')
else:raise AssertionError('wrong approval checksum')
print(json.dumps({'actual493approval_accepts':True,'rejected':rejected,'approval_sha256':sha(approval)},indent=2))
