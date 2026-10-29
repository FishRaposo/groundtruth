from app.services.answer_requirements import plan_requirements
from app.services.requirement_answers import witness_value_identity


def test_same_quantity_with_and_without_requested_unit_is_one_claim():
    req = plan_requirements("How many footstep surfaces are in a Copper map?")[0]
    assert witness_value_identity(
        req, "3", reading_profile="contextual_source_v1"
    ) == witness_value_identity(
        req, "3 footstep surfaces", reading_profile="contextual_source_v1"
    )


def test_wrong_unit_and_different_values_remain_distinct():
    req = plan_requirements("How many footstep surfaces are in a Copper map?")[0]
    key = witness_value_identity(req, "3", reading_profile="contextual_source_v1")
    assert key != witness_value_identity(
        req, "3 minutes", reading_profile="contextual_source_v1"
    )
    assert key != witness_value_identity(
        req, "8 footstep surfaces", reading_profile="contextual_source_v1"
    )


def test_duration_does_not_erase_units_and_legacy_does_not_change():
    req = plan_requirements("How long does the Copper turn last?")[0]
    assert witness_value_identity(
        req, "3 minutes", reading_profile="contextual_source_v1"
    ) != witness_value_identity(req, "3 hours", reading_profile="contextual_source_v1")
    assert witness_value_identity(req, "3 minutes") == "3 minutes"


def test_role_articles_keep_existing_role_identity():
    req = plan_requirements("Who leads Copper mapping?")[0]
    assert witness_value_identity(req, "the Map steward") == witness_value_identity(
        req, "Map steward"
    )
