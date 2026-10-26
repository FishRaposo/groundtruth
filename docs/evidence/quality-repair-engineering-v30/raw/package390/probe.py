"""Selected margin2 installed-wheel ASGI engineering probe; no quality claim."""
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import sys
from importlib import metadata
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Q = ROOT.parent
INSTALLED = Q / "context-package-v367/optional-env"
assert INSTALLED.resolve() in Path(sys.executable).resolve().parents
assert sys.dont_write_bytecode
OUT = ROOT / "workflow"
assert not OUT.exists()
OUT.mkdir()
settings_path = Q / "development-v30-typed-context-v2-locked329-margin2-reranked/execution-settings.json"
selected = json.loads(settings_path.read_text())
assert selected["margin"] == 2 and selected["settings"]["support_min_margin"] == 2
assert selected["settings"]["reader_null_threshold"] == 4
for key in list(os.environ):
    if key.upper().startswith(("OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_API", "GEMINI_")):
        del os.environ[key]
os.environ.update(
    DATABASE_URL="sqlite+aiosqlite:///" + (OUT / "wheel.sqlite").as_posix(), STORAGE_ROOT=str(OUT / "uploads"),
    AUTH_ENABLED="false", APP_ENV="development", RATE_LIMIT_ENABLED="false", EMBEDDING_MODE="local", EMBEDDING_DIMENSIONS="384",
    LOCAL_MODEL_PATH=selected["embedding"], LOCAL_MODEL_REVISION="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    ANSWER_SELECTION_MODE="reader", READER_MODEL_PATH=selected["reader"], READER_MODEL_REVISION="adc3b06f79f797d1c575d5479d6f5efe54a9e3b4", READER_NULL_THRESHOLD="4",
    ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH=selected["support"], SUPPORT_MODEL_REVISION="70de96bd327ef95839a8bd9f6299875cae396433", SUPPORT_MIN_MARGIN="2",
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

assert INSTALLED.resolve() in Path(app.main.__file__).resolve().parents
assert importlib.util.find_spec("shared_core") is None
assets = files("app.portfolio") / "assets/procedure-copy-demo"
manifest = json.loads((assets / "manifest.json").read_text())
case = manifest["files"][0]
payload = (assets / case["file"]).read_bytes()
assert hashlib.sha256(payload).hexdigest() == case["upload_sha256"]
body = payload.decode().removesuffix("\n")
assert hashlib.sha256(body.encode()).hexdigest() == case["canonical_sha256"]
PROFILE = {
    "contract": "evidence-profile-v4", "proposal_profile": "qa_plus_source_patterns_v1", "role_scope_policy": "ordinary_session_activity_v1",
    "origin_contract": "proposal-origin-v1", "role_policy_contract": "ordinary-session-activity-role-v1", "pattern_registry_contract": "typed-source-patterns-v1",
    "pattern_limits": {"per_source_requirement": 3, "per_requirement": 16}, "procedure_verification_profile": "source_declared_procedure_copy_v1",
    "source_context_policy": "scoped_note_context_v2", "source_context_contract": "source-note-context-v2",
}


async def main():
    await migrate()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.main.app), base_url="http://wheel.local", timeout=300) as client:
        ready = await client.get("/api/health/ready")
        assert ready.status_code == 200, ready.text
        runtime = ready.json()["runtime"]
        profile = dict(runtime["evidence_profile"])
        profile.pop("qualification", None)
        assert profile == PROFILE
        assert runtime["answer_selection"]["model"] == "deepset/roberta-base-squad2"
        assert runtime["answer_selection"]["revision"] == "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"
        assert runtime["answer_selection"]["threshold"] == 4
        assert runtime["evidence_support"]["mode"] == "local_nli"
        assert runtime["evidence_support"]["minimum_entailment_margin"] == 2
        assert runtime["evidence_support"]["revision"] == "70de96bd327ef95839a8bd9f6299875cae396433"
        assert runtime["evidence_support"]["device"] == "cpu"
        assert runtime["generation_mode"] == "extractive" and runtime["ingestion_mode"] == "inline"
        upload = await client.post("/api/documents/upload", files=[("files", (case["file"], payload, "text/plain"))])
        assert upload.status_code == 200, upload.text
        document = upload.json()["documents"][0]
        assert document["status"] == "ready"
        response = await client.post("/api/queries", json={"question": case["question"], "document_ids": [document["id"]], "retrieval_method": "reranked"})
        assert response.status_code == 200, response.text
        answer = response.json()
        with (OUT / "posted.json").open("x", encoding="utf-8") as target:
            json.dump(answer, target, indent=2)
            target.write("\n")
        assert answer["outcome"] == "completed" and not answer["refused"] and answer["sources"]
        selection = answer["provenance"]["answer_selection"]
        assert selection["evidence_profile"] == PROFILE
        assert selection["evidence_support"]["minimum_entailment_margin"] == 2
        proof = selection["requirements"][0]["procedure_completeness"]
        assert "condition_exclusion_inventory" not in proof
        assert proof["output_certificate"]["contract"] == "procedure-output-cover-v1"
        assert proof["output_certificate"]["answer_sha256"] == hashlib.sha256(answer["answer"].encode()).hexdigest()
        assert proof["content_hash"] == case["canonical_sha256"]
        assert proof["extent"] == case["copied_extent"]
        assert body[case["copied_extent"]["start"]:case["copied_extent"]["end"]] in answer["answer"]
        observed_nli = []
        for unit in proof["proof_units"]:
            assert unit["supported"] is True
            if unit["verification_method"] == "nli_entailment":
                assert unit["label"] == "entailment"
                assert math.isfinite(unit["entailment_margin"]) and unit["entailment_margin"] >= 2
                assert unit["pair_tokens"] > 0
                observed_nli.append({"kind": unit["kind"], "margin": unit["entailment_margin"], "pair_tokens": unit["pair_tokens"]})
            else:
                assert not any(name in unit for name in ("label", "logits", "entailment_margin", "pair_tokens"))
        assert {unit["kind"] for unit in observed_nli} == {"namespace", "applicability"}
        saved = await client.get("/api/queries/" + answer["id"])
        assert saved.status_code == 200 and saved.json()["answer"] == answer["answer"]
        assert saved.json()["sources"] == answer["sources"]
        snapshot = await client.get(f"/api/v1/documents/{document['id']}/versions/1")
        assert snapshot.status_code == 200 and snapshot.json()["normalized_content"] == body
        assert snapshot.json()["content_hash"] == case["canonical_sha256"]
        result = {"scope": "Installed v367 wheel reused read-only at independently selected margin2; actual exposed Cedar ASGI/SQLite/cache-only CPU workflow, not quality/auth/browser/live-server acceptance",
                  "python": sys.executable, "app_file": app.main.__file__, "selected_margin": 2, "reader_threshold": 4,
                  "ready": ready.json(), "upload": document, "response": answer, "saved": saved.json(), "snapshot": snapshot.json(), "actual_nli_units": observed_nli,
                  "packages": {name: metadata.version(name) for name in ("groundtruth", "torch", "transformers", "sentence-transformers")}}
        with (OUT / "result.json").open("x", encoding="utf-8") as target:
            json.dump(result, target, indent=2)
            target.write("\n")
        print(json.dumps({"ready": ready.status_code, "upload": upload.status_code, "query": response.status_code, "snapshot": snapshot.status_code, "history": saved.status_code, "outcome": answer["outcome"], "support_margin": 2, "scope": result["scope"]}), flush=True)
    missing = Settings(ANSWER_SELECTION_MODE="reader", ANSWER_SUPPORT_MODE="local_nli", GENERATION_MODE="extractive",
                       ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1", ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
                       PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1", SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
                       SUPPORT_MIN_MARGIN=2, READER_NULL_THRESHOLD=4, READER_MODEL_PATH=str(OUT / "absent-reader"), SUPPORT_MODEL_PATH=str(OUT / "absent-support"))
    assert missing.SUPPORT_MIN_MARGIN == 2 and missing.READER_NULL_THRESHOLD == 4
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
    with (OUT / "missing-assets.json").open("x", encoding="utf-8") as target:
        json.dump({"support_margin": 2, "reader_threshold": 4, "observed_errors": failures}, target, indent=2)
        target.write("\n")
    await async_engine.dispose()


asyncio.run(main())
