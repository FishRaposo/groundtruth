"""Run the credential-free portable profile with an explicit local data directory.

This profile uses SQLite, inline ingestion and extractive answers. Local semantic
embeddings require the separately downloaded pinned model; deterministic embeddings
are an explicitly selected alternative. Neither mode contacts a provider.
Reader serving with no profile flags selects the measured composite proposals,
activity roles, source-declared copying and contextual-v2 recipe with RoBERTa4
and NLI margin2. An explicit profile flag keeps legacy defaults for unspecified
profiles. Explicit model, threshold and margin options remain overrides. Set
--answer-support disabled explicitly to inspect the legacy reader profile.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]


def validate_support_options(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    from app.evidence_policy import validate_evidence_engines

    try:
        validate_evidence_engines(
            args.answer_proposal_profile,
            args.role_scope_policy,
            args.answer_selection,
            args.answer_support,
            procedure=args.procedure_verification_profile,
            generation="extractive",
            context=getattr(args, "source_context_policy", "explicit_target_v1"),
        )
    except ValueError as exc:
        parser.error(str(exc))
    if not math.isfinite(args.support_margin) or not 0 <= args.support_margin <= 4:
        parser.error("Choose a finite --support-margin in [0, 4]")
    if args.answer_support == "local_nli" and (
        args.support_dir is None or not args.support_dir.is_dir()
    ):
        parser.error(
            "Reader evidence checks require cached support assets. Run "
            "python -m app.support_setup --directory .tmp/models/support "
            "or pass an existing --support-dir."
        )


def resolve_launch_profile_defaults(args: argparse.Namespace) -> None:
    """Resolve CLI omissions together; validation still uses evidence-policy enums."""
    measured_recipe = (
        args.action == "serve"
        and args.answer_selection == "reader"
        and args.answer_support != "disabled"
        and all(
            value is None
            for value in (
                args.answer_proposal_profile,
                args.role_scope_policy,
                args.procedure_verification_profile,
                args.source_context_policy,
            )
        )
    )
    for field, legacy, measured in (
        ("answer_proposal_profile", "qa_only_v1", "qa_plus_source_patterns_v1"),
        ("role_scope_policy", "literal_v1", "ordinary_session_activity_v1"),
        (
            "procedure_verification_profile",
            "all_units_nli_v1",
            "source_declared_procedure_copy_v1",
        ),
        ("source_context_policy", "explicit_target_v1", "scoped_note_context_v2"),
    ):
        if getattr(args, field) is None:
            setattr(args, field, measured if measured_recipe else legacy)
    if args.support_margin is None:
        args.support_margin = 2.0 if measured_recipe else 4.0


def main() -> int:
    sys.path.insert(0, str(ROOT / "apps/api"))
    from app.evidence_policy import (
        ProcedureVerificationProfile,
        ProposalProfile,
        RoleScopePolicy,
        SourceContextPolicy,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("migrate", "serve", "seed"))
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".tmp/portfolio")
    parser.add_argument("--model-dir", type=Path, default=ROOT / ".tmp/models/minilm")
    parser.add_argument(
        "--embedding", choices=("local", "deterministic"), default="local"
    )
    parser.add_argument("--port", type=int, default=8400)
    parser.add_argument("--refusal-threshold", type=float, default=0.35)
    parser.add_argument("--answer-selection", choices=("reader", "lexical"))
    parser.add_argument(
        "--answer-proposal-profile",
        choices=get_args(ProposalProfile),
        help="Any explicit profile flag keeps legacy defaults for unspecified peers.",
    )
    parser.add_argument("--role-scope-policy", choices=get_args(RoleScopePolicy))
    parser.add_argument(
        "--procedure-verification-profile",
        choices=get_args(ProcedureVerificationProfile),
        help="Explicit source-declared copying retains reader/NLI evidence gates.",
    )
    parser.add_argument(
        "--source-context-policy",
        choices=get_args(SourceContextPolicy),
    )
    parser.add_argument(
        "--reader-model",
        choices=("minilm", "roberta"),
        default="roberta",
        help="Connected candidate: RoBERTa4; explicit MiniLM retains legacy -8.",
    )
    parser.add_argument("--reader-dir", type=Path)
    parser.add_argument("--reader-threshold", type=float)
    parser.add_argument(
        "--answer-support",
        choices=("disabled", "local_nli"),
        help=(
            "Reader serving defaults to local_nli; "
            "disabled is an explicit legacy profile."
        ),
    )
    parser.add_argument("--support-dir", type=Path)
    parser.add_argument(
        "--support-margin",
        type=float,
        help=(
            "Default: measured reader-serving recipe2; legacy recipe4. "
            "Explicit values win."
        ),
    )
    parser.add_argument("--corpus-dir", type=Path)
    parser.add_argument("--frontend-origin", default="http://127.0.0.1:3505")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 <= args.refusal_threshold <= 1:
        parser.error("Choose a valid port and refusal threshold in [0, 1]")
    args.answer_selection = args.answer_selection or (
        "reader" if args.embedding == "local" else "lexical"
    )
    if args.answer_support is None:
        args.answer_support = (
            "local_nli"
            if args.action == "serve" and args.answer_selection == "reader"
            else "disabled"
        )
    resolve_launch_profile_defaults(args)
    if args.answer_support == "local_nli" and args.support_dir is None:
        args.support_dir = ROOT / ".tmp/models/support"
    validate_support_options(parser, args)
    # Resolve the repository's immutable catalog, without loading model code.
    sys.path.insert(0, str(ROOT / "apps/api"))
    from app.reader_catalog import MINILM, ROBERTA
    from app.support_catalog import NLI

    reader_spec = ROBERTA if args.reader_model == "roberta" else MINILM
    reader_dir = args.reader_dir or ROOT / ".tmp/models" / (
        "reader-roberta" if args.reader_model == "roberta" else "reader"
    )
    reader_threshold = args.reader_threshold
    if reader_threshold is None:
        reader_threshold = 4 if args.reader_model == "roberta" else -8
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(
            ("OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_API", "GEMINI_")
        ):
            del env[key]
    env.update(
        PYTHONPATH=str(ROOT / "apps/api"),
        DATABASE_URL="sqlite+aiosqlite:///" + (data / "groundtruth.sqlite").as_posix(),
        STORAGE_ROOT=str(data / "uploads"),
        EMBEDDING_MODE=args.embedding,
        EMBEDDING_DIMENSIONS="384",
        LOCAL_MODEL_PATH=str(args.model_dir.resolve()),
        ANSWER_SELECTION_MODE=args.answer_selection,
        ANSWER_PROPOSAL_PROFILE=args.answer_proposal_profile,
        ROLE_SCOPE_POLICY=args.role_scope_policy,
        PROCEDURE_VERIFICATION_PROFILE=args.procedure_verification_profile,
        SOURCE_CONTEXT_POLICY=args.source_context_policy,
        READER_MODEL_PATH=str(reader_dir.resolve()),
        READER_MODEL_REVISION=reader_spec.revision,
        READER_NULL_THRESHOLD=str(reader_threshold),
        ANSWER_SUPPORT_MODE=args.answer_support,
        SUPPORT_MODEL_PATH=str(args.support_dir.resolve())
        if args.answer_support == "local_nli" and args.support_dir is not None
        else "",
        SUPPORT_MODEL_REVISION=NLI.revision,
        SUPPORT_MIN_MARGIN=str(args.support_margin),
        GENERATION_MODE="extractive",
        OPENAI_API_KEY="",
        INGESTION_MODE="inline",
        AUTH_ENABLED="true",
        RATE_LIMIT_ENABLED="true",
        APP_ENV="development",
        CORS_ORIGINS=(
            "http://localhost:3505,http://127.0.0.1:3505," + args.frontend_origin
        ),
        CONNECTED_REFUSAL_THRESHOLD=str(args.refusal_threshold),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
    )
    if args.action == "migrate":
        command = [sys.executable, "-m", "app.db.migrate"]
    elif args.action == "serve":
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--no-access-log",
        ]
    else:
        command = [
            sys.executable,
            str(ROOT / "scripts/seed_portfolio.py"),
            "--api-url",
            f"http://127.0.0.1:{args.port}",
            "--manifest",
            str(data / "seed-manifest.json"),
            "--confirm-disposable-database",
        ]
        if args.corpus_dir is not None:
            command.extend(["--corpus-dir", str(args.corpus_dir.resolve())])
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
