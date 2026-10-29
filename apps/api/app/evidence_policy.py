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
QuantityVerificationProfile = Literal["legacy_v1", "literal_source_count_v1"]
SourceGovernanceProfile = Literal["all_sources_v1", "requirement_bound_v1"]
ProcedureScopeProfile = Literal[
    "requested_scope_v1", "activity_quote_v1", "activity_quote_v2"
]
ACTIVITY_PROCEDURE_QUOTE_CONTRACT = "activity-procedure-quote-v1"
ACTIVITY_INSTRUCTION_QUOTE_CONTRACT = "activity-procedure-quote-v2"
SOURCE_BOUND_PROFILE_CONTRACT = "evidence-profile-v10"
SOURCE_BOUND_GOVERNANCE_CONTRACT = "source-bound-witness-scope-v1"
SOURCE_BOUND_OUTPUT_CONTRACT = "procedure-output-cover-v10"
_SOURCE_GOVERNANCE_VERSIONS = {
    "requirement_bound_v1": {
        "contract": SOURCE_BOUND_PROFILE_CONTRACT,
        "source_governance_contract": SOURCE_BOUND_GOVERNANCE_CONTRACT,
        "output_contract": SOURCE_BOUND_OUTPUT_CONTRACT,
    }
}
COUNT_PROFILE_CONTRACT = "evidence-profile-v7"
COUNT_OUTPUT_CONTRACT = "procedure-output-cover-v7"
COUNT_BINDING_CONTRACT = "literal-source-quantity-binding-v1"
EvidenceReadingProfile = Literal[
    "clause_bound_v1",
    "contextual_source_v1",
    "contextual_source_v2",
    "contextual_source_v3",
    "contextual_source_v4",
]
CURRENT_CONTRACT = "requirement-evidence-v2"
CONTEXTUAL_CONTRACT = "requirement-evidence-v3"
LINGUISTIC_CONTRACT = "requirement-evidence-v4"
STAGED_CONTRACT = "requirement-evidence-v5"
# Contextual history always dispatches to immutable output reconstruction.
# Unsupported kinds or incomplete v3 certificates fail closed, never fall back.
KNOWN_CONTRACTS = frozenset(
    {
        "requirement-evidence-v1",
        CURRENT_CONTRACT,
        CONTEXTUAL_CONTRACT,
        LINGUISTIC_CONTRACT,
        STAGED_CONTRACT,
    }
)
PROFILE_CONTRACT = "evidence-profile-v1"
COMBINED_PROFILE_CONTRACT = "evidence-profile-v2"
ORIGIN_CONTRACT = "proposal-origin-v1"
ROLE_POLICY_CONTRACT = "ordinary-session-activity-role-v1"
PATTERN_REGISTRY_CONTRACT = "typed-source-patterns-v1"
MAX_PATTERN_PROPOSALS_PER_SOURCE = 3
MAX_PATTERN_PROPOSALS_PER_REQUIREMENT = 16


@dataclass(frozen=True)
class ReadingVersion:
    profile: str
    evidence_profile: str
    requirement: str
    request_plan: str
    scope_cover: str
    role_manifest: str
    procedure: str
    output: str
    scope_documents: int
    request_parser: str = "bounded"
    parser_capture: str = "disabled"
    pattern_registry: str = PATTERN_REGISTRY_CONTRACT
    request_inputs: str | None = None
    source_productions: str | None = None
    fact_context: str | None = None


