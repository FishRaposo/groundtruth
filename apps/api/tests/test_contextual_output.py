"""UNITONLY synthetic protocol certificates: no inference or API success doubles."""

import hashlib
import importlib
import json
import subprocess
import sys
import types
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

# Bypass the legacy package's eager runtime initialization, load actual modules.
if "app.services" not in sys.modules:
    namespace = types.ModuleType("app.services")
    namespace.__path__ = [str(Path(__file__).parents[1] / "app/services")]
    sys.modules["app.services"] = namespace
from app.evidence_policy import EvidencePolicy, reading_version
from app.reader_catalog import ROBERTA
from app.services.answer_requirements import plan_requirements
from app.services.evidence_proposals import QAObservation, make_proposal
from app.services.procedure_output import render_extractive
from app.services.requirement_binding import support_claim
from app.support_catalog import NLI

output = importlib.import_module("app.services.contextual_output")

QUESTION = "How long is the Copper check?"
BODY = "The Copper check lasts 7 minutes."


def fixture(question=QUESTION, bodies=(BODY,), values=("7 minutes",)):
    """Manufactured wire records, UNITONLY; scores are never model observations."""
    profile = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v1",
    ).record()
    selection = {
        "contract": reading_version("contextual_source_v1").requirement,
        "evidence_profile": profile,
        "mode": "reader",
        "reader_contract": "reader-parts-v14",
        "model": ROBERTA.model,
        "revision": ROBERTA.revision,
        "threshold": 4.0,
        "max_length": 512,
        "stride": 64,
        "n_best": 10,
        "max_span_tokens": 64,
        "evidence_support": {
            "mode": "local_nli",
            "model": NLI.model,
            "revision": NLI.revision,
            "license": NLI.license,
            "minimum_entailment_margin": 2.0,
            "max_pair_tokens": 512,
            "batch_size": 8,
            "device": "cpu",
            "score_semantics": (
                "raw contradiction/entailment/neutral logits; uncalibrated"
            ),
        },
        "decision": "answer",
        "requirements": [],
        "candidates": [],
        "inspected_sources": [],
        "proposals": [],
        "qa_observations": [],
        "selected_proposal_ids": [],
        "conflicts": [],
        "procedure_contexts": [],
        "role_scope_interpretations": [],
        "role_scope_findings": [],
    }
    snapshots = {}
    citations = []
    requirements = plan_requirements(question, reading_profile="contextual_source_v1")
    for i, (req, body, value) in enumerate(
        zip(requirements, bodies, values, strict=True), 1
    ):
        doc = f"00000000-0000-0000-0000-{i:012d}"
        chunk = f"10000000-0000-0000-0000-{i:012d}"
        digest = hashlib.sha256(body.encode()).hexdigest()
        identity = {"document_id": doc, "document_version": 3, "content_hash": digest}
        member = dict(chunk_id=chunk, **identity)
        snapshots[doc] = dict(
            **identity,
            workspace_id=None,
            body=body,
            chunks=[{"id": chunk, "index": 0, "content": body}],
            metadata={},
        )
        start = body.index(value)
        end = start + len(value)
        raw = {"start": start, "end": end, "text": value, "null_margin": -3.0}
        reader = {
            "mode": "reader",
            "contract": "reader-parts-v14",
            "model": ROBERTA.model,
            "revision": ROBERTA.revision,
            "threshold": 4.0,
        }
        payload = json.dumps(
            {
                "span": {"start": start, "end": end, "text": value},
                "diagnostics": {"raw_candidates": [raw]},
                "question": req.question,
                "reader": reader,
            },
            sort_keys=True,
            allow_nan=False,
        )
        oid = hashlib.sha256(f"{req.id}:{chunk}:{payload}".encode()).hexdigest()
        observed = QAObservation(oid, req.id, chunk, payload)
        actual_chunk = SimpleNamespace(
            id=chunk, document_id=doc, content=body, metadata=identity
        )
        source = SimpleNamespace(
            body=body,
            identity=identity,
            chunks=[SimpleNamespace(chunk=actual_chunk, start=0, end=len(body))],
        )
        proposal = make_proposal(
            req.id,
            source,
            actual_chunk,
            start,
            end,
            origin="qa_reader",
            observation=observed,
        ).record()
        claim = support_claim(
            req, body, start, end, reading_profile="contextual_source_v1"
        )
        assert claim.rejection is None and not claim.proof_edges
        left, right = claim.support_start, claim.support_end
        span = {"start": left, "end": right, "text": body[left:right]}
        assessment = {
            "label": "entailment",
            "logits": [-1.0, 5.0, 0.0],
            "entailment_margin": 5.0,
            "supported": True,
            "pair_tokens": 28,
        }
        witness = dict(
            **member,
            value=claim.value,
            span=span,
            entailment_margin=5.0,
            proof_edges=[],
            proposals=[proposal],
            document_range={"start": left, "end": right},
        )
        row = {
            "id": req.id,
            "kind": req.kind,
            "original_text": req.original_text,
            "input_range": {"start": req.input_start, "end": req.input_end},
            "prepared_question": req.question,
            "source_workspace": req.source_workspace,
            "depends_on": list(req.depends_on),
            "status": "supported",
            "witnesses": [witness],
        }
        diagnostic = dict(
            **member,
            requirement_id=req.id,
            raw_span={"start": start, "end": end},
            null_margin=-3.0,
            hypothesis=claim.hypothesis,
            validated_answer_span={
                "start": claim.start,
                "end": claim.end,
                "text": claim.value,
            },
            condition="applies",
            decision="supported",
            primary_support_range={
                "start": claim.premise_start,
                "end": claim.premise_end,
            },
            proof_edges=[],
            support=assessment,
            support_checks=[],
            proposal=proposal,
            origin="qa_reader",
        )
        selection["requirements"].append(row)
        selection["candidates"].append(diagnostic)
        selection["inspected_sources"].append(member)
        selection["proposals"].append(proposal)
        selection["qa_observations"].append(observed.record())
        selection["selected_proposal_ids"].append(proposal["proposal_id"])
        citations.append(
            dict(citation_index=i, **member, quoted_text=body, answer_spans=[span])
        )
    selection["procedure_read_set"] = {
        "contract": "procedure-inspection-read-set-v1",
        "document_ids": None,
        "collection_ids": None,
        "sources": [
            {
                **member,
                "workspace_id": snapshots[member["document_id"]]["workspace_id"],
                "condition": None,
                "conflict_group": None,
                "chunk_hash": hashlib.sha256(
                    snapshots[member["document_id"]]["body"].encode()
                ).hexdigest(),
            }
            for member in sorted(
                selection["inspected_sources"], key=lambda s: s["chunk_id"]
            )
        ],
        "groups": [],
        "after_proofs": {
            "consistent": True,
            "reason": None,
            "changed_source_ids": [],
            "changed_groups": [],
        },
    }
    answer = render_extractive(citations)[0]
    return {
        "selection": selection,
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_snapshots": snapshots,
        "query_context": {"provenance": {"answer_selection": deepcopy(selection)}},
    }


