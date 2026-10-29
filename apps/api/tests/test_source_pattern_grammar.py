"""Invented literal protocol fixtures; proposals have no support authority."""

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.source_pattern_proposals import (
    collect_source_proposals,
)

# Only the fresh child process in the pure-import test bypasses package startup.
# Collection/ordinary tests retain the canonical application package and exports.
SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"

NUMBERED = (
    "Larch transfer procedure. This complete procedure applies to ordinary "
    "Larch transfers. 1. Verify the approval before starting the Larch transfer. "
    "2. Copy the identifier onto the register. Do not reopen the register."
)
PROCEDURE_QUESTION = "Give the complete ordered method for ordinary Larch transfers."
ROLE_QUESTION = "Who leads Alder review?"
PARAGRAPH_QUESTION = (
    "Give the entire ordinary procedure for the Lumen token bench, including "
    "prerequisites, parameters, prohibitions, and closure."
)
PARAGRAPH_FIRST = (
    "Before beginning an ordinary token run, obtain the signed card "
    "and check that the tray is open."
)
PARAGRAPHS = (
    "Lumen token bench: current operation note\n\n"
    "The activity owner is the records clerk.\n\nComplete ordinary procedure\n\n"
    "The next four instruction paragraphs are the entire ordinary procedure, "
    "in the stated order. Its prerequisites, inspection, prohibited actions, "
    "and final reconciliation are part of completion. The procedure ends at "
    "the explicit End of ordinary procedure marker immediately after the "
    "fourth instruction paragraph. It applies to an ordinary unflagged run, "
    "not a postponed audit.\n\n"
    + PARAGRAPH_FIRST
    + "\n\nPlace one token in the tray, with the marked edge facing the label.\n\n"
    "Do not remove a marked token or close the tray before the count is recorded.\n\n"
    "Count both compartments, write both totals on the card, and close the tray.\n\n"
    "End of ordinary procedure\n\nRecord governance commentary\n\n"
    "The ordinary run is complete once the four preceding instruction paragraphs "
    "have been satisfied. The following commentary describes separate "
    "post-completion record governance, not an additional ordinary-run "
    "instruction or completion condition.\n\n"
    "After the final paragraph, the signed record is stored in the station folder. "
    "Storage does not grant a recorder authority to destroy it."
)


def source(body, *, offset=0, end=None, document="doc-1", metadata=None):
    end = len(body) if end is None else end
    identity = {
        "document_id": document,
        "document_version": 1,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }
    chunk = SimpleNamespace(
        id=f"chunk-{document}",
        document_id=document,
        content=body[offset:end],
        metadata=dict(identity),
    )
    return SimpleNamespace(
        body=body,
        chunks=(SimpleNamespace(chunk=chunk, start=offset, end=end),),
        identity=identity,
        metadata=metadata or {},
        captured_scope=None,
    )


def batch_record(batch):
    return {
        "complete": batch.complete,
        "proposals": [p.record() for p in batch.proposals],
        "observations": list(batch.observations),
    }


# A wrong local/document offset or changed ID derivation breaks literal lineage.
@pytest.mark.parametrize(
    "question,body,expected,pattern",
    [
        (
            ROLE_QUESTION,
            "The archivist leads Alder review.",
            "The archivist",
            "literal-lead-deputy-v1",
        ),
        (
            PROCEDURE_QUESTION,
            NUMBERED,
            "Verify the approval before starting the Larch transfer.",
            "complete-numbered-procedure-v1",
        ),
        (
            "What are the steps for Larch seal review?",
            "Larch seal review: inspect the seal, record the result, and close "
            "the review. Never reopen the review.",
            "Larch seal review: inspect the seal, record the result, and close "
            "the review. Never reopen the review.",
            "complete-narrative-procedure-v1",
        ),
        (
            PARAGRAPH_QUESTION,
            PARAGRAPHS,
            PARAGRAPH_FIRST,
            "complete-declared-paragraph-procedure-v1",
        ),
    ],
)
def test_literal_patterns_keep_raw_source_and_registry(
    question, body, expected, pattern
):
    batch = collect_source_proposals(plan_requirements(question)[0], [source(body)])
    assert batch.complete and len(batch.proposals) == 1
    proposal = batch.proposals[0]
    assert proposal.text == expected
    assert body[proposal.document_start : proposal.document_end] == expected
    assert proposal.pattern_id == pattern
    assert proposal.origin == "source_pattern" and proposal.qa_observation_id is None
    assert proposal.grammar_version == "typed-source-patterns-v1"