_READING_VERSIONS = (
    ReadingVersion(
        "contextual_source_v1",
        "evidence-profile-v5",
        CONTEXTUAL_CONTRACT,
        "contextual-request-plan-v1",
        "declared-source-scope-cover-v1",
        "declared-context-role-manifest-v1",
        "complete-immutable-procedure-v4",
        "procedure-output-cover-v5",
        128,
    ),
    ReadingVersion(
        profile="contextual_source_v2",
        evidence_profile="evidence-profile-v6",
        requirement=LINGUISTIC_CONTRACT,
        request_plan="linguistic-request-plan-v1",
        scope_cover="declared-source-scope-cover-v1",
        role_manifest="declared-context-role-manifest-v2",
        procedure="complete-immutable-procedure-v5",
        output="procedure-output-cover-v6",
        scope_documents=128,
        request_parser="local_dependency",
        parser_capture="dependency-request-capture-v1",
        pattern_registry="typed-source-patterns-v2",
    ),
    ReadingVersion(
        profile="contextual_source_v3",
        evidence_profile="evidence-profile-v8",
        requirement=STAGED_CONTRACT,
        request_plan="staged-request-plan-v1",
        scope_cover="declared-source-scope-cover-v2",
        role_manifest="declared-context-role-manifest-v3",
        procedure="complete-immutable-procedure-v6",
        output="procedure-output-cover-v8",
        scope_documents=128,
        request_parser="local_dependency",
        parser_capture="dependency-request-capture-v1",
        pattern_registry="typed-source-patterns-v2",
    ),
    ReadingVersion(
        profile="contextual_source_v4",
        evidence_profile="evidence-profile-v9",
        requirement=STAGED_CONTRACT,
        request_plan="staged-request-plan-v2",
        scope_cover="declared-source-scope-cover-v3",
        role_manifest="declared-context-role-manifest-v4",
        procedure="complete-immutable-procedure-v7",
        output="procedure-output-cover-v9",
        scope_documents=128,
        request_parser="local_dependency",
        parser_capture="dependency-request-capture-v1",
        pattern_registry="typed-source-patterns-v2",
        request_inputs="staged-request-inputs-v2",
        source_productions="captured-source-productions-v1",
        fact_context="captured-governing-context-v1",
    ),
)


def reading_version(profile: str) -> ReadingVersion:
    """One identity authority for the opt-in contextual reading contract."""
    for version in _READING_VERSIONS:
        if version.profile == profile:
            return version
    raise ValueError("Unsupported contextual reading profile")


def staged_reading_profile(profile: str) -> bool:
    """Profiles that require the immutable staged publication archive.

    Reading contracts evolve independently of the shared archive's wire format.
    A registered staged requirement contract may never use mutable metadata as
    its historical source authority.
    """
    if profile == "clause_bound_v1":
        return False
    return reading_version(profile).requirement == STAGED_CONTRACT


def role_manifest_version(contract: str) -> ReadingVersion:
    """Resolve a recorded manifest through the same immutable version registry."""
    for version in _READING_VERSIONS:
        if version.role_manifest == contract:
            return version
    raise ValueError("Unsupported contextual role manifest")


@dataclass(frozen=True)
class SourceCopyVersion:
    policy: str
    reference: str
    instruction_arguments: str
    scope_proposition: str
    operand_semantics: str = "none"
    require_unique_semantic_inputs: bool = False
    argument_interpretation: str = "none"
    reference_catalog: str = "none"
    governing_context: str = "whole_source_v1"
    procedure_scope: str = "requested_scope_v1"


_SOURCE_COPY_VERSIONS = (
    SourceCopyVersion(
        "dependency_clause_locality_v2",
        "dependency-clause-reference-locality-v2",
        "captured_locality_nli",
        "requested_activity_v1",
    ),
    SourceCopyVersion(
        "source_declared_argument_copy_v1",
        "declared-instruction-reference-ast-v1",
        "exact_source_copy",
        "qualified_declared_relation_v1",
    ),
    SourceCopyVersion(
        "source_bound_argument_copy_v1",
        "declared-instruction-reference-ast-v2",
        "exact_source_copy",
        "qualified_declared_relation_v1",
        "source-bound-semantic-operand-v1",
    ),
    SourceCopyVersion(
        "source_bound_argument_copy_v2",
        "declared-instruction-reference-ast-v3",
        "exact_source_copy",
        "qualified_declared_relation_v1",
        "source-bound-semantic-operand-v2",
        True,
    ),
    SourceCopyVersion(
        policy="ordinary_source_argument_copy_v1",
        reference="ordinary-source-reference-ast-v1",
        instruction_arguments="exact_source_copy",
        scope_proposition="qualified_governing_context_v1",
        argument_interpretation="disclosed_literal_instruction_arguments_v1",
        reference_catalog="procedure-reference-lexicon-v1",
        governing_context="complete_governing_context_v1",
    ),
    SourceCopyVersion(
        policy="ordinary_activity_quote_v1",
        reference="ordinary-source-reference-ast-v1",
        instruction_arguments="exact_source_copy",
        scope_proposition="source_activity_quote_relation_v1",
        argument_interpretation="disclosed_literal_instruction_arguments_v1",
        reference_catalog="procedure-reference-lexicon-v1",
        governing_context="complete_governing_context_v1",
        procedure_scope="activity_quote_v1",
    ),
    SourceCopyVersion(
        policy="ordinary_activity_quote_v2",
        reference="ordinary-source-reference-ast-v1",
        instruction_arguments="exact_source_copy",
        scope_proposition="source_activity_quote_relation_v1",
        argument_interpretation="disclosed_literal_instruction_arguments_v1",
        reference_catalog="procedure-reference-lexicon-v1",
        governing_context="complete_governing_context_v1",
        procedure_scope="activity_quote_v2",
    ),
)


