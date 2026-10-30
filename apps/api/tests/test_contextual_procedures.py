"""Pure source-authority behavior; no services or model-success doubles."""

import importlib.util
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from app.evidence_policy import reading_version

# Import the actual pure module without the legacy services package's eager DB
# boundary; this test neither imports the application nor constructs an engine.
_path = Path(__file__).parents[1] / "app/services/contextual_procedures.py"
_spec = importlib.util.spec_from_file_location("pure_contextual_procedures", _path)
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
RoutineRejected = _module.RoutineRejected
routine_inventory = _module.routine_inventory
validate_routine_inventory = _module.validate_routine_inventory


BODY = (
    "The Orion station uses two pads. "
    "Do not move the outer pad. "
    "If the pointer rests between marks, record a tie instead of choosing a mark. "
    "The following routine applies to ordinary Orion sessions. "
    "Place the reference block on the inner pad. "
    "Record the result and return the block."
)
SUBJECT = "ordinary Orion sessions"


def identity(body=BODY, **changes):
    return {
        "document_id": "orion-guide",
        "workspace_id": "ops-a",
        "document_version": 2,
        "content_hash": sha256(body.encode("utf-8")).hexdigest(),
        **changes,
    }


def inventory(body=BODY, subject=SUBJECT):
    return routine_inventory(body, identity(body), requested_subject=subject)


def test_whole_source_cover_retains_prefix_governors_and_ordered_actions():
    # A tail-only parser would lose the prohibition and tie contingency.
    result = inventory()
    assert isinstance(result, dict), "A source-bound routine inventory is missing"
    assert result["contract"] == reading_version("contextual_source_v1").procedure
    assert result["source_identity"] == identity()
    assert result["source_body"] == BODY
    assert result["body_length"] == len(BODY)
    assert "".join(part["text"] for part in result["cover"]) == BODY
    assert [u["kind"] for u in result["units"]] == [
        "context_statement",
        "prohibition",
        "conditional_instruction",
        "declaration",
        "instruction",
        "instruction",
    ]
    instructions = result["instruction_ranges"]
    assert [BODY[r["start"] : r["end"]] for r in instructions] == [
        "Place the reference block on the inner pad.",
        "Record the result and return the block.",
    ]
    assert result["closure"] == {"kind": "immutable_eof", "offset": len(BODY)}
    assert result["units"][0]["scope"] == "unknown"


def test_conditions_are_source_bound_and_never_selected_away_as_nonordinary():
    result = inventory()
    unit = result["units"][2]
    assert unit["condition"]["text"] == "If the pointer rests between marks"
    assert unit["action"]["text"] == "record a tie instead of choosing a mark."
    assert (
        BODY[unit["condition"]["start"] : unit["condition"]["end"]]
        == unit["condition"]["text"]
    )
    assert unit["polarity"] == "positive"
    assert not {"supported", "irrelevant", "selected_branch", "logits"} & unit.keys()
    assert result["units"][1]["polarity"] == "negative"


def test_temporal_action_suffix_retains_its_trigger_instead_of_dropping_it():
    body = (
        "The following routine applies to ordinary Orion sessions. Start the timer. "
        "Stop the timer when the token crosses the stripe."
    )
    unit = inventory(body)["units"][-1]
    assert unit["kind"] == "conditional_instruction"
    assert unit["action"]["text"] == "Stop the timer"
    assert unit["condition"]["text"] == "when the token crosses the stripe."


def test_temporal_condition_offsets_exclude_separators_without_normalizing_body():
    body = (
        "The following routine applies to ordinary Orion sessions. Place the token. "
        "Stop the timer \t when the token crosses the stripe."
    )
    result = inventory(body)
    condition = result["units"][-1]["condition"]
    assert condition["text"] == "when the token crosses the stripe."
    assert condition["start"] == body.index("when the token")
    assert "".join(part["text"] for part in result["cover"]) == body


def test_qualified_physical_follow_action_is_not_a_fabricated_external_reference():
    body = (
        "For a folded teaching model, follow the bends of each boundary. "
        "The following routine applies to ordinary Orion sessions. "
        "Trace the outline. Record the result."
    )
    result = inventory(body)
    assert result["units"][0]["action"]["text"] == "follow the bends of each boundary."
    assert result["references"] == []