def call(f):
    data = dict(f)
    selection = data.pop("selection")
    return output.reconstruct_certificate(selection, **data)


def mirror(f):
    f["query_context"]["provenance"]["answer_selection"] = deepcopy(f["selection"])


def test_reconstructs_factual_source_answer_and_bindings():
    # Missing replay or trusting an answer hash instead of actual source fails here.
    f = fixture()
    certificate = call(f)
    assert isinstance(certificate, dict), (
        "The actual factual output certificate is missing"
    )
    assert certificate["contract"] == reading_version("contextual_source_v1").output
    assert certificate["renderer"] == "extractive-answer-v1"
    assert (
        certificate["question_sha256"] == hashlib.sha256(QUESTION.encode()).hexdigest()
    )
    assert (
        certificate["answer_sha256"] == hashlib.sha256(f["answer"].encode()).hexdigest()
    )
    assert certificate["selected_fragments"][0]["text"] == BODY
    assert (
        certificate["request_plan"][0]["prepared_question"]
        == "For Copper check, How long is the Copper check?"
    )
    assert (
        f["answer"] == "Source extracts (not model-generated):\n\n"
        "The Copper check lasts 7 minutes. [1]"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.update(answer="7 minutes [1]"),
        lambda f: f.update(answer=f["answer"] + " Extra unsupported prose."),
        lambda f: f["citations"].clear(),
        lambda f: f["citations"][0].update(citation_index=2),
        lambda f: f["citations"][0]["answer_spans"][0].update(start=True),
        lambda f: f["citations"][0].update(
            quoted_text="The Copper check lasts 99 minutes."
        ),
        lambda f: next(iter(f["source_snapshots"].values())).update(
            body="The Copper check lasts 99 minutes."
        ),
        lambda f: next(iter(f["source_snapshots"].values())).update(document_version=4),
        lambda f: next(iter(f["source_snapshots"].values())).update(
            content_hash="0" * 64
        ),
        lambda f: f["citations"][0].update(document_version=4),
        lambda f: f["citations"][0].update(content_hash="0" * 64),
        lambda f: f.update(question=QUESTION + " What unexplained extra is needed?"),
        lambda f: f.update(query_context={}),
        lambda f: f["query_context"]["provenance"]["answer_selection"]["candidates"][
            0
        ].update(hypothesis="Different retained input"),
    ],
)
def test_rejects_changed_actual_output_source_request_or_retained_capture(mutate):
    f = fixture()
    mutate(f)
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["requirements"][0]["input_range"].update(end=1),
        lambda s: s["requirements"][0].update(prepared_question="How long?"),
        lambda s: s["requirements"].clear(),
        lambda s: s["candidates"][0].update(
            hypothesis="The Copper check lasts 99 minutes"
        ),
        lambda s: s["candidates"][0]["raw_span"].update(start=0),
        lambda s: s["candidates"][0]["validated_answer_span"].update(text="99 minutes"),
        lambda s: s["candidates"][0]["primary_support_range"].update(start=1),
        lambda s: s["candidates"][0]["support"].update(logits=[0.0, 0.0, 0.0]),
        lambda s: s["candidates"][0]["support"].update(logits=[-1.0, 5.0]),
        lambda s: s["candidates"][0]["support"].update(label="neutral"),
        lambda s: s["candidates"][0]["support"].update(entailment_margin=99.0),
        lambda s: s["candidates"][0]["support"].update(pair_tokens=True),
        lambda s: s["candidates"][0]["support"].update(supported=False),
        lambda s: s["candidates"][0].update(support_checks=[{"name": "producer_only"}]),
        lambda s: s["evidence_support"].update(model="unapproved"),
        lambda s: s["evidence_support"].update(minimum_entailment_margin=4.1),
        lambda s: s.update(revision="floating-main"),
        lambda s: s.update(max_length=True),
        lambda s: s["proposals"][0]["chunk_range"].update(start=0),
        lambda s: s["proposals"][0]["document_range"].update(start=0),
        lambda s: s["selected_proposal_ids"].clear(),
        lambda s: s["selected_proposal_ids"].append("invented-id"),
        lambda s: s["qa_observations"][0].update(question="Different model input?"),
        lambda s: s["qa_observations"][0]["reader"].update(revision="unapproved"),
        lambda s: s["qa_observations"][0]["diagnostics"]["raw_candidates"][0].update(
            null_margin=5.0
        ),
    ],
)
def test_self_consistent_producer_and_trace_tampering_cannot_replace_reconstruction(
    mutate,
):
    f = fixture()
    mutate(f["selection"])
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


