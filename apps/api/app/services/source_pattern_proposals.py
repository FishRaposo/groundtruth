"""Runtime-compatible source-pattern facade over the shared pure grammar.

The source resolver owns authorization/current immutable context. This adapter
preserves the canonical source body, mappings, metadata and captured scope;
the pure registry performs the unchanged source/context/budget validation.
"""

from app.services.procedure_discovery import LocatedChunk, ProcedureSource
from app.services.source_pattern_grammar import (
    ENVELOPE_PATTERN as ENVELOPE_PATTERN,
)
from app.services.source_pattern_grammar import (
    NARRATIVE_PATTERN as NARRATIVE_PATTERN,
)
from app.services.source_pattern_grammar import (
    NUMBERED_PATTERN as NUMBERED_PATTERN,
)
from app.services.source_pattern_grammar import (
    PARAGRAPH_PATTERN as PARAGRAPH_PATTERN,
)
from app.services.source_pattern_grammar import (
    PATTERN_IDS as PATTERN_IDS,
)
from app.services.source_pattern_grammar import (
    ROLE_PATTERN as ROLE_PATTERN,
)
from app.services.source_pattern_grammar import (
    PatternBatch as PatternBatch,
)
from app.services.source_pattern_grammar import (
    collect_source_proposals as _collect,
)
from app.services.source_pattern_grammar import pattern_ids as pattern_ids


def collect_source_proposals(
    requirement, sources, *, reading_profile="clause_bound_v1"
) -> PatternBatch:
    return _collect(
        requirement,
        (
            ProcedureSource(
                source.body,
                tuple(
                    LocatedChunk(item.chunk, item.start, item.end)
                    for item in source.chunks
                ),
                source.identity,
                source.metadata,
                source.captured_scope,
            )
            for source in sources
        ),
        reading_profile=reading_profile,
    )
