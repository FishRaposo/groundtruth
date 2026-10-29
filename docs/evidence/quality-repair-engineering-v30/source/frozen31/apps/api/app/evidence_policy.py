"""Dependency-free evidence policy; safe to import during Settings creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, get_args

if TYPE_CHECKING:
    from app.config import Settings

ProposalProfile = Literal["qa_only_v1", "qa_plus_source_patterns_v1"]
RoleScopePolicy = Literal["literal_v1", "ordinary_session_activity_v1"]
SourceContextPolicy = Literal[
    "explicit_target_v1", "scoped_note_context_v1", "scoped_note_context_v2"
]
ProcedureVerificationProfile = Literal[
    "all_units_nli_v1", "source_declared_procedure_copy_v1"
]
CURRENT_CONTRACT = "requirement-evidence-v2"
KNOWN_CONTRACTS = frozenset({"requirement-evidence-v1", CURRENT_CONTRACT})
PROFILE_CONTRACT = "evidence-profile-v1"
COMBINED_PROFILE_CONTRACT = "evidence-profile-v2"
ORIGIN_CONTRACT = "proposal-origin-v1"
ROLE_POLICY_CONTRACT = "ordinary-session-activity-role-v1"
PATTERN_REGISTRY_CONTRACT = "typed-source-patterns-v1"
MAX_PATTERN_PROPOSALS_PER_SOURCE = 3
MAX_PATTERN_PROPOSALS_PER_REQUIREMENT = 16


@dataclass(frozen=True)
class ContextVersion:
    policy: str
    profile: str
    context: str
    grammar: str
    scope: str
    inventory: str
    output: str
    method: str


_CONTEXT_VERSIONS = (
    ContextVersion(
        "scoped_note_context_v1",
        "evidence-profile-v3",
        "source-note-context-v1",
        "scoped-note-grammar-v1",
        "procedure-condition-scope-v2",
        "procedure-condition-exclusion-inventory-v2",
        "procedure-output-cover-v3",
        "contextual_source_reading_and_nli",
    ),
    ContextVersion(
        "scoped_note_context_v2",
        "evidence-profile-v4",
        "source-note-context-v2",
        "scoped-note-grammar-v2",
        "procedure-condition-scope-v3",
        "procedure-condition-exclusion-inventory-v3",
        "procedure-output-cover-v4",
        "contextual_source_reading_nli_and_exact_reference",
    ),
)


def context_version(policy: str) -> ContextVersion:
    for version in _CONTEXT_VERSIONS:
        if version.policy == policy:
            return version
    raise ValueError("Unsupported contextual source policy")


def source_free_pattern_budget(row: Any) -> bool:
    """An exact typed request count contains neither source identity nor content."""
    return (
        isinstance(row, dict)
        and set(row)
        == {
            "requirement_id",
            "origin",
            "decision",
            "observed_count",
            "complete",
            "truncated",
        }
        and isinstance(row.get("requirement_id"), str)
        and bool(row["requirement_id"])
        and row.get("origin") == "source_pattern"
        and row.get("decision") == "pattern_requirement_budget_exceeded"
        and type(row.get("observed_count")) is int
        and row["observed_count"] > MAX_PATTERN_PROPOSALS_PER_REQUIREMENT
        and row.get("complete") is False
        and row.get("truncated") is True
    )


def validate_evidence_engines(
    proposal: ProposalProfile,
    role: RoleScopePolicy,
    reader: str,
    support: str,
    *,
    procedure: ProcedureVerificationProfile = "all_units_nli_v1",
    generation: str | None = None,
    context: SourceContextPolicy = "explicit_target_v1",
) -> None:
    if proposal not in get_args(ProposalProfile) or role not in get_args(
        RoleScopePolicy
    ):
        raise ValueError("Unknown evidence proposal profile or role scope policy")
    expanded = proposal != "qa_only_v1" or role != "literal_v1"
    if expanded and (reader != "reader" or support != "local_nli"):
        raise ValueError(
            "Expanded evidence profiles require the local QA reader and local_nli; "
            "source patterns and scope policy cannot bypass either engine"
        )
    if context not in get_args(SourceContextPolicy):
        raise ValueError("Unknown source context policy")
    if (
        context != "explicit_target_v1"
        and procedure != "source_declared_procedure_copy_v1"
    ):
        raise ValueError("Contextual source reading requires source-declared copying")
    if procedure not in get_args(ProcedureVerificationProfile):
        raise ValueError("Unknown procedure verification profile")
    if procedure == "source_declared_procedure_copy_v1" and (
        reader != "reader" or support != "local_nli" or generation != "extractive"
    ):
        raise ValueError(
            "Source-declared procedure copies require reader, local_nli and "
            "extractive generation; exact-copy checks cannot bypass those engines"
        )


@dataclass(frozen=True)
class EvidencePolicy:
    proposal_profile: ProposalProfile
    role_scope_policy: RoleScopePolicy
    procedure_verification_profile: ProcedureVerificationProfile = "all_units_nli_v1"

    source_context_policy: SourceContextPolicy = "explicit_target_v1"

    @property
    def procedure_copy(self) -> bool:
        return (
            self.procedure_verification_profile == "source_declared_procedure_copy_v1"
        )

    @property
    def source_patterns(self) -> bool:
        return self.proposal_profile == "qa_plus_source_patterns_v1"

    @property
    def activity_roles(self) -> bool:
        return self.role_scope_policy == "ordinary_session_activity_v1"

    def record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "contract": COMBINED_PROFILE_CONTRACT
            if self.procedure_copy
            else PROFILE_CONTRACT,
            "proposal_profile": self.proposal_profile,
            "role_scope_policy": self.role_scope_policy,
            "origin_contract": ORIGIN_CONTRACT,
            "role_policy_contract": ROLE_POLICY_CONTRACT,
            "pattern_registry_contract": PATTERN_REGISTRY_CONTRACT
            if self.source_patterns
            else "disabled",
            "pattern_limits": {
                "per_source_requirement": MAX_PATTERN_PROPOSALS_PER_SOURCE,
                "per_requirement": MAX_PATTERN_PROPOSALS_PER_REQUIREMENT,
            },
        }
        if self.procedure_copy:
            record["procedure_verification_profile"] = (
                self.procedure_verification_profile
            )
        if self.source_context_policy != "explicit_target_v1":
            version = context_version(self.source_context_policy)
            record.update(
                contract=version.profile,
                source_context_policy=self.source_context_policy,
                source_context_contract=version.context,
            )
        return record


def resolve_evidence_policy(config: Settings) -> EvidencePolicy:
    """Capture controls once per request, including mutable library Settings."""
    validate_evidence_engines(
        config.ANSWER_PROPOSAL_PROFILE,
        config.ROLE_SCOPE_POLICY,
        config.ANSWER_SELECTION_MODE,
        config.ANSWER_SUPPORT_MODE,
        procedure=config.PROCEDURE_VERIFICATION_PROFILE,
        generation=config.GENERATION_MODE,
        context=config.SOURCE_CONTEXT_POLICY,
    )
    return EvidencePolicy(
        config.ANSWER_PROPOSAL_PROFILE,
        config.ROLE_SCOPE_POLICY,
        config.PROCEDURE_VERIFICATION_PROFILE,
        config.SOURCE_CONTEXT_POLICY,
    )
