"""Catch a v1/native-only record silently masquerading as new production inputs."""

from copy import deepcopy

from app.services import captured_plan_inputs as transport
from app.services import staged_plan_replay as legacy

from .fixtures import arguments, profile


def test_new_capture_adds_full_productions_without_changing_any_v1_native_inputs():
    args = arguments()
    before = deepcopy(args)
    old = legacy.capture_inputs(**args)
    record = transport.capture_inputs_v2(**args, evidence_profile=profile())
    assert record["contract"] == "staged-request-inputs-v2"
    assert set(record) == set(old) | {
        "evidence_profile",
        "request_productions",
        "source_productions",
    }
    assert {k: v for k, v in record.items() if k in old and k != "contract"} == {
        k: v for k, v in old.items() if k != "contract"
    }
    assert record["evidence_profile"] == profile()
    assert record["request_productions"]["productions"][0]["operation"] == "labels_only"
    assert len(record["source_productions"]["sources"]) == 4
    assert not record["source_productions"]["full_plan_accepted"]
    assert args == before
