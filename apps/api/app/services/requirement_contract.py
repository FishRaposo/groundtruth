"""One identity authority for current and historically readable requirement evidence."""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, cast

from app.evidence_policy import CURRENT_CONTRACT as CURRENT_CONTRACT
from app.evidence_policy import KNOWN_CONTRACTS as KNOWN_CONTRACTS

PROCEDURE_CONTRACT = "complete-immutable-procedure-v2"
PROCEDURE_COPY_CONTRACT = "complete-immutable-procedure-v3"
REQUIRED_INVENTORY_CONTRACT = "procedure-required-inventory-v1"
PROCEDURE_READ_SET_CONTRACT = "procedure-inspection-read-set-v1"
CONDITION_INVENTORY_CONTRACT = "procedure-condition-exclusion-inventory-v1"
CONDITION_MODEL_SETTINGS_CONTRACT = "procedure-condition-model-settings-v1"

_CONDITION_READER_FIELDS = (
    "mode",
    "model",
    "revision",
    "threshold",
    "max_length",
    "stride",
    "n_best",
    "max_span_tokens",
)
_CONDITION_SUPPORT_FIELDS = (
    "mode",
    "model",
    "revision",
    "license",
    "minimum_entailment_margin",
    "max_pair_tokens",
    "batch_size",
    "device",
    "score_semantics",
)


def condition_model_settings(reader, support, reader_options, profile, generation):
    """Capture stable inference settings; runtime readiness/paths are not proof."""
    return {
        "contract": CONDITION_MODEL_SETTINGS_CONTRACT,
        "generation_mode": generation,
        "evidence_profile": profile,
        "reader": {
            key: {**reader, **reader_options}.get(key)
            for key in _CONDITION_READER_FIELDS
        },
        "support": {key: support.get(key) for key in _CONDITION_SUPPORT_FIELDS},
    }


