"""Install the built API wheel in a fresh environment and import its entrypoints."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "api" / "dist"
IMPORTS = """\
import app.main
import app.config
import app.db.session
import app.internal.vendor_core.config
import app.internal.vendor_core.database
import app.internal.vendor_core.docparse
import app.internal.vendor_core.embeddings
import app.internal.vendor_core.errors
import app.internal.vendor_core.evaljudge
import app.internal.vendor_core.llmmetrics
import app.internal.vendor_core.logging
import app.internal.vendor_core.pricing
import app.internal.vendor_core.tasks
import app.internal.vendor_core.clients
import app.services.answer_reader
import app.services.answer_support
import app.services.procedure_output
import app.reader_setup
import app.support_setup
from importlib.resources import files
from app.portfolio import load_corpus
from app.services.embedding import embedding_service
import asyncio
import hashlib
import json
corpus = load_corpus()
assert len(corpus["documents"]) == 12 and len(corpus["cases"]) == 100
development = load_corpus(files("app.portfolio") / "assets/coverage-development")
assert len(development["cases"]) == 80
blind = load_corpus(files("app.portfolio") / "assets/coverage-blind-canonical-v3")
assert len(blind["cases"]) == 200
assert blind["manifest"]["manifest_sha256"] == (
    "cbb9ebc3b48d18ba59ab40a344f7f64a2e01b691fe1a3fef0968144be38a6bc3"
)
demo_root = files("app.portfolio") / "assets/procedure-copy-demo"
demo = json.loads((demo_root / "manifest.json").read_text(encoding="utf-8"))
assert demo["schema"] == "procedure-copy-demo-v1"
assert len(demo["files"]) == 3
for asset in demo["files"]:
    actual_hash = hashlib.sha256((demo_root / asset["file"]).read_bytes()).hexdigest()
    assert actual_hash == asset["upload_sha256"]
assert (demo_root / "README.md").is_file()
assert (demo_root / "SHA256SUMS").is_file()
vectors = asyncio.run(embedding_service.embed_texts(["outside checkout probe"]))
assert len(vectors) == 1 and len(vectors[0]) == 384
import importlib.util
assert importlib.util.find_spec("shared_core") is None
assert importlib.util.find_spec("sentence_transformers") is None
assert importlib.util.find_spec("pdfplumber") is None
assert importlib.util.find_spec("torch") is None
assert importlib.util.find_spec("transformers") is None
import httpx
from app.db.migrate import migrate
from app.db.session import async_engine
async def exercise():
    await migrate()
    transport = httpx.ASGITransport(app=app.main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://wheel.local"
    ) as client:
        content = (b"Widget rollback: pause the widget queue before restoring "
                   b"the healthy widget image.")
        upload = await client.post(
            "/api/documents/upload",
            files=[("files", ("wheel-proof.txt", content, "text/plain"))]
        )
        assert upload.status_code == 200, upload.text
        document = upload.json()["documents"][0]
        assert document["status"] == "ready"
        answer = await client.post("/api/queries", json={
            "question":"How do I rollback the widget?",
            "document_ids":[document["id"]], "retrieval_method":"keyword"
        })
        assert answer.status_code == 200, answer.text
        row = answer.json()
        assert not row["refused"] and row["sources"][0]["document_version"] == 1
        saved = await client.get("/api/queries/" + row["id"])
        assert saved.status_code == 200 and saved.json()["sources"] == row["sources"]
    # Optional models remain absent. Explicit copy mode must fail visibly rather
    # than turn a missing reader/classifier into a successful lexical answer.
    from app.config import Settings
    from app.services.answer_reader import reader_service
    from app.services.answer_support import (
        LocalSupportVerifier, SupportPair, SupportUnavailableError,
    )
    configured = Settings(
        ANSWER_SELECTION_MODE="reader", ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        READER_MODEL_PATH="missing-reader-assets",
        SUPPORT_MODEL_PATH="missing-support-assets",
    )
    assert (
        configured.PROCEDURE_VERIFICATION_PROFILE
        == "source_declared_procedure_copy_v1"
    )
    try:
        await reader_service.select_atomic(
            "Who leads the review?", ["The clerk leads the review."],
            config=configured,
        )
    except RuntimeError as error:
        assert "no fallback" in str(error)
    else:
        raise AssertionError("Missing optional reader assets silently succeeded")
    try:
        await LocalSupportVerifier().assess(
            [SupportPair(
                "The clerk leads the review.", "The clerk is the lead.", "r1", "c1"
            )],
            config=configured,
        )
    except SupportUnavailableError:
        pass
    else:
        raise AssertionError("Missing optional classifier assets silently succeeded")
    assert importlib.util.find_spec("torch") is None
    assert importlib.util.find_spec("transformers") is None
    await async_engine.dispose()
asyncio.run(exercise())
"""


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    """Install only the wheel and declared dependencies in a fresh virtualenv."""
    wheels = sorted(
        DIST.glob("groundtruth-*.whl"), key=lambda path: path.stat().st_mtime
    )
    if not wheels:
        print(
            f"No GroundTruth wheel found. Run `python -m build apps/api` first: {DIST}"
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="groundtruth-wheel-") as directory:
        env = os.environ.copy()
        # Source metadata on PYTHONPATH can make pip skip the wheel entirely.
        for name in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(name, None)
        env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
        env["EMBEDDING_MODE"] = "deterministic"
        env["EMBEDDING_DIMENSIONS"] = "384"
        env["GENERATION_MODE"] = "extractive"
        env["ANSWER_SELECTION_MODE"] = "lexical"
        env["ANSWER_PROPOSAL_PROFILE"] = "qa_only_v1"
        env["ROLE_SCOPE_POLICY"] = "literal_v1"
        env["PROCEDURE_VERIFICATION_PROFILE"] = "all_units_nli_v1"
        env["SOURCE_CONTEXT_POLICY"] = "explicit_target_v1"
        env["ANSWER_SUPPORT_MODE"] = "disabled"
        env["OPENAI_API_KEY"] = ""
        env["HF_HUB_OFFLINE"] = "1"
        env["INGESTION_MODE"] = "inline"
        env["AUTH_ENABLED"] = "false"
        env["RATE_LIMIT_ENABLED"] = "false"
        env["APP_ENV"] = "development"
        env["STORAGE_ROOT"] = str(Path(directory) / "uploads")
        environment = Path(directory) / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(environment)],
            check=True,
            env=env,
            cwd=directory,
        )
        python = _venv_python(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheels[-1])],
            check=True,
            env=env,
            cwd=directory,
        )
        subprocess.run(
            [str(python), "-I", "-c", IMPORTS],
            check=True,
            env=env,
            cwd=directory,
        )

    print("Isolated wheel imports verified without an external shared_core package.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
