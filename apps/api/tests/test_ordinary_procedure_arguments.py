"""The approved ordinary-argument interpretation is not model role support."""

import json
from pathlib import Path

import pytest
from app.services.contextual_source_proof import SourceGuardRefusal, build_envelope

from tests.test_contextual_source_proof import fixture

POLICY = "ordinary_source_argument_copy_v1"


def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/source_copy_capture_v654.json").read_text(
            encoding="utf8"
        )
    )


def compile_actual():
    data = actual()
    return build_envelope(
        data["body"],
        data["identity"],
        data["request_plan"]["requirements"][0]["topic"],
        data["request_plan"],
        data["source_windows"],
        source_copy_policy=POLICY,
    )


def test_ordinary_copy_scope_uses_fixed_complete_governing_context():
    envelope = compile_actual()
    declaration = envelope["declared_relation"]["proposition"]
    assert [r["name"] for r in envelope["nli_obligations"]] == [
        "namespace",
        "applicability",
    ]
    for row in envelope["nli_obligations"]:
        assert row["premise"] == row["hypothesis"] == declaration["text"]
        assert row["source_range"] == {
            "start": declaration["start"],
            "end": declaration["end"],
        }
    interpretation = envelope["argument_interpretation"]
    assert interpretation["method"] == "disclosed_literal_instruction_arguments_v1"
    assert interpretation["model_support"] == "NOT_ASSERTED"
    assert interpretation["implicit_reference_absence"] == "NOT_ESTABLISHED"
    assert interpretation["disclosure"] in envelope["literal_scope"]["disclosure"]
    assert envelope["source_body"] == actual()["body"]


def test_historical_library_default_is_not_reinterpreted():
    data = actual()
    assert (
        build_envelope(
            data["body"],
            data["identity"],
            "Copper alignment",
            data["request_plan"],
            data["source_windows"],
        )
        == data["retained_envelope"]
    )


@pytest.mark.parametrize(
    "raw,spec",
    json.loads(
        (
            Path(__file__).parent / "fixtures/source_copy_closure_cases_v665.json"
        ).read_text(encoding="utf8")
    )["cases"],
)
def test_identified_instruction_content_cannot_become_an_ordinary_operand(raw, spec):
    body, identity, windows, plan, _ = fixture(((raw, spec),))
    with pytest.raises(
        SourceGuardRefusal, match="[Aa]uthority|[Cc]ontent|[Rr]eference"
    ):
        build_envelope(
            body,
            identity,
            plan.requirements[0].topic,
            plan.record(),
            windows,
            source_copy_policy=POLICY,
        )
