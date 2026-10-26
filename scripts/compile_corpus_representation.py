"""Compile frozen shared raw inputs to a new exact arm-specific source view.

Run this separately pinned harness outside an unchanged baseline application.
No production parser, model, database, API or observed prediction is consulted.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.portfolio.representation import PROFILES, compile_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    args = parser.parse_args()
    try:
        corpus = compile_corpus(args.source, args.target, args.profile)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Representation compilation failed: {exc}\n")
    descriptor = corpus["manifest"]["comparison_representation"]
    print(
        json.dumps(
            {
                key: descriptor[key]
                for key in (
                    "contract",
                    "profile",
                    "execution_arm",
                    "oracle_contract",
                    "compiler_contract",
                    "compiler_sha256",
                    "origin_common_manifest_sha256",
                    "common_contract_sha256",
                    "common_source_contract_sha256",
                    "common_case_contract_sha256",
                    "projection_sha256",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