def test_certification_is_staged_and_saved_certificate_is_reconstructed():
    f = fixture()
    args = {k: v for k, v in f.items() if k != "selection"}
    assert output.verify_output(f["selection"], **args) is False
    output.certify_output(f["selection"], **args)
    assert output.verify_output(f["selection"], **args) is True
    f["selection"]["contextual_output_certificate"]["answer_sha256"] = "0" * 64
    assert output.verify_output(f["selection"], **args) is False


def test_every_requested_fact_and_citation_order_is_bound():
    f = fixture(
        "How long is the Copper check? How many tokens are in the Copper kit?",
        (BODY, "The Copper kit contains 3 tokens."),
        ("7 minutes", "3"),
    )
    certificate = call(f)
    assert len(certificate["request_plan"]) == 2
    assert len(certificate["selected_fragments"]) == 2
    f["citations"].reverse()
    with pytest.raises(ValueError):
        call(f)


def test_certificate_maps_fragments_to_actual_answer_codepoints():
    f = fixture()
    certificate = call(f)
    fragment = certificate["selected_fragments"][0]
    interval = fragment.get("answer_range")
    assert isinstance(interval, dict), "Actual answer interval is missing"
    assert f["answer"][interval["start"] : interval["end"]] == BODY


def test_unit_fixture_and_verifier_do_not_initialize_database_or_models():
    # Other test modules may already initialize runtime packages in their own
    # process. Check the pure seam in a fresh interpreter rather than depend on
    # suite order or erase any of those real imports.
    script = (
        "import runpy, sys; "
        f"t = runpy.run_path({str(Path(__file__).resolve())!r}); "
        "t['call'](t['fixture']()); "
        "assert 'app.db.session' not in sys.modules; "
        "assert 'torch' not in sys.modules and 'transformers' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "kind_question",
    [
        "Who is the lead for the Copper check?",
        "List the full Copper check routine.",
        "What unexplained information is needed?",
    ],
)
def test_matching_producer_shape_cannot_enable_unsupported_request_kinds(kind_question):
    f = fixture()
    req = plan_requirements(kind_question, reading_profile="contextual_source_v1")[0]
    f["question"] = kind_question
    f["selection"]["requirements"][0].update(
        id=req.id,
        kind=req.kind,
        original_text=req.original_text,
        input_range={"start": req.input_start, "end": req.input_end},
        prepared_question=req.question,
        source_workspace=req.source_workspace,
        depends_on=list(req.depends_on),
    )
    mirror(f)
    with pytest.raises(ValueError, match="Unsupported request kind"):
        call(f)