def test_namespace_and_applicability_are_unassessed_nli_obligations():
    result = inventory(subject="ordinary Vega sessions")
    obligations = result["nli_obligations"]
    assert [o["kind"] for o in obligations] == ["namespace", "applicability"]
    assert all(o["verification_method"] == "nli_entailment" for o in obligations)
    assert all("Vega" in o["hypothesis"] for o in obligations)
    assert all(
        o["premise"] == "The following routine applies to ordinary Orion sessions."
        for o in obligations
    )
    assert all("supported" not in o and "label" not in o for o in obligations)
    assert result["source_subject"] == SUBJECT


@pytest.mark.parametrize(
    "prefix",
    [
        "For the short pad, omit the outer turn. ",
        "On the short pad, keep the inner turn. ",
        "Before beginning the run, obtain the signed checklist. ",
        "Unless the lamp is dark, do not move the token. ",
    ],
)
def test_qualified_prefixes_keep_exact_conditions_and_actions(prefix):
    body = (
        prefix + "The following routine applies to ordinary Orion sessions. "
        "Place the token. Record the result."
    )
    result = inventory(body)
    assert result["units"][0]["kind"] == "conditional_instruction"
    assert result["units"][0]["text"] == prefix.rstrip()
    assert (
        result["units"][0]["condition"]["text"]
        + ", "
        + result["units"][0]["action"]["text"]
        == prefix.rstrip()
    )


@pytest.mark.parametrize(
    "tail",
    [
        " Appendix A contains additional required actions.",
        " Additional requirements apply.",
        " The routine continues in the next section.",
        " Unknown appendix heading",
    ],
)
def test_unknown_or_governing_appendices_cannot_be_ignored(tail):
    with pytest.raises(RoutineRejected):
        inventory(BODY + tail)


@pytest.mark.parametrize(
    "extra",
    [
        " Follow the procedure in Appendix A.",
        " Consult the separate manual before continuing.",
        " Repeat step 4.",
    ],
)
def test_unresolved_normative_references_refuse_instead_of_certifying_complete(extra):
    with pytest.raises(RoutineRejected, match="reference"):
        inventory(BODY + extra)


def test_preceding_instruction_reference_has_an_exact_resolvable_target():
    body = (
        "The following routine applies to ordinary Orion sessions. Place the token. "
        "Repeat the preceding instruction. Record the result."
    )
    result = inventory(body)
    ref = next(r for r in result["references"] if r["kind"] == "instruction_reference")
    assert (
        body[ref["target_range"]["start"] : ref["target_range"]["end"]]
        == "Place the token."
    )
    assert ref["text"] == "the preceding instruction"
    assert ref["source_range"]["start"] > ref["target_range"]["end"]


def test_material_reference_stays_in_inventory_without_becoming_document_authority():
    ref = next(
        r for r in inventory()["references"] if r["kind"] == "material_reference"
    )
    assert ref["text"] == "reference block"
    assert "target_document_id" not in ref and "verified" not in ref


@pytest.mark.parametrize(
    "changed",
    [
        {"content_hash": "0" * 64},
        {"document_version": True},
        {"document_version": 2.0},
        {"document_version": 0},
        {"document_id": ""},
    ],
)
def test_source_identity_requires_actual_hash_and_exact_version_type(changed):
    with pytest.raises(RoutineRejected):
        routine_inventory(BODY, identity(**changed), requested_subject=SUBJECT)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["units"].pop(1),
        lambda d: d["units"].reverse(),
        lambda d: d["cover"].pop(0),
        lambda d: d["instruction_ranges"][0].update(start=0),
        lambda d: d["nli_obligations"][0].update(
            hypothesis="This routine is for anyone."
        ),
        lambda d: d.update(source_subject="ordinary Vega sessions"),
        lambda d: d.update(contract="complete-immutable-procedure-v3"),
        lambda d: d.update(producer_verified=True),
    ],
)
def test_reconstruction_rejects_pruned_reordered_coherent_or_forged_records(mutate):
    record = deepcopy(inventory())
    mutate(record)
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(record, BODY, identity(), requested_subject=SUBJECT)


