"""Run the credential-free portable profile with an explicit local data directory.

This profile uses SQLite, inline ingestion and extractive answers. Local semantic
embeddings require the separately downloaded pinned model; deterministic embeddings
are an explicitly selected alternative. Neither mode contacts a provider.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
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
        "--reader-model",
        choices=("minilm", "roberta"),
        default="roberta",
        help="Connected candidate: RoBERTa4; explicit MiniLM retains legacy -8.",
    )
    parser.add_argument("--reader-dir", type=Path)
    parser.add_argument("--reader-threshold", type=float)
    parser.add_argument("--corpus-dir", type=Path)
    parser.add_argument("--frontend-origin", default="http://127.0.0.1:3505")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 <= args.refusal_threshold <= 1:
        parser.error("Choose a valid port and refusal threshold in [0, 1]")
    # Resolve the repository's immutable catalog, without loading model code.
    sys.path.insert(0, str(ROOT / "apps/api"))
    from app.reader_catalog import MINILM, ROBERTA

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
        ANSWER_SELECTION_MODE=args.answer_selection
        or ("reader" if args.embedding == "local" else "lexical"),
        READER_MODEL_PATH=str(reader_dir.resolve()),
        READER_MODEL_REVISION=reader_spec.revision,
        READER_NULL_THRESHOLD=str(reader_threshold),
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
