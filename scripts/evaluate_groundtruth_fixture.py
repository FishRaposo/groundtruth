"""Run a local EvalForge-shaped GroundTruth fixture without EvalForge installed."""

# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.evaluation.evalforge_adapter import (  # noqa: E402
    GroundTruthEvaluationAdapter,
    load_evalforge_fixture,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a local GroundTruth fixture with offline judges."
    )
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    suite = load_evalforge_fixture(args.fixture)
    report = GroundTruthEvaluationAdapter().evaluate_sync(suite)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