def test_reconstruction_binds_actual_subject_body_and_source_version():
    record = inventory()
    assert (
        validate_routine_inventory(record, BODY, identity(), requested_subject=SUBJECT)
        == record
    )
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(
            record, BODY, identity(document_version=3), requested_subject=SUBJECT
        )
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(
            record, BODY, identity(), requested_subject="ordinary Vega sessions"
        )


def test_unicode_codepoints_and_literal_whitespace_are_preserved():
    body = (
        "  The Orion🧭 station uses two pads.\n\n"
        "The following routine applies to ordinary Orion🧭 sessions. "
        "Place the token. Record the result.\n"
    )
    result = inventory(body, "ordinary Orion🧭 sessions")
    assert "".join(p["text"] for p in result["cover"]) == body
    first = result["instruction_ranges"][0]
    assert first["start"] == body.index("Place the token.")
    assert body[first["start"] : first["end"]] == "Place the token."
    assert result["closure"]["offset"] == len(body)


@pytest.mark.parametrize(
    "body",
    [
        "Place the token. Record the result.",
        BODY
        + " The following routine applies to special Orion sessions. Stop the run.",
        "Whatever the reader prefers may be used. " + BODY,
        BODY.replace(
            "Record the result and return the block.",
            "The final appendix is authoritative.",
        ),
        BODY.replace(
            "Place the reference block on the inner pad.",
            "Place the token unless the lamp is red.",
        ),
    ],
)
def test_missing_ambiguous_or_unclassified_source_regions_refuse(body):
    with pytest.raises(RoutineRejected):
        inventory(body)


@pytest.mark.parametrize(
    "action",
    [
        "Read the required external instructions.",
        "Use the instructions in the separate guide.",
        "Read the omitted guide before continuing.",
        "Complete the actions required by the separate guide.",
        "Obtain the directions from the separate handbook.",
        "Carry out the prescribed sequence.",
        "Complete the prescribed work.",
        "Use the supervisor's advice.",
        "Follow the recommended approach.",
        "Read the signed checklist.",
        "Use the reference sheet to determine the required actions.",
        "Obtain the signed checklist and do what it says.",
        "Place the reference sheet so its contents can be carried out.",
    ],
)
def test_required_instruction_authority_is_not_inferred_from_an_admitted_verb(action):
    # An open verb-plus-arbitrary-object parser mistakes missing instructions
    # for a closed physical action, even when the introducer is not "follow".
    body = "The following routine applies to ordinary Orion sessions. " + action
    with pytest.raises(RoutineRejected):
        inventory(body)


@pytest.mark.parametrize(
    "action,condition",
    [
        ("Record the value while the lamp is green.", "while the lamp is green."),
        ("Stop the timer until the lamp is green.", "until the lamp is green."),
        (
            "Record the value only for ordinary Polaris sessions.",
            "only for ordinary Polaris sessions.",
        ),
    ],
)
def test_suffix_qualifications_have_exact_intervals_and_are_never_unqualified(
    action, condition
):
    body = "The following routine applies to ordinary Orion sessions. " + action
    unit = inventory(body)["units"][-1]
    assert unit["kind"] == "conditional_instruction"
    assert unit["condition"]["text"] == condition
    assert body[unit["condition"]["start"] : unit["condition"]["end"]] == condition
    assert "supported" not in unit


@pytest.mark.parametrize(
    "subject",
    [
        "it",
        "that session",
        "the above session",
        "this session",
        "them",
        "same sessions",
    ],
)
def test_unresolved_declared_subject_is_not_filled_from_the_request(subject):
    body = "This routine applies to " + subject + ". Place the token."
    with pytest.raises(RoutineRejected):
        inventory(body)


@pytest.mark.parametrize("field", ["units", "cover", "instruction_ranges"])
def test_replay_rejects_non_json_containers_instead_of_normalizing_them(field):
    record = deepcopy(inventory())
    record[field] = tuple(record[field])
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(record, BODY, identity(), requested_subject=SUBJECT)


def test_replay_refuses_a_cyclic_non_json_container_without_unbounded_recursion():
    record = deepcopy(inventory())
    record["units"].append(record)
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(record, BODY, identity(), requested_subject=SUBJECT)


