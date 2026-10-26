"""C399 guarded live coordinator. Preparation/preflight never contacts services.

Only --execute + explicit review/stop flags enables process/browser/network work.
Private seed bytes are read only by the fixed browser script during live execution.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

PREP = Path(__file__).resolve().parent
Q = PREP.parent
W = Q.parent / "delivery-worktree"
LIVE = Q / "typed-connected-live-v378"
API_RECORD = LIVE / "api-outage-retry-v481-process.json"
AUTHORITY = Q / "development-controller-v346/controller.py"
API_PYTHON = Q / "context-package-v329/optional-env/Scripts/python.exe"
API_COMMAND = [str(API_PYTHON), "-B", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8401", "--no-access-log"]
API = "http://127.0.0.1:8401"
FRONT = "http://127.0.0.1:3506"
AUTHORITY_SHA = "8c732ab64ad7085ad3385f81e29dded23c43395b4e51b068b269f5d6a846de1f"
CHAT_SHA = "09f7f0a529f7329de30e0f57d3e70c56013bd914307ae5e3c3cc2a0a54481042"
VENV_BINDING = PREP / "venv-executable-binding.json"
VENV_BINDING_SHA = "91bc41a78f9eda227e7b23dea7e1bfebe540e2b25b8d8fdd98412a99f66c22eb"
SENTINELS = {"contexts-ready", "api-down", "retry-failed", "api-ready", "browser-done", "browser-failed"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def read_public(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected public JSON object")
    return value


def preflight(args) -> dict:
    # Pure file checks only. Never open seed.json or SQLite, query a PID, bind a
    # socket, launch a child, or request a URL in this branch.
    record = read_public(API_RECORD)
    assert record["port"] == 8401 and record["command"] == API_COMMAND
    assert isinstance(record["owned_pid"], int) and record["owned_pid"] > 1
    assert sha(AUTHORITY) == AUTHORITY_SHA
    assert sha(W / "apps/web/src/components/PortfolioChat.tsx") == args.expected_chat_sha256
    assert (W / "apps/web/node_modules/@playwright/test/package.json").is_file()
    assert API_PYTHON.is_file()
    venv = read_venv_executables()
    build = args.frontend_build.resolve() if args.frontend_build else None
    build_facts = {"provided": build is not None}
    if build:
        assert build.is_dir() and (build / "BUILD_ID").is_file()
        assert (build / "standalone/server.js").is_file() and (build / "static").is_dir()
        build_facts.update(path=str(build), build_id=(build / "BUILD_ID").read_text().strip(), server_sha256=sha(build / "standalone/server.js"))
    private = Path(os.environ.get("GROUNDTRUTH_SEED_MANIFEST", str(LIVE / "private/seed.json"))).resolve()
    assert private == (LIVE / "private/seed.json").resolve(), "Only the reviewed v378 private seed path is permitted"
    return {"scope": "Pure preparation file checks; no live/process/browser/model/network work", "private_seed_opened": False,
            "private_seed_file_present": private.is_file(), "api_record_sha256": sha(API_RECORD), "recorded_api_pid": record["owned_pid"],
            "authority_sha256": AUTHORITY_SHA, "chat_sha256": args.expected_chat_sha256, "frontend": build_facts,
            "browser_sha256": sha(PREP / "browser.mjs"), "api_port": 8401, "frontend_port": 3506,
            "venv_executable_binding": venv}


def powershell(script: str) -> str:
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise RuntimeError("Fixed process ownership query failed; no stop is authorized")
    return result.stdout.strip()


def process_info(pid: int) -> dict:
    assert type(pid) is int and pid > 1
    text = powershell("$p=Get-CimInstance Win32_Process -Filter 'ProcessId = " + str(pid) + "'; if($null -eq $p){throw 'Process absent'}; [pscustomobject]@{pid=$p.ProcessId; parent_pid=$p.ParentProcessId; executable=$p.ExecutablePath; command_line=$p.CommandLine; created=$p.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress")
    return json.loads(text)


def command_tokens(command_line: str) -> list[str]:
    import ctypes
    from ctypes import wintypes
    count = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    values = parse(command_line, ctypes.byref(count))
    if not values:
        raise RuntimeError("Cannot inspect actual Windows command line")
    try:
        return [values[index] for index in range(count.value)]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(values, ctypes.c_void_p))


def listener_pids(port: int) -> set[int]:
    assert port in {8401, 3506}
    text = powershell("$ids=@(Get-NetTCPConnection -State Listen -LocalPort " + str(port) + " -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); ConvertTo-Json -InputObject $ids -Compress")
    value = json.loads(text) if text else []
    return set(value if isinstance(value, list) else [value])


def verify_process(pid: int, expected: list[str], creation: str | None = None) -> dict:
    actual = process_info(pid)
    tokens = command_tokens(actual["command_line"])
    assert Path(actual["executable"]).resolve() == Path(expected[0]).resolve()
    assert Path(tokens[0]).resolve() == Path(expected[0]).resolve() and tokens[1:] == expected[1:]
    if creation is not None:
        assert actual["created"] == creation, "PID was reused; refuse stop"
    return actual


def stop_verified(pid: int, expected: list[str], creation: str) -> None:
    verify_process(pid, expected, creation)
    # One verified PID only. Initial uvicorn has no workers/reloader; no broad
    # tree kill, name-based stop, owner/DEV port scan or arbitrary process action.
    powershell("Stop-Process -Id " + str(pid) + " -Force -ErrorAction Stop")


def read_venv_executables() -> dict:
    """Derive the one allowed base executable from pinned pyvenv.cfg bytes."""
    assert sha(VENV_BINDING) == VENV_BINDING_SHA
    pinned = read_public(VENV_BINDING)
    assert pinned["schema"] == "known-windows-venv-executables-v1"
    cfg = API_PYTHON.parent.parent / "pyvenv.cfg"
    assert Path(pinned["cfg_path"]).resolve() == cfg.resolve()
    assert sha(cfg) == pinned["cfg_sha256"], "Pinned venv configuration changed"
    values = {}
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            assert key not in values, "Duplicate venv configuration field"
            values[key] = value
    home = Path(values["home"])
    assert home.is_absolute()
    base = (home / "python.exe").resolve(strict=True)
    assert Path(pinned["launcher_path"]).resolve() == API_PYTHON.resolve()
    assert Path(pinned["base_path"]).resolve() == base
    assert sha(API_PYTHON) == pinned["launcher_sha256"]
    assert sha(base) == pinned["base_sha256"], "Pinned base interpreter changed"
    return pinned


def read_api_record_identity(record_path: Path, expected_sha256: str) -> dict:
    path = record_path.resolve()
    if path != API_RECORD.resolve():
        relative = path.relative_to((PREP / "runs").resolve())
        assert len(relative.parts) == 2 and relative.parts[-1] == "restarted-api-process.json"
    assert sha(path) == expected_sha256, "Recorded API identity changed"
    record = read_public(path)
    assert record["port"] == 8401 and record["command"] == API_COMMAND
    assert type(record["owned_pid"]) is int and record["owned_pid"] > 1
    return {"path": str(path), "sha256": expected_sha256, "record": record,
            "written_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()}


def birth(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert result.tzinfo is not None, "Process birth must carry a timezone"
    return result.astimezone(UTC)


def api_listener_binding(record_path: Path, expected_record_sha256: str) -> dict:
    """Admit direct launcher or only its exact pinned immediate base child."""
    record = read_api_record_identity(record_path, expected_record_sha256)
    venv = read_venv_executables()
    launcher_pid = record["record"]["owned_pid"]
    launcher = verify_process(launcher_pid, API_COMMAND)
    assert launcher["pid"] == launcher_pid
    assert 0 <= (birth(record["written_at"]) - birth(launcher["created"])).total_seconds() <= 30
    if "created" in record["record"]:
        assert record["record"]["created"] == launcher["created"]
    listeners = listener_pids(8401)
    assert len(listeners) == 1, "Require exactly one 8401 listener"
    serving_pid = next(iter(listeners))
    assert type(serving_pid) is int and serving_pid > 1
    if serving_pid == launcher_pid:
        serving = launcher
        serving_command = list(API_COMMAND)
        shape = "direct-recorded-launcher"
    else:
        serving_command = [venv["base_path"], *API_COMMAND[1:]]
        serving = verify_process(serving_pid, serving_command)
        assert serving["pid"] == serving_pid
        assert type(serving["parent_pid"]) is int and serving["parent_pid"] == launcher_pid, "Listener is not the immediate recorded-launcher child"
        assert 0 <= (birth(serving["created"]) - birth(launcher["created"])).total_seconds() <= 30, "Child birth is outside the known launch window"
        shape = "pinned-venv-immediate-base-child"
    return {"schema": "strict-api-listener-binding-v1", "shape": shape, "record": record,
            "venv": venv, "launcher": launcher, "serving": serving,
            "serving_command": serving_command, "listener_pids": sorted(listeners)}


def stop_api_listener_binding(binding: dict) -> dict:
    """Recheck the full chain/files immediately before one serving-PID stop."""
    path = Path(binding["record"]["path"])
    assert path.resolve() == API_RECORD.resolve(), "Initial stop is restricted to the root API record"
    expected = binding["record"]["sha256"]
    assert api_listener_binding(path, expected) == binding, "API process chain or file identity changed"
    assert read_api_record_identity(path, expected) == binding["record"]
    assert read_venv_executables() == binding["venv"]
    launcher = binding["launcher"]
    serving = binding["serving"]
    assert verify_process(launcher["pid"], API_COMMAND, launcher["created"]) == launcher
    assert verify_process(serving["pid"], binding["serving_command"], serving["created"]) == serving
    assert listener_pids(8401) == {serving["pid"]}
    assert read_api_record_identity(path, expected) == binding["record"]
    assert read_venv_executables() == binding["venv"]
    stop_verified(serving["pid"], binding["serving_command"], serving["created"])
    return {"stopped_serving_pid": serving["pid"], "recorded_launcher_pid": launcher["pid"], "shape": binding["shape"],
            "launcher_explicitly_stopped": serving["pid"] == launcher["pid"], "initial_tree_stop": False}


def port_closed(port: int, deadline: float = 20) -> bool:
    until = time.monotonic() + deadline
    while time.monotonic() < until:
        with socket.socket() as stream:
            stream.settimeout(0.4)
            if stream.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.2)
    return False


def wait_ready(url: str, deadline: float = 300) -> dict:
    assert url in {API + "/api/health/ready", FRONT + "/chat"}
    until = time.monotonic() + deadline
    while time.monotonic() < until:
        try:
            with urllib.request.urlopen(url, timeout=min(60, max(1, until - time.monotonic()))) as response:
                payload = response.read()
                if response.status == 200:
                    return json.loads(payload) if url.startswith(API) else {"status": 200}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    raise TimeoutError("Owned service readiness deadline exceeded")


@lru_cache(maxsize=1)
def runtime_authority():
    """One pinned authority/config instance for both readiness and child env."""
    assert sha(AUTHORITY) == AUTHORITY_SHA
    spec = importlib.util.spec_from_file_location("c419_environment_authority", AUTHORITY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    selected = read_public(Q / "development-v30-typed-context-v2-locked329-margin2-reranked/execution-settings.json")
    config = SimpleNamespace(source=W, output=LIVE, embedding=Path(selected["embedding"]), reader=Path(selected["reader"]), support=Path(selected["support"]), margin=2,
                             proposal_profile="qa_plus_source_patterns_v1", role_scope_policy="ordinary_session_activity_v1", procedure_profile="source_declared_procedure_copy_v1", source_context_policy="scoped_note_context_v2")
    return module, config


def check_runtime(payload: dict) -> None:
    module, config = runtime_authority()
    assert module.includes(payload["runtime"], module.expected_runtime(config)), "Runtime differs from the pinned restart environment authority"


def sentinel(run: Path, name: str, *, wait: bool = False, browser=None) -> dict:
    assert name in SENTINELS
    path = run / (name + ".json")
    deadline = time.monotonic() + 360
    while wait and not path.is_file():
        if (run / "browser-failed.json").exists() or (browser is not None and browser.poll() is not None):
            raise RuntimeError("Browser gate failed; inspect sanitized v399 evidence")
        if time.monotonic() > deadline:
            raise TimeoutError("Browser IPC deadline exceeded")
        time.sleep(0.2)
    value = read_public(path)
    assert value["phase"] == name and value["viewports"] == [390, 768, 1440]
    assert set(value) == {"phase", "viewports"}, "IPC contains unexpected data"
    return value


def write_sentinel(run: Path, name: str) -> None:
    assert name in SENTINELS
    destination = run / (name + ".json")
    temporary = run / (name + ".pending")
    assert not destination.exists()
    save(temporary, {"phase": name, "viewports": [390, 768, 1440]})
    os.replace(temporary, destination)


def register_owned(owned: list, process, command: list[str], label: str) -> dict:
    # Retain the newly obtained Popen handle even if OS metadata inspection fails.
    owned.append((process, command, None, label))
    actual = verify_process(process.pid, command)
    owned[-1] = (process, command, actual["created"], label)
    return actual


def execute(args, facts: dict) -> None:
    assert os.name == "nt" and args.reviews_complete and args.stop_recorded_root_api
    assert args.frontend_build and args.expected_api_record_sha256 == sha(API_RECORD)
    assert os.environ.get("GROUNDTRUTH_SEED_MANIFEST"), "Root must explicitly set the private seed path environment variable"
    assert not listener_pids(3506), "Do not stop another frontend; root must close it first"
    initial_binding = api_listener_binding(API_RECORD, args.expected_api_record_sha256)
    module, config = runtime_authority()
    check_runtime(wait_ready(API + "/api/health/ready"))
    run = PREP / "runs" / args.run_label
    run.mkdir(parents=True, exist_ok=False)
    save(run / "preflight.json", facts)
    save(run / "initial-api-ownership.json", {"record_sha256": sha(API_RECORD), "binding": initial_binding, "expected_command": API_COMMAND})
    build = args.frontend_build.resolve()
    staged = run / "frontend"
    shutil.copytree(build / "standalone", staged)
    if (W / "apps/web/public").is_dir():
        shutil.copytree(W / "apps/web/public", staged / "public", dirs_exist_ok=True)
    shutil.copytree(build / "static", staged / build.name / "static", dirs_exist_ok=True)
    node = shutil.which("node.exe") or shutil.which("node")
    assert node
    api_env = module.environment(config)
    assert api_env["DATABASE_URL"] == "sqlite+aiosqlite:///" + (LIVE / "data/groundtruth.sqlite").as_posix()
    seed_path = os.environ["GROUNDTRUTH_SEED_MANIFEST"]
    api_env.pop("GROUNDTRUTH_SEED_MANIFEST", None)
    frontend_env = {**api_env, "NODE_ENV": "production", "PORT": "3506", "HOSTNAME": "127.0.0.1", "NEXT_TELEMETRY_DISABLED": "1"}
    frontend_env.pop("PYTHONPATH", None)
    for name in ("NODE_OPTIONS", "NODE_PATH", "DEBUG", "PWDEBUG"):
        frontend_env.pop(name, None)
    frontend_command = [node, str(staged / "server.js")]
    browser_command = [node, str(PREP / "browser.mjs"), "--execute", "--run-dir", str(run)]
    save(run / "commands.json", {"frontend": frontend_command, "api_restart": API_COMMAND, "browser": browser_command, "environment_authority_sha256": AUTHORITY_SHA,
                                  "shared_database": str(LIVE / "data/groundtruth.sqlite"), "profile": {"support_margin": 2, "qa_threshold": 4, "source_context_policy": "scoped_note_context_v2"}})
    owned = []
    browser = None
    handles = []
    initial_stopped = False
    cleanup = []
    try:
        front_log = (run / "frontend.log").open("x", encoding="utf-8")
        handles.append(front_log)
        frontend = subprocess.Popen(frontend_command, cwd=staged, env=frontend_env, stdout=front_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        register_owned(owned, frontend, frontend_command, "frontend")
        wait_ready(FRONT + "/chat")
        browser_log = (run / "browser.log").open("x", encoding="utf-8")
        handles.append(browser_log)
        browser_env = {**frontend_env, "GROUNDTRUTH_SEED_MANIFEST": seed_path}
        browser = subprocess.Popen(browser_command, cwd=run, env=browser_env, stdout=browser_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        register_owned(owned, browser, browser_command, "browser")
        sentinel(run, "contexts-ready", wait=True, browser=browser)
        stop_observation = stop_api_listener_binding(initial_binding)
        initial_stopped = True
        save(run / "initial-api-stop.json", stop_observation)
        assert port_closed(8401)
        write_sentinel(run, "api-down")
        sentinel(run, "retry-failed", wait=True, browser=browser)
        api_log = (run / "api-restarted.log").open("x", encoding="utf-8")
        handles.append(api_log)
        api = subprocess.Popen(API_COMMAND, cwd=W, env=api_env, stdout=api_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        api_info = register_owned(owned, api, API_COMMAND, "api-restarted")
        save(run / "restarted-api-process.json", {"owned_pid": api.pid, "command": API_COMMAND, "created": api_info["created"], "port": 8401})
        ready = wait_ready(API + "/api/health/ready")
        check_runtime(ready)
        restart_record = run / "restarted-api-process.json"
        restart_binding = api_listener_binding(restart_record, sha(restart_record))
        assert restart_binding["launcher"]["created"] == api_info["created"]
        save(run / "restarted-api-listener-binding.json", restart_binding)
        save(run / "restarted-readiness.json", ready)
        write_sentinel(run, "api-ready")
        sentinel(run, "browser-done", wait=True, browser=browser)
        assert browser.wait(timeout=30) == 0
        save(run / "result.json", {"scope": "Actual engineering outage/retry/route observations; not model quality or release acceptance", "browser_exit": 0, "initial_recorded_api_stopped": True, "api_restarted_once": True})
    finally:
        if browser is not None and browser.poll() is None:
            # A key-free local signal lets the harness close its contexts/browser.
            save(run / "coordinator-abort.json", {"phase": "abort"})
            try:
                browser.wait(timeout=50)
            except subprocess.TimeoutExpired:
                pass
        order = {"browser": 0, "api-restarted": 1, "frontend": 2}
        for process, command, created, label in sorted(owned, key=lambda item: order[item[3]]):
            if process.poll() is None:
                try:
                    if created is None:
                        # Only our original process handle is trusted here. Do
                        # not infer a safe tree kill from failed metadata checks.
                        process.terminate()
                        process.wait(timeout=20)
                        cleanup.append({"process": label, "owned_handle_stopped": True, "stopped": False, "tree_verification_unavailable": True})
                        continue
                    verify_process(process.pid, command, created)
                    # A tree stop is limited to a newly spawned, verified owned
                    # child. The initial root API above is stopped as one PID.
                    taskkill = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
                    stopped = subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], capture_output=True, text=True, check=False)
                    assert stopped.returncode == 0
                    process.wait(timeout=20)
                    cleanup.append({"process": label, "stopped": True})
                except Exception as error:
                    cleanup.append({"process": label, "stopped": False, "error_class": type(error).__name__})
            else:
                cleanup.append({"process": label, "already_exited": True, "exit": process.returncode})
        for handle in handles:
            handle.close()
        final = {"initial_recorded_api_stopped": initial_stopped, "owned_processes": cleanup, "api_port_closed": port_closed(8401) if initial_stopped else None, "frontend_port_closed": port_closed(3506)}
        save(run / "cleanup.json", final)
        if any(item.get("stopped") is False for item in cleanup) or not final["frontend_port_closed"] or (initial_stopped and not final["api_port_closed"]):
            raise RuntimeError("Owned cleanup is incomplete; do not claim a passing browser gate")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--frontend-build", type=Path)
    parser.add_argument("--expected-chat-sha256", default=CHAT_SHA)
    parser.add_argument("--expected-api-record-sha256")
    parser.add_argument("--run-label", default="first")
    parser.add_argument("--reviews-complete", action="store_true")
    parser.add_argument("--stop-recorded-root-api", action="store_true")
    args = parser.parse_args()
    import re
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.run_label)
    assert re.fullmatch(r"[a-f0-9]{64}", args.expected_chat_sha256)
    return args


if __name__ == "__main__":
    args = arguments()
    facts = preflight(args)
    if args.preflight:
        print(json.dumps(facts, indent=2))
    else:
        execute(args, facts)
