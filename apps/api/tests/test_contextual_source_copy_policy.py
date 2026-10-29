"""Pure policy tests over retained actual654 graphs; no fresh model execution."""

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
from app.evidence_policy import reading_version, source_copy_version
from app.services.contextual_source_proof import (
    SourceGuardError,
    SourceGuardRefusal,
    build_envelope,
    reconstruct_source_guard,
)

from tests import test_contextual_source_proof as source

NEW_POLICY = "source_declared_argument_copy_v1"
NEXT_POLICY = "source_bound_argument_copy_v2"


def actual_capture():
    return json.loads(
        (Path(__file__).parent / "fixtures/source_copy_capture_v654.json").read_text(
            encoding="utf8"
        )
    )


def copy_envelope(data):
    return build_envelope(
        data["body"],
        data["identity"],
        data["request_plan"]["requirements"][0]["topic"],
        data["request_plan"],
        data["source_windows"],
        source_copy_policy=NEW_POLICY,
    )


def test_actual_governing_target_not_replaced_by_activity_abstraction():
    # Defect: the actual governing NP is dropped from both mandatory claims.
    data = actual_capture()
    envelope = copy_envelope(data)
    rows = {r["name"]: r for r in envelope["nli_obligations"]}
    for name in ("namespace", "applicability"):
        assert "standard Copper alignment routine" in rows[name]["hypothesis"]
        assert rows[name]["premise"] == data["body"]


def test_actual_ordinary_instruction_arguments_are_copied_without_physical_claim():
    # Defect: exact copied directive arguments acquire an unrelated NLI claim
    # that they are physical objects/literal mentions and exclude all referrals.
    data = actual_capture()
    envelope = copy_envelope(data)
    assert not [
        r
        for r in envelope["nli_obligations"]
        if r["name"].startswith("reference_locality:")
    ]
    entries = envelope["reference_inventory"]["entries"]
    for text in (
        "First, inspect the counter.",
        "Second, place the provided tokens in the tray.",
        "Do not reset the counter until every reading is stored.",
        "Finally, retain the signed record.",
    ):
        entry = next(e for e in entries if e["clause"]["text"] == text)
        assert entry["classification"] == "copied_directive_arguments"
        assert entry["verification_method"] == "exact_source_interval_copy"


def test_legacy_actual_envelope_and_observed_scores_are_unchanged():
    data = actual_capture()
    actual = build_envelope(
        data["body"],
        data["identity"],
        "Copper alignment",
        data["request_plan"],
        data["source_windows"],
    )
    assert actual == data["retained_envelope"]
    assert all(
        row["assessment"]["supported"] is False
        for row in data["retained_nli_assessments"]
    )


def unit_data(raw, spec):
    body, identity, windows, plan, _ = source.fixture(((raw, spec),))
    return {
        "body": body,
        "identity": identity,
        "source_windows": windows,
        "request_plan": plan.record(),
    }