def test_certificate_does_not_alias_original_producer_evidence():
    f = fixture()
    before = deepcopy(f["selection"])
    certificate = call(f)
    certificate["model_settings"]["evidence_profile"]["contract"] = "tampered-copy"
    certificate["selected_fragments"][0]["raw_range"]["start"] = 0
    assert f["selection"] == before, (
        "Certificate edits mutated the original model/source evidence"
    )


def test_renumbered_reordered_citations_and_answer_cannot_change_canonical_order():
    f = fixture(
        "How long is the Copper check? How many tokens are in the Copper kit?",
        (BODY, "The Copper kit contains 3 tokens."),
        ("7 minutes", "3"),
    )
    f["citations"].reverse()
    for i, citation in enumerate(f["citations"], 1):
        citation["citation_index"] = i
    f["answer"] = render_extractive(f["citations"])[0]
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize(
    "key,recorded,observed",
    [
        ("threshold", 1, True),
        ("threshold", 1, 1.0),
        ("threshold", 1.0, 1),
        ("max_length", 512, 512.0),
        ("stride", 64, 64.0),
        ("n_best", 10, 10.0),
        ("max_span_tokens", 64, 64.0),
    ],
)
def test_reidentified_qa_reader_settings_preserve_exact_recorded_types(
    key, recorded, observed
):
    # A coherent QA/proposal re-ID and mirrored trace must not exploit Python's
    # bool/int/float equality to substitute a different actual model setting.
    f = fixture()
    selection = f["selection"]
    selection[key] = recorded
    record = selection["qa_observations"][0]
    record["reader"][key] = observed
    payload = json.dumps(
        {k: record[k] for k in ("span", "diagnostics", "question", "reader")},
        sort_keys=True,
        allow_nan=False,
    )
    oid = hashlib.sha256(f"r1:{record['chunk_id']}:{payload}".encode()).hexdigest()
    record["observation_id"] = oid
    observation = QAObservation(oid, "r1", record["chunk_id"], payload)
    proposal = selection["proposals"][0]
    snapshot = next(iter(f["source_snapshots"].values()))
    identity = {
        k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
    }
    chunk = SimpleNamespace(
        id=proposal["chunk_id"],
        document_id=proposal["document_id"],
        content=snapshot["body"],
        metadata=identity,
    )
    source = SimpleNamespace(
        body=snapshot["body"],
        identity=identity,
        chunks=[SimpleNamespace(chunk=chunk, start=0, end=len(snapshot["body"]))],
    )
    expected = make_proposal(
        "r1",
        source,
        chunk,
        proposal["chunk_range"]["start"],
        proposal["chunk_range"]["end"],
        origin="qa_reader",
        observation=observation,
    ).record()
    proposal.clear()
    proposal.update(expected)
    selection["selected_proposal_ids"] = [expected["proposal_id"]]
    mirror(f)
    with pytest.raises(ValueError, match="QA.*settings|reader.*identity"):
        call(f)


