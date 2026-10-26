"""One new disposable trusted test identity; no documents/chunks or predictions."""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
q=Path(__file__).resolve().parent.parent
w=q.parent/"delivery-worktree"
out=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("combined_environment",q/"development-controller-v346/controller.py")
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
settings=json.loads((q/"development-v22-composite-activity-margin0-reranked/execution-settings.json").read_text())
cfg=SimpleNamespace(source=w,output=q/"typed-connected-live-v378",embedding=Path(settings["embedding"]),reader=Path(settings["reader"]),support=Path(settings["support"]),margin=2,proposal_profile="qa_plus_source_patterns_v1",role_scope_policy="ordinary_session_activity_v1",procedure_profile="source_declared_procedure_copy_v1",source_context_policy="scoped_note_context_v2")
os.environ.update(m.environment(cfg))
sys.path.insert(0,str(w/"apps/api"))
from app.db.session import AsyncSessionLocal
from app.models.api_key import ApiKey,generate_api_key
async def main():
    private=q/"typed-connected-live-v378/private/combined-v456-seed.json"
    assert private.parent.is_dir() and not private.exists()
    raw,digest,prefix=generate_api_key()
    identifier=uuid.uuid4()
    workspace="engineering-combined-v456"
    async with AsyncSessionLocal() as db:
        db.add(ApiKey(id=identifier,name="combined-admin-v456",key_hash=digest,key_prefix=prefix,is_admin=True,rate_limit=100000,metadata_={"workspace_id":workspace,"organization_id":workspace,"group_ids":[]}))
        await db.commit()
    with private.open("x",encoding="utf-8") as f:
        json.dump({"api_url":"http://127.0.0.1:8401","principals":{"admin-a":{"id":str(identifier),"api_key":raw,"workspace_id":workspace}}},f)
    # Private ACL inherited from the already-restricted private directory.
    assert os.name=="nt"
    result=subprocess.run(["icacls",str(private)],capture_output=True,text=True)
    assert result.returncode==0
    (out/"identity-bootstrap.json").write_text(json.dumps({"id":str(identifier),"workspace_id":workspace,"created":True,"scope":"Trusted identity only; all document content goes through browser HTTP upload","private_manifest_exists":private.is_file()},indent=2)+"\n")
    print("Disposable combined identity created; no content seeded; private key not printed.")
asyncio.run(main())
