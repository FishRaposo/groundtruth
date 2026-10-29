"""Exercise the actual candidate gate, before the external NLI boundary."""

import uuid

from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_requirements import plan_requirements
from app.services.requirement_answers import _eligible_candidates


def test_configured_contextual_reader_reaches_the_strict_pending_support_gate():
    text = (
        "The Copper cipher wheel uses a 26-letter alphabet. "
        "The alignment check lasts 7 minutes."
    )
    chunk = ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=text,
        chunk_index=0,
        relevance_score=1,
        metadata={"document_version": 1, "workspace_id": "test"},
    )
    start = text.index("7 minutes")
    prediction = ReaderSelection(
        passage_span(text, start, start + 9),
        {
            "raw_span": {"start": start, "end": start + 9, "text": "7 minutes"},
            "null_margin": -5,
        },
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v1",
    )
    req = plan_requirements(
        "How long is the Copper alignment check?",
        reading_profile="contextual_source_v1",
    )[0]
    diagnostics = []
    pending = _eligible_candidates(req, [chunk], [prediction], config, diagnostics)
    assert len(pending) == 1
    assert diagnostics[-1]["decision"] == "support_pending"
    assert diagnostics[-1]["hypothesis"] == "the Copper alignment check lasts 7 minutes"
    # No model outcome or successful publication can be fabricated at this seam.
    assert "support" not in diagnostics[-1]
