"""Known canonical alias dispatch only; interval proof remains its own consumer."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.evidence_policy import resolve_evidence_policy
from app.services import curated_conflict_proof as proof
from app.services import linguistic_conflicts as runtime

from tests.test_curated_quote_scope995 import config, quote_record


def selected(version):
    return config().model_copy(update={"PROCEDURE_SCOPE_PROFILE": version})


@pytest.mark.parametrize("version", ["activity_quote_v1", "activity_quote_v2"])
def test_known_canonical_quote_profile_reaches_curated_quote_policy(version):
    assert proof.quote_policy(resolve_evidence_policy(selected(version)).record())


@pytest.mark.parametrize("version", ["activity_quote_v1", "activity_quote_v2"])
async def test_known_quote_versions_dispatch_to_existing_quote_inspection(
    monkeypatch, version
):
    class SelectedQuoteInspection(Exception):
        pass

    async def quote(*args, **kwargs):
        raise SelectedQuoteInspection

    monkeypatch.setattr(runtime, "_inspect_quote_group", quote)
    with pytest.raises(SelectedQuoteInspection):
        await runtime.inspect_group(
            None,
            None,
            None,
            SimpleNamespace(id="alias-control"),
            selected(version),
            [],
            False,
            [object()],
            {},
            [],
        )


def test_copy_policy_must_match_canonical_version_and_v1_basis_is_unchanged():
    _, req, snapshots, settings, inventories = quote_record()
    original = proof.selected_quote_scope(req, inventories, snapshots)
    assert (
        proof.selected_quote_scope(
            req, inventories, snapshots, evidence_profile=settings["evidence_profile"]
        )
        == original
    )
    v2 = resolve_evidence_policy(selected("activity_quote_v2")).record()
    upgraded = deepcopy(inventories)
    upgraded[0]["source_copy_policy"] = "ordinary_activity_quote_v2"
    # Scope-input alias only; this is not acceptance of an interval/source proof.
    assert (
        proof.selected_quote_scope(req, upgraded, snapshots, evidence_profile=v2)
        == original
    )
    for profile, records in (
        (v2, inventories),
        (settings["evidence_profile"], upgraded),
        (None, upgraded),
    ):
        with pytest.raises(proof.SelectedQuoteScopeUnresolved):
            proof.selected_quote_scope(
                req, records, snapshots, evidence_profile=profile
            )
    bad = deepcopy(upgraded)
    bad[0]["declared_relation"]["declared_subject"]["text"] = "foreign"
    with pytest.raises(ValueError):
        proof.selected_quote_scope(req, bad, snapshots, evidence_profile=v2)
