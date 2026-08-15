"""Access-control contracts for group shares and workflow visibility."""

from __future__ import annotations

import uuid

from app.api.v1.workflows import workflow_definition_visibility
from app.models.collection import CollectionShare
from app.models.document.workflow import WorkflowDefinition
from app.services.access_control.permissions import AccessControlService
from sqlalchemy.dialects import postgresql


class EmptyResult:
    def scalar_one_or_none(self) -> None:
        return None


class CapturingSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyResult()


async def test_group_memberships_are_included_in_share_lookup() -> None:
    session = CapturingSession()
    service = AccessControlService(session)
    await service._get_share(
        str(uuid.UUID("550e8400-e29b-41d4-a716-446655440000")),
        "user-1",
        group_ids=["finance", "reviewers"],
    )
    compiled = str(
        session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert CollectionShare.group_id.key in compiled
    assert "finance" in compiled
    assert "reviewers" in compiled
    assert "everyone" in compiled


def test_workflow_visibility_includes_owner_organization_and_system() -> None:
    clause = workflow_definition_visibility(
        {"id": "owner-1", "organization_id": "org-1"}
    )
    compiled = str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert WorkflowDefinition.owner_id.key in compiled
    assert "owner-1" in compiled
    assert "org-1" in compiled
    assert "is_system" in compiled