# The pure public seam must reproduce runtime discovery, not return no candidates.
def test_pure_entry_reconstructs_existing_literal_pattern():
    from app.services import source_pattern_grammar as module

    req = plan_requirements(ROLE_QUESTION)[0]
    actual = module.collect_source_proposals(
        req, [source("The archivist leads Alder review.")]
    )
    expected = collect_source_proposals(
        req, [source("The archivist leads Alder review.")]
    )
    assert batch_record(actual) == batch_record(expected)


def test_public_aliases_keep_shared_types_and_discovery_authority():
    from app.services import procedure_discovery as pure
    from app.services import procedure_evidence as runtime
    from app.services import procedure_support as support
    from app.services import source_pattern_grammar as grammar
    from app.services import source_pattern_proposals as wrapper

    assert runtime.ProcedureRejected is pure.ProcedureRejected
    assert runtime.ProcedureSource is pure.ProcedureSource
    assert runtime.LocatedChunk is pure.LocatedChunk
    assert runtime.ProcedureExtent is pure.ProcedureExtent
    assert runtime.discover_procedure_candidates is pure.discover_procedure_candidates
    assert support.discover_plan is pure.discover_plan
    assert support.build_plan is pure.build_plan
    assert support.ProcedurePlan is pure.ProcedurePlan
    assert support.ProofUnit is pure.ProofUnit
    assert wrapper.PatternBatch is grammar.PatternBatch


def test_nonzero_unicode_chunk_offset_keeps_exact_ids_and_ranges():
    item = source("ß🙂. The archivist leads Alder review.", offset=4)
    batch = collect_source_proposals(plan_requirements(ROLE_QUESTION)[0], [item])
    assert batch.complete and len(batch.proposals) == 1
    proposal = batch.proposals[0]
    assert (proposal.chunk_start, proposal.chunk_end) == (0, 13)
    assert (proposal.document_start, proposal.document_end) == (4, 17)
    assert proposal.proposal_id == (
        "488c2255d9b91cdc1a2e12f3148d075c8d761f95ec4670bdaa2cfd71c8950fe3"
    )


def test_numbered_seed_must_fit_one_actual_chunk():
    item = source(NUMBERED, offset=NUMBERED.index("2. Copy"))
    result = collect_source_proposals(plan_requirements(PROCEDURE_QUESTION)[0], [item])
    assert not result.complete and not result.proposals
    assert (
        result.observations[0]["decision"] == "procedure_pattern_seed_unrepresentable"
    )


@pytest.mark.parametrize(
    "mutation",
    ["hash", "version", "offset", "chunk_text", "chunk_hash", "chunk_version"],
)
def test_invalid_immutable_mapping_refuses(mutation):
    item = source("The archivist leads Alder review.")
    if mutation == "hash":
        item.identity["content_hash"] = "0" * 64
    elif mutation == "version":
        item.identity["document_version"] = True
    elif mutation == "offset":
        item.chunks[0].start = True
    elif mutation == "chunk_text":
        item.chunks[0].chunk.content = "forged"
    elif mutation == "chunk_hash":
        item.chunks[0].chunk.metadata["content_hash"] = "0" * 64
    else:
        item.chunks[0].chunk.metadata["document_version"] = 2
    result = collect_source_proposals(plan_requirements(ROLE_QUESTION)[0], [item])
    assert not result.complete and not result.proposals
    assert result.observations[0]["decision"].startswith("proposal_source_")


