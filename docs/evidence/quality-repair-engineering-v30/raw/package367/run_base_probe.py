"""Execute the current canonical smoke body in the new installed base wheel."""
import importlib.util
import json
from pathlib import Path

import package_gate as gate

spec = importlib.util.spec_from_file_location("canonical_base_v367", gate.W / "scripts/verify_isolated_wheel.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
directory = gate.OUT / "base-workflow"
directory.mkdir()
env = gate.clean_env()
# Exactly the canonical child profile, including explicit neutralization of
# inherited copy/context/role/discovery/support settings.
env.update(DATABASE_URL="sqlite+aiosqlite:///:memory:", EMBEDDING_MODE="deterministic", EMBEDDING_DIMENSIONS="384",
           GENERATION_MODE="extractive", ANSWER_SELECTION_MODE="lexical", ANSWER_PROPOSAL_PROFILE="qa_only_v1",
           ROLE_SCOPE_POLICY="literal_v1", PROCEDURE_VERIFICATION_PROFILE="all_units_nli_v1", SOURCE_CONTEXT_POLICY="explicit_target_v1",
           ANSWER_SUPPORT_MODE="disabled", OPENAI_API_KEY="", HF_HUB_OFFLINE="1", INGESTION_MODE="inline", AUTH_ENABLED="false",
           RATE_LIMIT_ENABLED="false", APP_ENV="development", STORAGE_ROOT=str(directory / "uploads"))
code = module.IMPORTS + '\nprint("Canonical base ASGI upload/query/history and missing-optional-assets assertions completed.")\n'
result = gate.command("base-workflow", [str(gate.OUT / "base-env/Scripts/python.exe"), "-I", "-c", code], env=env, cwd=directory)
gate.write("base-workflow-observation.json", {"exit": result, "smoke_source": str(gate.W / "scripts/verify_isolated_wheel.py"),
    "smoke_source_sha256": gate.sha(gate.W / "scripts/verify_isolated_wheel.py"), "installed_python": str(gate.OUT / "base-env/Scripts/python.exe"),
    "scope": "Canonical current smoke body on fresh installed wheel; actual ASGI upload/query/history, packaged corpora/demo integrity and missing reader/classifier failures; not model quality or auth acceptance"})
raise SystemExit(result)