@pytest.mark.parametrize(
    "raw,spec",
    [
        (
            "Execute the steps on the wall. ",
            [
                ("Execute", "VERB", "ROOT", 0, "execute"),
                ("the", "DET", "det", 2, "the"),
                ("steps", "NOUN", "dobj", 0, "step"),
                ("on", "ADP", "prep", 2, "on"),
                ("the", "DET", "det", 5, "the"),
                ("wall", "NOUN", "pobj", 3, "wall"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
        (
            "Enact whatever Theo wrote. ",
            [
                ("Enact", "VERB", "ROOT", 0, "enact"),
                ("whatever", "PRON", "dobj", 3, "whatever"),
                ("Theo", "PROPN", "nsubj", 3, "Theo"),
                ("wrote", "VERB", "ccomp", 0, "write"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
        (
            "Follow the checklist. ",
            [
                ("Follow", "VERB", "ROOT", 0, "follow"),
                ("the", "DET", "det", 2, "the"),
                ("checklist", "NOUN", "dobj", 0, "checklist"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
    ],
)
def test_instruction_material_or_unknown_reported_content_needs_actual_closure(
    raw, spec
):
    # No existing positive locality score may close missing instruction content.
    with pytest.raises(SourceGuardRefusal):
        copy_envelope(unit_data(raw, spec))


def test_modifier_participles_and_subordinate_subjects_keep_their_local_roles():
    inventory = copy_envelope(actual_capture())["reference_inventory"]
    assert "directive_ast" in inventory
    ast = inventory["directive_ast"]
    provided = next(t for c in ast for t in c["tokens"] if t["text"] == "provided")
    signed = next(t for c in ast for t in c["tokens"] if t["text"] == "signed")
    assert provided["role"] == signed["role"] == "literal_modifier"
    prohibition = next(c for c in ast if c["clause"]["text"].startswith("Do not reset"))
    assert prohibition["kind"] == "root_directive"
    assert any(
        c["clause_marker"] == "until" for c in prohibition["subordinate_clauses"]
    )
    every = next(t for t in prohibition["tokens"] if t["text"] == "every")
    assert every["governing_clause"] != prohibition["root_token"]


def actual_guard_inputs():
    data = actual_capture()
    version = reading_version("contextual_source_v2")
    selection = {
        "contract": version.requirement,
        "evidence_profile": {
            "contract": version.evidence_profile,
            "evidence_reading_profile": version.profile,
            "procedure_contract": version.procedure,
        },
        "evidence_support": data["evidence_support"],
        "source_guard_records": [
            {
                "requirement_id": "r1",
                "source_identity": data["identity"],
                "requested_subject": "Copper alignment",
                "source_windows": data["source_windows"],
                "envelope_inventory": data["retained_envelope"],
                "nli_assessments": data["retained_nli_assessments"],
            }
        ],
    }
    snapshot = {
        **data["identity"],
        "body": data["body"],
        "chunks": [{"id": "captured-source", "index": 0, "content": data["body"]}],
    }
    return data, selection, snapshot


def test_actual_legacy_negative_rows_replay_without_reinterpretation():
    data, selection, snapshot = actual_guard_inputs()
    guard = reconstruct_source_guard(
        selection,
        data["request_plan"]["requirements"][0],
        snapshot,
        data["request_plan"],
    )
    assert guard["supported"] is False
    assert guard["nli_assessments"] == data["retained_nli_assessments"]


def test_actual_old_model_scores_cannot_be_relabelled_as_new_policy_decisions():
    data, selection, snapshot = actual_guard_inputs()
    selection["source_guard_records"][0]["envelope_inventory"] = copy_envelope(data)
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(
            selection,
            data["request_plan"]["requirements"][0],
            snapshot,
            data["request_plan"],
        )


@pytest.mark.parametrize("policy", ["unknown", "", True, 1, None])
def test_declared_unknown_or_removed_policy_cannot_select_a_weaker_consumer(policy):
    data, selection, snapshot = actual_guard_inputs()
    inventory = copy_envelope(data)
    inventory["source_copy_policy"] = policy
    selection["source_guard_records"][0]["envelope_inventory"] = inventory
    with pytest.raises(SourceGuardError):
        reconstruct_source_guard(
            selection,
            data["request_plan"]["requirements"][0],
            snapshot,
            data["request_plan"],
        )


def test_central_runtime_retires_prototype_but_preserves_historical_library_policies():
    assert (
        source_copy_version(reading_profile="contextual_source_v2").policy
        == "ordinary_source_argument_copy_v1"
    )
    assert source_copy_version(NEXT_POLICY).require_unique_semantic_inputs is True
    assert source_copy_version(NEW_POLICY).policy == NEW_POLICY
    assert source_copy_version().instruction_arguments == "captured_locality_nli"
    data = actual_capture()
    inv = copy_envelope(data)
    assert inv["source_copy_policy"] == NEW_POLICY
    assert inv["nli_meaning"]["shared_proposition"] is True
    assert inv["nli_meaning"]["independent_model_facts"] is False
    assert inv["declared_relation"]["proposition"]["text"] == (
        "The following instructions govern the standard Copper alignment routine only, "
        "including references that omit the activity name."
    )
    assert inv["declared_relation"]["requested_method"] == "routine"
    assert (
        inv["reference_inventory"]["semantic_authority_support"]
        == "NOT_ESTABLISHED_BY_COPY"
    )


@pytest.mark.parametrize(
    "raw,spec",
    [
        (
            "Act as requested. ",
            [
                ("Act", "VERB", "ROOT", 0, "act"),
                ("as", "SCONJ", "mark", 2, "as"),
                ("requested", "VERB", "advcl", 0, "request"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
        (
            "Reposition the data. ",
            [
                ("Reposition", "VERB", "ROOT", 0, "reposition"),
                ("the", "DET", "det", 2, "the"),
                ("data", "NOUN", "dep", 0, "data"),
                (".", "PUNCT", "punct", 0, "."),
            ],
        ),
    ],
)
def test_unknown_control_or_unresolved_token_attachment_refuses(raw, spec):
    with pytest.raises(SourceGuardRefusal):
        copy_envelope(unit_data(raw, spec))


@pytest.mark.parametrize(
    "change", ["copy_method", "target", "shared_proposition", "condition_scope"]
)
def test_producer_ast_or_scope_success_assertions_cannot_replace_reconstruction(change):
    data, selection, snapshot = actual_guard_inputs()
    inventory = copy_envelope(data)
    if change == "copy_method":
        inventory["reference_inventory"]["entries"][1]["verification_method"] = (
            "model_supported"
        )
    elif change == "target":
        inventory["declared_relation"]["target"]["text"] = "unqualified activity"
    elif change == "shared_proposition":
        inventory["nli_meaning"]["independent_model_facts"] = True
    else:
        inventory["reference_inventory"]["directive_ast"][2]["tokens"][0][
            "governing_clause"
        ] = False
    selection["source_guard_records"][0]["envelope_inventory"] = inventory
    with pytest.raises(SourceGuardError, match="Canonical source proof mismatch"):
        reconstruct_source_guard(
            selection,
            data["request_plan"]["requirements"][0],
            snapshot,
            data["request_plan"],
        )


def test_whole_body_input_and_captures_remain_required_for_new_policy():
    data = deepcopy(actual_capture())
    data["body"] += " Hidden qualification."
    with pytest.raises(SourceGuardError):
        copy_envelope(data)


def test_uncatalogued_action_operands_are_literal_copy_not_classifier_support():
    data = unit_data(
        "Zorbulate the digitized payload. ",
        [
            ("Zorbulate", "VERB", "ROOT", 0, "zorbulate"),
            ("the", "DET", "det", 3, "the"),
            ("digitized", "VERB", "amod", 3, "digitize"),
            ("payload", "NOUN", "dobj", 0, "payload"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    inv = copy_envelope(data)
    assert inv["source_body"] == data["body"]
    assert len(inv["nli_obligations"]) == 2
    ast = inv["reference_inventory"]["directive_ast"][-1]
    assert ast["action_semantics"] == "NOT_ASSERTED"
    assert ast["tokens"][2]["role"] == "literal_modifier"
    assert all("supported" not in row for row in ast["tokens"])


def test_request_mapping_must_match_declared_name_not_substring_or_copy_success():
    data = actual_capture()
    data["request_plan"] = source.fixture()[3].record()
    with pytest.raises(SourceGuardRefusal, match="literal declared-target bridge"):
        copy_envelope(data)


def test_unknown_requested_governor_remains_refused_with_exact_copy_policy():
    plan = source.governor_plan(
        "with emergency overrides",
        [
            ("with", "ADP", "prep", 3, "with"),
            ("emergency", "NOUN", "compound", 9, "emergency"),
            ("overrides", "NOUN", "pobj", 7, "override"),
        ],
    )
    body, identity, windows, _, _ = source.fixture()
    with pytest.raises(SourceGuardRefusal, match="governor"):
        copy_envelope(
            {
                "body": body,
                "identity": identity,
                "source_windows": windows,
                "request_plan": plan.record(),
            }
        )


@pytest.mark.parametrize(
    "dep", ["csubj", "csubjpass", "ccomp", "xcomp", "pcomp", "acl", "relcl"]
)
def test_unknown_clause_predicate_roles_cannot_become_literal_context(dep):
    # These are UNITONLY graph-role controls, not claims about model parsing.
    raw = "Reprocessing data remains mandatory. "
    spec = [
        ("Reprocessing", "VERB", dep, 2, "reprocess"),
        ("data", "NOUN", "dobj", 0, "data"),
        ("remains", "VERB", "ROOT", 2, "remain"),
        ("mandatory", "ADJ", "acomp", 2, "mandatory"),
        (".", "PUNCT", "punct", 2, "."),
    ]
    with pytest.raises(SourceGuardRefusal):
        copy_envelope(unit_data(raw, spec))


def test_unrecognized_content_verb_attachment_is_not_an_implicit_modifier():
    raw = "Reprocessing data remains mandatory. "
    spec = [
        ("Reprocessing", "VERB", "appos", 2, "reprocess"),
        ("data", "NOUN", "dobj", 0, "data"),
        ("remains", "VERB", "ROOT", 2, "remain"),
        ("mandatory", "ADJ", "acomp", 2, "mandatory"),
        (".", "PUNCT", "punct", 2, "."),
    ]
    with pytest.raises(SourceGuardRefusal):
        copy_envelope(unit_data(raw, spec))


SEMANTIC_POLICY = "source_bound_argument_copy_v1"


def semantic_envelope(data):
    return build_envelope(
        data["body"],
        data["identity"],
        data["request_plan"]["requirements"][0]["topic"],
        data["request_plan"],
        data["source_windows"],
        source_copy_policy=SEMANTIC_POLICY,
    )


def unit_semantic_selection(data, inventory):
    # UNITONLY protocol decisions, copied from V665's score shape. These are
    # neither actual inference nor factual assertions about the target types.
    _, selection, _ = actual_guard_inputs()
    selection["source_guard_records"] = [
        {
            "requirement_id": data["request_plan"]["requirements"][0]["id"],
            "source_identity": inventory["source_identity"],
            "requested_subject": inventory["requested_subject"],
            "source_windows": data["source_windows"],
            "envelope_inventory": inventory,
            "nli_assessments": [
                {
                    **row,
                    "assessment": {
                        "label": "entailment",
                        "logits": [-1.0, 5.0, 0.0],
                        "entailment_margin": 5.0,
                        "supported": True,
                        "pair_tokens": 80,
                    },
                }
                for row in inventory["nli_obligations"]
            ],
        }
    ]
    return selection


def replay_semantic(data, selection):
    snapshot = {
        **data["identity"],
        "body": data["body"],
        "chunks": [{"id": "UNITONLY", "index": 0, "content": data["body"]}],
    }
    return reconstruct_source_guard(
        selection,
        data["request_plan"]["requirements"][0],
        snapshot,
        data["request_plan"],
    )


def test_new_policy_requires_bound_semantic_operand_roles_without_copy_support_flags():
    data = actual_capture()
    inventory = semantic_envelope(data)
    assert inventory["source_copy_policy"] == SEMANTIC_POLICY
    assert inventory["semantic_operand_inventory"]
    assert len(inventory["nli_obligations"]) == 2 + 2 * len(
        inventory["semantic_operand_inventory"]
    )
    for item in inventory["semantic_operand_inventory"]:
        assert item["source_identity"] == data["identity"]
        assert item["status"] == "pending_actual_semantic_nli"
        assert "supported" not in item
        clause, argument = item["clause"], item["argument"]
        assert data["body"][clause["start"] : clause["end"]] == clause["text"]
        assert data["body"][argument["start"] : argument["end"]] == argument["text"]
        assert item["predicate"]["text"]
        obligation = next(
            r for r in inventory["nli_obligations"] if r["name"] == item["nli_name"]
        )
        assert obligation["premise"] == data["body"]
        assert obligation["hypothesis"] == (
            "In the instruction «"
            + clause["text"]
            + "», the role of "
            + argument["text"]
            + " is an entity or data operand of the stated action."
        )
        selected = next(
            r
            for r in inventory["nli_obligations"]
            if r["name"] == item["clause_nli_name"]
        )
        assert selected["hypothesis"] == obligation["hypothesis"]
        assert selected["premise"] == clause["text"]
        assert selected["source_range"] == {k: clause[k] for k in ("start", "end")}


def test_namespace_positive_rows_cannot_replace_missing_semantic_operand_proof():
    data = actual_capture()
    selection = unit_semantic_selection(data, semantic_envelope(data))
    selection["source_guard_records"][0]["nli_assessments"] = [
        row
        for row in selection["source_guard_records"][0]["nli_assessments"]
        if row["name"] in {"namespace", "applicability"}
    ]
    with pytest.raises(SourceGuardError):
        replay_semantic(data, selection)


@pytest.mark.parametrize("decision", ["neutral", "contradiction"])
@pytest.mark.parametrize("context", ["clause", "body"])
def test_semantic_negative_or_abstention_remains_unsupported(decision, context):
    data = actual_capture()
    selection = unit_semantic_selection(data, semantic_envelope(data))
    semantic_rows = [
        r
        for r in selection["source_guard_records"][0]["nli_assessments"]
        if r["name"].startswith("semantic_operand:")
        and r["name"].endswith(":" + context)
    ]
    assert semantic_rows
    assessment = semantic_rows[0]["assessment"]
    assessment.update(
        label=decision,
        logits=[-1.0, 0.0, 5.0] if decision == "neutral" else [5.0, 0.0, -1.0],
        entailment_margin=-5.0,
        supported=False,
    )
    assert replay_semantic(data, selection)["supported"] is False


def test_unitonly_positive_semantic_protocol_is_a_model_boundary_not_quality_evidence():
    data = actual_capture()
    selection = unit_semantic_selection(data, semantic_envelope(data))
    guard = replay_semantic(data, selection)
    assert guard["supported"] is True
    assert any(
        r["name"].startswith("semantic_operand:") for r in guard["nli_assessments"]
    )


def test_same_operand_under_distinct_predicates_has_distinct_bound_model_input():
    # Actual654 mentions the counter under inspect and reset. A free target
    # string must not make either judgment borrow the other's clause context.
    inv = semantic_envelope(actual_capture())
    repeated = [
        b
        for b in inv["semantic_operand_inventory"]
        if b["argument"]["text"] == "the counter"
    ]
    assert len(repeated) == 2
    assert repeated[0]["predicate"] != repeated[1]["predicate"]
    rows = {r["name"]: r for r in inv["nli_obligations"]}
    pairs = {
        (rows[b["nli_name"]]["premise"], rows[b["nli_name"]]["hypothesis"])
        for b in repeated
    }
    assert len(pairs) == 2


def closure_cases():
    return json.loads(
        (
            Path(__file__).parent / "fixtures/source_copy_closure_cases_v665.json"
        ).read_text(encoding="utf8")
    )["cases"]


@pytest.mark.parametrize("raw,spec", closure_cases())
def test_new_policy_missing_content_cases_need_semantic_proof_not_only_scope_gates(
    raw, spec
):
    data = unit_data(raw, spec)
    try:
        inv = semantic_envelope(data)
    except SourceGuardRefusal:
        return  # Explicit authority grammar is rejected before any classification.
    assert inv["semantic_operand_inventory"]
    selection = unit_semantic_selection(data, inv)
    rows = selection["source_guard_records"][0]["nli_assessments"]
    selection["source_guard_records"][0]["nli_assessments"] = [
        r for r in rows if not r["name"].startswith("semantic_operand:")
    ]
    with pytest.raises(SourceGuardError):
        replay_semantic(data, selection)


@pytest.mark.parametrize("raw,spec", closure_cases())
def test_new_policy_unresolved_semantic_roles_stay_unsupported_for_missing_content(
    raw, spec
):
    data = unit_data(raw, spec)
    try:
        inv = semantic_envelope(data)
    except SourceGuardRefusal:
        return
    selection = unit_semantic_selection(data, inv)
    rows = [
        r
        for r in selection["source_guard_records"][0]["nli_assessments"]
        if r["name"].startswith("semantic_operand:")
    ]
    assert rows
    for r in rows:
        r["assessment"].update(
            label="neutral",
            logits=[-1.0, 0.0, 5.0],
            entailment_margin=-5.0,
            supported=False,
        )
    assert replay_semantic(data, selection)["supported"] is False


@pytest.mark.parametrize(
    "change",
    ["predicate", "argument", "clause", "identity", "input_hash", "copy_assertion"],
)
def test_semantic_roles_are_reconstructed_from_actual_graph_not_producer_bindings(
    change,
):
    data = actual_capture()
    inv = semantic_envelope(data)
    selection = unit_semantic_selection(data, inv)
    item = inv["semantic_operand_inventory"][0]
    if change == "input_hash":
        item["input_sha256"] = "0" * 64
    elif change == "copy_assertion":
        item["status"] = "discharged_by_literal_copy"
    elif change == "identity":
        item["source_identity"]["document_version"] += 1
    else:
        item[change]["text"] = "producer invented binding"
    with pytest.raises(SourceGuardError, match="Canonical source proof mismatch"):
        replay_semantic(data, selection)


@pytest.mark.parametrize(
    "change",
    [
        "tokens_bool",
        "tokens_budget",
        "missing",
        "missing_body",
        "hypothesis",
        "range",
        "logits",
    ],
)
def test_semantic_model_metadata_input_and_budget_must_replay_strictly(change):
    data = actual_capture()
    selection = unit_semantic_selection(data, semantic_envelope(data))
    rows = selection["source_guard_records"][0]["nli_assessments"]
    row = next(r for r in rows if r["name"].startswith("semantic_operand:"))
    if change == "tokens_bool":
        row["assessment"]["pair_tokens"] = True
    elif change == "tokens_budget":
        row["assessment"]["pair_tokens"] = 513
    elif change == "missing":
        rows.remove(row)
    elif change == "missing_body":
        rows.remove(
            next(
                r
                for r in rows
                if r["name"].startswith("semantic_operand:")
                and r["name"].endswith(":body")
            )
        )
    elif change == "hypothesis":
        row["hypothesis"] = "producer declares operand safe"
    elif change == "range":
        row["source_range"]["end"] -= 1
    else:
        row["assessment"]["logits"] = [True, 5.0, 0.0]
    with pytest.raises(SourceGuardError):
        replay_semantic(data, selection)


@pytest.mark.parametrize("error_kind", ["budget", "model_error"])
@pytest.mark.parametrize(
    "copy_policy", [NEXT_POLICY, "ordinary_source_argument_copy_v1"]
)
def test_producer_semantic_assessment_errors_cannot_create_a_supported_record(
    monkeypatch, error_kind, copy_policy
):
    # Run only immediate UNITONLY coroutine boundaries: no event loop/socket,
    # parser/QA/NLI/model execution, database, or service process is involved.
    from app.models.query import QueryRequest
    from app.services import linguistic_procedure_runtime as runtime
    from app.services import procedure_evidence
    from app.services.answer_reader import ReaderSelection
    from app.services.answer_support import SupportInputBudgetExceeded
    from app.services.linguistic_requirements import plan_request

    from tests.test_composite_procedures import chunk
    from tests.test_linguistic_runtime_dispatch import config

    data = actual_capture()
    plan = plan_request(data["request_plan"]["question"], data["request_capture"])
    member = chunk(data["body"])
    immutable = procedure_evidence.single_chunk_source(member)
    captured_pairs = []

    async def resolve(*a, **kw):
        return immutable

    async def qa(*a, **kw):
        return [ReaderSelection(None, {"decision": "no_answer", "null_margin": 9.0})]

    async def windows(*a, **kw):
        return data["source_windows"]

    async def assess(pairs, **kw):
        captured_pairs.extend(pairs)
        if error_kind == "budget":
            raise SupportInputBudgetExceeded("UNITONLY semantic model budget")
        raise RuntimeError("UNITONLY semantic model failure")

    async def current(_):
        return True

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(runtime, "resolve_version", resolve)
    monkeypatch.setattr(runtime.reader_service, "select_atomic", qa)
    monkeypatch.setattr(runtime.support_service, "assess", assess)
    monkeypatch.setattr(runtime, "_windows", windows)
    monkeypatch.setattr(
        runtime,
        "source_copy_version",
        lambda **kwargs: source_copy_version(copy_policy),
    )
    candidates = []
    coro = runtime.find_procedure_witnesses(
        None,
        QueryRequest(question=plan.question),
        None,
        plan.requirements[0],
        config(),
        candidates,
        {member.id: member},
        [],
        current,
        request_plan=plan,
        source_window_cache={},
    )
    try:
        if error_kind == "model_error":
            with pytest.raises(RuntimeError, match="UNITONLY semantic model failure"):
                coro.send(None)
        else:
            with pytest.raises(StopIteration) as completed:
                coro.send(None)
            assert completed.value.value == []
    finally:
        coro.close()
    if copy_policy == NEXT_POLICY:
        assert Counter(pair.premise for pair in captured_pairs) == {
            data["body"]: 8,
            "First, inspect the counter.": 1,
            "Second, place the provided tokens in the tray.": 2,
            "Do not reset the counter until every reading is stored.": 2,
            "Finally, retain the signed record.": 1,
        }
    else:
        assert Counter(pair.premise for pair in captured_pairs) == {
            copy_envelope(data)["declared_relation"]["proposition"]["text"]: 2
        }
    assert not any("source_guard_record" in row for row in candidates)


def bounded_semantic_envelope(data):
    return build_envelope(
        data["body"],
        data["identity"],
        data["request_plan"]["requirements"][0]["topic"],
        data["request_plan"],
        data["source_windows"],
        source_copy_policy=NEXT_POLICY,
    )


def input_collision_cases():
    return json.loads(
        (
            Path(__file__).parent / "fixtures/source_copy_input_cases_v680.json"
        ).read_text(encoding="utf8")
    )["cases"]


@pytest.mark.parametrize("case", input_collision_cases())
def test_next_policy_refuses_unexpressed_predicate_occurrences_without_dropping_steps(
    case,
):
    with pytest.raises(SourceGuardRefusal, match="Ambiguous semantic input"):
        bounded_semantic_envelope(unit_data(case["raw"], case["spec"]))


@pytest.mark.parametrize("case", input_collision_cases())
def test_v667_historical_model_inputs_keep_their_original_meaning(case):
    inv = semantic_envelope(unit_data(case["raw"], case["spec"]))
    names = {row["name"] for row in case["historical_inputs"]}
    assert [r for r in inv["nli_obligations"] if r["name"] in names] == case[
        "historical_inputs"
    ]


def test_independent_condition_occurrences_cannot_borrow_each_others_role():
    raw = "Reset the counter until the counter is stored. "
    spec = [
        ("Reset", "VERB", "ROOT", 0, "reset"),
        ("the", "DET", "det", 2, "the"),
        ("counter", "NOUN", "dobj", 0, "counter"),
        ("until", "SCONJ", "mark", 7, "until"),
        ("the", "DET", "det", 5, "the"),
        ("counter", "NOUN", "nsubjpass", 7, "counter"),
        ("is", "AUX", "auxpass", 7, "be"),
        ("stored", "VERB", "advcl", 0, "store"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    with pytest.raises(SourceGuardRefusal, match="Ambiguous semantic input"):
        bounded_semantic_envelope(unit_data(raw, spec))


def test_distinct_argument_occurrences_of_one_predicate_cannot_share_semantic_input():
    raw = "Compare the counter to the counter. "
    spec = [
        ("Compare", "VERB", "ROOT", 0, "compare"),
        ("the", "DET", "det", 2, "the"),
        ("counter", "NOUN", "dobj", 0, "counter"),
        ("to", "ADP", "prep", 0, "to"),
        ("the", "DET", "det", 5, "the"),
        ("counter", "NOUN", "pobj", 3, "counter"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    with pytest.raises(SourceGuardRefusal, match="Ambiguous semantic input"):
        bounded_semantic_envelope(unit_data(raw, spec))


def test_distinct_coordinate_operands_keep_every_step_and_bound_input():
    raw = "Inspect the counter and retain the record. "
    spec = [
        ("Inspect", "VERB", "ROOT", 0, "inspect"),
        ("the", "DET", "det", 2, "the"),
        ("counter", "NOUN", "dobj", 0, "counter"),
        ("and", "CCONJ", "cc", 0, "and"),
        ("retain", "VERB", "conj", 0, "retain"),
        ("the", "DET", "det", 6, "the"),
        ("record", "NOUN", "dobj", 4, "record"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    data = unit_data(raw, spec)
    inv = bounded_semantic_envelope(data)
    assert inv["source_body"] == data["body"]
    assert "".join(r["text"] for r in inv["ordered_ranges"]) == data["body"]
    bindings = [
        b
        for b in inv["semantic_operand_inventory"]
        if b["clause"]["text"] == raw.strip()
    ]
    assert len(bindings) == 2
    assert {b["predicate"]["text"] for b in bindings} == {"Inspect", "retain"}
    rows = {r["name"]: r for r in inv["nli_obligations"]}
    for context in ("nli_name", "clause_nli_name"):
        assert (
            len(
                {
                    (rows[b[context]]["premise"], rows[b[context]]["hypothesis"])
                    for b in bindings
                }
            )
            == 2
        )


@pytest.mark.parametrize("case", input_collision_cases())
def test_public_reconstructor_refuses_collisions_with_unit_positive_rows(
    case,
):
    data = unit_data(case["raw"], case["spec"])
    inv = semantic_envelope(data)  # Retained historical inputs, not current admission.
    inv["source_copy_policy"] = NEXT_POLICY
    inv["reference_inventory"]["policy"] = source_copy_version(NEXT_POLICY).reference
    selection = unit_semantic_selection(data, inv)
    with pytest.raises(SourceGuardRefusal, match="Ambiguous semantic input"):
        replay_semantic(data, selection)


def test_current_ordinary_and_condition_bindings_preserve_source_and_proof():
    data = actual_capture()
    inv = bounded_semantic_envelope(data)
    assert inv["source_copy_policy"] == NEXT_POLICY
    assert inv["source_body"] == data["body"]
    assert "".join(r["text"] for r in inv["ordered_ranges"]) == data["body"]
    proof = inv["reference_inventory"]["semantic_input_binding"]
    assert proof["method"] == "distinct_occurrence_input_injectivity_v1"
    assert len(proof["inputs"]) == 12  # Six target occurrences, two contexts each.
    assert len({r["occurrence_sha256"] for r in proof["inputs"]}) == 6
    assert (
        replay_semantic(data, unit_semantic_selection(data, inv))["supported"] is True
    )
    proof["inputs"][0]["occurrence_sha256"] = "0" * 64
    with pytest.raises(SourceGuardError, match="Canonical source proof mismatch"):
        replay_semantic(data, unit_semantic_selection(data, inv))
