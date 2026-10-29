"""Immutable, approved local extractive readers; importing never uses the network."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReaderSpec:
    model: str
    revision: str
    files: tuple[str, ...]
    license: str


MINILM = ReaderSpec(
    model="deepset/minilm-uncased-squad2",
    revision="934656cdda79824eabf503ed56e15c01ddbdbe3f",
    files=(
        "config.json",
        "model.safetensors",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.txt",
    ),
    license="CC-BY-4.0",
)
ROBERTA = ReaderSpec(
    model="deepset/roberta-base-squad2",
    revision="adc3b06f79f797d1c575d5479d6f5efe54a9e3b4",
    files=(
        "config.json",
        "model.safetensors",
        "merges.txt",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    ),
    license="CC-BY-4.0",
)


def get_reader_spec(revision: str) -> ReaderSpec:
    """Resolve an exact approved commit, never an alias or fallback."""
    for spec in (MINILM, ROBERTA):
        if revision == spec.revision:
            return spec
    raise ValueError(f"Unknown reader revision: {revision!r}")