@pytest.mark.parametrize("suffix", ["activity", "activities"])
def test_named_subject_strips_activity_suffixes_like_sessions(suffix):
    text = f"ordinary Tern Clock event ledger {suffix}"
    first, last = _module._envelope_named_subject(text)
    assert text[first:last] == "Tern Clock event ledger"


@pytest.mark.parametrize(
    "subject",
    [
        "its activity",
        "the activity",
        "this activity",
        "their activities",
    ],
)
def test_unresolved_activity_subject_is_not_filled_from_the_request(subject):
    body = "This routine applies to " + subject + ". Place the token."
    with pytest.raises(RoutineRejected):
        inventory(body)


@pytest.mark.parametrize(
    "action",
    ["Place the reference sheet on the pad.", "Obtain the signed checklist."],
)
def test_physical_material_handling_remains_literal_without_instruction_authority(
    action,
):
    body = "The following routine applies to ordinary Orion sessions. " + action
    result = inventory(body)
    assert len(result["references"]) == 1
    assert result["references"][0]["kind"] == "material_reference"


@pytest.mark.parametrize(
    "action",
    [
        "Carry out the prescribed work.",
        "Take the actions described elsewhere.",
        "Record the value and follow the supervisor's advice.",
        "Record the value; use the supervisor's advice.",
        "Record the value and read the separate document.",
        "Place the token and carry out the prescribed work.",
        "Enter the actions described elsewhere.",
        "Move the token; take the actions described elsewhere.",
        "Stop the timer and enter the actions described elsewhere.",
        "Record the value and place the token and obey its markings.",
        "Record the value as recommended elsewhere.",
        "Record the value when ready and follow the supervisor's advice.",
    ],
)
def test_every_whole_action_complement_must_parse_not_just_its_initial_verb(action):
    body = "The following routine applies to ordinary Orion sessions. " + action
    with pytest.raises(RoutineRejected):
        inventory(body)


@pytest.mark.parametrize(
    "subject",
    [
        "the former session",
        "the latter session",
        "the previously mentioned session",
        "the session referred to earlier",
        "the aforementioned exercise",
        "the one already identified",
    ],
)
def test_source_subject_requires_an_independent_nominal_namespace(subject):
    body = "This routine applies to " + subject + ". Place the token."
    with pytest.raises(RoutineRejected):
        inventory(body)


def test_coordinated_and_semicolon_actions_are_separately_consumed_with_exact_cover():
    body = (
        "The following routine applies to ordinary Orion sessions. "
        "Place the token; record the value and return the block."
    )
    unit = inventory(body)["units"][-1]
    assert [a["text"] for a in unit["action_clauses"]] == [
        "Place the token",
        "record the value",
        "return the block.",
    ]
    assert "".join(p["text"] for p in unit["action_cover"]) == unit["text"]
    for action in unit["action_clauses"]:
        assert body[action["start"] : action["end"]] == action["text"]
        assert action["polarity"] == "positive"


def test_nested_action_inventory_is_required_during_reconstruction():
    record = inventory()
    record["units"][-1]["action_clauses"].pop()
    with pytest.raises(RoutineRejected):
        validate_routine_inventory(record, BODY, identity(), requested_subject=SUBJECT)


@pytest.mark.parametrize(
    "actions",
    [
        "Place the token and record the value when the lamp is green.",
        "Place the token. Record the value and repeat the preceding instruction.",
        "Place the token and record the value. Repeat the preceding instruction.",
        "Do not move the token and record the result.",
    ],
)
def test_ambiguous_condition_or_instruction_referent_attachment_refuses(actions):
    body = "The following routine applies to ordinary Orion sessions. " + actions
    with pytest.raises(RoutineRejected):
        inventory(body)


ENVELOPE_DECLARATION = (
    "The following instructions govern the standard Citrine fragment desk routine "
    "only, including references that omit the activity name."
)
ENVELOPE_BODY = (
    ENVELOPE_DECLARATION + " "
    "Use this routine only for fragments sharing one datagram tag. "
    "Do not combine different datagram tags. "
    "First, rasterize the uncatalogued operand in opaque-format 🧭. "
    "Second, if a byte is missing, mark it incomplete; otherwise retain it. "
    "If fragments overlap, suspend assembly and retain both. "
    "At the separate Indigo game, discard overlap; that game does not govern Citrine."
)
ENVELOPE_SUBJECT = "ordinary Citrine fragment desk sessions"


