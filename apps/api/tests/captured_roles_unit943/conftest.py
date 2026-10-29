"""Pure-unit guard: actual parser/model/network/SQL/old context is forbidden."""

import socket
import subprocess

import pytest
from app.services import (
    answer_support,
    request_parser,
    staged_plan_binding,
    staged_plan_replay,
    staged_role_evidence,
)
from sqlalchemy.engine import Engine


@pytest.fixture(autouse=True)
def forbid_real_execution(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError(
            "943 UNITONLY test attempted real or legacy semantic execution"
        )

    for owner, name in (
        (socket, "create_connection"),
        (subprocess, "Popen"),
        (Engine, "connect"),
        (request_parser, "_load_pipeline"),
        (answer_support, "_load_backend"),
        (answer_support.support_service, "assess"),
        (staged_plan_binding, "reconstruct_staged_plan"),
        (staged_plan_replay, "reconstruct_request"),
        (staged_role_evidence, "_context"),
    ):
        monkeypatch.setattr(owner, name, deny)
