"""Malformed dependent receipt identities must fail as integrity errors."""

from types import SimpleNamespace

import pytest
from app.services import staged_availability_evidence as availability


@pytest.mark.parametrize("identifier", ["missing", None, True, {}, []])
def test_unknown_member_identity_is_a_value_error(identifier):
    plan = SimpleNamespace(requirements=(), uses=())
    with pytest.raises(ValueError, match="Unique actual dependent requirement"):
        availability._binding(plan, None, identifier, {}, {}, None)


@pytest.mark.parametrize("requirements,uses", [(0, 1), (1, 0), (2, 1), (1, 2)])
def test_missing_or_duplicate_binding_is_not_silently_selected(requirements, uses):
    plan = SimpleNamespace(
        requirements=tuple(SimpleNamespace(id="child") for _ in range(requirements)),
        uses=tuple(SimpleNamespace(requirement_id="child") for _ in range(uses)),
    )
    with pytest.raises(ValueError, match="Unique actual dependent requirement"):
        availability._binding(plan, None, "child", {}, {}, None)


def test_unknown_aggregate_identity_is_a_value_error(monkeypatch):
    plan = SimpleNamespace(requirements=(), uses=())
    monkeypatch.setattr(
        availability.role, "_context", lambda _: (plan, {}, None, None, None)
    )
    with pytest.raises(ValueError, match="Unique actual dependent requirement"):
        availability.aggregate(actors={}, children={}, requirement_id="missing")
