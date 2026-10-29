"""Independent metadata-only review; no models, app, network or subprocess."""
import ast
import copy
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

H=Path(__file__).resolve().parent; Q=H.parent; P=Q/'blind-pair-controller-v493'; OLD=Q/'blind-pair-controller-v476'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
blocked={'app','torch','transformers','sentence_transformers','onnxruntime'}
class NoImports(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in blocked:raise ImportError('App/model import blocked by independent metadata review')
def audit(event,args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','os.exec'}:raise RuntimeError('Network/children forbidden')
assert not blocked & set(sys.modules);sys.meta_path.insert(0,NoImports());sys.addaudithook(audit)
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
w=load('independent493worker',P/'worker.py'); old=load('independent476worker',OLD/'worker.py')
direct=sys.argv[-1]=='--canonical'
if direct:
    frozen=read(Q/'candidate-freeze-v446/runtime.json'); assert sys.version==frozen['python'] and Path(sys.executable).resolve()==Path(frozen['executable']).resolve()
    result=w.runtime_check(Q/'candidate-freeze-v446/runtime.json');assert result=={'runtime_packages_verified':92,'model_imports':False}
    old_rejected=False
    try:old.runtime_check(Q/'candidate-freeze-v446/runtime.json')
    except ValueError:old_rejected=True
    assert old_rejected
    required={d['name'].lower().replace('_','-'):d for d in frozen['distributions']};actual={d.metadata['Name'].lower().replace('_','-'):d for d in importlib.metadata.distributions()};assert set(actual)==set(required)
    records=[];text_differences=0
    for name,d in sorted(actual.items()):
        own=Path(d._path)/'RECORD'; raw=sha(own) if own.is_file() else None
        assert d.version==required[name]['version'] and raw==required[name]['record_sha256']
        normalized=d.read_text('RECORD');normalized_hash=hashlib.sha256(normalized.encode()).hexdigest() if normalized is not None else None
        text_differences+=normalized_hash!=raw
        records.append({'name':name,'version':d.version,'own_RECORD':str(own),'record_sha256':raw})
    assert all(sha(Path(r['own_RECORD']))==r['record_sha256'] for r in records if r['record_sha256'] is not None)
    assert not blocked & set(sys.modules)
    result.update({'old476_rejected_same_actual_runtime':True,'raw_bytes_and_versions_match':len(records),'text_normalization_differences':text_differences,'python':sys.version,'executable':sys.executable,'imports_blocked':True,'network_children_blocked':True})
    (H/'canonical-L-records.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8');(H/'canonical-L-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));raise SystemExit(0)

# Exact source preservation with only the intended raw-owning-RECORD repair.
paths=[p for p in P.iterdir() if p.is_file()]+[OLD/'worker.py',OLD/'controller.py',OLD/'frozen-inputs.json',Q/'candidate-freeze-v446/runtime.json',Q/'candidate-freeze-v446/freeze.json',Q/'freeze_candidate_v446.py',Q/'runtime-record-diagnosis-v491.json']
before={str(p):sha(p) for p in paths};(H/'hashes-before.json').write_text(json.dumps(before,indent=2)+'\n')
assert (P/'controller.py').read_bytes()==(OLD/'controller.py').read_bytes()
assert (P/'frozen-inputs.json').read_bytes()==(OLD/'frozen-inputs.json').read_bytes()
old_functions={n.name:ast.dump(n,include_attributes=False) for n in ast.parse((OLD/'worker.py').read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
new_functions={n.name:ast.dump(n,include_attributes=False) for n in ast.parse((P/'worker.py').read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
assert set(old_functions)==set(new_functions)
assert all(new_functions[k]==v for k,v in old_functions.items() if k!='runtime_check')
assert sha(P/'worker.py')=='0bf5535ee726aab3ffabf979ed431f538adcc24a38923bb10dec1037a3243835'
fixture=H/'fixtures';fixture.mkdir(exist_ok=False);owner=fixture/'Owner.Dist-Info';owner.mkdir();vendor=fixture/'vendored.dist-info';vendor.mkdir()
raw=b'actual-package.py,sha256=owner,19\r\nOwner.Dist-Info/RECORD,,\r\n';(owner/'RECORD').write_bytes(raw);(vendor/'RECORD').write_bytes(raw)
class Dist:
    metadata={'Name':'Example_Package'};version='1.2.3';_path=owner
    @property
    def files(self):raise AssertionError('Must never scan dist.files/vendored RECORDs')
    def read_text(self,name):raise AssertionError('Must never use normalized text to bind own RECORD')
d=Dist();frozen={'python':sys.version,'executable':str(Path(sys.executable).resolve()),'distributions':[{'name':'example-package','version':'1.2.3','record_sha256':hashlib.sha256(raw).hexdigest()}]}
target=fixture/'runtime.json';target.write_text(json.dumps(frozen),encoding='utf-8');cases=[]
def check(name,accepted,distributions=None,mutate=None):
    value=copy.deepcopy(frozen)
    if mutate:mutate(value)
    target.write_text(json.dumps(value),encoding='utf-8')
    with patch.object(w.importlib.metadata,'distributions',return_value=[d] if distributions is None else distributions):
        try:out=w.runtime_check(target);actual=True
        except (ValueError,KeyError,TypeError,FileNotFoundError):actual=False
    assert actual==accepted,name;cases.append({'case':name,'expected_accept':accepted,'actual_accept':actual})
check('raw CRLF owner accepted without files/read_text',True)
(owner/'RECORD').write_bytes(raw.replace(b'\r\n',b'\n'));check('same semantic text with LF bytes rejected',False)
(owner/'RECORD').write_bytes(raw+b'x');check('changed raw bytes rejected despite matching vendored RECORD',False)
(owner/'RECORD').write_bytes(raw);d.version='9.9';check('changed version rejected',False);d.version='1.2.3'
check('missing distribution rejected',False,[])
extra=SimpleNamespace(metadata={'Name':'unexpected'},version='1',_path=vendor);check('extra inventory rejected',False,[d,extra])
(owner/'RECORD').unlink();check('missing owning RECORD cannot use valid vendor',False)
(owner/'RECORD').write_bytes(raw);(vendor/'RECORD').write_bytes(b'unrelated vendor changed');check('vendored bytes irrelevant to actual owner',True)
check('changed Python version rejected',False,mutate=lambda v:v.update(python='other Python'))
check('changed executable rejected',False,mutate=lambda v:v.update(executable=str(fixture/'other-python.exe')))
check('changed frozen RECORD hash rejected',False,mutate=lambda v:v['distributions'][0].update(record_sha256='f'*64))
check('changed frozen version rejected',False,mutate=lambda v:v['distributions'][0].update(version='other'))
after={str(p):sha(p) for p in paths};assert before==after
(H/'hashes-after.json').write_text(json.dumps(after,indent=2)+'\n')
assert not blocked & set(sys.modules)
result={'pure_cases':cases,'controller_and_pins_byte_identical':True,'other_worker_functions_unchanged':True,'hashed_inputs_unchanged':len(before),'imports_blocked':True,'network_children_blocked':True}
(H/'pure-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
