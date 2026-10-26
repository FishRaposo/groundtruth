"Generalized lossless fact requests and literal source binding; no model calls."

from dataclasses import replace

import pytest
from app.services.answer_requirements import plan_requirements, resolve_requirement
from app.services.requirement_answers import _claim_edges_error
from app.services.requirement_binding import (
    SupportCheck,
    SupportClaim,
    SupportEdge,
    support_claim,
)

ROLE_QUESTIONS = [
    (
        "Who owns the ordinary operation at the Lumen token desk, who "
        "is the deputy, and when can I consult the owner?"
    ),
    (
        "For the Lumen token desk, name the ordinary operation owner "
        "and deputy, then give that owner role's consultation window."
    ),
    (
        "I need the owner role for the Lumen token desk ordinary "
        "operation, its deputy, and the owner's published "
        "consultation availability."
    ),
    (
        "At the Lumen token desk, which role owns the ordinary "
        "operation? Include the deputy and tell me when the owning "
        "role takes consultations."
    ),
]


@pytest.mark.parametrize("question", ROLE_QUESTIONS)
def test_role_consultation_intent_and_explicit_owner_dependency_are_preserved(question):
    plan = plan_requirements(question)
    assert [r.kind for r in plan] == ["owner", "deputy", "availability"]
    assert [r.topic for r in plan] == ["Lumen token desk ordinary operation"] * 3
    assert plan[-1].relation == "consultation_window"
    assert plan[-1].depends_on == (plan[0].id,)
    assert (
        plan[1].depends_on == ()
    )  # operation deputy is not the owner's personal deputy
    assert all(question[r.input_start : r.input_end] == r.original_text for r in plan)
    with pytest.raises(ValueError, match="missing_dependency"):
        resolve_requirement(plan[-1], {})
    resolved = resolve_requirement(plan[-1], {plan[0].id: "the record steward"})
    assert resolved.topic == "the record steward"
    assert "consult" in resolved.question.casefold()


@pytest.mark.parametrize(
    "question,kinds",
    [
        (
            (
                "When does the ordinary Lumen token desk session start, how "
                "long does it last, and what quantity in the stated units is "
                "allocated to it?"
            ),
            ["start_time", "duration", "quantity"],
        ),
        (
            (
                "Give the start time, duration, and full allocation with "
                "units for one ordinary session at the Lumen token desk."
            ),
            ["start_time", "duration", "quantity"],
        ),
        (
            (
                "For a single ordinary Lumen token desk session, report its "
                "allocated amount, its beginning time, and its duration."
            ),
            ["quantity", "start_time", "duration"],
        ),
        (
            (
                "I am scheduling the ordinary Lumen token desk session. What "
                "are its start, length, and allocation, keeping the "
                "allocation units?"
            ),
            ["start_time", "duration", "quantity"],
        ),
    ],
)
def test_coordinated_session_attributes_all_get_requirements(question, kinds):
    plan = plan_requirements(question)
    assert [r.kind for r in plan] == kinds
    assert all("Lumen token desk" in r.topic and "session" in r.topic for r in plan)
    assert all(question[r.input_start : r.input_end] == r.original_text for r in plan)
    assert next(r for r in plan if r.kind == "quantity").relation == "allocation"


def test_unknown_nominal_is_retained_next_to_recognized_attributes():
    question = (
        "For an ordinary Lumen token desk session, report its color, "
        "its start time, and its duration."
    )
    plan = plan_requirements(question)
    assert [r.kind for r in plan] == ["generic", "start_time", "duration"]
    assert "color" in plan[0].original_text


@pytest.mark.parametrize(
    "question,topic",
    [
        (
            (
                "Give the entire ordinary procedure for the Lumen token desk, "
                "in order, including its prerequisites, parameters, "
                "prohibitions, and closure."
            ),
            "Lumen token desk",
        ),
        (
            (
                "How do I carry out the complete ordinary routine at the "
                "Lumen token desk? Quote the full ordered instructions, from "
                "prerequisites through final closure."
            ),
            "Lumen token desk",
        ),
        (
            (
                "Provide all instructions for an ordinary Lumen token desk "
                "run, retaining their order and every prerequisite, "
                "measurement, prohibition, and closing action."
            ),
            "ordinary Lumen token desk run",
        ),
        (
            (
                "I need the full ordinary Lumen token desk procedure, "
                "including the opening conditions, exact settings, forbidden "
                "actions, and last reconciliation step."
            ),
            "ordinary Lumen token desk",
        ),
    ],
)
def test_whole_procedure_requests_do_not_fragment_into_fact_nouns(question, topic):
    plan = plan_requirements(question)
    assert len(plan) == 1 and plan[0].kind == "procedure"
    assert plan[0].original_text == question
    assert plan[0].topic == topic