def source_copy_version(
    policy: str | None = None,
    *,
    reading_profile: str | None = None,
    procedure_scope: ProcedureScopeProfile = "requested_scope_v1",
) -> SourceCopyVersion:
    """Explicit copy-policy authority; the pure library default stays legacy.

    Only the opt-in linguistic producer requests the new reading-profile policy.
    Captured consumers dispatch on recorded policy, never current defaults.
    """
    if reading_profile is not None:
        if policy is not None or not dependency_reading_profile(reading_profile):
            raise ValueError("Unsupported source-copy reading profile")
        if procedure_scope in {"activity_quote_v1", "activity_quote_v2"}:
            if reading_profile != "contextual_source_v4":
                raise ValueError("Activity procedure quote requires captured reading")
            return next(
                v for v in _SOURCE_COPY_VERSIONS if v.procedure_scope == procedure_scope
            )
        if procedure_scope != "requested_scope_v1":
            raise ValueError("Unknown procedure scope profile")
        return next(
            v
            for v in _SOURCE_COPY_VERSIONS
            if v.policy == "ordinary_source_argument_copy_v1"
        )
    if procedure_scope != "requested_scope_v1":
        raise ValueError("Recorded source-copy policy required")
    if policy is None:
        return _SOURCE_COPY_VERSIONS[0]
    for version in _SOURCE_COPY_VERSIONS:
        if version.policy == policy:
            return version
    raise ValueError("Unsupported source-copy policy")


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


def dependency_reading_profile(profile: str) -> bool:
    """Explicit registry membership; no unknown-version or legacy promotion."""
    return profile in {
        "contextual_source_v2",
        "contextual_source_v3",
        "contextual_source_v4",
    }


def _validate_request_parser(reading, request_parser):
    if type(request_parser) is not str or request_parser not in {
        "bounded",
        "local_dependency",
    }:
        raise ValueError("Unknown request parser mode")
    if dependency_reading_profile(reading) and request_parser != "local_dependency":
        raise ValueError("Linguistic source reading requires local_dependency parsing")
    if request_parser == "local_dependency" and not dependency_reading_profile(reading):
        raise ValueError(
            "Local dependency parsing requires "
            "contextual_source_v2, contextual_source_v3 or contextual_source_v4"
        )


def _validate_quantity_profile(quantity, reading):
    if quantity not in get_args(QuantityVerificationProfile):
        raise ValueError("Unknown quantity verification profile")
    if quantity != "legacy_v1" and not dependency_reading_profile(reading):
        raise ValueError("Source-bound counts require a dependency reading profile")


def _validate_source_governance(governance, reading):
    if type(governance) is not str or governance not in get_args(
        SourceGovernanceProfile
    ):
        raise ValueError("Unknown source governance profile")
    if governance != "all_sources_v1" and reading != "contextual_source_v4":
        raise ValueError("Requirement-bound governance requires contextual_source_v4")