def test_source_order_identity_dedup_and_source_budget():
    req = plan_requirements(ROLE_QUESTION)[0]
    one = source("The archivist leads Alder review.")
    two = source("The clerk leads Alder review.", document="doc-2")
    result = collect_source_proposals(req, [one, one, two])
    assert [p.document_id for p in result.proposals] == ["doc-1", "doc-2"]
    overflow = source(
        " ".join(
            f"The {actor} leads Alder review."
            for actor in (
                "archivist",
                "records clerk",
                "desk steward",
                "dispatch clerk",
            )
        )
    )
    result = collect_source_proposals(req, [one, overflow])
    assert not result.complete and not result.proposals
    assert result.observations[-1]["decision"] == "pattern_source_budget_exceeded"
    assert result.observations[-1]["observed_count"] == 4


def test_requirement_budget_preserves_refusal_observation():
    req = plan_requirements(ROLE_QUESTION)[0]
    items = [
        source(f"The clerk leads Alder review. Record {i}.", document=f"d-{i}")
        for i in range(17)
    ]
    result = collect_source_proposals(req, items)
    assert not result.complete and not result.proposals
    assert result.observations[-1] == {
        "requirement_id": req.id,
        "origin": "source_pattern",
        "decision": "pattern_requirement_budget_exceeded",
        "observed_count": 17,
        "complete": False,
        "truncated": True,
    }


def test_procedure_condition_remains_discovery_guard():
    req = plan_requirements(PROCEDURE_QUESTION)[0]
    result = collect_source_proposals(
        req, [source(NUMBERED, metadata={"condition": "special Larch transfers"})]
    )
    assert not result.complete and not result.proposals
    assert (
        result.observations[0]["decision"]
        == "procedure_source_condition_not_established"
    )


def test_unknown_kind_has_no_new_pattern_alias():
    req = replace(plan_requirements(ROLE_QUESTION)[0], kind="duration")
    result = collect_source_proposals(req, [source("Alder review lasts 12 minutes.")])
    assert result.complete and not result.proposals and not result.observations


# Direct helper loading must not pull SQL/model/runtime modules, even during use.
def test_direct_pure_import_and_execution_blocks_runtime_dependencies():
    script = r"""
import importlib.abc, pathlib, sys, types, json
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ('app.db', 'app.models', 'app.config',
                   'app.services.procedure_evidence',
                   'app.services.procedure_support', 'app.services.answer_support')
        if (fullname.split('.')[0] in {'sqlalchemy', 'torch', 'transformers',
                                      'pydantic'} or fullname.startswith(blocked)):
            raise AssertionError('runtime import: ' + fullname)
sys.meta_path.insert(0, Guard())
services = pathlib.Path(sys.argv[1])
for name, directory in [('app', services.parent), ('app.services', services)]:
    package = types.ModuleType(name)
    package.__path__ = [str(directory)]
    sys.modules[name] = package
from app.services.source_pattern_grammar import collect_source_proposals
from app.services.answer_requirements import plan_requirements
import hashlib
from types import SimpleNamespace as S
for question, body, pattern in json.loads(sys.argv[2]):
    identity = dict(document_id='doc-1', document_version=1,
                    content_hash=hashlib.sha256(body.encode()).hexdigest())
    chunk = S(id='chunk-doc-1', document_id='doc-1', content=body, metadata=identity)
    source = S(body=body, identity=identity, metadata={}, captured_scope=None,
               chunks=(S(chunk=chunk,start=0,end=len(body)),))
    result = collect_source_proposals(plan_requirements(question)[0], [source])
    assert result.complete and len(result.proposals) == 1
    assert result.proposals[0].pattern_id == pattern
print('four pure pattern families')
"""
    cases = [
        (ROLE_QUESTION, "The archivist leads Alder review.", "literal-lead-deputy-v1"),
        (PROCEDURE_QUESTION, NUMBERED, "complete-numbered-procedure-v1"),
        (
            "What are the steps for Larch seal review?",
            "Larch seal review: inspect the seal, record the result, and close "
            "the review. Never reopen the review.",
            "complete-narrative-procedure-v1",
        ),
        (PARAGRAPH_QUESTION, PARAGRAPHS, "complete-declared-paragraph-procedure-v1"),
    ]
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(SERVICES), json.dumps(cases)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "four pure pattern families"