def bound(question, source, value):
    req = plan_requirements(question)[0]
    start = source.index(value)
    return req, support_claim(req, source, start, start + len(value))


def test_literal_operation_owner_target_binds_without_activity_equivalence():
    _, claim = bound(
        "Who owns the ordinary operation at the Lumen token desk?",
        ("The owner of the Lumen token desk ordinary operation is the record steward."),
        "record steward",
    )
    assert claim.rejection is None
    assert "Lumen token desk ordinary operation" in claim.hypothesis


@pytest.mark.parametrize(
    "target",
    [
        "Lumen token desk pilot",
        "Lumen token desk session",
        "Willow token desk ordinary operation",
    ],
)
def test_distinct_owner_scope_is_not_accepted_by_name_overlap(target):
    _, claim = bound(
        "Who owns the ordinary operation at the Lumen token desk?",
        f"The owner of the {target} is the record steward.",
        "record steward",
    )
    assert claim.rejection is not None


def test_deputy_operation_anaphor_requires_exact_separate_proof_checks():
    source = (
        "The owner of the Lumen token desk ordinary operation is the "
        "record steward. The deputy for that operation is the shift "
        "clerk."
    )
    req, claim = bound(
        "Who is the deputy for the Lumen token desk ordinary operation?",
        source,
        "shift clerk",
    )
    assert claim.rejection is None
    assert len(claim.checks) == 2 and len(claim.proof_edges) == 1
    assert {c.name for c in claim.checks} == {
        "operation_owner_antecedent",
        "operation_deputy_assignment",
    }
    assert claim.proof_edges[0].name == "operation_antecedent_to_deputy"
    assert _claim_edges_error(claim, req, source) is None
    for check in claim.checks:
        assert source[check.start : check.end] == check.premise


@pytest.mark.parametrize(
    "antecedent",
    [
        "",
        (
            "The owner of the Willow token desk ordinary operation is the "
            "record steward. "
        ),
        (
            "The owner of the Lumen token desk ordinary operation is the "
            "record steward. The owner of the Willow token desk ordinary "
            "operation is the other steward. "
        ),
    ],
)
def test_missing_or_foreign_immediate_operation_antecedent_remains_unbound(antecedent):
    source = antecedent + "The deputy for that operation is the shift clerk."
    _, claim = bound(
        "Who is the deputy for the Lumen token desk ordinary operation?",
        source,
        "shift clerk",
    )
    assert claim.rejection is not None


def test_consultation_keeps_weekday_interval_and_named_verified_owner():
    plan = plan_requirements(ROLE_QUESTIONS[0])
    req = resolve_requirement(plan[-1], {plan[0].id: "the record steward"})
    source = (
        "The record steward is available for consultations on Tuesday "
        "from 08:10 to 09:40."
    )
    value = "Tuesday from 08:10 to 09:40"
    start = source.index(value)
    claim = support_claim(req, source, start, start + len(value))
    assert claim.rejection is None
    assert all(
        part in claim.hypothesis
        for part in ["record steward", "consultations", "Tuesday", "08:10", "09:40"]
    )


@pytest.mark.parametrize(
    "source",
    [
        (
            "The shift clerk is available for consultations on Tuesday "
            "from 08:10 to 09:40."
        ),
        "The record steward is present on Tuesday from 08:10 to 09:40.",
    ],
)
def test_consultation_does_not_become_other_role_presence(source):
    plan = plan_requirements(ROLE_QUESTIONS[0])
    req = resolve_requirement(plan[-1], {plan[0].id: "the record steward"})
    value = "Tuesday from 08:10 to 09:40"
    start = source.index(value)
    assert support_claim(req, source, start, start + len(value)).rejection is not None