def reidentify_first_qa_record(f):
    """Re-ID UNITONLY protocol mutations without bypassing source/proposal helpers."""
    selection = f["selection"]
    record = selection["qa_observations"][0]
    payload = json.dumps(
        {k: record[k] for k in ("span", "diagnostics", "question", "reader")},
        sort_keys=True,
        allow_nan=False,
    )
    oid = hashlib.sha256(
        f"{record['requirement_id']}:{record['chunk_id']}:{payload}".encode()
    ).hexdigest()
    record["observation_id"] = oid
    observation = QAObservation(
        oid, record["requirement_id"], record["chunk_id"], payload
    )
    proposal = selection["proposals"][0]
    snapshot = f["source_snapshots"][proposal["document_id"]]
    identity = {
        k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
    }
    chunk = SimpleNamespace(
        id=proposal["chunk_id"],
        document_id=proposal["document_id"],
        content=snapshot["body"],
        metadata=identity,
    )
    source = SimpleNamespace(
        body=snapshot["body"],
        identity=identity,
        chunks=[SimpleNamespace(chunk=chunk, start=0, end=len(snapshot["body"]))],
    )
    expected = make_proposal(
        record["requirement_id"],
        source,
        chunk,
        proposal["chunk_range"]["start"],
        proposal["chunk_range"]["end"],
        origin="qa_reader",
        observation=observation,
    ).record()
    proposal.clear()
    proposal.update(expected)
    selection["selected_proposal_ids"] = [expected["proposal_id"]]
    mirror(f)


@pytest.mark.parametrize("field", ["start", "end"])
def test_coherently_reidentified_raw_qa_offsets_must_be_exact_integers(field):
    f = fixture()
    raw = f["selection"]["qa_observations"][0]["diagnostics"]["raw_candidates"][0]
    raw[field] = float(raw[field])
    reidentify_first_qa_record(f)
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize(
    "span",
    [
        {"start": True, "end": 0.0, "text": "forged non-source span"},
        {"start": 0, "end": 4, "text": "fake"},
        {"start": 0, "end": 9999, "text": "outside"},
    ],
)
def test_coherently_reidentified_observation_span_is_canonical_source_literal(span):
    f = fixture()
    f["selection"]["qa_observations"][0]["span"] = span
    reidentify_first_qa_record(f)
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize("field", ["batch_size", "max_pair_tokens"])
def test_recorded_nli_fixed_setting_types_match_pure_catalogue(field):
    f = fixture()
    support = f["selection"]["evidence_support"]
    support[field] = float(support[field])
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize("context", [False, None, {}, 0, ""])
def test_explicit_conflicts_context_must_be_a_list(context):
    f = fixture()
    f["selection"]["conflicts"] = context
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


def two_supported_facts(second_value, *, retain_witness=True, quantity=False):
    question = "How many tokens are in the Copper kit?" if quantity else QUESTION
    first = "3" if quantity else "7 minutes"
    body = (
        f"The Copper kit contains {first} tokens. "
        f"The Copper kit contains {second_value} tokens."
        if quantity
        else f"The Copper check lasts {first}. The Copper check lasts {second_value}."
    )
    f = fixture(question, (body,), (first,))
    other = fixture(question, (body,), (second_value,))
    if retain_witness:
        f["selection"]["requirements"][0]["witnesses"].extend(
            other["selection"]["requirements"][0]["witnesses"]
        )
    for key in ("proposals", "qa_observations", "candidates"):
        f["selection"][key].extend(other["selection"][key])
    mirror(f)
    return f


@pytest.mark.parametrize("retain_witness", [True, False])
def test_unselected_supported_opposing_value_cannot_be_removed_by_selection(
    retain_witness,
):
    f = two_supported_facts("99 minutes", retain_witness=retain_witness)
    with pytest.raises(ValueError, match="conflict|Conflicting"):
        call(f)


