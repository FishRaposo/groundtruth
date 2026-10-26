"""New installed wheel, exact cached CPU models, actual ASGI package workflow."""
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from importlib import metadata
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Q = ROOT.parent
assert (ROOT / "optional-env").resolve() in Path(sys.executable).resolve().parents
OUT = ROOT / "optional-workflow-2"
assert not OUT.exists()
OUT.mkdir()
previous = json.loads((Q / "development-v30-typed-context-v2-locked329-margin0-reranked/execution-settings.json").read_text())
for key in list(os.environ):
    if key.upper().startswith(("OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_API", "GEMINI_")):
        del os.environ[key]
os.environ.update(
    DATABASE_URL="sqlite+aiosqlite:///" + (OUT / "wheel.sqlite").as_posix(), STORAGE_ROOT=str(OUT / "uploads"),
    AUTH_ENABLED="false", APP_ENV="development", RATE_LIMIT_ENABLED="false", EMBEDDING_MODE="local", EMBEDDING_DIMENSIONS="384",
    LOCAL_MODEL_PATH=previous["embedding"], LOCAL_MODEL_REVISION="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    ANSWER_SELECTION_MODE="reader", READER_MODEL_PATH=previous["reader"], READER_MODEL_REVISION="adc3b06f79f797d1c575d5479d6f5efe54a9e3b4", READER_NULL_THRESHOLD="4",
    ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH=previous["support"], SUPPORT_MODEL_REVISION="70de96bd327ef95839a8bd9f6299875cae396433", SUPPORT_MIN_MARGIN="0",
    GENERATION_MODE="extractive", INGESTION_MODE="inline", ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1", ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
    PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1", SOURCE_CONTEXT_POLICY="scoped_note_context_v2", SOURCE_CONTEXT_MODE="body",
    HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", TOKENIZERS_PARALLELISM="false", CUDA_VISIBLE_DEVICES="",
    HF_HOME=str(OUT / "hf-cache"), TORCH_HOME=str(OUT / "torch-cache"), XDG_CACHE_HOME=str(OUT / "runtime-cache"),
)
import httpx
import app.main
from app.config import Settings
from app.db.migrate import migrate
from app.db.session import async_engine
from app.services.answer_reader import reader_service
from app.services.answer_support import LocalSupportVerifier, SupportPair, SupportUnavailableError
from app.services.source_context_scope import grammar_descriptor

assert (ROOT / "optional-env").resolve() in Path(app.main.__file__).resolve().parents
assert importlib.util.find_spec("shared_core") is None
assets = files("app.portfolio") / "assets/procedure-copy-demo"
manifest = json.loads((assets / "manifest.json").read_text())
case = manifest["files"][0]
payload = (assets / case["file"]).read_bytes()
assert hashlib.sha256(payload).hexdigest() == case["upload_sha256"]


async def main():
    await migrate()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.main.app), base_url="http://wheel.local", timeout=300) as client:
        ready = await client.get("/api/health/ready")
        assert ready.status_code == 200, ready.text
        runtime = ready.json()["runtime"]
        assert runtime["evidence_profile"]["source_context_policy"] == "scoped_note_context_v2"
        assert runtime["evidence_profile"]["role_scope_policy"] == "ordinary_session_activity_v1"
        assert runtime["evidence_profile"]["contract"] == "evidence-profile-v4"
        assert runtime["answer_selection"]["revision"] == "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"
        upload = await client.post("/api/documents/upload", files=[("files", (case["file"], payload, "text/plain"))])
        assert upload.status_code == 200, upload.text
        document = upload.json()["documents"][0]
        assert document["status"] == "ready"
        response = await client.post("/api/queries", json={"question": case["question"], "document_ids": [document["id"]], "retrieval_method": "reranked"})
        assert response.status_code == 200, response.text
        answer = response.json()
        assert not answer["refused"] and answer["sources"], answer
        assert answer["provenance"]["answer_selection"]["evidence_profile"]["contract"] == "evidence-profile-v4"
        proof = answer["provenance"]["answer_selection"]["requirements"][0]["procedure_completeness"]
        # Frozen procedure_output emits v1 for this exact Cedar/no-inventory case.
        assert "condition_exclusion_inventory" not in proof
        assert proof["output_certificate"]["contract"] == "procedure-output-cover-v1"
        saved = await client.get("/api/queries/" + answer["id"])
        assert saved.status_code == 200 and saved.json()["answer"] == answer["answer"]
        assert saved.json()["sources"] == answer["sources"]
        snapshot = await client.get(f"/api/v1/documents/{document['id']}/versions/1")
        assert snapshot.status_code == 200
        assert snapshot.json()["content_hash"] == case["canonical_sha256"]
        assert hashlib.sha256(snapshot.json()["normalized_content"].encode()).hexdigest() == case["canonical_sha256"]
        result = {"scope": "Fresh installed wheel, actual ASGI/SQLite/cache-only CPU models; exposed Cedar engineering case at approved activity/copy/context-v2 profile. Not model quality, auth, browser or live-server acceptance.",
                  "python": sys.executable, "app_file": app.main.__file__, "ready": ready.json(), "upload": document,
                  "response": answer, "saved": saved.json(), "snapshot": snapshot.json(),
                  "grammar_contract": grammar_descriptor(policy="scoped_note_context_v2")["contract"],
                  "packages": {name: metadata.version(name) for name in ("groundtruth", "torch", "transformers", "sentence-transformers")}}
        (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ready": ready.status_code, "upload": upload.status_code, "query": response.status_code, "history": saved.status_code, "refused": answer["refused"], "scope": result["scope"]}), flush=True)
    # Explicitly missing paths must fail even after actual models have loaded.
    missing = Settings(ANSWER_SELECTION_MODE="reader", ANSWER_SUPPORT_MODE="local_nli", GENERATION_MODE="extractive",
                       ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1", ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
                       PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1", SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
                       READER_MODEL_PATH=str(OUT / "absent-reader"), SUPPORT_MODEL_PATH=str(OUT / "absent-support"))
    failures = {}
    try:
        await reader_service.select_atomic("Who leads the review?", ["The clerk leads the review."], config=missing)
    except RuntimeError as error:
        assert "no fallback" in str(error)
        failures["reader"] = "visible RuntimeError, no fallback"
    else:
        raise AssertionError("Missing reader assets silently succeeded")
    try:
        await LocalSupportVerifier().assess([SupportPair("The clerk leads the review.", "The clerk is the lead.", "r1", "c1")], config=missing)
    except SupportUnavailableError:
        failures["support"] = "visible SupportUnavailableError"
    else:
        raise AssertionError("Missing support assets silently succeeded")
    (OUT / "missing-assets.json").write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    await async_engine.dispose()


asyncio.run(main())