def envelope(body=ENVELOPE_BODY, subject=ENVELOPE_SUBJECT):
    return _module.declared_envelope_inventory(
        body, identity(body), requested_subject=subject
    )


def test_opaque_envelope_preserves_every_character_without_action_semantics():
    result = envelope()
    assert isinstance(result, dict), "Declared opaque source envelope is missing"
    assert result["contract"] == reading_version("contextual_source_v1").procedure
    assert result["envelope_kind"] == "opaque_declared_source"
    assert result["claim_semantics"] == "complete_literal_copy_of_declared_source_body"
    assert result["source_identity"] == identity(ENVELOPE_BODY)
    assert result["source_body"] == ENVELOPE_BODY
    assert result["envelope_range"] == {"start": 0, "end": len(ENVELOPE_BODY)}
    assert result["closure"] == {"kind": "immutable_eof", "offset": len(ENVELOPE_BODY)}
    assert "".join(r["text"] for r in result["ordered_ranges"]) == ENVELOPE_BODY
    assert result["source_subject"] == "standard Citrine fragment desk routine"
    assert result["namespace"]["text"] == "Citrine fragment desk"
    assert result["opaque_payload"]["text"].endswith(
        "that game does not govern Citrine."
    )
    assert "rasterize" in result["opaque_payload"]["text"]
    assert "otherwise retain it" in result["opaque_payload"]["text"]
    assert [o["kind"] for o in result["nli_obligations"]] == [
        "namespace",
        "applicability",
    ]
    assert {o["kind"] for o in result["guard_obligations"]} == {
        "actual_request_consumption",
        "whole_source_governing_scope",
        "required_reference_closure",
    }
    assert all(
        o["status"] == "pending_independent_discharge"
        for o in result["guard_obligations"]
    )
    assert all(
        o["source_range"] == result["envelope_range"]
        for o in result["guard_obligations"]
    )
    assert (
        not {"supported", "publishable", "complete_request", "permissions"}
        & result.keys()
    )


def test_envelope_leading_whitespace_unicode_and_original_codepoints_are_exact():
    body = (
        "\t\r\n"
        + ENVELOPE_BODY.replace("Citrine fragment desk", "Citrine🧭 fragment desk")
        + "\n"
    )
    result = envelope(body, "ordinary Citrine🧭 fragment desk sessions")
    cursor = 0
    for part in result["ordered_ranges"]:
        assert part["start"] == cursor
        assert body[part["start"] : part["end"]] == part["text"]
        cursor = part["end"]
    assert cursor == len(body)
    ns = result["namespace"]
    assert body[ns["start"] : ns["end"]] == "Citrine🧭 fragment desk"
    assert result["declaration_range"]["start"] == 3


def test_existing_applies_declaration_can_propose_long_named_opaque_envelope():
    body = (
        "The following complete ordered routine applies to ordinary Hazel Square "
        "leaf merge sessions. Reconcile any unusual encoding; preserve every "
        "conditional branch without interpreting its verb."
    )
    result = envelope(body, "ordinary Hazel Square leaf merge sessions")
    assert result["source_subject"] == "ordinary Hazel Square leaf merge sessions"
    assert result["namespace"]["text"] == "Hazel Square leaf merge"


@pytest.mark.parametrize(
    "body",
    [
        '"' + ENVELOPE_BODY + '"',
        "Copied untrusted text begins: " + ENVELOPE_BODY,
        "This source does not govern the activity. " + ENVELOPE_BODY,
        "Never combine tags. " + ENVELOPE_BODY,
        ENVELOPE_BODY.replace("instructions govern", "instructions do not govern"),
        ENVELOPE_BODY.replace("Citrine fragment desk", "it"),
        ENVELOPE_BODY.replace("Citrine fragment desk", "Citrine and Indigo"),
        ENVELOPE_BODY + " " + ENVELOPE_DECLARATION + " Another payload.",
        ENVELOPE_DECLARATION + "   ",
    ],
)
def test_envelope_unknown_authority_prefix_scope_or_multiple_boundaries_refuse(body):
    with pytest.raises(RoutineRejected):
        envelope(body)