def test_equivalent_unselected_quantity_is_reconstructed_without_false_conflict():
    f = two_supported_facts("3.0", quantity=True)
    certificate = call(f)
    assert len(certificate.get("supported_fact_inventory", [])) == 2
    assert len(certificate["selected_fragments"]) == 1


def test_observed_expanded_best_span_may_differ_from_selected_raw_candidate():
    body = "The Copper check lasts 8 minutes. The Copper check lasts 7 minutes."
    f = fixture(bodies=(body,))
    record = f["selection"]["qa_observations"][0]
    record["span"] = {
        "start": 0,
        "end": len("The Copper check lasts 8 minutes."),
        "text": "The Copper check lasts 8 minutes.",
    }
    start = body.index("8 minutes")
    record["diagnostics"]["raw_candidates"].insert(
        0,
        {
            "start": start,
            "end": start + len("8 minutes"),
            "text": "8 minutes",
            "null_margin": -4.0,
        },
    )
    reidentify_first_qa_record(f)
    assert call(f)["selected_fragments"][0]["value"] == "7 minutes"


def test_retained_assessed_candidate_request_binding_cannot_hide_opposition():
    f = two_supported_facts("99 minutes", retain_witness=False)
    f["selection"]["candidates"][-1]["requirement_id"] = "r99"
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


def test_retained_numeric_support_cannot_be_hidden_by_a_refused_decision_flag():
    f = two_supported_facts("99 minutes", retain_witness=False)
    f["selection"]["candidates"][-1]["decision"] = "support_rejected"
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


@pytest.mark.parametrize(
    "checks",
    [
        None,
        False,
        {},
        [
            {
                "name": "invented unrelated veto",
                "hypothesis": "unrelated veto",
                "source_range": {"start": 0, "end": 1},
                "label": "neutral",
                "logits": [0.0, -1.0, 5.0],
                "entailment_margin": -6.0,
                "supported": False,
                "pair_tokens": 28,
            }
        ],
    ],
)
def test_rejected_candidate_cannot_hide_opposition_with_unreplayed_checks(checks):
    f = two_supported_facts("99 minutes", retain_witness=False)
    f["selection"]["candidates"][-1]["decision"] = "support_rejected"
    f["selection"]["candidates"][-1]["support_checks"] = checks
    mirror(f)
    with pytest.raises(ValueError):
        call(f)


def test_genuine_primary_neutral_candidate_is_validated_without_becoming_support():
    f = two_supported_facts("99 minutes", retain_witness=False)
    candidate = f["selection"]["candidates"][-1]
    candidate["decision"] = "support_rejected"
    candidate["support"] = {
        "label": "neutral",
        "logits": [0.0, -1.0, 5.0],
        "entailment_margin": -6.0,
        "supported": False,
        "pair_tokens": 28,
    }
    mirror(f)
    assert len(call(f)["supported_fact_inventory"]) == 1


def test_publication_annotation_preserves_the_staged_certificate():
    f = fixture()
    context = {k: v for k, v in f.items() if k != "selection"}
    output.certify_output(f["selection"], **context)
    check = deepcopy(f["selection"]["procedure_read_set"]["after_proofs"])
    f["selection"]["procedure_read_set"]["before_publication"] = check
    # The actual coordinator persists the same check in the retained trace.
    mirror(f)
    assert output.verify_output(f["selection"], **context)


@pytest.mark.parametrize(
    "change", ["missing", "sources", "workspace", "check", "typed"]
)
def test_factual_sql_read_set_is_required_and_reconstructed(change):
    f = fixture()
    read_set = f["selection"]["procedure_read_set"]
    if change == "missing":
        del f["selection"]["procedure_read_set"]
    elif change == "sources":
        read_set["sources"] = []
    elif change == "workspace":
        read_set["sources"][0]["workspace_id"] = "other"
    elif change == "check":
        read_set["after_proofs"]["consistent"] = False
    else:
        read_set["after_proofs"]["consistent"] = 1
    mirror(f)
    with pytest.raises(ValueError):
        call(f)