def _validate_procedure_scope(scope, reading, governance):
    if type(scope) is not str or scope not in get_args(ProcedureScopeProfile):
        raise ValueError("Unknown procedure scope profile")
    if scope in {"activity_quote_v1", "activity_quote_v2"} and (
        reading != "contextual_source_v4" or governance != "requirement_bound_v1"
    ):
        raise ValueError(
            "Activity procedure quote requires captured requirement-bound governance"
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
    reading: EvidenceReadingProfile = "clause_bound_v1",
    request_parser: str = "bounded",
    quantity: QuantityVerificationProfile = "legacy_v1",
    source_governance: SourceGovernanceProfile = "all_sources_v1",
    procedure_scope: ProcedureScopeProfile = "requested_scope_v1",
) -> None:
    _validate_quantity_profile(quantity, reading)
    _validate_source_governance(source_governance, reading)
    _validate_procedure_scope(procedure_scope, reading, source_governance)
    if reading not in get_args(EvidenceReadingProfile):
        raise ValueError("Unknown evidence reading profile")
    if reading != "clause_bound_v1" and (
        reader != "reader"
        or support != "local_nli"
        or generation != "extractive"
        or proposal != "qa_plus_source_patterns_v1"
        or role != "ordinary_session_activity_v1"
        or procedure != "source_declared_procedure_copy_v1"
        or context != "scoped_note_context_v2"
    ):
        raise ValueError(
            "Contextual source reading requires the reader, local_nli, extractive "
            "generation and explicit composite/activity/copy/context-v2 controls"
        )
    _validate_request_parser(reading, request_parser)
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
    evidence_reading_profile: EvidenceReadingProfile = "clause_bound_v1"
    quantity_verification_profile: QuantityVerificationProfile = "legacy_v1"
    source_governance_profile: SourceGovernanceProfile = "all_sources_v1"
    procedure_scope_profile: ProcedureScopeProfile = "requested_scope_v1"

    def __post_init__(self) -> None:
        _validate_quantity_profile(
            self.quantity_verification_profile, self.evidence_reading_profile
        )
        _validate_source_governance(
            self.source_governance_profile, self.evidence_reading_profile
        )
        _validate_procedure_scope(
            self.procedure_scope_profile,
            self.evidence_reading_profile,
            self.source_governance_profile,
        )
        if self.source_governance_profile != "all_sources_v1":
            # These are policy prerequisites, never claims that engines ran.
            validate_evidence_engines(
                self.proposal_profile,
                self.role_scope_policy,
                "reader",
                "local_nli",
                procedure=self.procedure_verification_profile,
                generation="extractive",
                context=self.source_context_policy,
                reading=self.evidence_reading_profile,
                request_parser="local_dependency",
                quantity=self.quantity_verification_profile,
                source_governance=self.source_governance_profile,
                procedure_scope=self.procedure_scope_profile,
            )

    @property
    def source_bound_counts(self) -> bool:
        return self.quantity_verification_profile == "literal_source_count_v1"

    @property
    def staged_request(self) -> bool:
        return staged_reading_profile(self.evidence_reading_profile)

    @property
    def dependency_reading(self) -> bool:
        return dependency_reading_profile(self.evidence_reading_profile)

    @property
    def output_contract(self) -> str:
        if self.source_governance_profile in _SOURCE_GOVERNANCE_VERSIONS:
            return _SOURCE_GOVERNANCE_VERSIONS[self.source_governance_profile][
                "output_contract"
            ]
        if self.staged_request:
            return reading_version(self.evidence_reading_profile).output
        if self.source_bound_counts:
            return COUNT_OUTPUT_CONTRACT
        return reading_version(self.evidence_reading_profile).output

    @property
    def contextual_source(self) -> bool:
        return self.evidence_reading_profile != "clause_bound_v1"

    @property
    def requirement_contract(self) -> str:
        return (
            reading_version(self.evidence_reading_profile).requirement
            if self.contextual_source
            else CURRENT_CONTRACT
        )

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
        if self.contextual_source:
            reading = reading_version(self.evidence_reading_profile)
            record.update(
                contract=reading.evidence_profile,
                evidence_reading_profile=self.evidence_reading_profile,
                requirement_contract=reading.requirement,
                request_plan_contract=reading.request_plan,
                scope_cover_contract=reading.scope_cover,
                role_manifest_contract=reading.role_manifest,
                procedure_contract=reading.procedure,
                output_contract=reading.output,
                scope_document_limit=reading.scope_documents,
                pattern_registry_contract=reading.pattern_registry,
            )
            if reading.request_parser != "bounded":
                record.update(
                    request_parser_mode=reading.request_parser,
                    request_parser_contract=reading.parser_capture,
                )
            if reading.request_inputs is not None:
                record.update(
                    request_input_contract=reading.request_inputs,
                    source_production_contract=reading.source_productions,
                    fact_context_contract=reading.fact_context,
                )
        if self.source_bound_counts:
            if not self.dependency_reading:
                raise ValueError(
                    "Source-bound counts require a dependency reading profile"
                )
            record.update(
                contract=(
                    reading_version(self.evidence_reading_profile).evidence_profile
                    if self.staged_request
                    else COUNT_PROFILE_CONTRACT
                ),
                output_contract=self.output_contract,
                quantity_verification_profile=self.quantity_verification_profile,
                quantity_binding_contract=COUNT_BINDING_CONTRACT,
            )
        if self.source_governance_profile in _SOURCE_GOVERNANCE_VERSIONS:
            record.update(_SOURCE_GOVERNANCE_VERSIONS[self.source_governance_profile])
            record["source_governance_profile"] = self.source_governance_profile
        if self.procedure_scope_profile in {"activity_quote_v1", "activity_quote_v2"}:
            record.update(
                procedure_scope_profile=self.procedure_scope_profile,
                procedure_scope_contract=(
                    ACTIVITY_INSTRUCTION_QUOTE_CONTRACT
                    if self.procedure_scope_profile == "activity_quote_v2"
                    else ACTIVITY_PROCEDURE_QUOTE_CONTRACT
                ),
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
        reading=getattr(config, "EVIDENCE_READING_PROFILE", "clause_bound_v1"),
        request_parser=getattr(config, "REQUEST_PARSER_MODE", "bounded"),
        quantity=getattr(config, "QUANTITY_VERIFICATION_PROFILE", "legacy_v1"),
        source_governance=getattr(
            config, "SOURCE_GOVERNANCE_PROFILE", "all_sources_v1"
        ),
        procedure_scope=getattr(
            config, "PROCEDURE_SCOPE_PROFILE", "requested_scope_v1"
        ),
    )
    return EvidencePolicy(
        config.ANSWER_PROPOSAL_PROFILE,
        config.ROLE_SCOPE_POLICY,
        config.PROCEDURE_VERIFICATION_PROFILE,
        config.SOURCE_CONTEXT_POLICY,
        getattr(config, "EVIDENCE_READING_PROFILE", "clause_bound_v1"),
        getattr(config, "QUANTITY_VERIFICATION_PROFILE", "legacy_v1"),
        getattr(config, "SOURCE_GOVERNANCE_PROFILE", "all_sources_v1"),
        getattr(config, "PROCEDURE_SCOPE_PROFILE", "requested_scope_v1"),
    )