def test_allocation_copies_number_and_unit_from_exact_named_subject():
    question = (
        "For one ordinary Lumen token desk session, give the "
        "allocation in its stated units."
    )
    source = (
        "The allocation for one ordinary Lumen token desk session is 38 archive tabs."
    )
    _, claim = bound(question, source, "38")
    assert claim.rejection is None
    assert claim.value == "38 archive tabs"
    assert "38 archive tabs" in claim.hypothesis


@pytest.mark.parametrize(
    "source",
    [
        "The reserve box has 38 archive tabs.",
        (
            "The allocation for one ordinary Willow token desk session is "
            "38 archive tabs."
        ),
        (
            "The allocation for one ordinary Lumen token desk session is "
            "38 archive tabs if approved."
        ),
    ],
)
def test_allocation_does_not_use_inventory_foreign_subject_or_unparsed_condition(
    source,
):
    _, claim = bound(
        (
            "For one ordinary Lumen token desk session, give the "
            "allocation in its stated units."
        ),
        source,
        "38",
    )
    assert claim.rejection is not None


def test_new_operation_edge_guard_requires_its_two_separate_source_checks():
    source = (
        "The owner of the Lumen token desk ordinary operation is the "
        "record steward. The deputy for that operation is the shift "
        "clerk."
    )
    req = plan_requirements(
        "Who is the deputy for the Lumen token desk ordinary operation?"
    )[0]
    split = source.index("The deputy")
    first = source[:split].rstrip()
    second = source[split:]
    checks = (
        SupportCheck("operation_owner_antecedent", first, first, 0, len(first)),
        SupportCheck("operation_deputy_assignment", second, second, split, len(source)),
    )
    edge = SupportEdge(
        "operation_antecedent_to_deputy", 0, len(first), split, len(source), req.id, ()
    )
    start = source.index("shift clerk")
    claim = SupportClaim(
        ("the shift clerk is the deputy for Lumen token desk ordinary operation"),
        source,
        "shift clerk",
        start,
        start + 11,
        None,
        0,
        len(source),
        checks,
        (edge,),
        0,
        len(source),
    )
    assert _claim_edges_error(claim, req, source) is None
    assert (
        _claim_edges_error(replace(claim, checks=checks[:1]), req, source) is not None
    )
    assert (
        _claim_edges_error(
            replace(claim, proof_edges=(replace(edge, requirement_id="wrong"),)),
            req,
            source,
        )
        is not None
    )


pytest_plugins = ["tests.test_connected_contract"]


def external_fact_models(monkeypatch):
    from tests.test_requirement_answer_contract import external_models

    def select(question, context):
        body = question.casefold()
        value = (
            "Tuesday from 08:10 to 09:40"
            if "consult" in body
            else "shift clerk"
            if "deput" in body
            else "record steward"
            if "owner" in body or "owns" in body
            else "38"
            if "allocation" in body
            else "09:15"
            if "time" in body or "start" in body
            else "27 minutes"
            if "long" in body or "duration" in body
            else None
        )
        return value if value and value in context else None

    external_models(monkeypatch, select)


async def test_public_roles_consultation_keeps_source_edges_and_history(
    real_client, monkeypatch
):
    from tests.test_connected_contract import upload

    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            (
                "The owner of the Lumen token desk ordinary operation is the "
                "record steward. The deputy for that operation is the shift "
                "clerk."
            ),
            (
                "The record steward is available for consultations on Tuesday "
                "from 08:10 to 09:40."
            ),
        ]
    ]
    external_fact_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": ROLE_QUESTIONS[0],
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False, body
    assert all(
        value in body["answer"]
        for value in ["record steward", "shift clerk", "Tuesday", "08:10", "09:40"]
    )
    rows = body["provenance"]["answer_selection"]["requirements"]
    assert [r["kind"] for r in rows] == ["owner", "deputy", "availability"]
    assert rows[-1]["depends_on"] == [rows[0]["id"]]
    assert (
        rows[1]["witnesses"][0]["proof_edges"][0]["name"]
        == "operation_antecedent_to_deputy"
    )
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["evidence_access"] == "available" and saved["answer"] == body["answer"]