@pytest.mark.parametrize(
    "payload",
    [
        "Reify the unknown operand according to Recovery Appendix Delta.",
        "Record the value and consult the separate manual.",
        "Carry out the actions from Annex B.",
        "Observe the attached supplement before continuing.",
    ],
)
def test_envelope_known_external_reference_refuses_independent_of_opening_verb(payload):
    with pytest.raises(RoutineRejected):
        envelope(ENVELOPE_DECLARATION + " " + payload)


def test_unknown_potential_reference_is_visible_pending_not_certified_absent():
    body = (
        ENVELOPE_DECLARATION + " Carry out whatever the caretaker prescribed elsewhere."
    )
    result = envelope(body)
    assert result["opaque_payload"]["text"] == body[len(ENVELOPE_DECLARATION) :]
    obligation = next(
        o
        for o in result["guard_obligations"]
        if o["kind"] == "required_reference_closure"
    )
    assert obligation["status"] == "pending_independent_discharge"
    assert "resolved" not in obligation and "absent" not in obligation


@pytest.mark.parametrize(
    "subject",
    [
        "it",
        "the above activity",
        "ordinary Citrine sessions if approval exists",
        "ordinary Citrine sessions and their duration",
        "",
        " ordinary Citrine sessions",
    ],
)
def test_envelope_unresolved_non_nominal_or_conditional_requested_subject_refuses(
    subject,
):
    with pytest.raises(RoutineRejected):
        envelope(subject=subject)


def test_envelope_namespace_mismatch_remains_actual_unassessed_nli_input():
    result = envelope(subject="ordinary Vega workbench sessions")
    assert result["source_subject"] == "standard Citrine fragment desk routine"
    assert all("Vega workbench" in o["hypothesis"] for o in result["nli_obligations"])
    assert all(o["premise"] == ENVELOPE_DECLARATION for o in result["nli_obligations"])
    assert all(
        "supported" not in o and "label" not in o for o in result["nli_obligations"]
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["ordered_ranges"].pop(),
        lambda d: d["ordered_ranges"][0].update(start=False),
        lambda d: d["envelope_range"].update(end=float(d["envelope_range"]["end"])),
        lambda d: d["opaque_payload"].update(text="Only a convenient tail."),
        lambda d: d["namespace"].update(text="Vega"),
        lambda d: d["guard_obligations"][0].update(status="resolved"),
        lambda d: d["guard_obligations"].clear(),
        lambda d: d["nli_obligations"][1].update(hypothesis="This applies to anyone."),
        lambda d: d.update(publishable=True),
        lambda d: d.update(envelope_kind="semantic_procedure_proof"),
    ],
)
def test_envelope_replay_rejects_inventories_ranges_types_and_guard_outcomes(mutate):
    result = deepcopy(envelope())
    mutate(result)
    with pytest.raises(RoutineRejected):
        _module.validate_declared_envelope_inventory(
            result,
            ENVELOPE_BODY,
            identity(ENVELOPE_BODY),
            requested_subject=ENVELOPE_SUBJECT,
        )


def test_envelope_replay_binds_authoritative_body_identity_and_requested_subject():
    result = envelope()
    assert (
        _module.validate_declared_envelope_inventory(
            result,
            ENVELOPE_BODY,
            identity(ENVELOPE_BODY),
            requested_subject=ENVELOPE_SUBJECT,
        )
        == result
    )
    for body, ident, subject in [
        (
            ENVELOPE_BODY + " New governor.",
            identity(ENVELOPE_BODY + " New governor."),
            ENVELOPE_SUBJECT,
        ),
        (
            ENVELOPE_BODY,
            identity(ENVELOPE_BODY, document_id="different"),
            ENVELOPE_SUBJECT,
        ),
        (ENVELOPE_BODY, identity(ENVELOPE_BODY, document_version=3), ENVELOPE_SUBJECT),
        (ENVELOPE_BODY, identity(ENVELOPE_BODY), "ordinary Vega sessions"),
    ]:
        with pytest.raises(RoutineRejected):
            _module.validate_declared_envelope_inventory(
                result, body, ident, requested_subject=subject
            )