def recorded_evidence_policy(profile: dict[str, Any]) -> EvidencePolicy:
    """Reconstruct recorded controls; absent count control retains historical rules."""
    governance_record = isinstance(profile, dict) and (
        "source_governance_profile" in profile
        or "source_governance_contract" in profile
        or profile.get("contract") == SOURCE_BOUND_PROFILE_CONTRACT
        or profile.get("output_contract") == SOURCE_BOUND_OUTPUT_CONTRACT
        or "procedure_scope_profile" in profile
        or "procedure_scope_contract" in profile
    )
    try:
        policy = EvidencePolicy(
            profile["proposal_profile"],
            profile["role_scope_policy"],
            profile.get("procedure_verification_profile", "all_units_nli_v1"),
            profile.get("source_context_policy", "explicit_target_v1"),
            profile.get("evidence_reading_profile", "clause_bound_v1"),
            profile.get("quantity_verification_profile", "legacy_v1"),
            profile.get("source_governance_profile", "all_sources_v1"),
            profile.get("procedure_scope_profile", "requested_scope_v1"),
        )
    except (KeyError, TypeError) as exc:
        if governance_record:
            raise ValueError("Incomplete source governance profile") from exc
        raise
    if (
        governance_record or policy.source_governance_profile != "all_sources_v1"
    ) and not _exact_profile_record(profile, policy.record()):
        raise ValueError("Source governance record is not the canonical known profile")
    return policy


def _exact_profile_record(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            _exact_profile_record(actual[key], expected[key]) for key in expected
        )
    return actual == expected