async def test_rejected_separate_antecedent_nli_cannot_certify_deputy(
    real_client, monkeypatch
):
    from app.services.answer_support import SupportAssessment, support_service

    from tests.test_connected_contract import upload

    client, _, _ = real_client
    document = await upload(
        client,
        (
            "The owner of the Lumen token desk ordinary operation is the "
            "record steward. The deputy for that operation is the shift "
            "clerk."
        ),
    )
    external_fact_models(monkeypatch)
    seen = []

    async def assessed(pairs, config=None):
        seen.extend(pairs)
        return [
            SupportAssessment(
                "neutral" if p.hypothesis.startswith("The owner of") else "entailment",
                (-5.0, 5.0, -5.0),
                10.0,
                not p.hypothesis.startswith("The owner of"),
                12,
            )
            for p in pairs
        ]

    monkeypatch.setattr(support_service, "assess", assessed)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who is the deputy for the Lumen token desk "
            "ordinary operation?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert any(p.hypothesis.startswith("The owner of") for p in seen)
    assert response.json()["refused"] is True and response.json()["answer"] is None


async def test_unknown_coordinated_attribute_prevents_public_partial_success(
    real_client, monkeypatch
):
    from tests.test_connected_contract import upload

    client, _, _ = real_client
    document = await upload(
        client,
        (
            "The ordinary Lumen token desk session begins at 09:15. The "
            "ordinary Lumen token desk session lasts 27 minutes."
        ),
    )
    external_fact_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "For an ordinary Lumen token desk session, report its color, "
                "its start time, and its duration."
            ),
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True and body["answer"] is None
    rows = body["provenance"]["answer_selection"]["requirements"]
    assert rows[0]["kind"] == "generic" and rows[0]["status"] == "unsupported"
    assert len(rows) == 3


def test_unparsed_consultation_constraint_does_not_become_another_owner_fact():
    question = (
        "Who owns the ordinary operation at the Lumen token desk, and "
        "when can I consult the owner under a separate appointment "
        "rule?"
    )
    plan = plan_requirements(question)
    assert len(plan) == 2 and plan[-1].kind == "generic"
    assert "separate appointment rule" in plan[-1].original_text


def test_literal_operation_owner_request_does_not_equate_a_lead_with_an_owner():
    _, claim = bound(
        "Who is the owner of the Lumen token desk ordinary operation?",
        "The record steward leads the Lumen token desk ordinary operation.",
        "record steward",
    )
    assert claim.rejection is not None


def test_non_session_cardinality_subject_is_not_rewritten_by_session_frames():
    req = plan_requirements("How many tabs does one ordinary Lumen kit contain?")[0]
    assert req.topic == "one ordinary Lumen kit"


def test_consultation_word_inside_entity_name_is_not_request_intent():
    req = plan_requirements(
        "Who owns the ordinary operation at the Lumen consultation desk?"
    )[0]
    assert req.kind == "owner"


def test_explicit_counted_unit_is_not_replaced_by_stated_unit_allocation_frame():
    question = (
        "How many archive tabs are allocated to the ordinary Lumen token desk session?"
    )
    req = plan_requirements(question)[0]
    assert req.attribute == "archive tabs"
    source = (
        "The allocation for one ordinary Lumen token desk session is 38 reserve labels."
    )
    start = source.index("38")
    assert support_claim(req, source, start, start + 2).rejection is not None


def test_property_of_instructions_is_not_a_request_for_the_whole_method():
    plan = plan_requirements(
        "What color are all instructions for the Lumen token desk?"
    )
    assert all(req.kind != "procedure" for req in plan)


def test_coordinated_operation_antecedents_are_not_unique_source_identity():
    source = (
        "The owner of the Lumen token desk ordinary operation is the record steward "
        "and the owner of the Willow token desk ordinary operation is the "
        "other steward. "
        "The deputy for that operation is the shift clerk."
    )
    _, claim = bound(
        "Who is the deputy for the Lumen token desk ordinary operation?",
        source,
        "shift clerk",
    )
    assert claim.rejection is not None


def test_unknown_allocation_request_tail_is_retained_as_unresolved():
    question = (
        "For an ordinary Lumen token desk session, give its allocation "
        "excluding a separate approval window."
    )
    plan = plan_requirements(question)
    assert len(plan) == 1 and plan[0].kind == "generic"
    assert "excluding a separate approval window" in plan[0].original_text
