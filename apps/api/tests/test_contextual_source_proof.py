"""UNITONLY NLI/source graphs; retained request graph is actual634 engineering."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.evidence_policy import reading_version  # noqa: E402
from app.services.contextual_source_proof import (  # noqa: E402
    SourceGuardError,
    SourceGuardRefusal,
    build_envelope,
    reconstruct_source_guard,
)
from app.services.linguistic_requirements import plan_request  # noqa: E402
from app.services.request_parser import _cover, _proposals, make_capture  # noqa: E402
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI  # noqa: E402

QUESTION = (
    "For Onyx calibration, give the full routine including all conditions "
    "and prohibitions."
)
HEADER = "This complete routine applies to Onyx calibration. "
HEADER_SPEC = [
    ("This", "DET", "det", 2, "this"),
    ("complete", "ADJ", "amod", 2, "complete"),
    ("routine", "NOUN", "nsubj", 3, "routine"),
    ("applies", "VERB", "ROOT", 3, "apply"),
    ("to", "ADP", "prep", 3, "to"),
    ("Onyx", "PROPN", "compound", 6, "Onyx"),
    ("calibration", "NOUN", "pobj", 4, "calibration"),
    (".", "PUNCT", "punct", 3, "."),
]
ACTION = "Frobnicate the token. "
ACTION_SPEC = [
    ("Frobnicate", "VERB", "ROOT", 0, "frobnicate"),
    ("the", "DET", "det", 2, "the"),
    ("token", "NOUN", "dobj", 0, "token"),
    (".", "PUNCT", "punct", 0, "."),
]


def unit_capture(raw, spec):
    tokens = []
    cursor = 0
    for i, (text, pos, dep, head, lemma) in enumerate(spec):
        start = raw.index(text, cursor)
        end = start + len(text)
        cursor = end
        tokens.append(
            {
                "i": i,
                "start": start,
                "end": end,
                "text": text,
                "whitespace": "",
                "pos": pos,
                "tag": "VB"
                if pos == "VERB"
                else "."
                if pos == "PUNCT"
                else "NNP"
                if pos == "PROPN"
                else "NN",
                "dep": dep,
                "head": head,
                "lemma": lemma,
                "morph": "",
                "sentence_start": i == 0,
                "children": [],
            }
        )
    for i, t in enumerate(tokens):
        right = tokens[i + 1]["start"] if i + 1 < len(tokens) else len(raw)
        t["whitespace"] = raw[t["end"] : right]
        t["children"] = [j for j, c in enumerate(tokens) if j != i and c["head"] == i]
    sentences = [
        {
            "start": 0,
            "end": tokens[-1]["end"],
            "text": raw[: tokens[-1]["end"]],
            "token_start": 0,
            "token_end": len(tokens),
        }
    ]
    return make_capture(
        {
            "raw_text": raw,
            "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "coordinate_system": "python-unicode-codepoints",
            "tokens": tokens,
            "sentences": sentences,
            "lossless_input_cover": _cover(raw, tokens),
            "linguistic_proposals": _proposals(tokens, sentences),
            "protected_token_indices": [
                t["i"]
                for t in tokens
                if t["dep"] in {"neg", "cc", "conj", "mark", "aux", "auxpass", "nummod"}
                or t["tag"] == "MD"
            ],
            "all_token_indices_retained": list(range(len(tokens))),
            "semantic_obligation_completeness": "NOT_ESTABLISHED",
            "support_or_permissions": "NOT_ASSESSED",
        }
    )


def fixture(extra=()):
    captures = json.loads(
        (Path(__file__).parent / "fixtures/dependency_graphs_v634.json").read_text(
            encoding="utf-8"
        )
    )["captures"]
    request = next(
        r["capture"]
        for r in captures
        if r["capture"]["annotation"]["raw_text"] == QUESTION
    )
    plan = plan_request(QUESTION, request)
    assert plan.resolved_request
    body = ""
    windows = []
    for raw, spec in [(HEADER, HEADER_SPEC), (ACTION, ACTION_SPEC), *extra]:
        start = len(body)
        body += raw
        windows.append(
            {"start": start, "end": len(body), "capture": unit_capture(raw, spec)}
        )
    identity = {
        "document_id": "source-unitonly639",
        "document_version": 2,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "workspace_id": "unitonly-workspace",
    }
    snapshot = {
        **identity,
        "body": body,
        "chunks": [{"id": "unitonly-chunk", "index": 0, "content": body}],
    }
    return body, identity, windows, plan, snapshot


def settings():
    return {
        "mode": "local_nli",
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "device": "cpu",
        "minimum_entailment_margin": 2,
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "batch_size": BATCH_SIZE,
        "score_semantics": "raw contradiction/entailment/neutral logits; uncalibrated",
    }


def selected(extra=()):
    body, identity, windows, plan, snapshot = fixture(extra)
    req = next(r for r in plan.requirements if r.kind == "procedure")
    inventory = build_envelope(body, identity, req.topic, plan, windows)
    assert isinstance(inventory, dict), "Whole source consumer envelope is missing"
    version = reading_version("contextual_source_v2")
    selection = {
        "contract": version.requirement,
        "evidence_profile": {
            "contract": version.evidence_profile,
            "evidence_reading_profile": version.profile,
            "procedure_contract": version.procedure,
        },
        "evidence_support": settings(),
        "source_guard_records": [
            {
                "requirement_id": req.id,
                "source_identity": identity,
                "requested_subject": req.topic,
                "source_windows": windows,
                "envelope_inventory": inventory,
                "nli_assessments": [
                    {
                        **obligation,
                        "assessment": {
                            "label": "entailment",
                            "logits": [-1.0, 5.0, 0.0],
                            "entailment_margin": 5.0,
                            "supported": True,
                            "pair_tokens": 80,
                        },
                    }
                    for obligation in inventory["nli_obligations"]
                ],
            }
        ],
    }
    return selection, req, snapshot, plan


def test_opaque_actions_get_complete_literal_envelope_and_full_body_nli():
    body, identity, windows, plan, _ = fixture()
    req = plan.requirements[0]
    result = build_envelope(body, identity, req.topic, plan, windows)
    assert isinstance(result, dict), "Whole source consumer envelope is missing"
    assert result["source_body"] == body
    assert result["envelope_range"] == {"start": 0, "end": len(body)}
    assert "".join(p["text"] for p in result["ordered_ranges"]) == body
    assert all(
        o["premise"] == body and o["source_range"] == {"start": 0, "end": len(body)}
        for o in result["nli_obligations"]
        if o["name"] in {"namespace", "applicability"}
    )
    assert all(u["coverage"] == "covered_verbatim" for u in result["covered_units"])
    applicability = next(
        o for o in result["nli_obligations"] if o["name"] == "applicability"
    )
    assert applicability["hypothesis"] == f"This routine applies to {req.topic}."
    namespace = next(o for o in result["nli_obligations"] if o["name"] == "namespace")
    assert namespace["hypothesis"] == f"This routine is for {req.topic}."
    assert result["requirement"]["original_text"] == req.original_text


def test_guard_replays_real_inputs_and_unitonly_nli_without_producer_success_flags():
    selection, req, snapshot, plan = selected()
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert isinstance(guard, dict), "Independent canonical consumer guard is missing"
    assert guard["status"] == "discharged" and guard["method"] == "consumer_envelope"
    assert (
        guard["envelope_inventory"]
        == selection["source_guard_records"][0]["envelope_inventory"]
    )
    assert guard["literal_scope"] == guard["envelope_inventory"]["literal_scope"]


@pytest.mark.parametrize("verb", ["Clamp", "Use"])
def test_physical_attachment_context_uses_bound_nli_instead_of_bare_word_rejection(
    verb,
):
    raw = f"{verb} the metal attachments beside the device. "
    spec = [
        (verb, "VERB", "ROOT", 0, verb.casefold()),
        ("the", "DET", "det", 3, "the"),
        ("metal", "ADJ", "amod", 3, "metal"),
        ("attachments", "NOUN", "dobj", 0, "attachment"),
        ("beside", "ADP", "prep", 0, "beside"),
        ("the", "DET", "det", 6, "the"),
        ("device", "NOUN", "pobj", 4, "device"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    selection, req, snapshot, plan = selected(((raw, spec),))
    inventory = selection["source_guard_records"][0]["envelope_inventory"]
    assert any(
        o["name"].startswith("reference_locality:") and raw.strip() in o["premise"]
        for o in inventory["nli_obligations"]
    )
    assert (
        reconstruct_source_guard(selection, req, snapshot, plan)["status"]
        == "discharged"
    )
    assert raw in inventory["source_body"]


@pytest.mark.parametrize(
    "raw,spec",
    [
        (
            "Consult Appendix Delta. ",
            [
                ("Consult", "VERB", "ROOT", 0, "consult"),
                ("Appendix", "NOUN", "dobj", 0, "appendix"),
                ("Delta", "PROPN", "compound", 1, "Delta"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
        (
            "Operate as prescribed elsewhere. ",
            [
                ("Operate", "VERB", "ROOT", 0, "operate"),
                ("as", "SCONJ", "mark", 2, "as"),
                ("prescribed", "VERB", "advcl", 0, "prescribe"),
                ("elsewhere", "ADV", "advmod", 2, "elsewhere"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
    ],
)
def test_required_external_directions_refuse_without_actual_copy_closure(raw, spec):
    body, identity, windows, plan, _ = fixture(((raw, spec),))
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "invented",
        "premise",
        "float_range",
        "margin",
        "bool_tokens",
        "extra_assessment",
        "physical_false",
    ],
)
def test_required_nli_inventory_is_canonical_before_acceptance(change):
    selection, req, snapshot, plan = selected()
    record = selection["source_guard_records"][0]
    assessments = record["nli_assessments"]
    if change == "missing":
        assessments.pop()
    elif change == "duplicate":
        assessments.append(deepcopy(assessments[0]))
    elif change == "invented":
        assessments[0]["name"] = "invented"
    elif change == "premise":
        assessments[0]["premise"] = HEADER
    elif change == "float_range":
        assessments[0]["source_range"]["start"] = 0.0
    elif change == "margin":
        assessments[1]["assessment"]["entailment_margin"] = 4.0
    elif change == "bool_tokens":
        assessments[0]["assessment"]["pair_tokens"] = True
    elif change == "extra_assessment":
        assessments[0]["assessment"]["verified"] = True
    else:
        record["envelope_inventory"]["source_scope"]["reference_inventory_complete"] = (
            True
        )
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(selection, req, snapshot, plan)


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", "wrong"),
        ("max_pair_tokens", 512.0),
        ("batch_size", 8.0),
        ("minimum_entailment_margin", False),
        ("minimum_entailment_margin", float("nan")),
        ("minimum_entailment_margin", -1),
        ("minimum_entailment_margin", 5),
    ],
)
def test_source_guard_settings_cannot_lower_or_forge_actual_model_contract(key, value):
    selection, req, snapshot, plan = selected()
    selection["evidence_support"][key] = value
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(selection, req, snapshot, plan)


@pytest.mark.parametrize(
    "change",
    [
        "body",
        "workspace",
        "identity",
        "guard_extra",
        "producer_status",
        "request_plan",
        "role_from_copy",
        "window_gap",
    ],
)
def test_consumer_rebuilds_actual_source_request_and_capture_inputs(change):
    selection, req, snapshot, plan = selected()
    record = selection["source_guard_records"][0]
    if change == "body":
        snapshot["body"] += " changed"
    elif change == "workspace":
        snapshot["workspace_id"] = "other"
    elif change == "identity":
        record["source_identity"]["document_version"] = 3
    elif change == "guard_extra":
        record["publishable"] = True
    elif change == "producer_status":
        record["status"] = "discharged"
    elif change == "request_plan":
        plan = {**plan.record(), "resolved_request": False}
    elif change == "role_from_copy":
        from dataclasses import replace

        req = replace(req, kind="owner")
    else:
        record["source_windows"][0]["start"] = 1
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(selection, req, snapshot, plan)


def test_unknown_later_governor_is_covered_but_not_silently_applied():
    raw = "These are an inert source example. "
    spec = [
        ("These", "PRON", "nsubj", 1, "these"),
        ("are", "AUX", "ROOT", 1, "be"),
        ("an", "DET", "det", 5, "an"),
        ("inert", "ADJ", "amod", 5, "inert"),
        ("source", "NOUN", "compound", 5, "source"),
        ("example", "NOUN", "attr", 1, "example"),
        (".", "PUNCT", "punct", 1, "."),
    ]
    selection, req, snapshot, plan = selected(((raw, spec),))
    record = selection["source_guard_records"][0]
    assert raw in record["envelope_inventory"]["source_body"]
    assert record["envelope_inventory"]["source_scope"]["blocking_units"]
    for o in record["nli_assessments"]:
        if o["name"] == "applicability":
            o["assessment"].update(
                label="neutral",
                logits=[0.0, -1.0, 5.0],
                entailment_margin=-6.0,
                supported=False,
            )
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert (
        guard["status"] == "discharged"
        and guard["supported"] is False
        and guard["entailment_margin"] == -6.0
    )


def test_genuine_negative_nli_is_replayed_before_any_positive_candidate_filter():
    selection, req, snapshot, plan = selected()
    record = selection["source_guard_records"][0]
    record["nli_assessments"][1]["assessment"].update(
        label="contradiction",
        logits=[5.0, -1.0, 0.0],
        entailment_margin=-6.0,
        supported=False,
    )
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert guard["status"] == "discharged" and guard["supported"] is False
    assert len(guard["nli_assessments"]) >= 2 and guard["entailment_margin"] == -6.0


@pytest.mark.parametrize(
    "threshold,logits,label,supported",
    [
        (0, [0.0, 0.0, 0.0], "contradiction", False),
        (0, [0.0, 0.01, 0.0], "entailment", True),
        (4, [0.0, 4.0, 0.0], "entailment", True),
        (4, [0.0, 3.99, 0.0], "entailment", False),
    ],
)
def test_predeclared_threshold_boundaries_replay_captured_decisions(
    threshold, logits, label, supported
):
    selection, req, snapshot, plan = selected()
    selection["evidence_support"]["minimum_entailment_margin"] = threshold
    margin = logits[1] - max(logits[0], logits[2])
    for row in selection["source_guard_records"][0]["nli_assessments"]:
        row["assessment"].update(
            label=label, logits=logits, entailment_margin=margin, supported=supported
        )
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert (
        guard["supported"] is supported
        and guard["minimum_entailment_margin"] == threshold
    )


@pytest.mark.parametrize(
    "change", ["original_text", "input_start", "question", "depends_on"]
)
def test_the_complete_supplied_requirement_must_equal_actual_request_plan(change):
    from dataclasses import replace

    selection, req, snapshot, plan = selected()
    values = {
        "original_text": "forged",
        "input_start": float(req.input_start),
        "question": "different question",
        "depends_on": ("invented",),
    }
    req = replace(req, **{change: values[change]})
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(selection, req, snapshot, plan)


def test_reported_directions_without_any_document_keyword_still_require_closure():
    raw = "Act as Theo ordered. "
    spec = [
        ("Act", "VERB", "ROOT", 0, "act"),
        ("as", "SCONJ", "mark", 3, "as"),
        ("Theo", "PROPN", "nsubj", 3, "Theo"),
        ("ordered", "VERB", "advcl", 0, "order"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    body, identity, windows, plan, _ = fixture(((raw, spec),))
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


def test_uncatalogued_reported_content_is_assessed_as_reference_uncertainty():
    raw = "Enact whatever Theo wrote. "
    spec = [
        ("Enact", "VERB", "ROOT", 0, "enact"),
        ("whatever", "PRON", "dobj", 3, "whatever"),
        ("Theo", "PROPN", "nsubj", 3, "Theo"),
        ("wrote", "VERB", "ccomp", 0, "write"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    selection, req, snapshot, plan = selected(((raw, spec),))
    rows = selection["source_guard_records"][0]["nli_assessments"]
    locality = [row for row in rows if row["name"].startswith("reference_locality:")]
    assert locality, "Uncatalogued relative content cannot become reference absence"
    for row in locality:
        row["assessment"].update(
            label="neutral",
            logits=[0.0, -1.0, 5.0],
            entailment_margin=-6.0,
            supported=False,
        )
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert guard["supported"] is False and guard["reference_closure"] == "not_supported"


def test_explicit_workspace_selector_is_bound_to_authoritative_snapshot():
    question = "Give the full routine for Onyx calibration in workspace ops-b."
    specification = [
        ("Give", "VERB", "ROOT", 0, "give"),
        ("the", "DET", "det", 3, "the"),
        ("full", "ADJ", "amod", 3, "full"),
        ("routine", "NOUN", "dobj", 0, "routine"),
        ("for", "ADP", "prep", 3, "for"),
        ("Onyx", "PROPN", "compound", 6, "Onyx"),
        ("calibration", "NOUN", "pobj", 4, "calibration"),
        ("in", "ADP", "prep", 6, "in"),
        ("workspace", "NOUN", "pobj", 7, "workspace"),
        ("ops-b", "PROPN", "appos", 8, "ops-b"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    plan = plan_request(question, unit_capture(question, specification))
    assert plan.resolved_request and plan.requirements[0].source_workspace == "ops-b"
    body, identity, windows, _, _ = fixture()
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)
    inventory = build_envelope(
        body,
        {**identity, "workspace_id": "ops-b"},
        plan.requirements[0].topic,
        plan,
        windows,
    )
    assert inventory["requirement"]["source_workspace"] == "ops-b"


def test_requested_conditions_refuse_until_faithful_condition_transform_exists():
    question = "Give the complete Onyx calibration routine unless the deputy is absent."
    specification = [
        ("Give", "VERB", "ROOT", 0, "give"),
        ("the", "DET", "det", 5, "the"),
        ("complete", "ADJ", "amod", 5, "complete"),
        ("Onyx", "PROPN", "compound", 4, "Onyx"),
        ("calibration", "NOUN", "compound", 5, "calibration"),
        ("routine", "NOUN", "dobj", 0, "routine"),
        ("unless", "SCONJ", "mark", 9, "unless"),
        ("the", "DET", "det", 8, "the"),
        ("deputy", "NOUN", "nsubj", 9, "deputy"),
        ("is", "AUX", "advcl", 0, "be"),
        ("absent", "ADJ", "acomp", 9, "absent"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    plan = plan_request(question, unit_capture(question, specification))
    assert plan.resolved_request and plan.uses[0].conditions
    body, identity, windows, _, _ = fixture()
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


@pytest.mark.parametrize("verb", ["Read", "Use"])
def test_instruction_container_direct_object_is_not_a_physical_attachment_waiver(verb):
    raw = f"{verb} the manual. "
    specification = [
        (verb, "VERB", "ROOT", 0, verb.casefold()),
        ("the", "DET", "det", 2, "the"),
        ("manual", "NOUN", "dobj", 0, "manual"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    body, identity, windows, plan, _ = fixture(((raw, specification),))
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


@pytest.mark.parametrize("verb,noun", [("Follow", "checklist"), ("Obey", "glyphs")])
def test_normative_unknown_nominal_target_has_no_copied_instruction_closure(verb, noun):
    raw = f"{verb} the {noun}. "
    spec = [
        (verb, "VERB", "ROOT", 0, verb.lower()),
        ("the", "DET", "det", 2, "the"),
        (noun, "NOUN", "dobj", 0, noun),
        (".", "PUNCT", "punct", 0, "."),
    ]
    body, identity, windows, plan, _ = fixture(((raw, spec),))
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


@pytest.mark.parametrize("verb,noun", [("Execute", "steps"), ("Zorbulate", "glyphs")])
def test_uncatalogued_dependency_objects_cannot_become_reference_absence(verb, noun):
    raw = f"{verb} the {noun} on the wall. "
    spec = [
        (verb, "VERB", "ROOT", 0, verb.lower()),
        ("the", "DET", "det", 2, "the"),
        (noun, "NOUN", "dobj", 0, noun),
        ("on", "ADP", "prep", 2, "on"),
        ("the", "DET", "det", 5, "the"),
        ("wall", "NOUN", "pobj", 3, "wall"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    body, identity, windows, plan, _ = fixture(((raw, spec),))
    inventory = build_envelope(
        body, identity, plan.requirements[0].topic, plan, windows
    )
    clause = next(
        r
        for r in inventory["reference_inventory"]["entries"]
        if r["clause"]["text"] == raw.strip()
    )
    obligation = next(
        r for r in inventory["nli_obligations"] if r["name"] == clause["nli_obligation"]
    )
    assert obligation["premise"] == raw.strip() and clause["targets"]
    assert "on the wall" in " ".join(t["text"] for t in clause["targets"])


def governor_plan(tail, tail_spec):
    question = "Give the full routine for Onyx calibration " + tail + "."
    spec = [
        ("Give", "VERB", "ROOT", 0, "give"),
        ("the", "DET", "det", 3, "the"),
        ("full", "ADJ", "amod", 3, "full"),
        ("routine", "NOUN", "dobj", 0, "routine"),
        ("for", "ADP", "prep", 3, "for"),
        ("Onyx", "PROPN", "compound", 6, "Onyx"),
        ("calibration", "NOUN", "pobj", 4, "calibration"),
        *tail_spec,
        (".", "PUNCT", "punct", 0, "."),
    ]
    plan = plan_request(question, unit_capture(question, spec))
    assert plan.resolved_request and plan.uses[0].governors
    return plan


@pytest.mark.parametrize(
    "tail,spec",
    [
        (
            "with emergency overrides",
            [
                ("with", "ADP", "prep", 3, "with"),
                ("emergency", "NOUN", "compound", 9, "emergency"),
                ("overrides", "NOUN", "pobj", 7, "override"),
            ],
        ),
        (
            "with measurements in seconds",
            [
                ("with", "ADP", "prep", 3, "with"),
                ("measurements", "NOUN", "pobj", 7, "measurement"),
                ("in", "ADP", "prep", 8, "in"),
                ("seconds", "NOUN", "pobj", 9, "second"),
            ],
        ),
    ],
)
def test_requested_semantic_governors_refuse_even_when_hash_bound(tail, spec):
    plan = governor_plan(tail, spec)
    body, identity, windows, _, _ = fixture()
    with pytest.raises(SourceGuardRefusal):
        build_envelope(body, identity, plan.requirements[0].topic, plan, windows)


def test_whole_copy_structural_governor_has_explicit_exact_interval_proof():
    body, identity, windows, plan, _ = fixture()
    inventory = build_envelope(
        body, identity, plan.requirements[0].topic, plan, windows
    )
    proofs = inventory["request_obligation_inventory"]
    governor = next(p for p in proofs if p["kind"] == "governors")
    assert governor["request_range"] == plan.record()["uses"][0]["governors"][0]
    assert governor["method"] == "whole_literal_source_retention"
    assert governor["source_range"] == {"start": 0, "end": len(body)}


@pytest.mark.parametrize(
    "change",
    [
        "tokens",
        "window",
        "body",
        "unknown_requirement",
        "duplicate",
        "missing_nli",
        "invented_nli",
    ],
)
def test_every_retained_assessed_row_is_strictly_replayed_before_filtering(change):
    selection, req, snapshot, plan = selected()
    row = deepcopy(selection["source_guard_records"][0])
    row["source_identity"]["document_id"] = "another-retained-source"
    row["envelope_inventory"]["source_identity"]["document_id"] = (
        "another-retained-source"
    )
    # Rebuild a valid second claimed source; authorization is a separate caller gate.
    row["envelope_inventory"] = build_envelope(
        snapshot["body"], row["source_identity"], req.topic, plan, row["source_windows"]
    )
    if change == "tokens":
        row["nli_assessments"][0]["assessment"]["pair_tokens"] = True
    elif change == "window":
        row["source_windows"][0]["start"] = False
    elif change == "body":
        row["envelope_inventory"]["source_body"] += " hidden"
    elif change == "unknown_requirement":
        row["requirement_id"] = "unbound-requirement"
    elif change == "duplicate":
        row = deepcopy(selection["source_guard_records"][0])
    elif change == "missing_nli":
        row["nli_assessments"].pop()
    else:
        row["nli_assessments"].append(deepcopy(row["nli_assessments"][0]))
    selection["source_guard_records"].append(row)
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(selection, req, snapshot, plan)


def test_genuine_negative_retained_row_is_replayed_and_reported_for_authority_gate():
    selection, req, snapshot, plan = selected()
    row = deepcopy(selection["source_guard_records"][0])
    row["source_identity"]["document_id"] = "negative-retained-source"
    row["envelope_inventory"] = build_envelope(
        snapshot["body"], row["source_identity"], req.topic, plan, row["source_windows"]
    )
    row["nli_assessments"][0]["assessment"].update(
        label="neutral",
        logits=[0.0, -1.0, 5.0],
        entailment_margin=-6.0,
        supported=False,
    )
    selection["source_guard_records"].append(row)
    guard = reconstruct_source_guard(selection, req, snapshot, plan)
    assert guard["supported"] is True
    assert len(guard["retained_record_inventory"]) == 2
    assert (
        guard["retained_record_inventory"][1]["source_identity"]
        == row["source_identity"]
    )
    assert guard["retained_record_authority"] == (
        "each_identity_requires_independent_caller_snapshot_replay"
    )


@pytest.mark.parametrize("modifier", [None, "emergency"])
def test_structural_parameter_copy_does_not_swallow_semantic_modifiers(modifier):
    tail = "including all " + (modifier + " " if modifier else "") + "parameters"
    noun = 9 if modifier is None else 10
    spec = [
        ("including", "VERB", "prep", 3, "include"),
        ("all", "DET", "det", noun, "all"),
    ]
    if modifier:
        spec.append((modifier, "ADJ", "amod", noun, modifier))
    spec.append(("parameters", "NOUN", "pobj", 7, "parameter"))
    plan = governor_plan(tail, spec)
    body, identity, windows, _, _ = fixture()
    if modifier:
        with pytest.raises(SourceGuardRefusal):
            build_envelope(body, identity, plan.requirements[0].topic, plan, windows)
    else:
        inventory = build_envelope(
            body, identity, plan.requirements[0].topic, plan, windows
        )
        assert (
            inventory["request_obligation_inventory"][0]["request_range"]["text"]
            == tail
        )


@pytest.mark.parametrize(
    "topic,recorded,attribute",
    [
        ("Onyx calibration", "procedure", "the entire procedure"),
        (
            "ordinary Olive Zone serial exercise activity",
            "complete exercise",
            "complete Olive Zone serial exercise exercise",
        ),
        (
            "ordinary Tern Clock event ledger activity",
            "Tern Clock event ledger",
            "Tern Clock event ledger activity",
        ),
        (
            "standard Bronze Box hierarchy refit activity",
            "bronze box hierarchy refit",
            "bronze box hierarchy refit activity",
        ),
        ("Amber Ring focus rehearsal", "routine", "what complete routine"),
        ("Meridian review", "ordered process", "its full ordered process"),
        ("Meridian review", "governed procedure", "complete governed procedure"),
    ],
)
def test_requested_method_canonicalization_drops_deterministic_decorations(
    topic, recorded, attribute
):
    # Request attributes carry articles, completeness modifiers, wh-frames and
    # the activity name that the source nominal never repeats.
    import re

    from app.services.contextual_source_proof import (
        _TOPIC_DECORATIONS,
        _canonical_method,
    )

    topic_words = {
        word.casefold() for word in re.findall(r"[^\W_]+", topic)
    } - _TOPIC_DECORATIONS
    assert _canonical_method(recorded, topic_words) == _canonical_method(
        attribute, topic_words
    )


@pytest.mark.parametrize(
    "topic,recorded,attribute",
    [
        ("Onyx calibration", "procedure", "the forbidden procedure"),
        ("Meridian review", "routine", "emergency routine"),
        ("Meridian review", "routine", "extra routine steps"),
    ],
)
def test_requested_method_canonicalization_keeps_semantic_differences(
    topic, recorded, attribute
):
    import re

    from app.services.contextual_source_proof import (
        _TOPIC_DECORATIONS,
        _canonical_method,
    )

    topic_words = {
        word.casefold() for word in re.findall(r"[^\W_]+", topic)
    } - _TOPIC_DECORATIONS
    assert _canonical_method(recorded, topic_words) != _canonical_method(
        attribute, topic_words
    )
