"""Immutable DEVELOPMENT80 process controller; no model or HTTP runs on import."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

METHODS = ("keyword", "vector", "hybrid", "reranked")
READER = "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"
SUPPORT = "70de96bd327ef95839a8bd9f6299875cae396433"
EMBEDDING = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BASE_URL = "http://127.0.0.1:8402"
PROPOSALS = ("qa_only_v1", "qa_plus_source_patterns_v1")
ROLES = ("literal_v1", "ordinary_session_activity_v1")
PROCEDURES = ("all_units_nli_v1", "source_declared_procedure_copy_v1")
SOURCE_CONTEXT_POLICIES = ("explicit_target_v1", "scoped_note_context_v1")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")  # noqa: TRY004 - CLI input error contract.
    return value


def child(root: Path, name: str) -> Path:
    value = (root / name).resolve(strict=True)
    if not value.is_relative_to(root.resolve(strict=True)) or not value.is_file():
        raise ValueError("Manifest path escapes its root")
    return value


def verified_files(root: Path, files: dict) -> dict:
    if not isinstance(files, dict) or not files:
        raise ValueError("Manifest requires files")
    for name, expected in files.items():
        if (
            not isinstance(name, str)
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise ValueError("Invalid file hash binding")
        if digest(child(root, name)) != expected:
            raise ValueError("File hash mismatch")
    return dict(files)


@dataclass(frozen=True)
class Config:
    source: Path
    source_manifest: Path
    source_manifest_sha256: str
    corpus: Path
    corpus_manifest_sha256: str
    common_manifest_sha256: str
    output: Path
    python: Path
    embedding: Path
    reader: Path
    support: Path
    margin: int
    proposal_profile: str
    role_scope_policy: str
    procedure_profile: str = "all_units_nli_v1"
    method: str = "reranked"
    readiness_timeout: float = 300.0
    command_timeout: float = 7200.0
    source_context_policy: str = "explicit_target_v1"


def source_context_policy(config) -> str:
    """Historical duck-typed tool callers predate this optional control."""
    return getattr(config, "source_context_policy", "explicit_target_v1")


def expected_settings(config: Config) -> dict:
    settings = {
        "top_k": 5,
        "refusal_threshold": 0.35,
        "reader_null_threshold": 4,
        "reader_model_revision": READER,
        "answer_support_mode": "local_nli",
        "support_model_revision": SUPPORT,
        "support_min_margin": config.margin,
        "selection_contract": "requirement-evidence-v2",
        "answer_proposal_profile": config.proposal_profile,
        "role_scope_policy": config.role_scope_policy,
        "procedure_verification_profile": config.procedure_profile,
    }
    if config.procedure_profile == "source_declared_procedure_copy_v1":
        settings.update(answer_selection_mode="reader", generation_mode="extractive")
    if source_context_policy(config) != "explicit_target_v1":
        settings["source_context_policy"] = source_context_policy(config)
    return settings


def expected_runtime(config: Config) -> dict:
    """Only public, safe fields; additional API metadata is saved unmodified."""
    runtime = {
        "answer_selection": {
            "mode": "reader",
            "model": "deepset/roberta-base-squad2",
            "revision": READER,
            "threshold": 4,
            "contract": "requirement-evidence-v2",
            "readiness": "ready",
        },
        "evidence_support": {
            "mode": "local_nli",
            "revision": SUPPORT,
            "model": "cross-encoder/nli-deberta-v3-small",
            "minimum_entailment_margin": config.margin,
            "readiness": "ready",
            "device": "cpu",
        },
        "evidence_profile": {
            "contract": "evidence-profile-v2"
            if config.procedure_profile == "source_declared_procedure_copy_v1"
            else "evidence-profile-v1",
            "proposal_profile": config.proposal_profile,
            "role_scope_policy": config.role_scope_policy,
        },
        "embedding": {
            "mode": "local",
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "revision": EMBEDDING,
            "dimension": 384,
        },
        "generation_mode": "extractive",
        "ingestion_mode": "inline",
        "persistence": "sqlite",
        "authentication": "api-key",
    }
    if config.procedure_profile == "source_declared_procedure_copy_v1":
        runtime["evidence_profile"]["procedure_verification_profile"] = (
            config.procedure_profile
        )
    if source_context_policy(config) != "explicit_target_v1":
        runtime["evidence_profile"].update(
            contract="evidence-profile-v3",
            source_context_policy=source_context_policy(config),
            source_context_contract="source-note-context-v1",
        )
    return runtime


def includes(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and includes(actual[key], value)
            for key, value in expected.items()
        )
    return (
        actual == expected
        and type(actual) is type(expected)
        or (
            isinstance(expected, (float, int))
            and not isinstance(expected, bool)
            and isinstance(actual, (float, int))
            and not isinstance(actual, bool)
            and actual == expected
        )
    )


def environment(config: Config) -> dict[str, str]:
    env = (
        os.environ.copy()
    )  # Preserve Windows SystemRoot/Path spelling and all OS state.
    private = (
        "OPENAI_",
        "ANTHROPIC_",
        "AZURE_OPENAI_",
        "GOOGLE_API",
        "GEMINI_",
        "COHERE_",
        "MISTRAL_",
        "GROQ_",
        "TOGETHER_",
        "DEEPSEEK_",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "LANGSMITH_",
        "LANGCHAIN_API",
        "WANDB_",
    )
    for name in list(env):
        if name.upper().startswith(private):
            del env[name]
    env.update(
        {
            "PYTHONPATH": str(config.source / "apps/api"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "LOG_FILE": "",
            "DATABASE_URL": "sqlite+aiosqlite:///"
            + (config.output / "data/groundtruth.sqlite").as_posix(),
            "STORAGE_ROOT": str(config.output / "data/uploads"),
            "APP_ENV": "development",
            "AUTH_ENABLED": "true",
            "RATE_LIMIT_ENABLED": "false",
            "OFFLINE_MODE": "false",
            "EMBEDDING_MODE": "local",
            "EMBEDDING_DIMENSIONS": "384",
            "LOCAL_MODEL_PATH": str(config.embedding),
            "LOCAL_MODEL_REVISION": EMBEDDING,
            "GENERATION_MODE": "extractive",
            "INGESTION_MODE": "inline",
            "SOURCE_CONTEXT_MODE": "body",
            "CONNECTED_REFUSAL_THRESHOLD": "0.35",
            "ANSWER_SELECTION_MODE": "reader",
            "READER_MODEL_PATH": str(config.reader),
            "READER_MODEL_REVISION": READER,
            "READER_NULL_THRESHOLD": "4",
            "READER_MAX_LENGTH": "384",
            "READER_STRIDE": "128",
            "READER_N_BEST": "20",
            "READER_MAX_SPAN_TOKENS": "96",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "SUPPORT_MODEL_PATH": str(config.support),
            "SUPPORT_MODEL_REVISION": SUPPORT,
            "SUPPORT_MIN_MARGIN": str(config.margin),
            "ANSWER_PROPOSAL_PROFILE": config.proposal_profile,
            "ROLE_SCOPE_POLICY": config.role_scope_policy,
            "PROCEDURE_VERIFICATION_PROFILE": config.procedure_profile,
            "SOURCE_CONTEXT_POLICY": source_context_policy(config),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
            "CUDA_VISIBLE_DEVICES": "",
            "CORS_ORIGINS": "http://127.0.0.1:3506",
        }
    )
    return env


class SystemBoundary:
    """Actual process and local HTTP boundary. No shell or arbitrary destinations."""

    def port_free(self) -> bool:
        with socket.socket() as stream:
            if os.name == "nt":
                stream.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                stream.bind(("127.0.0.1", 8402))
                return True
            except OSError:
                return False

    def start(self, argv, *, cwd, env, log):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with log.open("xb") as stream:
            return subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )

    def run(self, argv, *, cwd, env, log, timeout):
        process = self.start(argv, cwd=cwd, env=env, log=log)
        try:
            return process.wait(timeout=timeout)
        except BaseException:
            self.stop(process)
            raise

    def alive(self, process):
        return process.poll() is None

    def request(self, path, timeout):
        request = urllib.request.Request(
            BASE_URL + path, headers={"Accept": "application/json"}
        )
        # Loopback never goes through owner proxy configuration.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())

    def stop(self, process):
        running = process.poll() is None
        kill_exit = None
        if running:
            if os.name == "nt":
                result = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
                kill_exit = result.returncode
            else:
                process.terminate()
            process.wait(timeout=30)
        return {
            "pid": process.pid,
            "stopped": process.poll() is not None,
            "was_running": running,
            "tree_kill_exit": kill_exit,
            "method": "taskkill-owned-PID-tree"
            if os.name == "nt"
            else "terminate-owned-PID",
        }

    def wait_closed(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.port_free():
                return True
            time.sleep(0.1)
        return self.port_free()


def source_files(config: Config) -> dict:
    if digest(config.source_manifest) != config.source_manifest_sha256:
        raise ValueError("Source manifest differs from independently selected pin")
    files = verified_files(config.source, read(config.source_manifest)["files"])
    actual = {
        path.relative_to(config.source).as_posix()
        for path in config.source.rglob("*")
        if path.is_file()
        and path.suffix in (".py", ".json")
        and "__pycache__" not in path.parts
    }
    if actual != set(files):
        raise ValueError("Frozen source contains unmanifested or missing code/data")
    for name in (
        "apps/api/app/__init__.py",
        "scripts/seed_portfolio.py",
        "scripts/evaluate_portfolio_retrieval.py",
    ):
        if name not in files:
            raise ValueError("Frozen source lacks a required entry point")
    return files


def corpus_files(config: Config) -> dict:
    manifest = config.corpus / "manifest.json"
    if digest(manifest) != config.corpus_manifest_sha256:
        raise ValueError("Corpus manifest differs from independently selected pin")
    metadata = read(manifest)
    if (
        metadata.get("schema_version") != 2
        or metadata.get("corpus_role") != "development"
    ):
        raise ValueError("Only version-two DEVELOPMENT corpora are permitted")
    if set(metadata.get("files", {})) != {
        "documents.json",
        "cases.json",
        "profile.json",
    }:
        raise ValueError("Unexpected corpus file set")
    return {
        "manifest.json": config.corpus_manifest_sha256,
        **verified_files(config.corpus, metadata["files"]),
    }


def model_binding(root, name, model, revision):
    path = root / name
    metadata = read(path)
    if metadata.get("model") != model or metadata.get("revision") != revision:
        raise ValueError("Configured model identity differs from approved revision")
    return {
        "root": str(root),
        "manifest": name,
        "manifest_sha256": digest(path),
        "model": model,
        "revision": revision,
        "files": verified_files(root, metadata.get("files")),
    }


def model_bindings(config):
    return {
        "embedding": model_binding(
            config.embedding,
            "groundtruth-model.json",
            "sentence-transformers/all-MiniLM-L6-v2",
            EMBEDDING,
        ),
        "reader": model_binding(
            config.reader,
            "groundtruth-reader.json",
            "deepset/roberta-base-squad2",
            READER,
        ),
        "support": model_binding(
            config.support,
            "groundtruth-support.json",
            "cross-encoder/nli-deberta-v3-small",
            SUPPORT,
        ),
    }


def inventory_program(config):
    return (
        "import app,json;from pathlib import Path;"
        "from app.portfolio import load_corpus;"
        f"c=load_corpus(Path({str(config.corpus)!r}),"
        "expected_representation_profile='connected-paragraphs-v1',"
        f"expected_common_manifest_sha256={config.common_manifest_sha256!r});"
        "assert c['manifest']['corpus_role']=='development';"
        "print(json.dumps({'app_file':app.__file__,'cases':"
        "[{'id':r['id'],'category':r['category']} for r in c['cases'] "
        "if r['split']=='development']}))"
    )


def check_inventory(config, value):
    if (
        Path(value["app_file"]).resolve()
        != (config.source / "apps/api/app/__init__.py").resolve()
    ):
        raise ValueError("Imported app is outside the frozen source")
    cases = value["cases"]
    if (
        len(cases) != 80
        or len({row["id"] for row in cases}) != 80
        or not all(isinstance(row["id"], str) and row["id"] for row in cases)
    ):
        raise ValueError("Development inventory requires eighty unique case IDs")
    counts = Counter(row["category"] for row in cases)
    # Corpus category spelling is checked by its frozen loader; preserve labels.
    if (
        counts.get("answerable") != 48
        or counts.get("unanswerable") != 16
        or counts.get("adversarial") != 8
        or sum(
            v
            for k, v in counts.items()
            if k not in {"answerable", "unanswerable", "adversarial"}
        )
        != 8
        or len(counts) != 4
    ):
        raise ValueError("Development inventory must be 48/16/8/8")
    return {row["id"]: row["category"] for row in cases}


def evaluate_argv(config):
    argv = [
        str(config.python),
        "-B",
        str(config.source / "scripts/evaluate_portfolio_retrieval.py"),
        "--seed-manifest",
        str(config.output / "data/seed-manifest.json"),
        "--corpus-dir",
        str(config.corpus),
        "--output",
        str(config.output / "report.json"),
        "--split",
        "development",
        "--method",
        config.method,
        "--execution-arm",
        "candidate",
        "--require-answer-spans",
        "--expected-top-k",
        "5",
        "--expected-refusal-threshold",
        "0.35",
        "--expected-reader-null-threshold",
        "4",
        "--expected-reader-model-revision",
        READER,
        "--expected-support-mode",
        "local_nli",
        "--expected-support-revision",
        SUPPORT,
        "--expected-support-margin",
        str(config.margin),
        "--expected-selection-contract",
        "requirement-evidence-v2",
        "--expected-proposal-profile",
        config.proposal_profile,
        "--expected-role-scope-policy",
        config.role_scope_policy,
        "--expected-procedure-verification-profile",
        config.procedure_profile,
    ]
    if config.procedure_profile == "source_declared_procedure_copy_v1":
        argv.extend(
            [
                "--expected-answer-selection-mode",
                "reader",
                "--expected-generation-mode",
                "extractive",
            ]
        )
    if source_context_policy(config) != "explicit_target_v1":
        argv.extend(["--expected-source-context-policy", source_context_policy(config)])
    return argv


def complete_report(config, inventory):
    report = read(config.output / "report.json")
    methods = list(METHODS) if config.method == "all" else [config.method]
    if (
        report.get("split") != "development"
        or report.get("execution_arm") != "candidate"
        or report.get("corpus_manifest_sha256") != config.corpus_manifest_sha256
        or report.get("span_integrity_required") is not True
        or not includes(report.get("settings"), expected_settings(config))
        or not isinstance(report.get("results"), dict)
        or set(report["results"]) != set(methods)
    ):
        raise ValueError("Report metadata or method set is incomplete")
    for method in methods:
        rows = report["results"][method]["cases"]
        if (
            len(rows) != 80
            or len({row["case_id"] for row in rows}) != 80
            or {row["case_id"]: row["category"] for row in rows} != inventory
        ):
            raise ValueError("Report lacks the exact complete development inventory")
    return methods


def execute(config: Config, boundary: Any = None) -> int:  # noqa: C901 - staged process lifecycle and evidence cleanup
    """Return evaluator 0/1/2 only for a complete report; all other states return2.

    Creating an output directory that already exists raises before touching it.
    A result cannot claim the product quality gate. Inspection follows SEALED.
    """
    output = config.output.resolve()
    for protected in (
        config.source,
        config.corpus,
        config.embedding,
        config.reader,
        config.support,
    ):
        protected = protected.resolve()
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError("Output must be disjoint from all immutable input roots")
    config.output.mkdir(parents=True, exist_ok=False)
    system = boundary or SystemBoundary()
    commands, checks = [], []
    process = None
    result = {
        "status": "setup_error",
        "evaluation_exit": None,
        "controller_exit": 2,
        "quality_gate_claimed": False,
        "blind_acceptance": False,
        "source_unchanged": False,
        "corpus_unchanged": False,
        "models_unchanged": False,
        "methods": [],
        "error": None,
    }
    children_closed = True
    source_pin = corpus_pin = models_pin = None
    env = environment(config)

    def unchanged(stage):
        state = {
            "stage": stage,
            "source": source_files(config) == source_pin,
            "corpus": corpus_files(config) == corpus_pin,
        }
        checks.append(state)
        if not state["source"] or not state["corpus"]:
            raise ValueError("Frozen inputs changed")

    def run(argv, stage):
        unchanged("before_" + stage)
        entry = {
            "stage": stage,
            "argv": argv,
            "cwd": str(config.source),
            "log": stage + ".log",
            "exit": None,
            "exception": None,
        }
        commands.append(entry)
        try:
            entry["exit"] = system.run(
                argv,
                cwd=config.source,
                env=env,
                log=config.output / entry["log"],
                timeout=config.command_timeout,
            )
            return entry["exit"]
        except BaseException as exc:
            entry["exception"] = type(exc).__name__
            raise
        finally:
            unchanged("after_" + stage)

    try:
        if (
            config.margin not in range(5)
            or config.proposal_profile not in PROPOSALS
            or config.role_scope_policy not in ROLES
            or config.procedure_profile not in PROCEDURES
            or config.source_context_policy not in SOURCE_CONTEXT_POLICIES
            or (
                config.source_context_policy == "scoped_note_context_v1"
                and config.procedure_profile != "source_declared_procedure_copy_v1"
            )
            or config.method not in (*METHODS, "all")
        ):
            raise ValueError("Unknown explicit development controls")
        if not config.python.is_file():
            raise ValueError("Optional-model Python does not exist")
        # Check before migration/import; do not touch an existing listener.
        if not system.port_free():
            raise ValueError("Dedicated 8402 occupied; no process was stopped")
        source_pin, corpus_pin, models_pin = (
            source_files(config),
            corpus_files(config),
            model_bindings(config),
        )
        settings = {
            **{
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(config).items()
            },
            "settings": expected_settings(config),
            "port": 8402,
            "model_binding": models_pin,
            "environment_overrides": {
                key: value for key, value in env.items() if key in environment_keys()
            },
            "provider_credentials_removed": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        save(config.output / "execution-settings.json", settings)
        (config.output / "data").mkdir()
        if (
            run(
                [str(config.python), "-B", "-c", inventory_program(config)], "inventory"
            )
            != 0
        ):
            raise ValueError("Frozen import/corpus validation failed")
        inventory = check_inventory(config, read(config.output / "inventory.log"))
        if run([str(config.python), "-B", "-m", "app.db.migrate"], "migrate") != 0:
            raise ValueError("Migration failed")
        unchanged("before_api")
        argv = [
            str(config.python),
            "-B",
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8402",
            "--no-access-log",
        ]
        entry = {
            "stage": "api",
            "argv": argv,
            "cwd": str(config.source),
            "log": "api.log",
            "exit": None,
            "exception": None,
        }
        commands.append(entry)
        process = system.start(
            argv, cwd=config.source, env=env, log=config.output / "api.log"
        )
        children_closed = False
        save(
            config.output / "process.json",
            {"owned_pid": process.pid, "port": 8402, "source": str(config.source)},
        )
        deadline = time.monotonic() + config.readiness_timeout
        live = ready = None
        attempt = 0
        while time.monotonic() < deadline:
            if not system.alive(process):
                raise ValueError("Owned API exited before readiness")
            try:
                code, live = system.request(
                    "/api/health/live", timeout=min(5, config.readiness_timeout)
                )
                if code == 200:
                    code, ready = system.request(
                        "/api/health/ready",
                        timeout=max(0.001, deadline - time.monotonic()),
                    )
                    attempt += 1
                    save(
                        config.output / f"readiness-attempt-{attempt:03d}.json",
                        {"status_code": code, "payload": ready},
                    )
                    if code == 200 and ready.get("status") == "ready":
                        break
                    if code == 503:
                        raise ValueError("Selected model/storage is not ready")
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(min(0.1, config.readiness_timeout))
        else:
            raise TimeoutError("Owned API readiness deadline exceeded")
        save(config.output / "liveness.json", live)
        save(config.output / "readiness.json", ready)
        if not includes(ready.get("runtime"), expected_runtime(config)) or any(
            ready.get("checks", {}).get(key) != "ok"
            for key in ("database", "embeddings", "reader", "evidence_support")
        ):
            raise ValueError("Observed runtime differs from explicit settings")
        unchanged("after_readiness")
        if (
            run(
                [
                    str(config.python),
                    "-B",
                    str(config.source / "scripts/seed_portfolio.py"),
                    "--api-url",
                    BASE_URL,
                    "--manifest",
                    str(config.output / "data/seed-manifest.json"),
                    "--confirm-disposable-database",
                    "--corpus-dir",
                    str(config.corpus),
                ],
                "seed",
            )
            != 0
        ):
            raise ValueError("Canonical API seeding failed")
        code = run(evaluate_argv(config), "evaluate")
        result["evaluation_exit"] = code
        try:
            result["methods"] = complete_report(config, inventory)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result["status"] = "incomplete"
            result["error"] = type(exc).__name__ + ": " + str(exc)
        else:
            if code not in (0, 1, 2):
                raise ValueError("Unexpected evaluator exit")
            result.update(status="complete_report", controller_exit=code)
    except BaseException as exc:  # noqa: BLE001 - Preserve interrupt evidence before returning non-success.
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if process is not None:
            try:
                stop = system.stop(process)
                closed = system.wait_closed(30)
                children_closed = bool(stop["stopped"] and closed)
                save(config.output / "cleanup.json", {**stop, "port_closed": closed})
                entry["exit"] = process.returncode
            except BaseException as exc:  # noqa: BLE001 - Cleanup failure must be recorded and block inspection.
                children_closed = False
                result["cleanup_error"] = type(exc).__name__ + ": " + str(exc)
        for name, getter, pin in (
            ("source", source_files, source_pin),
            ("corpus", corpus_files, corpus_pin),
            ("models", model_bindings, models_pin),
        ):
            try:
                result[name + "_unchanged"] = pin is not None and getter(config) == pin
            except BaseException:  # noqa: BLE001 - Any failed integrity read is an unchanged=false result.
                result[name + "_unchanged"] = False
        if not children_closed or (
            source_pin is not None
            and not all(
                result[name + "_unchanged"] for name in ("source", "corpus", "models")
            )
        ):
            result.update(status="setup_error", controller_exit=2)
        save(config.output / "commands.json", commands)
        save(config.output / "input-checks.json", checks)
        save(config.output / "result.json", result)
        seal = {
            path.relative_to(config.output).as_posix(): digest(path)
            for path in config.output.rglob("*")
            if path.is_file()
        }
        save(
            config.output / "SEALED.json",
            {
                "files": seal,
                "children_closed": children_closed,
                "created_at": datetime.now(UTC).isoformat(),
                "inspection_allowed": children_closed,
            },
        )
    return result["controller_exit"]


def environment_keys():
    """Record explicit non-secret overrides only, never the inherited environment."""
    return {
        "PYTHONPATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "LOG_FILE",
        "DATABASE_URL",
        "STORAGE_ROOT",
        "APP_ENV",
        "AUTH_ENABLED",
        "RATE_LIMIT_ENABLED",
        "OFFLINE_MODE",
        "EMBEDDING_MODE",
        "EMBEDDING_DIMENSIONS",
        "LOCAL_MODEL_PATH",
        "LOCAL_MODEL_REVISION",
        "GENERATION_MODE",
        "INGESTION_MODE",
        "SOURCE_CONTEXT_MODE",
        "CONNECTED_REFUSAL_THRESHOLD",
        "ANSWER_SELECTION_MODE",
        "READER_MODEL_PATH",
        "READER_MODEL_REVISION",
        "READER_NULL_THRESHOLD",
        "READER_MAX_LENGTH",
        "READER_STRIDE",
        "READER_N_BEST",
        "READER_MAX_SPAN_TOKENS",
        "ANSWER_SUPPORT_MODE",
        "SUPPORT_MODEL_PATH",
        "SUPPORT_MODEL_REVISION",
        "SUPPORT_MIN_MARGIN",
        "ANSWER_PROPOSAL_PROFILE",
        "ROLE_SCOPE_POLICY",
        "PROCEDURE_VERIFICATION_PROFILE",
        "SOURCE_CONTEXT_POLICY",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY",
        "TOKENIZERS_PARALLELISM",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "CUDA_VISIBLE_DEVICES",
        "CORS_ORIGINS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "source",
        "source_manifest",
        "corpus",
        "output",
        "python",
        "embedding",
        "reader",
        "support",
    ):
        parser.add_argument(
            "--" + key.replace("_", "-"),
            type=lambda p: Path(p).resolve(),
            required=True,
        )
    for key in (
        "source_manifest_sha256",
        "corpus_manifest_sha256",
        "common_manifest_sha256",
    ):
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    parser.add_argument("--margin", type=int, choices=range(5), required=True)
    parser.add_argument("--proposal-profile", choices=PROPOSALS, required=True)
    parser.add_argument("--role-scope-policy", choices=ROLES, required=True)
    parser.add_argument(
        "--procedure-profile", choices=PROCEDURES, default="all_units_nli_v1"
    )
    parser.add_argument("--method", choices=(*METHODS, "all"), default="reranked")
    parser.add_argument(
        "--source-context-policy",
        choices=SOURCE_CONTEXT_POLICIES,
        default="explicit_target_v1",
    )
    parser.add_argument("--readiness-timeout", type=float, default=300)
    parser.add_argument("--command-timeout", type=float, default=7200)
    args = parser.parse_args()
    try:
        code = execute(Config(**vars(args)))
    except (FileExistsError, OSError, ValueError) as exc:
        print("Controller unavailable: " + type(exc).__name__ + ": " + str(exc))
        return 2
    # Do not print report metrics or case-level outcomes before independent inspection.
    print(
        json.dumps(
            {
                "seal": str(args.output / "SEALED.json"),
                "controller_exit": code,
                "scope": "Development observation; no blind/product-quality claim",
            }
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
