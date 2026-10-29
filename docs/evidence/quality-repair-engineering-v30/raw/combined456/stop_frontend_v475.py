"""Stop one recorded Node child after exact command/birth/listener checks."""
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

out=Path(__file__).resolve().parent
q=out.parent
spec=importlib.util.spec_from_file_location("guarded_outage_module",q/"typed-restart-outage-v466/coordinator.py")
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
record=out/"frontend-process.json"
value=json.loads(record.read_text(encoding="utf-8"))
pid=value["owned_pid"]
assert value["port"]==3506 and value["build"]=="430"
assert m.listener_pids(3506)=={pid}
actual=m.process_info(pid)
assert m.command_tokens(actual["command_line"])==value["command"]
assert Path(actual["executable"]).resolve()==Path(value["command"][0]).resolve()
born=datetime.fromisoformat(actual["created"].replace("Z","+00:00"))
written=datetime.fromtimestamp(record.stat().st_mtime,UTC)
assert 0 <= (written-born).total_seconds() <= 5
m.verify_process(pid,value["command"],actual["created"])
assert m.listener_pids(3506)=={pid}
m.powershell("Stop-Process -Id "+str(pid)+" -ErrorAction Stop")
for _ in range(30):
    if m.port_closed(3506):break
    m.time.sleep(.1)
assert m.port_closed(3506)
result={"owned_pid":pid,"command":value["command"],"created":actual["created"],"record_sha256":hashlib.sha256(record.read_bytes()).hexdigest(),"port3506_closed":True,"api8401_untouched":True}
with (out/"frontend-cleanup.json").open("x",encoding="utf-8") as f:json.dump(result,f,indent=2);f.write("\n")
print("Recorded frontend3506 stopped with exact ownership checks; API untouched.")

