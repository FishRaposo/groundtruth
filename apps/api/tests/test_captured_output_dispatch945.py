"""Dispatch stops at independent consumer entry; no certificate is fabricated."""

import sys
from copy import deepcopy
from types import ModuleType

import pytest
from app.services import output_dispatch, staged_output

from tests.captured_inputs_unit932.fixtures import profile


class CapturedConsumerReached(RuntimeError):
    pass


@pytest.mark.parametrize("channel", ["presented", "retained", "input_only"])
@pytest.mark.parametrize("operation", ["certify", "verify"])
def test_new_output_markers_never_dispatch_through_old_staged_contract(
    monkeypatch, channel, operation
):
    consumer = ModuleType("app.services.captured_output")
    consumer.CERTIFICATE_FIELD = "captured_output_certificate"

    def reached(*args, **kwargs):
        raise CapturedConsumerReached("The actual new consumer must reconstruct proof")

    consumer.reconstruct_certificate = reached
    consumer.verify_output = reached
    monkeypatch.setitem(sys.modules, consumer.__name__, consumer)

    def old_forbidden(*args, **kwargs):
        raise AssertionError("New captured evidence was sent to the old contract")

    monkeypatch.setattr(staged_output, "reconstruct_certificate", old_forbidden)
    monkeypatch.setattr(staged_output, "verify_output", old_forbidden)
    fresh = {"contract": "requirement-evidence-v5", "evidence_profile": profile()}
    old = {
        "contract": "requirement-evidence-v5",
        "evidence_profile": {
            "contract": "evidence-profile-v8",
            "evidence_reading_profile": "contextual_source_v3",
        },
    }
    selected, retained = deepcopy(fresh), deepcopy(fresh)
    if channel == "retained":
        selected = old
    elif channel == "input_only":
        selected = deepcopy(old)
        selected["staged_request_inputs"] = {"contract": "staged-request-inputs-v2"}
        retained = deepcopy(old)
    context = {"query_context": {"provenance": {"answer_selection": retained}}}
    function = (
        output_dispatch.certify_output
        if operation == "certify"
        else output_dispatch.verify_output
    )
    with pytest.raises(CapturedConsumerReached):
        function(selected, **context)
