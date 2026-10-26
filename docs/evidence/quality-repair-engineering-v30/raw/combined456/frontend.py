"""Start only the frozen staged build430 on the disposable browser port."""
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

out=Path(__file__).resolve().parent
q=out.parent
stage=q/"typed-restart-outage-v449/runs/first/frontend"
assert (stage/".next-context-v430/BUILD_ID").read_text(encoding="utf-8").strip()=="2E-2O2E9X649dLudTKGES"
with socket.socket() as sock:
    assert sock.connect_ex(("127.0.0.1",3506))!=0
env={**os.environ,"PORT":"3506","HOSTNAME":"127.0.0.1","NODE_ENV":"production","NEXT_TELEMETRY_DISABLED":"1"}
for key in ("NODE_OPTIONS","NODE_PATH","DEBUG","PWDEBUG"):
    env.pop(key,None)
command=[shutil.which("node.exe"),str(stage/"server.js")]
assert command[0]
p=subprocess.Popen(command,cwd=stage,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
with (out/"frontend-process.json").open("x",encoding="utf-8") as f:
    json.dump({"owned_pid":p.pid,"command":command,"port":3506,"build":"430"},f)
raise SystemExit(p.wait())
