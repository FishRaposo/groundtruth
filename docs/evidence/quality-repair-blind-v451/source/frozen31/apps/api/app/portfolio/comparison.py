"""Bind shared raw identity to authoritative per-arm source views, never scores."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from app.evidence_policy import (
    KNOWN_CONTRACTS,
    ProcedureVerificationProfile,
    ProposalProfile,
    RoleScopePolicy,
    SourceContextPolicy,
    context_version,
)
from app.portfolio import representation as rep

COMMON = "common_corpus_manifest_sha256"
PUBLIC_FIELDS = frozenset(
    {
        "contract",
        "profile",
        "execution_arm",
        "oracle_contract",
        "compiler_contract",
        "compiler_sha256",
        "origin_common_manifest_sha256",
        "common_source_contract_sha256",
        "common_case_contract_sha256",
        "common_contract_sha256",
        "projection_sha256",
    }
)
SHARED_FIELDS = PUBLIC_FIELDS - {"profile", "execution_arm", "projection_sha256"}
HASH_FIELDS = {key for key in PUBLIC_FIELDS if key.endswith("sha256")}


def _hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def validate_descriptor(value: Any, arm: str | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != PUBLIC_FIELDS:
        raise ValueError("Comparison representation descriptor is missing or invalid")
    profile = value["profile"]
    if (
        not isinstance(profile, str)
        or profile not in rep.PROFILES
        or value["contract"] != rep.CONTRACT
        or value["oracle_contract"] != rep.ORACLE
        or value["compiler_contract"] != rep.COMPILER
        or value["execution_arm"] != rep.PROFILES[profile]
        or (arm is not None and value["execution_arm"] != arm)
        or any(not _hash(value[key]) for key in HASH_FIELDS)
        or value["compiler_sha256"]
        != hashlib.sha256(Path(rep.__file__).read_bytes()).hexdigest()
    ):
        raise ValueError(
            "Comparison representation profile, arm or pinned compiler differs"
        )
    return dict(value)


def public_descriptor(corpus: dict, arm: str | None = None) -> dict | None:
    manifest = corpus["manifest"]
    if rep.META not in manifest:
        return None
    envelope = manifest[rep.META]
    if not isinstance(envelope, dict):
        raise ValueError("Comparison representation envelope is invalid")
    return validate_descriptor(
        {
            k: v
            for k, v in envelope.items()
            if k not in {"common_manifest_text", "common_files"}
        },
        arm,
    )


def record_descriptor(
    record: dict, arm: str | None = None, *, require_common: bool = False
) -> dict | None:
    if rep.META not in record:
        if COMMON in record:
            raise ValueError(
                "Common comparison identity requires its representation descriptor"
            )
        return None
    descriptor = validate_descriptor(record[rep.META], arm)
    if (require_common or COMMON in record) and record.get(COMMON) != descriptor[
        "origin_common_manifest_sha256"
    ]:
        raise ValueError("Report common corpus identity differs from its descriptor")
    if not _hash(record.get("corpus_manifest_sha256")):
        raise ValueError("Comparison arm manifest identity is invalid")
    return descriptor


def _validate_view(corpus: dict) -> None:
    """Recheck Python-supplied views as well as views already checked by the loader."""
    manifest = dict(corpus["manifest"])
    try:
        original = json.loads(
            manifest[rep.META]["common_manifest_text"].encode("utf-8")
        )
        if "manifest_sha256" in original:
            manifest["manifest_sha256"] = original["manifest_sha256"]
        else:
            manifest.pop("manifest_sha256", None)
        rep.validate_representation(
            manifest, {key: corpus[key] for key in ("documents", "cases", "profile")}
        )
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError(
            "Comparison authoritative representation view is incomplete"
        ) from exc


def bind_record(
    record: dict, corpus: dict, arm: str | None, *, report: bool = False
) -> dict | None:
    expected = public_descriptor(corpus, arm)
    if expected is not None and arm not in rep.PROFILES.values():
        raise ValueError("Projected comparison requires an explicit execution arm")
    observed = record_descriptor(record, arm, require_common=report)
    if expected != observed:
        raise ValueError("Seed/report representation differs from its frozen arm view")
    if expected is not None:
        _validate_view(corpus)
        if (
            record.get("corpus_manifest_sha256")
            != corpus["manifest"]["manifest_sha256"]
        ):
            raise ValueError("Seed/report arm corpus manifest differs")
    return expected


def report_binding(corpus: dict) -> dict:
    descriptor = public_descriptor(corpus)
    return (
        {}
        if descriptor is None
        else {
            rep.META: descriptor,
            COMMON: descriptor["origin_common_manifest_sha256"],
        }
    )


def selection_identity(corpus: dict) -> str:
    descriptor = public_descriptor(corpus)
    return (
        corpus["manifest"]["manifest_sha256"]
        if descriptor is None
        else descriptor["origin_common_manifest_sha256"]
    )


def validate_pair(baseline: dict, candidate: dict) -> bool:
    """Header coherence only; source auditing is a separate mandatory portable gate."""
    before = record_descriptor(baseline, "baseline", require_common=True)
    after = record_descriptor(candidate, "candidate", require_common=True)
    if before is None and after is None:
        if not baseline.get("corpus_manifest_sha256") or baseline[
            "corpus_manifest_sha256"
        ] != candidate.get("corpus_manifest_sha256"):
            raise ValueError("Comparison dataset differs")
        return False
    if (
        before is None
        or after is None
        or any(before[key] != after[key] for key in SHARED_FIELDS)
    ):
        raise ValueError(
            "Comparison common raw, semantic, compiler or oracle identity differs"
        )
    return True


def validate_common_view(corpus: dict, common: dict, arm: str) -> None:
    if rep.META in common["manifest"]:
        raise ValueError(
            "Comparison common corpus must be the unprojected raw contract"
        )
    descriptor = public_descriptor(corpus, arm)
    if descriptor is None:
        raise ValueError("Projected comparison needs both authoritative arm views")
    _validate_view(corpus)
    envelope = corpus["manifest"][rep.META]
    original = json.loads(envelope["common_manifest_text"].encode("utf-8"))
    actual_manifest = {
        k: v for k, v in common["manifest"].items() if k != "manifest_sha256"
    }
    expected_manifest = {k: v for k, v in original.items() if k != "manifest_sha256"}
    expected = {
        "origin_common_manifest_sha256": common["manifest"]["manifest_sha256"],
        "common_source_contract_sha256": rep._digest(common["documents"]),
        "common_case_contract_sha256": rep._digest(common["cases"]),
        "common_contract_sha256": rep._digest(
            {
                "manifest": original,
                **{k: common[k] for k in ("documents", "cases", "profile")},
            }
        ),
    }
    if actual_manifest != expected_manifest or any(
        descriptor[k] != v for k, v in expected.items()
    ):
        raise ValueError(
            "Arm projection differs from the authoritative common contract"
        )


def load_views(
    common_path: Path, baseline_path: Path | None, candidate_path: Path | None
):
    from app.portfolio import load_corpus

    common = load_corpus(common_path)
    if baseline_path is None and candidate_path is None:
        return common, None, None
    if baseline_path is None or candidate_path is None:
        raise ValueError("Projected comparison requires both arm corpus directories")
    if rep.META in common["manifest"]:
        raise ValueError("--corpus-dir must identify the common raw corpus")
    profiles = {arm: profile for profile, arm in rep.PROFILES.items()}
    views = []
    for arm, path in (("baseline", baseline_path), ("candidate", candidate_path)):
        view = load_corpus(
            path,
            expected_representation_profile=profiles[arm],
            expected_common_manifest_sha256=common["manifest"]["manifest_sha256"],
        )
        validate_common_view(view, common, arm)
        views.append(view)
    return common, views[0], views[1]


def disclosure(baseline: dict, candidate: dict, *, verified: bool) -> dict:
    descriptor = record_descriptor(baseline, "baseline", require_common=True)
    if descriptor is None:
        return {}
    after = record_descriptor(candidate, "candidate", require_common=True)
    assert after is not None
    return {
        "input_equivalence": {
            "scope": "end_to_end_shared_raw_per_arm_representation",
            "verified_against_common_sources": verified,
            **{key: descriptor[key] for key in SHARED_FIELDS},
            "baseline_corpus_manifest_sha256": baseline["corpus_manifest_sha256"],
            "candidate_corpus_manifest_sha256": candidate["corpus_manifest_sha256"],
            "baseline_projection_sha256": descriptor["projection_sha256"],
            "candidate_projection_sha256": after["projection_sha256"],
            "reader_only_improvement_claim": False,
        }
    }


def require_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_object(path: Path, label: str) -> dict:
    return require_object(json.loads(path.read_bytes()), label)


def check_measured_settings(selection, development):
    declared = require_object(selection.get("settings", {}), "Selected settings")
    measured = require_object(development.get("settings", {}), "Development settings")
    for key in ("top_k", "refusal_threshold"):
        if declared.get(key) != measured.get(key):
            raise ValueError(
                "Selected settings differ from measured development settings"
            )
    if declared.get(
        "procedure_verification_profile", "all_units_nli_v1"
    ) != measured.get("procedure_verification_profile", "all_units_nli_v1"):
        raise ValueError("Selected procedure profile differs from measured settings")
    if declared.get("source_context_policy", "explicit_target_v1") != measured.get(
        "source_context_policy", "explicit_target_v1"
    ):
        raise ValueError(
            "Selected source context policy differs from measured settings"
        )


def read_selection(split, selection_path, corpus_hash):
    selection = None
    if split == "held_out":
        if selection_path is None:
            raise ValueError(
                "Held-out evaluation requires a frozen development-only selection"
            )
        selection = _artifact_object(selection_path, "Selection artifact")
        if selection.get("schema_version") == 2:
            return read_coverage_selection(selection, selection_path, corpus_hash)
        if selection.get("selection_basis") != "development_only":
            raise ValueError("Selection must declare development_only")
        if selection.get("corpus_manifest_sha256") != corpus_hash:
            raise ValueError("Selection belongs to a different corpus")
        dev_path = Path(selection["development_report_path"])
        if not dev_path.is_absolute():
            dev_path = selection_path.parent / dev_path
        if _file_hash(dev_path) != selection["development_report_sha256"]:
            raise ValueError("Development report checksum mismatch")
        dev = _artifact_object(dev_path, "Development artifact")
        if (
            dev.get("split") != "development"
            or dev.get("corpus_manifest_sha256") != corpus_hash
        ):
            raise ValueError("Selection must reference matching development evidence")
        if not selection.get("frozen_at"):
            raise ValueError("Selection requires frozen_at")
        check_measured_settings(selection, dev)
    return selection


def _validate_binding_times(selection, freeze):
    stamp, bound = selection.get("frozen_at"), selection.get("binding_at")
    if not isinstance(stamp, str) or not stamp or stamp != freeze.get("frozen_at"):
        raise ValueError("Selection must preserve the candidate freeze timestamp")
    if not isinstance(bound, str) or not bound:
        raise ValueError("Validation binding requires binding_at")
    try:
        frozen_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        binding_at = datetime.fromisoformat(bound.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Selection artifact timestamps are invalid") from exc
    if frozen_at.tzinfo is None or binding_at.tzinfo is None or binding_at < frozen_at:
        raise ValueError("Binding must occur after the dated candidate freeze")


def read_coverage_selection(selection, selection_path, corpus_hash):
    """Bind later validation sources to an immutable earlier candidate freeze."""
    if selection.get("selection_basis") != "development_only":
        raise ValueError("Selection must declare development_only")
    if selection.get("validation_corpus_manifest_sha256") != corpus_hash:
        raise ValueError("Selection belongs to a different validation corpus")

    def artifact(name):
        target = selection.get(name + "_path")
        if not isinstance(target, str) or not target:
            raise ValueError("Selection artifact reference is invalid")
        path = Path(target)
        if not path.is_absolute():
            path = selection_path.parent / path
        if _file_hash(path) != selection[name + "_sha256"]:
            raise ValueError(name.replace("_", " ") + " checksum mismatch")
        return _artifact_object(path, name.replace("_", " ") + " artifact")

    development = artifact("development_report")
    freeze = artifact("candidate_freeze")
    development_hash = selection.get("development_corpus_manifest_sha256")
    if (
        not development_hash
        or development.get("split") != "development"
        or development.get("corpus_manifest_sha256") != development_hash
        or freeze.get("development_corpus_manifest_sha256") != development_hash
    ):
        raise ValueError("Selection must reference frozen development evidence")
    require_object(selection.get("settings"), "Selected settings")
    require_object(development.get("settings"), "Development settings")
    require_object(freeze.get("settings"), "Frozen settings")
    _validate_binding_times(selection, freeze)
    if selection.get("settings") != development.get("settings") or selection.get(
        "settings"
    ) != freeze.get("settings"):
        raise ValueError("Selected settings differ from measured frozen settings")
    return selection


RUNTIME_KEYS = frozenset(
    {
        "top_k",
        "reader_null_threshold",
        "reader_model_revision",
        "answer_proposal_profile",
        "role_scope_policy",
        "answer_support_mode",
        "support_model_revision",
        "support_min_margin",
        "selection_contract",
    }
)


def validate_runtime_settings(settings: Any, *, complete: bool = False) -> dict:
    settings = require_object(settings, "Runtime settings")
    if complete and not RUNTIME_KEYS.issubset(settings):
        raise ValueError("Frozen candidate runtime settings are incomplete")
    choices = {
        "answer_proposal_profile": get_args(ProposalProfile),
        "role_scope_policy": get_args(RoleScopePolicy),
        "source_context_policy": get_args(SourceContextPolicy),
        "answer_support_mode": ("disabled", "local_nli"),
        "procedure_verification_profile": get_args(ProcedureVerificationProfile),
        "answer_selection_mode": ("lexical", "reader"),
        "generation_mode": ("legacy", "extractive", "provider"),
    }
    for key, allowed in choices.items():
        if key in settings and settings[key] not in allowed:
            raise ValueError(
                "Frozen runtime profile, policy or support mode is invalid"
            )
    if (
        settings.get("source_context_policy", "explicit_target_v1")
        != "explicit_target_v1"
        and settings.get("procedure_verification_profile")
        != "source_declared_procedure_copy_v1"
    ):
        raise ValueError("Contextual reading requires source-declared copy profile")
    _validate_runtime_numbers(settings)
    if settings.get(
        "procedure_verification_profile"
    ) == "source_declared_procedure_copy_v1" and (
        settings.get("answer_selection_mode") != "reader"
        or settings.get("answer_support_mode") != "local_nli"
        or settings.get("generation_mode") != "extractive"
    ):
        raise ValueError(
            "Procedure copy profile requires reader, local_nli and extractive engines"
        )
    if "selection_contract" in settings and (
        not isinstance(settings["selection_contract"], str)
        or settings["selection_contract"] not in KNOWN_CONTRACTS
    ):
        raise ValueError("Frozen evidence contract is unsupported")
    for key in (
        "reader_model_revision",
        "support_model_revision",
        "selection_contract",
    ):
        if key in settings and (
            not isinstance(settings[key], str) or not settings[key]
        ):
            raise ValueError("Frozen runtime revision/contract is missing")
    if complete and settings["top_k"] != 5:
        raise ValueError("Frozen runtime top_k differs from the comparison contract")
    return settings


def _validate_runtime_numbers(settings):
    import math

    for key in ("reader_null_threshold", "support_min_margin", "refusal_threshold"):
        if key in settings:
            value = settings[key]
            if key == "refusal_threshold" and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Frozen runtime threshold/margin is invalid")
    if (
        "support_min_margin" in settings
        and not 0 <= settings["support_min_margin"] <= 4
    ):
        raise ValueError("Frozen support margin is outside its supported range")


def _same_runtime(expected, actual) -> bool:
    import math

    if type(expected) in (int, float):
        return (
            type(actual) in (int, float)
            and math.isfinite(actual)
            and expected == actual
        )
    return expected == actual


def support_configuration_matches(selection, settings):
    support = selection.get("evidence_support")
    support = support if isinstance(support, dict) else {}
    expected = {
        "answer_support_mode": support.get("mode"),
        "support_model_revision": support.get("revision"),
        "support_min_margin": support.get("minimum_entailment_margin"),
        "selection_contract": selection.get("contract"),
    }
    return all(
        key not in settings or _same_runtime(settings[key], actual)
        for key, actual in expected.items()
    )


def _recorded_procedure_profile(profile):
    if (
        not isinstance(profile, dict)
        or profile.get("proposal_profile") not in get_args(ProposalProfile)
        or profile.get("role_scope_policy") not in get_args(RoleScopePolicy)
    ):
        return None
    contract = profile.get("contract")
    procedure = profile.get("procedure_verification_profile", "all_units_nli_v1")
    if contract == "evidence-profile-v1" and procedure == "all_units_nli_v1":
        return procedure
    if (
        contract
        in ("evidence-profile-v2", "evidence-profile-v3", "evidence-profile-v4")
        and procedure == "source_declared_procedure_copy_v1"
        and (
            (
                contract == "evidence-profile-v2"
                and "source_context_policy" not in profile
            )
            or (
                profile.get("source_context_policy")
                in ("scoped_note_context_v1", "scoped_note_context_v2")
                and contract
                == context_version(profile["source_context_policy"]).profile
                and profile.get("source_context_contract")
                == context_version(profile["source_context_policy"]).context
            )
        )
    ):
        return procedure
    return None


def evidence_profile_matches(selection, settings):
    if "evidence_profile" not in selection:
        # Historical absence is unknown only when no profile was expected.
        return not any(
            key in settings
            for key in (
                "answer_proposal_profile",
                "role_scope_policy",
                "procedure_verification_profile",
                "source_context_policy",
            )
        )
    profile = selection["evidence_profile"]
    actual_procedure = _recorded_procedure_profile(profile)
    expected_procedure = settings.get(
        "procedure_verification_profile", "all_units_nli_v1"
    )
    return (
        expected_procedure in get_args(ProcedureVerificationProfile)
        and actual_procedure is not None
        and actual_procedure == expected_procedure
        and settings.get("source_context_policy", "explicit_target_v1")
        == profile.get("source_context_policy", "explicit_target_v1")
        and all(
            setting not in settings or settings[setting] == profile.get(actual)
            for setting, actual in (
                ("answer_proposal_profile", "proposal_profile"),
                ("role_scope_policy", "role_scope_policy"),
            )
        )
    )


def runtime_configuration_error(
    response, status, settings, arm, *, require_reader=True
):
    """One online/portable authority. Non-200 authorization denials ran no reader."""
    if status != 200:
        return None
    if not isinstance(response, dict) or not isinstance(settings, dict):
        return "Runtime response/settings shape is invalid"
    trace = response.get("retrieval_trace")
    provenance = response.get("provenance")
    if trace is not None and not isinstance(trace, dict):
        return "Runtime retrieval trace is invalid"
    if provenance is not None and not isinstance(provenance, dict):
        return "Runtime provenance is invalid"
    trace, provenance = trace or {}, provenance or {}
    selection = provenance.get("answer_selection")
    if selection is not None and not isinstance(selection, dict):
        return "Runtime answer-selection metadata is invalid"
    selection = selection or {}
    expected_threshold = (
        None if arm == "candidate" else settings.get("refusal_threshold")
    )
    if not _same_runtime(expected_threshold, trace.get("refusal_threshold")):
        return "Actual refusal threshold differs"
    if (
        arm == "candidate"
        and settings.get("procedure_verification_profile")
        == "source_declared_procedure_copy_v1"
    ):
        generations = [
            value
            for value in (
                response.get("execution_mode"),
                provenance.get("generation_mode"),
            )
            if value is not None
        ]
        if not generations or any(value != "extractive" for value in generations):
            return (
                "Actual candidate procedure profile requires "
                "observed extractive generation"
            )
        if selection.get("mode") != "reader":
            return "Actual candidate procedure profile requires reader selection"
    return _selection_runtime_error(selection, settings, arm, require_reader)


def _selection_runtime_error(selection, settings, arm, require_reader):
    if arm == "baseline" and selection.get("mode") not in (None, "lexical"):
        return "Baseline must use the lexical answer selection contract"
    if (
        arm == "candidate"
        and require_reader
        and (
            selection.get("mode") != "reader"
            or "reader_null_threshold" not in settings
            or "reader_model_revision" not in settings
            or not _same_runtime(
                settings["reader_null_threshold"], selection.get("threshold")
            )
            or settings["reader_model_revision"] != selection.get("revision")
        )
    ):
        return "Actual candidate reader mode, threshold or revision differs"
    if arm == "candidate" and not support_configuration_matches(selection, settings):
        return "Actual candidate support mode/revision/margin/contract differs"
    if arm == "candidate" and not evidence_profile_matches(selection, settings):
        return "Actual candidate evidence proposal or role scope profile differs"
    return None


def check_response_configuration(row, response, status, settings, arm):
    error = runtime_configuration_error(response, status, settings, arm)
    if error:
        row.update(configuration_error=error, execution_error=True, passed=False)
        if "answer_quality_passed" in row:
            row["answer_quality_passed"] = False


def selected_runtime_settings(path: Path, report: dict, common_hash: str) -> dict:
    """Read actual selected/development/freeze files, never a report's SHA claim."""
    path = Path(path)
    if _file_hash(path) != report.get("selection_sha256"):
        raise ValueError(
            "Actual frozen selection artifact checksum differs from report"
        )
    selection = read_selection("held_out", path, common_hash)
    if selection is None or selection.get("schema_version") != 2:
        raise ValueError("Projected runtime requires a version-two frozen selection")
    settings = validate_runtime_settings(selection.get("settings"), complete=True)
    declared = validate_runtime_settings(report.get("settings"), complete=True)
    if declared != settings:
        raise ValueError(
            "Report runtime settings differ from the actual frozen selection"
        )
    return settings