def valid_condition_model_settings(settings, selection) -> bool:  # noqa: C901 - historical settings, never current model readiness
    from app.reader_catalog import get_reader_spec
    from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

    try:
        if settings != condition_model_settings(
            selection,
            selection["evidence_support"],
            selection,
            selection["evidence_profile"],
            "extractive",
        ):
            return False
        reader, support = settings["reader"], settings["support"]
        spec = get_reader_spec(reader["revision"])
        if reader["mode"] != "reader" or reader["model"] != spec.model:
            return False
        if any(
            support[key] != value
            for key, value in {
                "mode": "local_nli",
                "model": NLI.model,
                "revision": NLI.revision,
                "license": NLI.license,
                "device": "cpu",
                "max_pair_tokens": MAX_PAIR_TOKENS,
                "batch_size": BATCH_SIZE,
                "score_semantics": (
                    "raw contradiction/entailment/neutral logits; uncalibrated"
                ),
            }.items()
        ):
            return False
        margin = support["minimum_entailment_margin"]
        threshold = reader["threshold"]
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in (margin, threshold)
            )
            or not 0 <= margin <= 4
        ):
            return False
        return all(
            type(reader[key]) is int and low <= reader[key] <= high
            for key, low, high in (
                ("max_length", 128, 512),
                ("stride", 0, 256),
                ("n_best", 1, 100),
                ("max_span_tokens", 1, 128),
            )
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def valid_condition_assessment(assessment, settings) -> bool:
    """Recompute the captured NLI decision without inference or asset access."""
    try:
        logits = assessment["logits"]
        if (
            not isinstance(logits, (list, tuple))
            or len(logits) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in logits
            )
        ):
            return False
        contradiction, entailment, neutral = logits
        margin = entailment - max(contradiction, neutral)
        recorded = assessment["entailment_margin"]
        tokens = assessment["pair_tokens"]
        return (
            assessment["label"] == "entailment"
            and assessment["supported"] is True
            and type(tokens) is int
            and 0 < tokens <= settings["support"]["max_pair_tokens"]
            and not isinstance(recorded, bool)
            and isinstance(recorded, (int, float))
            and math.isfinite(recorded)
            and recorded == margin
            and margin > 0
            and margin >= settings["support"]["minimum_entailment_margin"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def requirement_record(selection: dict[str, Any]) -> bool:
    contract = selection.get("contract")
    return (
        isinstance(contract, str) and contract.startswith("requirement-evidence-")
    ) or any(
        key in selection
        for key in ("requirements", "inspected_sources", "procedure_contexts")
    )


def validate_discovery_lineage(selection: dict[str, Any]) -> dict[str, Any]:  # noqa: C901 - strict cross-linked historical certificate
    """Validate recorded discovery only; never retrocertify old history or support."""
    from app.evidence_policy import (
        ORIGIN_CONTRACT,
        EvidencePolicy,
        ProcedureVerificationProfile,
        ProposalProfile,
        RoleScopePolicy,
        SourceContextPolicy,
    )
    from app.services.source_pattern_proposals import PATTERN_IDS

    profile = selection.get("evidence_profile")
    if profile is None:
        return {"status": "legacy_unrecorded", "valid": None}
    invalid = {"status": "invalid", "valid": False}
    if not isinstance(profile, dict):
        return invalid
    proposal_profile = profile.get("proposal_profile")
    role_policy = profile.get("role_scope_policy")
    procedure_profile = profile.get(
        "procedure_verification_profile", "all_units_nli_v1"
    )
    if procedure_profile not in {
        "all_units_nli_v1",
        "source_declared_procedure_copy_v1",
    }:
        return invalid
    if not isinstance(proposal_profile, str) or not isinstance(role_policy, str):
        return invalid
    if proposal_profile not in {
        "qa_only_v1",
        "qa_plus_source_patterns_v1",
    } or role_policy not in {"literal_v1", "ordinary_session_activity_v1"}:
        return invalid
    context_policy = profile.get("source_context_policy", "explicit_target_v1")
    if (
        not isinstance(context_policy, str)
        or context_policy
        not in {
            "explicit_target_v1",
            "scoped_note_context_v1",
            "scoped_note_context_v2",
        }
        or (
            context_policy != "explicit_target_v1"
            and procedure_profile != "source_declared_procedure_copy_v1"
        )
    ):
        return invalid
    expected = EvidencePolicy(
        cast(ProposalProfile, proposal_profile),
        cast(RoleScopePolicy, role_policy),
        cast(ProcedureVerificationProfile, procedure_profile),
        cast(SourceContextPolicy, context_policy),
    ).record()
    if profile != expected:
        return invalid
    proposals, observations = (
        selection.get("proposals"),
        selection.get("qa_observations"),
    )
    if not isinstance(proposals, (list, tuple)) or not isinstance(
        observations, (list, tuple)
    ):
        return invalid
    observed = {}
    for item in observations:
        if not isinstance(item, dict) or not isinstance(
            item.get("observation_id"), str
        ):
            return invalid
        if item["observation_id"] in observed or not isinstance(
            item.get("diagnostics"), dict
        ):
            return invalid
        observed[item["observation_id"]] = item
    identities = selection.get("inspected_sources", [])
    if not isinstance(identities, list):
        return invalid
    known = {
        item.get("chunk_id"): item for item in identities if isinstance(item, dict)
    }
    proposed = {}
    for proposal in proposals:
        if (
            not isinstance(proposal, dict)
            or proposal.get("contract") != ORIGIN_CONTRACT
        ):
            return invalid
        identifier = proposal.get("proposal_id")
        if not isinstance(identifier, str) or not identifier or identifier in proposed:
            return invalid
        if not isinstance(proposal.get("chunk_id"), str):
            return invalid
        identity = known.get(proposal.get("chunk_id"))
        if identity is None or any(
            proposal.get(key) != identity.get(key)
            for key in ("document_id", "document_version", "content_hash")
        ):
            return invalid
        text = proposal.get("text")
        if not isinstance(text, str) or not text:
            return invalid
        ranges = [proposal.get("chunk_range"), proposal.get("document_range")]
        if any(
            not isinstance(interval, dict)
            or type(interval.get("start")) is not int
            or type(interval.get("end")) is not int
            or interval["start"] < 0
            or interval["end"] - interval["start"] != len(text)
            for interval in ranges
        ):
            return invalid
        if (
            type(proposal.get("document_version")) is not int
            or proposal["document_version"] < 1
        ):
            return invalid
        if (
            not isinstance(proposal.get("content_hash"), str)
            or re.fullmatch(r"[a-f0-9]{64}", proposal["content_hash"]) is None
        ):
            return invalid
        if proposal.get("origin") == "source_pattern":
            from app.evidence_policy import PATTERN_REGISTRY_CONTRACT

            if (
                proposal_profile != "qa_plus_source_patterns_v1"
                or not isinstance(proposal.get("pattern_id"), str)
                or proposal.get("pattern_id") not in PATTERN_IDS
                or proposal.get("grammar_version") != PATTERN_REGISTRY_CONTRACT
                or proposal.get("qa_observation_id") is not None
                or any(
                    key in proposal
                    for key in ("null_margin", "reader_score", "supported", "logits")
                )
            ):
                return invalid
        elif proposal.get("origin") == "qa_reader":
            if not isinstance(proposal.get("qa_observation_id"), str):
                return invalid
            observation = observed.get(proposal.get("qa_observation_id"))
            if (
                observation is None
                or observation.get("requirement_id") != proposal.get("requirement_id")
                or observation.get("chunk_id") != proposal.get("chunk_id")
                or not isinstance(observation.get("span"), dict)
                or proposal.get("pattern_id") is not None
                or proposal.get("grammar_version") is not None
            ):
                return invalid
            from app.services.evidence_proposals import qa_raw_candidates

            try:
                raw_candidates = qa_raw_candidates(observation["diagnostics"])
            except (TypeError, KeyError):
                return invalid
            if not all(isinstance(item, dict) for item in raw_candidates):
                return invalid
            if not any(
                item.get("start") == proposal["chunk_range"]["start"]
                and item.get("end") == proposal["chunk_range"]["end"]
                and item.get("text", text) == text
                for item in raw_candidates
            ):
                return invalid
        else:
            return invalid
        proposed[identifier] = proposal
    selected_ids = selection.get("selected_proposal_ids", [])
    if not isinstance(selected_ids, (list, tuple)) or any(
        not isinstance(identifier, str) or identifier not in proposed
        for identifier in selected_ids
    ):
        return invalid
    requirements = selection.get("requirements", [])
    if not isinstance(requirements, list):
        return invalid
    for requirement in requirements:
        if not isinstance(requirement, dict):
            return invalid
        if requirement.get("status") != "supported":
            continue
        if requirement.get("kind") == "procedure" and not _raw_seed_lineage(
            requirement.get("procedure_completeness"),
            proposed,
            requirement.get("id"),
            known,
            selection.get("procedure_contexts", []),
        ):
            return invalid
        requirement_witnesses = requirement.get("witnesses", [])
        if not isinstance(requirement_witnesses, list):
            return invalid
        for witness in requirement_witnesses:
            if not isinstance(witness, dict):
                return invalid
            if witness.get(
                "procedure_completeness"
            ) is not None and not _raw_seed_lineage(
                witness["procedure_completeness"],
                proposed,
                requirement.get("id"),
                known,
                selection.get("procedure_contexts", []),
            ):
                return invalid
            origins = witness.get("proposals")
            if not isinstance(origins, list) or not origins:
                return invalid
            if any(
                not isinstance(item, dict)
                or proposed.get(item.get("proposal_id")) != item
                or item.get("requirement_id") != requirement.get("id")
                for item in origins
            ):
                return invalid
            if any(
                not _proposal_witness_mapping(
                    item, witness, selection.get("procedure_contexts", [])
                )
                for item in origins
            ):
                return invalid
    return {"status": "recorded", "valid": True}


def _same_document(first, second) -> bool:
    return all(
        type(first.get(key)) is type(second.get(key))
        and first.get(key) == second.get(key)
        for key in ("document_id", "document_version", "content_hash")
    )


def _raw_seed_lineage(proof, proposals, requirement_id, known, contexts) -> bool:
    if not isinstance(proof, dict) or not isinstance(proof.get("raw_seed"), dict):
        return False
    raw = proof["raw_seed"]
    identifier = raw.get("proposal_id")
    if not isinstance(identifier, str):
        return False
    proposal = proposals.get(identifier)
    return (
        isinstance(proposal, dict)
        and proposal.get("requirement_id") == requirement_id
        and _same_document(proof, proposal)
        and _procedure_fragments_lineage(proof, known, contexts)
        and all(
            raw.get(key) == proposal.get(key)
            for key in ("origin", "chunk_id", "text", "chunk_range", "document_range")
        )
    )


def _procedure_fragments_lineage(proof, known, contexts) -> bool:
    """Every projected carrier belongs to this captured immutable document."""
    fragments = proof.get("fragments")
    if (
        not isinstance(fragments, list)
        or not fragments
        or not isinstance(contexts, list)
    ):
        return False
    sources = [
        source
        for context in contexts
        if isinstance(context, dict) and _same_document(context, proof)
        for source in context.get("sources", [])
        if isinstance(source, dict)
    ]
    for part in fragments:
        if not isinstance(part, dict):
            return False
        identity = known.get(part.get("chunk_id"))
        if not isinstance(identity, dict) or not _same_document(identity, proof):
            return False
        if not any(
            source.get("chunk_id") == part.get("chunk_id")
            and _same_document(source, proof)
            and _fragment_in_source(part, source)
            for source in sources
        ):
            return False
    return True


def _fragment_in_source(part, source) -> bool:
    interval = source.get("document_range")
    points = [
        part.get(key)
        for key in ("chunk_start", "chunk_end", "document_start", "document_end")
    ]
    if not isinstance(interval, dict) or not all(
        type(point) is int for point in points
    ):
        return False
    first, last = interval.get("start"), interval.get("end")
    return (
        type(first) is int
        and type(last) is int
        and 0 <= points[0] < points[1] <= last - first
        and points[2] == first + points[0]
        and points[3] == first + points[1]
    )


def _proposal_witness_mapping(
    proposal: dict[str, Any], witness: dict[str, Any], contexts
) -> bool:
    if not _same_document(proposal, witness):
        return False
    span, document = witness.get("span"), witness.get("document_range")
    if not isinstance(span, dict) or not isinstance(document, dict):
        return False
    text = span.get("text")
    first, last = span.get("start"), span.get("end")
    left, right = document.get("start"), document.get("end")
    if (
        not isinstance(text, str)
        or type(first) is not int
        or type(last) is not int
        or type(left) is not int
        or type(right) is not int
        or first < 0
        or left < 0
        or last - first != len(text)
        or right - left != len(text)
    ):
        return False
    proof = witness.get("procedure_completeness")
    if proof is not None and not _procedure_witness_mapping(witness, proof):
        return False
    if proposal.get("chunk_id") != witness.get("chunk_id"):
        return _procedure_proposal_mapping(proposal, witness, contexts)
    local, origin = proposal["chunk_range"], proposal["document_range"]
    return (
        first <= local["start"] < local["end"] <= last
        and text[local["start"] - first : local["end"] - first] == proposal["text"]
        and origin["start"] == left + local["start"] - first
        and origin["end"] == left + local["end"] - first
    )


def _procedure_witness_mapping(witness, proof) -> bool:
    if not isinstance(proof, dict) or not _same_document(proof, witness):
        return False
    fragments = proof.get("fragments", [])
    own = [
        part for part in fragments if part.get("chunk_id") == witness.get("chunk_id")
    ]
    if len(own) != 1:
        return False
    part = own[0]
    span, document = witness["span"], witness["document_range"]
    return (span["start"], span["end"]) == (
        part["chunk_start"],
        part["chunk_end"],
    ) and (document["start"], document["end"]) == (
        part["document_start"],
        part["document_end"],
    )


def _procedure_proposal_mapping(proposal, witness, contexts) -> bool:
    """A different seed uses its own original immutable source-context mapping.

    Overlapping originals can carry the same raw seed while the projected cover
    uses a later part of one of them. The cover is not the raw proposal mapping.
    """
    proof = witness.get("procedure_completeness")
    if not isinstance(proof, dict):
        return False
    origin = proposal["document_range"]
    local = proposal["chunk_range"]
    extent = proof.get("extent", {})
    value = witness.get("value")
    if (
        not isinstance(value, str)
        or type(extent.get("start")) is not int
        or not extent["start"]
        <= origin["start"]
        < origin["end"]
        <= extent["start"] + len(value)
    ):
        return False
    return any(
        source.get("chunk_id") == proposal["chunk_id"]
        and _same_document(source, proposal)
        and _fragment_in_source(
            {
                "chunk_start": local["start"],
                "chunk_end": local["end"],
                "document_start": origin["start"],
                "document_end": origin["end"],
            },
            source,
        )
        and value[origin["start"] - extent["start"] : origin["end"] - extent["start"]]
        == proposal["text"]
        for context in contexts
        if isinstance(context, dict) and _same_document(context, proposal)
        for source in context.get("sources", [])
        if isinstance(source, dict)
    )


def validate_role_scope_evidence(selection: dict[str, Any]) -> dict[str, Any]:  # noqa: C901 - fail closed on captured policy certificates
    """Validate the captured contract, without current-policy/model inference."""
    from app.evidence_policy import ROLE_POLICY_CONTRACT
    from app.services.role_scope_inspection import ROLE_READ_SET_CONTRACT

    invalid = {"status": "invalid", "valid": False}
    profile = selection.get("evidence_profile")
    if not isinstance(profile, dict):
        if any(
            selection.get(name)
            for name in (
                "role_scope_read_set",
                "role_scope_interpretations",
                "role_scope_findings",
            )
        ):
            return invalid
        return {"status": "legacy_unrecorded", "valid": None}
    requirements = selection.get("requirements", [])
    if not isinstance(requirements, list):
        return invalid
    interpretations = selection.get("role_scope_interpretations", [])
    findings = selection.get("role_scope_findings", [])
    read_set = selection.get("role_scope_read_set", {})
    if (
        not isinstance(interpretations, list)
        or not isinstance(findings, list)
        or not isinstance(read_set, dict)
    ):
        return invalid
    for requirement in requirements:
        if not isinstance(requirement, dict):
            return invalid
        record = requirement.get("role_scope_interpretation")
        needed = (
            requirement.get("status") == "supported"
            and requirement.get("kind") in {"owner", "deputy"}
            and re.search(r"\bsessions?\b", requirement.get("original_text", ""))
            and profile.get("role_scope_policy") == "ordinary_session_activity_v1"
        )
        if record is None:
            if needed:
                return invalid
            continue
        constraint = requirement.get("source_workspace")
        if constraint is not None and (
            not isinstance(constraint, str) or not constraint.strip()
        ):
            return invalid
        if (
            not isinstance(record, dict)
            or record.get("contract") != ROLE_POLICY_CONTRACT
            or profile.get("role_scope_policy") != "ordinary_session_activity_v1"
            or record not in interpretations
            or record.get("requirement_id") != requirement.get("id")
            or record.get("original_text") != requirement.get("original_text")
            or record.get("input_range") != requirement.get("input_range")
            or record.get("kind") != requirement.get("kind")
            or record.get("source_workspace") != constraint
        ):
            return invalid
        scope = record.get("effective_scope")
        if scope not in {"activity", "session"} or record.get(
            "activity_fallback"
        ) is not (scope == "activity"):
            return invalid
        if any(
            not isinstance(record.get(key), str) or not record[key].strip()
            for key in (
                "requested_scope",
                "session_scope",
                "activity_scope",
                "prepared_question",
            )
        ):
            return invalid
        role = "lead" if record["kind"] == "owner" else "deputy"
        disclosure = (
            (
                f"Activity scope: the documented {role} for "
                f"{record['activity_scope']} is used "
                "for this ordinary-session question. The source documents an activity "
                "role, rather than a separate session assignment."
            )
            if scope == "activity"
            else None
        )
        if (
            record.get("disclosure") != disclosure
            or record.get("basis")
            != (
                "activity_role"
                if scope == "activity"
                else "documented_session_assignment"
            )
            or requirement.get("prepared_question") != record["prepared_question"]
            or record.get("effective_target")
            != (
                record["activity_scope"]
                if scope == "activity"
                else record["requested_scope"]
            )
        ):
            return invalid
        if requirement.get("status") == "supported":
            matching = [
                item
                for item in findings
                if isinstance(item, dict)
                and item.get("requirement_id") == requirement["id"]
            ]
            if (
                read_set.get("contract") != ROLE_READ_SET_CONTRACT
                or read_set.get("complete") is not True
                or read_set.get("reason") is not None
                or read_set.get("after_proofs", {}).get("consistent") is not True
                or len(matching) != 1
                or matching[0].get("complete") is not True
            ):
                return invalid
            documents = read_set.get("documents")
            if not isinstance(documents, list):
                return invalid
            expected_ids = {
                item.get("document_id") for item in documents if isinstance(item, dict)
            }
            if len(expected_ids) != len(documents):
                return invalid
            contexts = matching[0].get("contexts", [])
            if (
                not isinstance(contexts, list)
                or len(contexts) != len(documents)
                or {
                    item.get("document_id")
                    for item in contexts
                    if isinstance(item, dict)
                }
                != expected_ids
            ):
                return invalid
            if any(
                not isinstance(item, dict) or item.get("disposition") == "unresolved"
                for item in contexts
            ):
                return invalid
            captured = {item["document_id"]: item for item in documents}
            for context in contexts:
                origin = captured[context["document_id"]]
                if any(
                    context.get(key) != origin.get(key)
                    for key in (
                        "document_version",
                        "content_hash",
                        "workspace_id",
                        "owner_id",
                        "snapshot_id",
                        "snapshot_chunk_hash",
                        "live_chunk_hash",
                        "metadata_hash",
                    )
                ):
                    return invalid
                if not _role_context_body_valid(
                    context, origin, record.get("source_workspace")
                ):
                    return invalid
            if any(
                not any(
                    witness.get("document_id") == document.get("document_id")
                    and witness.get("document_version")
                    == document.get("document_version")
                    and witness.get("content_hash") == document.get("content_hash")
                    for document in documents
                )
                for witness in requirement.get("witnesses", [])
            ):
                return invalid
    return {"status": "recorded", "valid": True}


def _role_context_body_valid(context, origin, source_workspace) -> bool:
    import hashlib

    body, units = context.get("body"), context.get("units")
    if (
        not isinstance(body, str)
        or not isinstance(units, list)
        or context.get("body_length") != len(body)
        or hashlib.sha256(body.encode()).hexdigest() != origin.get("content_hash")
    ):
        return False
    if context.get("disposition") == "requested_workspace_excluded":
        return (
            isinstance(source_workspace, str)
            and source_workspace != origin.get("workspace_id")
            and units == []
        )
    if context.get("disposition") != "classified":
        return False
    cursor = 0
    known = {
        "activity_assignment",
        "session_assignment",
        "irrelevant_typed_assignment",
        "irrelevant_typed_role",
        "irrelevant_typed_attribute",
        "irrelevant_typed_procedure",
    }
    for unit in units:
        if not isinstance(unit, dict) or unit.get("disposition") not in known:
            return False
        interval = _range(unit.get("source_range"), len(body))
        if (
            interval is None
            or interval[0] < cursor
            or body[cursor : interval[0]].strip()
            or body[interval[0] : interval[1]] != unit.get("text")
        ):
            return False
        cursor = interval[1]
    return not body[cursor:].strip()


def _range(value: Any, limit: int) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    first, last = value.get("start"), value.get("end")
    if type(first) is int and type(last) is int and 0 <= first < last <= limit:
        return first, last
    return None


def numbered_seed_core(
    clause: Any, raw_text: Any, raw_range: Any, length: int
) -> tuple[int, int] | None:
    """Derive the original raw's core; only a complete source clause can match.

    All lengths/offsets use Python source-codepoint coordinates. Whitespace
    follows str.isspace, as does the source parser; no internal normalization,
    case folding, inferred punctuation or accepted-raw rewriting is performed.
    """
    if not isinstance(clause, dict) or not isinstance(raw_text, str):
        return None
    interval = _range(clause.get("source_range"), length)
    raw = _range(raw_range, length)
    text = clause.get("text")
    if (
        clause.get("unit_name") != "step_1_action_1"
        or interval is None
        or raw is None
        or not isinstance(text, str)
        or not text
        or text != text.strip()
        or len(text) != interval[1] - interval[0]
        or len(raw_text) != raw[1] - raw[0]
    ):
        return None
    core = raw_text.strip()
    first = raw[0] + len(raw_text) - len(raw_text.lstrip())
    last = raw[1] - (len(raw_text) - len(raw_text.rstrip()))
    if core == text and (first, last) == interval:
        return first, last
    if text[-1] in ".!?":
        without_punctuation = text[:-1].rstrip()
        if (
            without_punctuation
            and core == without_punctuation
            and (first, last) == (interval[0], interval[0] + len(without_punctuation))
        ):
            return first, last
    return None


def _extent_identity(proof: dict[str, Any]) -> tuple[int, int, int] | None:
    uuid.UUID(proof["document_id"])
    length = proof["body_length"]
    if (
        type(proof["document_version"]) is not int
        or proof["document_version"] <= 0
        or not re.fullmatch(r"[a-f0-9]{64}", proof["content_hash"])
        or type(length) is not int
        or length <= 0
    ):
        return None
    extent = _range(proof["extent"], length)
    if extent is None:
        return None
    first, last = extent
    closure = proof["closure"]
    if closure["end"] != last:
        return None
    if closure["kind"] == "immutable_eof":
        return (first, last, length) if last == length else None
    if closure["kind"] in {"independent_section", "declared_paragraph_end"}:
        boundary = _range(closure["boundary_range"], length)
        return (
            (first, last, length)
            if boundary is not None and boundary[0] >= last
            else None
        )
    return None


def _steps_valid(proof: dict[str, Any], first: int, last: int) -> bool:
    steps = proof["step_ranges"]
    if proof.get("structure") in {"narrative", "declared_paragraphs"}:
        return proof["step_count"] is None and steps == []
    if (
        proof.get("structure") != "numbered"
        or type(proof["step_count"]) is not int
        or not isinstance(steps, list)
        or not 1 <= proof["step_count"] == len(steps) <= 32
    ):
        return False
    cursor = steps[0]["start"]
    for ordinal, step in enumerate(steps, 1):
        interval = _range(step, last)
        if (
            step["ordinal"] != ordinal
            or interval is None
            or interval[0] != cursor
            or cursor < first
        ):
            return False
        cursor = interval[1]
    return cursor == last


def _units_valid(proof: dict[str, Any], length: int) -> bool:
    units = proof["proof_units"]
    if (
        not isinstance(units, list)
        or type(proof["mandatory_proof_count"]) is not int
        or not 1 <= proof["mandatory_proof_count"] == len(units) <= 64
    ):
        return False
    names = set()
    for unit in units:
        tokens, margin = unit["pair_tokens"], unit["entailment_margin"]
        if (
            not isinstance(unit["name"], str)
            or unit["name"] in names
            or not isinstance(unit["hypothesis"], str)
            or not unit["hypothesis"]
            or unit["supported"] is not True
            or unit["label"] != "entailment"
            or type(tokens) is not int
            or not 0 < tokens <= 512
            or _range(unit["source_range"], length) is None
            or _range(unit["premise_range"], length) is None
            or isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(margin)
            or margin <= 0
        ):
            return False
        names.add(unit["name"])
    return True


def _joins_valid(proof: dict[str, Any], first: int, last: int) -> bool:
    units, edges = proof["proof_units"], proof["structure_edges"]
    if not isinstance(edges, list) or len(edges) > 64:
        return False
    if proof.get("structure") == "declared_paragraphs":
        return _declared_record_valid(proof)
    if proof.get("structure") == "narrative":
        whole = [u for u in units if u["kind"] == "whole_method"]
        return (
            len(whole) == 1
            and whole[0]["source_range"] == {"start": first, "end": last}
            and not edges
        )
    names = {u["name"] for u in units}
    kinds = {u["name"]: u["kind"] for u in units}
    namespace = {
        "name": "namespace_to_applicability",
        "source": "namespace",
        "target": "applicability",
    }
    if (
        not {"namespace", "applicability", "requested_scope"}.issubset(names)
        or any(
            kinds.get(name) != kind
            for name, kind in (
                ("namespace", "namespace"),
                ("applicability", "applicability"),
                ("requested_scope", "request_scope"),
            )
        )
        or edges.count(namespace) != 1
    ):
        return False
    for unit in units:
        if unit["kind"] in {"instruction", "prohibition"}:
            joins = [e for e in edges if e.get("target") == unit["name"]]
            if (
                len(joins) != 1
                or joins[0].get("name")
                not in {"namespace_to_action", "applicability_to_action"}
                or joins[0].get("source") not in {"namespace", "applicability"}
            ):
                return False
    return True


def _required_step_valid(requirement, inventory, interval) -> bool:
    step = requirement["step"]
    if inventory["structure"] == "declared_paragraphs":
        return step is None  # Exact ranges/premises are independently replayed.
    if (
        requirement["kind"] not in {"instruction", "prohibition"}
        or inventory["structure"] != "numbered"
    ):
        return (
            step is None and requirement["premise_range"] == requirement["source_range"]
        )
    if step is None:
        return (
            interval[1] <= inventory["step_ranges"][0]["start"]
            and requirement["premise_range"] == requirement["source_range"]
        )
    if type(step) is not int or not 1 <= step <= len(inventory["step_ranges"]):
        return False
    parent = inventory["step_ranges"][step - 1]
    joins = [
        e
        for e in inventory["structure_edges"]
        if e.get("target") == requirement["name"]
    ]
    return (
        parent["start"] <= interval[0] < interval[1] <= parent["end"]
        and requirement["premise_range"]
        == {"start": parent["start"], "end": parent["end"]}
        and len(joins) == 1
        and joins[0].get("step") == step
    )


def _inventory_valid(proof: dict[str, Any], length: int) -> bool:
    """Every source-planned obligation needs its own exact assessed discharge.

    The inventory is generated before inference, not inferred from the proof
    units remaining in a record. This is record consistency, not a public
    cryptographic attestation of source truth.
    """
    inventory = proof["required_inventory"]
    if (
        not isinstance(inventory, dict)
        or inventory.get("contract") != REQUIRED_INVENTORY_CONTRACT
    ):
        return False
    if any(
        inventory.get(key) != proof.get(key)
        for key in (
            "document_id",
            "workspace_id",
            "document_version",
            "content_hash",
            "extent",
            "structure",
            "step_ranges",
        )
    ):
        return False
    required = inventory["units"]
    if (
        not isinstance(required, list)
        or not 1 <= len(required) <= 64
        or len(required) != len(proof["proof_units"])
    ):
        return False
    if inventory["structure_edges"] != proof["structure_edges"]:
        return False
    associated = set()
    for requirement, assessed in zip(required, proof["proof_units"], strict=True):
        if (
            not isinstance(requirement, dict)
            or any(
                requirement.get(key) != assessed.get(key)
                for key in (
                    "name",
                    "kind",
                    "source_range",
                    "premise_range",
                    "hypothesis",
                )
            )
            or (
                "step" in assessed
                and (
                    assessed["step"] != requirement["step"]
                    or type(assessed["step"]) is not type(requirement["step"])
                )
            )
        ):
            return False
        interval = _range(requirement["source_range"], length)
        if interval is None:
            return False
        if not _required_step_valid(requirement, inventory, interval):
            return False
        if requirement["step"] is not None:
            associated.add(requirement["step"])
    return inventory["structure"] in {
        "narrative",
        "declared_paragraphs",
    } or associated == set(range(1, len(inventory["step_ranges"]) + 1))


def _numbered_seed_valid(proof, length, raw, local) -> bool:
    inventory, seed = proof["required_inventory"], proof["raw_seed"]
    clause = inventory["seed_clause"]
    unit = next((u for u in inventory["units"] if u["name"] == "step_1_action_1"), None)
    if (
        unit is None
        or unit["kind"] not in {"instruction", "prohibition"}
        or type(unit["step"]) is not int
        or unit["step"] != 1
        or clause["source_range"] != unit["source_range"]
        or numbered_seed_core(clause, seed["text"], seed["document_range"], length)
        is None
        or len(seed["text"]) != local[1] - local[0]
    ):
        return False
    step = proof["step_ranges"][0]
    return step["start"] <= raw[0] < raw[1] <= step["end"]


def _cover_valid(proof: dict[str, Any], first: int, last: int, length: int) -> bool:
    fragments = proof["fragments"]
    if not isinstance(fragments, list) or not fragments or len(fragments) > 64:
        return False
    cursor = first
    for part in fragments:
        uuid.UUID(part["chunk_id"])
        points = [
            part[k]
            for k in ("chunk_start", "chunk_end", "document_start", "document_end")
        ]
        if (
            not all(type(p) is int for p in points)
            or not 0 <= points[0] < points[1]
            or points[2] != cursor
            or not cursor < points[3] <= last
            or points[1] - points[0] != points[3] - points[2]
        ):
            return False
        cursor = points[3]
    seed = proof["raw_seed"]
    raw, local = (
        _range(seed["document_range"], length),
        _range(seed["chunk_range"], length),
    )
    if cursor != last or raw is None or local is None:
        return False
    origin = [p for p in fragments if p["chunk_id"] == seed["chunk_id"]]
    if (
        len(origin) != 1
        or not origin[0]["document_start"]
        <= raw[0]
        < raw[1]
        <= origin[0]["document_end"]
        or not origin[0]["chunk_start"] <= local[0] < local[1] <= origin[0]["chunk_end"]
        or raw[0] - local[0] != origin[0]["document_start"] - origin[0]["chunk_start"]
        or raw[1] - local[1] != origin[0]["document_start"] - origin[0]["chunk_start"]
    ):
        return False
    if proof["structure"] == "numbered":
        return _numbered_seed_valid(proof, length, raw, local)
    if proof["structure"] == "declared_paragraphs":
        from app.services.procedure_paragraphs import parse, seed_matches

        parsed = parse(
            proof["required_inventory"]["declared_paragraphs"]["source_body"]
        )
        return (
            parsed is not None
            and seed_matches(parsed, seed["text"], raw)
            and len(seed["text"]) == local[1] - local[0]
        )
    return any(
        u["kind"] in {"instruction", "prohibition", "whole_method"}
        and u["source_range"]["start"] <= raw[0] < raw[1] <= u["source_range"]["end"]
        for u in proof["proof_units"]
    )


def _declared_record_valid(proof):
    """Reparse the immutable source; never derive obligations from assessments."""
    import hashlib

    from app.services.procedure_paragraphs import parse, scope_matches, unit_specs

    inventory = proof["required_inventory"]
    descriptor = inventory["declared_paragraphs"]
    body = descriptor["source_body"]
    topic, original = descriptor["request_topic"], descriptor["request_original"]
    if (
        not isinstance(body, str)
        or len(body) != proof["body_length"]
        or hashlib.sha256(body.encode()).hexdigest() != proof["content_hash"]
        or not isinstance(topic, str)
        or not topic
        or not isinstance(original, str)
        or not original
    ):
        return False
    parsed = parse(body)
    if (
        parsed is None
        or not scope_matches(parsed, topic)
        or descriptor != parsed.record(topic, original)
    ):
        return False
    units, edges = unit_specs(parsed, topic, original)
    return (
        proof["extent"] == {"start": parsed.start, "end": parsed.end}
        and proof["closure"]
        == {
            "kind": "declared_paragraph_end",
            "end": parsed.end,
            "boundary_range": {
                "start": parsed.end_marker[0],
                "end": parsed.end_marker[1],
            },
        }
        and inventory["units"] == units
        and proof["structure_edges"] == edges
    )


def complete_procedure(
    proof: Any,
    *,
    question=None,
    answer=None,
    citations=None,
    requirement=None,
    source_snapshots=None,
    selection=None,
    query_context=None,
) -> bool:
    """Validate recorded completeness, never retrocertify historical claims."""
    from app.services.procedure_output import COPY_CONTRACT, has_v3, verify_output

    if (isinstance(proof, dict) and proof.get("contract") == COPY_CONTRACT) or has_v3(
        None, query_context=query_context
    ):
        if (
            not isinstance(proof, dict)
            or proof.get("contract") != COPY_CONTRACT
            or not isinstance(selection, dict)
            or not isinstance(selection.get("requirements"), list)
            or not any(
                isinstance(row, dict) and row.get("procedure_completeness") == proof
                for row in selection.get("requirements", [])
            )
        ):
            return False
        return verify_output(
            selection,
            question=question,
            answer=answer,
            citations=citations,
            source_snapshots=source_snapshots,
            query_context=query_context,
        )
    try:
        if (
            not isinstance(proof, dict)
            or proof.get("contract") != PROCEDURE_CONTRACT
            or proof.get("status") != "supported"
            or proof.get("coverage_complete") is not True
        ):
            return False
        identity = _extent_identity(proof)
        if identity is None:
            return False
        first, last, length = identity
        return (
            _steps_valid(proof, first, last)
            and _units_valid(proof, length)
            and _joins_valid(proof, first, last)
            and _inventory_valid(proof, length)
            and _cover_valid(proof, first, last, length)
        )
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return False


def procedure_completeness(
    selection: dict[str, Any],
    *,
    question=None,
    answer=None,
    citations=None,
    source_snapshots=None,
    query_context=None,
) -> bool | None:
    from app.services.procedure_output import has_v3, verify_output

    if has_v3(selection, query_context=query_context):
        return selection.get("contract") == CURRENT_CONTRACT and verify_output(
            selection,
            question=question,
            answer=answer,
            citations=citations,
            source_snapshots=source_snapshots,
            query_context=query_context,
        )
    rows = selection.get("requirements", [])
    procedures = [
        r
        for r in rows
        if r.get("kind") == "procedure" and r.get("status") == "supported"
    ]
    if not procedures:
        return None
    if selection.get("contract") != CURRENT_CONTRACT:
        return False  # Readable historical v1 is never retrocertified complete.
    for row in procedures:
        proof = row.get("procedure_completeness")
        if not complete_procedure(proof):
            return False
        if isinstance(proof, dict) and proof.get("structure") == "declared_paragraphs":
            if proof.get("required_inventory", {}).get("declared_paragraphs", {}).get(
                "request_original"
            ) != row.get("original_text"):
                return False
    return True
