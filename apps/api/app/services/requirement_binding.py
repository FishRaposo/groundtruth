"""Source-bound verification propositions; never generated answer prose."""

import re
from dataclasses import dataclass, replace

from app.services.answer_requirements import (
    Requirement,
    _count_as_parts,
    _phrasal_action,
    _without_preface,
    prohibition_request,
    temporal_request_consumed,
)
from app.services.answer_requirements import (
    _requirement_anchors as named_anchors,
)
from app.services.requirement_booleans import BooleanClaim, negative_boolean_claim
from app.services.requirement_quantities import (
    allocation_answer_range,
)
from app.services.requirement_quantities import (
    quantity_hypothesis as _literal_quantity_hypothesis,
)
from app.services.requirement_relations import (
    relation_answer_range,
    relation_hypothesis,
    relation_source_range,
)


@dataclass(frozen=True)
class SupportCheck:
    name: str
    premise: str
    hypothesis: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class SupportEdge:
    name: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    requirement_id: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportClaim:
    hypothesis: str | None
    premise: str
    value: str
    start: int
    end: int
    rejection: str | None
    support_start: int | None = None
    support_end: int | None = None
    checks: tuple[SupportCheck, ...] = ()
    proof_edges: tuple[SupportEdge, ...] = ()
    premise_start: int | None = None
    premise_end: int | None = None


@dataclass(frozen=True)
class _AtomicProof:
    hypothesis: str
    premise: str
    premise_start: int
    premise_end: int
    checks: tuple[SupportCheck, ...]
    edges: tuple[SupportEdge, ...]


def _profile_support_claim(
    req: Requirement,
    context: str,
    start: int,
    end: int,
    reading_profile: str,
) -> SupportClaim:
    """Dispatch through existing recorded reading profiles without changing them."""
    from app.evidence_policy import dependency_reading_profile

    if dependency_reading_profile(reading_profile):
        if req.kind == "quantity":
            from app.services.linguistic_quantities import scoped_quantity_claim

            return scoped_quantity_claim(req, context, start, end)
        from app.services.linguistic_binding import support_linguistic_claim

        return support_linguistic_claim(req, context, start, end)
    from app.evidence_policy import reading_version
    from app.services.contextual_binding import contextual_support_claim

    reading_version(reading_profile)
    return contextual_support_claim(req, context, start, end)


def support_claim(
    req: Requirement,
    context: str,
    start: int,
    end: int,
    *,
    reading_profile: str = "clause_bound_v1",
) -> SupportClaim:
    """Bind a literal candidate to a supported, relation-preserving proposition.

    Passing these surface checks does not establish entailment. Unknown grammar
    has no hypothesis rather than turning the selected quote into a tautology.
    """
    if reading_profile != "clause_bound_v1":
        return _profile_support_claim(req, context, start, end, reading_profile)
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return SupportClaim(None, "", "", start, end, "invalid_candidate_offsets")
    negative = _negative_proposal(req, context, start, end)
    if negative is not None and negative.rejection is not None:
        return SupportClaim(
            None,
            context[start:end],
            context[start:end],
            start,
            end,
            negative.rejection,
        )
    if negative is not None:
        assert isinstance(negative.start, int) and isinstance(negative.end, int)
        start, end = negative.start, negative.end
    start, end = _normalized_relation_answer(req, context, start, end)
    start, end, preparation_error = _prepare_argument(req, context, start, end)
    if preparation_error:
        return SupportClaim(
            None, context[start:end], context[start:end], start, end, preparation_error
        )
    value = context[start:end]
    if negative is not None:
        clause_start, clause_end = negative.support_start, negative.support_end
        assert isinstance(clause_start, int) and isinstance(clause_end, int)
    else:
        clause_start, clause_end = _selected_source_clause(req, context, start, end)
    clause = context[clause_start:clause_end]
    clause_start += len(clause) - len(clause.lstrip())
    premise = clause.strip()

    def rejected(reason: str) -> SupportClaim:
        return SupportClaim(None, premise, value, start, end, reason)

    topic = re.split(r"\s+with\s+", req.topic, maxsplit=1, flags=re.I)[0]
    topic_words = _required_topic_words(req, topic)
    premise, clause_start = _selected_premise(
        req, context, clause_start, clause_end, topic_words, premise
    )
    present = _words(premise) | _words(_scope_prefix(req, context, start, premise))
    if not topic or (topic_words and not topic_words.issubset(present)):
        return rejected("subject_missing_from_selected_clause")
    binding = _Binding(
        req,
        context,
        value,
        premise,
        topic,
        start,
        end,
        clause_start,
        negative.hypothesis if negative is not None else None,
    )
    rejection = _binding_rejection(binding)
    if rejection:
        return rejected(rejection)
    binding = _expanded_argument(binding)
    start, end, value = binding.start, binding.end, binding.value
    hypothesis, rejection, checks = _binding_proposition(binding)
    return _assembled_claim(
        binding, hypothesis, rejection, checks, clause_start, clause_end
    )


def _assembled_claim(
    binding: "_Binding",
    hypothesis: str | None,
    rejection: str | None,
    checks: tuple[SupportCheck, ...],
    clause_start: int,
    clause_end: int,
) -> SupportClaim:
    req, context = binding.req, binding.context
    start, end, value = binding.start, binding.end, binding.value
    verified_premise = _verification_premise(req, context, binding.premise, start)
    edges: tuple[SupportEdge, ...] = ()
    atomic = (
        _operation_deputy_proof(binding) or _worksheet_atomic_proof(binding)
        if rejection is None
        else None
    )
    if atomic is not None:
        hypothesis, verified_premise = atomic.hypothesis, atomic.premise
        checks, edges = atomic.checks, atomic.edges
    elif rejection is None and req.relation == "cover_window":
        edges = (_cover_edge(binding),)
    if len(checks) > 8 or len(edges) > 8:
        return SupportClaim(
            None, binding.premise, value, start, end, "proof_budget_exceeded"
        )
    coordinates = (
        (atomic.premise_start, atomic.premise_end)
        if atomic is not None
        else _premise_coordinates(context, verified_premise, start, end)
    )
    return SupportClaim(
        hypothesis,
        verified_premise,
        value,
        start,
        end,
        rejection,
        clause_start if rejection is None else None,
        _terminal_end(context, clause_end) if rejection is None else None,
        checks,
        edges,
        coordinates[0] if coordinates else None,
        coordinates[1] if coordinates else None,
    )


def _premise_coordinates(
    context: str, premise: str, start: int, end: int
) -> tuple[int, int] | None:
    matches = [
        m.span()
        for m in re.finditer(re.escape(premise), context)
        if m.start() <= start < end <= m.end()
    ]
    return matches[0] if len(matches) == 1 else None


def _binding_proposition(
    binding: "_Binding",
) -> tuple[str | None, str | None, tuple[SupportCheck, ...]]:
    handler = _HYPOTHESES.get(binding.req.kind)
    if handler is None:
        return None, "unsupported_question_transformation", ()
    hypothesis, rejection = handler(binding)
    checks = (
        _procedure_checks(binding)
        if rejection is None and binding.req.kind == "procedure"
        else ()
    )
    if len(checks) > 8:
        return None, "procedure_proof_limit", ()
    return hypothesis, rejection, checks


def _negative_proposal(
    req: Requirement, context: str, start: int, end: int
) -> BooleanClaim | None:
    if req.kind != "boolean" or req.relation != "boolean":
        return None
    negative = negative_boolean_claim(req, context, start, end)
    if negative.rejection is not None:
        return (
            negative if _negative_action_selection(req, context, start, end) else None
        )
    first, last = negative.start, negative.end
    left, right = negative.support_start, negative.support_end
    if not (
        type(first) is int
        and type(last) is int
        and type(left) is int
        and type(right) is int
        and 0 <= left <= first < last <= right <= len(context)
        and (start <= first < last <= end or first <= start < end <= last)
        and isinstance(negative.hypothesis, str)
        and negative.hypothesis
    ):
        raise ValueError("Invalid negative relation binding")
    return negative


def _negative_action_selection(
    req: Requirement, context: str, start: int, end: int
) -> bool:
    if not re.match(
        r"(?:does|do|may|can|must|should)\s+", _without_preface(req.question), re.I
    ):
        return False
    left, right = _clause(context, start, end)
    return bool(
        re.search(
            r"\b(?:does|do|may|must|should|can)\s+not\b|\bcannot\b|\bnever\b"
            r"|\b(?:is|are)\s+not\s+(?:permitted|allowed)\b",
            context[left:right],
            re.I,
        )
    )


def _required_topic_words(req: Requirement, topic: str) -> set[str]:
    words = (
        _words(topic) - _GRAMMAR
        if req.kind == "deputy" and req.depends_on
        else set(req.anchors) or (_words(topic) - _GRAMMAR if req.depends_on else set())
    )
    if req.relation == "owner_relative_deputy":
        words |= set(req.anchors)
    return words


def _coverage_argument(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int, str | None] | None:
    if req.relation == "allocation":
        interval = allocation_answer_range(req, context, start, end)
        if interval is None:
            return start, end, "allocation_subject_unit_or_relation_missing"
        return interval[0], interval[1], None
    if req.relation == "consultation_window":
        interval = _consultation_answer_range(req, context, start, end)
        if interval:
            return interval[0], interval[1], None
    return None


def _prepare_argument(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int, str | None]:
    coverage = _coverage_argument(req, context, start, end)
    if coverage is not None:
        return coverage
    if req.kind == "procedure":
        expanded = _expand_procedure(req, context, start, end)
        if expanded is None:
            return start, end, "ordered_instruction_block_missing"
        start, end = expanded
    elif req.kind == "prohibition":
        refined = _contained_prohibition(req, context, start, end)
        if refined is not None:
            start, end = refined
        start, end = _expand_prohibition(context, start, end)
    elif req.relation == "cover_window":
        expanded = _cover_window_argument(req, context, start, end)
        if expanded is not None:
            start, end = expanded
    start, end = _attach_unit(req, context, start, end)
    return start, end, None


def _normalized_relation_answer(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int]:
    normalized = (
        relation_answer_range(req, context, start, end)
        if req.kind == "generic"
        else None
    )
    if normalized:
        left, right = normalized
        if type(left) is int and type(right) is int and start <= left < right <= end:
            return left, right
    return start, end


def _selected_source_clause(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int]:
    operation = _operation_deputy_context(req, context, start, end)
    if operation:
        return operation[0], operation[3]
    # Only the relation authority's recognized ordered-imperative grammar may
    # include adjacent instructions needed to prove a before/after condition.
    cover = _cover_statement(req, context, start, end)
    if cover is not None:
        return cover.span()
    extra = (
        relation_source_range(req, context, start, end)
        if req.kind == "generic"
        else None
    )
    if extra:
        left, right = extra
        if (
            type(left) is int
            and type(right) is int
            and 0 <= left <= start < end <= right <= len(context)
        ):
            return left, right
    return _clause(context, start, end)


def _cover_requested(req: Requirement) -> bool:
    return req.relation == "cover_window" or (
        req.kind == "deputy"
        and bool(
            re.search(r"\b(?:cover|substitute|deputize)\b", req.original_text, re.I)
        )
    )


def _cover_statement(
    req: Requirement, context: str, start: int, end: int
) -> re.Match[str] | None:
    if not _cover_requested(req):
        return None
    for match in re.finditer(
        r"(?:^|(?<=[.!?;])\s+)(?P<actor>[^.!?;]+?)\s+is\s+the\s+deputy\s+for\s+"
        r"(?P<target>[^.!?;]+?)\s+and\s+(?P<permission>[^.!?;]+)",
        context,
        re.I,
    ):
        if match.start() <= start < end <= match.end():
            return match
    return None


def _cover_permission(binding: "_Binding") -> str | None:
    match = _cover_statement(binding.req, binding.context, binding.start, binding.end)
    if match is None:
        return None
    permission = match.group("permission").strip()
    if not re.fullmatch(
        rf"may\s+(?:substitute|cover)\s+only\s+on\s+{_WEEKDAY}"
        r"\s+from\s+\d{1,2}:\d{2}\s+to\s+\d{1,2}:\d{2}",
        permission,
        re.I,
    ):
        return None
    requested = binding.req.original_text + " " + binding.req.question
    days = re.findall(_WEEKDAY, requested, re.I)
    clocks = re.findall(r"\b\d{1,2}:\d{2}\b", requested)
    if any(day.casefold() not in permission.casefold() for day in days):
        return None
    if any(clock not in permission for clock in clocks):
        return None
    return permission


def _cover_window_argument(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    statement = _cover_statement(req, context, start, end)
    if statement is None:
        return None
    window = re.fullmatch(
        rf"may\s+(?:substitute|cover)\s+only\s+on\s+(?P<window>{_WEEKDAY}"
        r"\s+from\s+\d{1,2}:\d{2}\s+to\s+\d{1,2}:\d{2})",
        statement.group("permission"),
        re.I,
    )
    if window is None:
        return None
    left = statement.start("permission") + window.start("window")
    right = statement.start("permission") + window.end("window")
    if left <= start < end <= right and re.search(
        rf"{_WEEKDAY}|\b\d{{1,2}}:\d{{2}}\b", context[start:end], re.I
    ):
        return left, right
    return None


def _cover_window_hypothesis(binding: "_Binding") -> tuple[str | None, str | None]:
    req = binding.req
    if len(req.depends_on) != 1 or req.id in req.depends_on:
        return None, "scoped_deputy_dependency_missing"
    match = _cover_statement(req, binding.context, binding.start, binding.end)
    permission = _cover_permission(binding)
    if match is None or permission is None:
        return None, "deputy_cover_permission_missing"
    if _canonical_argument(match.group("actor")) != _canonical_argument(req.topic):
        return None, "deputy_cover_actor_mismatch"
    scope = re.match(r"\s*for\s+([^,;?!]+),\s*", req.question, re.I)
    if scope is None:
        return None, "deputy_cover_scope_missing"
    requested = scope.group(1)
    core = re.sub(r"^(?:ordinary|standard|normal)\s+", "", requested, flags=re.I)
    expected = _canonical_argument(core)
    source_target = _canonical_argument(match.group("target"))
    generic_session = re.sub(r"\s+sessions?$", "", expected, flags=re.I)
    if source_target not in {expected, generic_session}:
        return None, "deputy_cover_scope_mismatch"
    interval = re.search(
        r"\bfrom\s+(\d{1,2}:\d{2}\s+to\s+\d{1,2}:\d{2})$", permission, re.I
    )
    window = _cover_window_argument(req, binding.context, binding.start, binding.end)
    expected = binding.context[window[0] : window[1]] if window else ""
    if interval is None or binding.value.casefold() not in {
        expected.casefold(),
        interval.group(1).casefold(),
        "from " + interval.group(1).casefold(),
    }:
        return None, "availability_interval_missing"
    return f"{req.topic} {permission}", None


def _cover_edge(binding: "_Binding") -> SupportEdge:
    match = _cover_statement(binding.req, binding.context, binding.start, binding.end)
    assert match is not None
    return SupportEdge(
        "scoped_deputy_to_permission",
        match.start("actor"),
        match.end("target"),
        match.start("permission"),
        match.end("permission"),
        binding.req.id,
        binding.req.depends_on,
    )


def _binding_rejection(binding: "_Binding") -> str | None:
    req, premise = binding.req, binding.premise
    if not temporal_request_consumed(req.original_text, req.kind, req.topic):
        return "unconsumed_temporal_request"
    if req.source_workspace:
        workspace = _literal_workspace(premise)
        if workspace is None or workspace.casefold() != req.source_workspace.casefold():
            return "workspace_binding_missing"
    header = _header_rejection(req, binding.context)
    if header:
        return header
    governance = _worksheet_governance_rejection(binding)
    if governance:
        return governance
    if (
        req.kind == "procedure"
        and re.match(
            r"\s*for\s+[^,]+,\s*take\s+me\s+through\s+every\s+step\b",
            req.original_text,
            re.I,
        )
        and not _worksheet_request_frame(binding)
    ):
        return "unsupported_worksheet_request_frame"
    if req.kind in {
        "duration",
        "start_time",
        "weekday",
        "availability",
        "quantity",
    } and _negated_fact(binding):
        return "selected_fact_is_negated"
    return None


def _selected_premise(
    req: Requirement,
    context: str,
    left: int,
    right: int,
    topic_words: set[str],
    premise: str,
) -> tuple[str, int]:
    if req.relation == "count_as":
        premise, left = _count_as_scope_context(req, context, left, right, premise)
    if req.kind == "boolean":
        copular = re.fullmatch(
            r"(?:is|are)\s+(.+?)\s+(?:an?|the)\s+.+",
            _without_preface(req.question).strip().rstrip("?. "),
            re.I,
        )
        if copular:
            topic_words = topic_words | (
                _words(copular.group(1) + " " + _boolean_namespace(req)) - _GRAMMAR
            )
    return _coreference_premise(context, left, right, topic_words, premise)


def _coreference_premise(
    context: str,
    clause_start: int,
    clause_end: int,
    topic_words: set[str],
    premise: str,
) -> tuple[str, int]:
    conjunction = re.search(r"\band\s*$", context[:clause_start], re.I)
    if conjunction and not named_anchors(premise):
        previous_start = max(
            (m.end() for m in re.finditer(r"[.!?;]", context[: conjunction.start()])),
            default=0,
        )
        previous = context[previous_start : conjunction.start()]
        if topic_words.issubset(_words(previous)):
            clause_start = previous_start
            while clause_start < clause_end and context[clause_start].isspace():
                clause_start += 1
            premise = context[clause_start:clause_end].strip()
    if re.match(r"(?:it|they)\s+", premise, re.I) and topic_words:
        preceding = context[:clause_start].rstrip()
        previous_end = len(preceding.rstrip(".!?;"))
        previous_start = max(
            (m.end() for m in re.finditer(r"[.!?;]", context[:previous_end])), default=0
        )
        antecedent = context[previous_start:previous_end].strip()
        if topic_words.issubset(_words(antecedent)):
            clause_start = previous_start
            while clause_start < clause_end and context[clause_start].isspace():
                clause_start += 1
            premise = context[clause_start:clause_end].strip()
    return premise, clause_start


@dataclass(frozen=True)
class _Binding:
    req: Requirement
    context: str
    value: str
    premise: str
    topic: str
    start: int
    end: int
    clause_start: int
    negative_hypothesis: str | None = None


def _role_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    req = binding.req
    value = binding.value
    premise = binding.premise
    topic = binding.topic
    start = binding.start
    end = binding.end
    clause_start = binding.clause_start
    if _operation_deputy_context(req, binding.context, start, end):
        return f"{value} is the deputy for {topic}", None
    role = _role_argument(req, premise)
    local_start, local_end = start - clause_start, end - clause_start
    if role is None or not (role[0] <= local_start < local_end <= role[1]):
        return None, "requested_role_not_selected_argument"
    predicate = req.relation if req.relation != "owner" else "is the owner of"
    hypothesis = (
        f"{value} {predicate} {topic}"
        if req.kind == "owner"
        else f"{value} is the {_requested_deputy_label(req)} for {topic}"
    )
    if (
        req.kind == "owner"
        and req.relation == "leads"
        and re.match(
            r"\s*(?:for\s+[^,.;]+,\s+(?:the\s+)?lead\s+is\b|(?:the\s+)?lead\s+for\b)",
            premise,
            re.I,
        )
    ):
        hypothesis = f"The lead for {topic} is {value}"
    if req.kind == "deputy" and req.depends_on:
        target = _selected_role_target(binding)
        hypothesis = (
            f"{value} deputizes for {target}"
            if req.relation == "deputizes"
            else f"{value} is {_the(target)}'s deputy"
        )
    scope = _condition_header(req, binding.context)
    if scope and req.relation in {"owner", "owns", "deputy"}:
        qualifier = re.match(r"(standard|ordinary|normal)\s+", topic, re.I)
        if qualifier:
            condition = qualifier.group(1).casefold()
            subject = topic[qualifier.end() :]
            role_relation = (
                "owner of"
                if req.kind == "owner"
                else f"{_requested_deputy_label(req)} for"
            )
            hypothesis = (
                f"For {condition} conditions, {_the(value)} is the "
                f"{role_relation} {_the(subject)}"
            )
    if _cover_requested(req):
        permission = _cover_permission(binding)
        if permission is None:
            return None, "deputy_cover_permission_missing"
        # Role and permission are separate facts; the dependent cover node
        # must still prove the complete permission/window under its scoped root.
    return hypothesis, None


def _requested_deputy_label(req: Requirement) -> str:
    label = re.search(
        r"\b(?:the|an?|its|their)\s+((?:[\w-]+\s+){0,2}deputy)\b",
        req.original_text,
        re.I,
    )
    return label.group(1) if label else "deputy"


def _duration_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    value = binding.value
    topic = binding.topic
    if not re.fullmatch(rf"\d+(?:\.\d+)?\s+{_DURATION_UNIT}", value, re.I):
        return None, "elapsed_duration_unit_missing"
    if (
        binding.req.attribute != "duration"
        and value.split()[-1].rstrip("s").casefold()
        != binding.req.attribute.rstrip("s").casefold()
    ):
        return None, "elapsed_duration_requested_unit_mismatch"
    if not _bound_predicate(
        binding,
        r"(?:lasts?(?:\s+for)?|takes?|occupies|runs?\s+for|duration\s*(?:is|of|:))",
    ):
        return None, "duration_relation_missing"
    hypothesis = f"{topic} lasts {value}"
    return hypothesis, None


def _start_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    value = binding.value
    topic = binding.topic
    if not re.fullmatch(r"\d{1,2}:\d{2}(?:\s*[ap]m)?", value, re.I):
        return None, "start_clock_missing"
    predicate = r"opens?" if binding.req.relation == "opens" else r"(?:starts?|begins?)"
    if not _bound_predicate(
        binding,
        rf"{predicate}(?:\s+(?:on|each|every)\s+{_WEEKDAY})?(?:\s+at)?|(?:is\s+)?scheduled\s+for|start\s+time\s*(?:is|:)",
    ):
        return None, "start_relation_missing"
    verb = "opens" if binding.req.relation == "opens" else "starts"
    hypothesis = f"{topic} {verb} at {value}"
    return hypothesis, None


def _weekday_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    value = binding.value
    topic = binding.topic
    predicate = r"opens?" if binding.req.relation == "opens" else r"(?:starts?|begins?)"
    if not re.fullmatch(_WEEKDAY, value, re.I) or not _bound_predicate(
        binding,
        rf"{predicate}(?:\s+at\s+\d{{1,2}}:\d{{2}}(?:\s*[ap]m)?)?(?:\s+(?:on|each|every))?|(?:is\s+)?scheduled\s+for\s+\d{{1,2}}:\d{{2}}\s+on|weekday\s*(?:is|:)",
    ):
        return None, "start_weekday_missing"
    verb = "opens" if binding.req.relation == "opens" else "starts"
    hypothesis = f"{topic} {verb} on {value}"
    return hypothesis, None


def _availability_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    if binding.req.relation == "consultation_window":
        return _consultation_hypothesis(binding)
    if binding.req.relation == "cover_window":
        return _cover_window_hypothesis(binding)
    value = binding.value
    premise = binding.premise
    topic = binding.topic
    if not re.search(r"\b(?:present|available|availability|hours)\b", premise, re.I):
        return None, "availability_relation_missing"
    if not re.fullmatch(
        r"(?:from\s+)?\d{1,2}:\d{2}\s*(?:to|[-–—])\s*\d{1,2}:\d{2}", value, re.I
    ):
        return None, "availability_interval_missing"
    if not _bound_predicate(
        binding, r"(?:available|present)(?:\s+from)?|hours\s+(?:are|:)\s*"
    ):
        return None, "availability_relation_missing"
    hypothesis = f"{topic} is present from {value.removeprefix('from ')}"
    return hypothesis, None


def _consultation_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    source = re.fullmatch(
        rf"(?P<subject>.+?)\s+is\s+available\s+for\s+consultations\s+on\s+"
        rf"(?P<window>{_WEEKDAY}\s+from\s+\d{{1,2}}:\d{{2}}\s+to\s+\d{{1,2}}:\d{{2}})",
        binding.premise.strip(),
        re.I,
    )
    if source is None or _canonical_argument(
        source.group("subject")
    ) != _canonical_argument(binding.topic):
        return None, "consultation_subject_or_relation_missing"
    left, right = source.span("window")
    if (
        not left
        <= binding.start - binding.clause_start
        < binding.end - binding.clause_start
        <= right
    ):
        return None, "consultation_window_not_selected"
    if binding.value != source.group("window"):
        return None, "consultation_weekday_or_interval_missing"
    return f"{binding.topic} is available for consultations on {binding.value}", None


def _consultation_answer_range(req, context: str, start: int, end: int):
    left, right = _clause(context, start, end)
    left += len(context[left:right]) - len(context[left:right].lstrip())
    source = re.fullmatch(
        rf"(?P<subject>.+?)\s+is\s+available\s+for\s+consultations\s+on\s+"
        rf"(?P<window>{_WEEKDAY}\s+from\s+\d{{1,2}}:\d{{2}}\s+to\s+\d{{1,2}}:\d{{2}})\s*",
        context[left:right],
        re.I,
    )
    if source is None or _canonical_argument(
        source.group("subject")
    ) != _canonical_argument(req.topic):
        return None
    first, last = (left + point for point in source.span("window"))
    return (first, last) if first <= start < end <= last else None


def _quantity_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    if binding.req.relation == "operand_count":
        return _operand_hypothesis(binding)
    return _literal_quantity_hypothesis(binding)


def _prohibition_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    if not _complete_prohibition_request(binding.req):
        return None, "unsupported_prohibition_request_frame"
    value = binding.value
    premise = binding.premise
    topic = binding.req.topic
    if _worksheet_scope_prefix(binding.req, binding.context, binding.start, premise):
        declaration = _worksheet_following_declaration(
            binding.context, binding.clause_start, premise
        )
        if declaration is None or not _first_worksheet_instruction(
            binding.context, declaration
        ):
            return None, "worksheet_prohibition_governance_incomplete"
    start = binding.start
    end = binding.end
    clause_start = binding.clause_start
    negative_instruction = re.search(r"\b(?:do|must|should)\s+not\s+(.+)", value, re.I)
    if negative_instruction and negative_instruction.start() == 0:
        if re.match(r"should\s+not\b", value, re.I):
            return None, "advisory_prohibition_not_obligation"
        if not _prohibition_target_matches(binding.req, negative_instruction.group(1)):
            return None, "requested_prohibition_target_missing"
        return f"{topic} must not {negative_instruction.group(1)}", None
    if _negated_fact(binding):
        return None, "selected_fact_is_negated"
    prohibited = re.search(r"\bprohibits?\s+(.+)", premise, re.I)
    if not prohibited or not (
        prohibited.start(1)
        <= start - clause_start
        < end - clause_start
        <= prohibited.end(1)
    ):
        return None, "prohibited_action_not_selected"
    if not _prohibition_target_matches(binding.req, value):
        return None, "requested_prohibition_target_missing"
    hypothesis = f"{topic} prohibits {value}"
    return hypothesis, None


def _requested_prohibition_target(
    req: Requirement, question: str
) -> tuple[str, str] | None:
    contract = prohibition_request(question, req.topic)
    if contract is None or contract.mode == "generic":
        return None
    return contract.mode, contract.argument


def _regular_gerund(verb: str) -> str:
    if verb.endswith("e") and not verb.endswith("ee"):
        return verb[:-1] + "ing"
    if re.fullmatch(r"[^aeiou]*[aeiou][^aeiouwxy]", verb, re.I):
        return verb + verb[-1] + "ing"
    return verb + "ing"


def _prohibition_argument_bound(requested: str, source: str) -> bool:
    """Compare complete governing fields, never a noun-prefix plus any tail."""
    requested = re.sub(r"\s+", " ", _canonical_argument(requested))
    source = re.sub(r"\s+", " ", _canonical_argument(source)).rstrip(".!?")
    if requested == source:
        return True
    # A literal cardinal may specialize the same requested object. The entire
    # remaining noun phrase must still match (coefficients -> zero coefficients).
    quantified = re.fullmatch(rf"{_CARDINAL}\s+(.+)", source, re.I)
    return bool(quantified and quantified.group(1) == requested)


def _prohibition_action_object_bound(
    requested: str, action: str, *, between: bool = False
) -> bool:
    """Bind the object before a proved action-level adjunct, not inside a field.

    These closed constructions cannot be used for a replacement object,
    destination, inferred operands or classification field. Unrecognized source
    attachment stays unresolved, even when a model could entail the copied H.
    """
    _, _, argument = action.strip().partition(" ")
    if _prohibition_argument_bound(requested, argument):
        return True
    # A bare infinitive is a purpose only with a recognized transitive verb and
    # its complete determiner + simple object. 'to vertex mapping' is not one.
    purpose = re.fullmatch(
        r"(?P<object>.+?)\s+to\s+"
        r"(?:remove|avoid|prevent|preserve|retain|verify)\s+"
        r"(?:a|an|the|this|that)\s+[a-z][\w-]*",
        argument,
        re.I,
    )
    concurrent = re.fullmatch(
        r"(?P<object>.+?)\s+while\s+[a-z][\w-]*ing\s+(?:it|them)",
        argument,
        re.I,
    )
    # Only a requested action can use the existing bounded mathematical
    # locative: an optional quantitative modifier and one plural location head.
    locative = (
        re.fullmatch(
            r"(?P<object>.+?)\s+between\s+"
            r"(?:(?:nonzero|positive|negative|signed|unsigned)\s+)?[a-z][\w-]*s",
            argument,
            re.I,
        )
        if between
        else None
    )
    return any(
        match is not None
        and _prohibition_argument_bound(requested, match.group("object"))
        for match in (purpose, concurrent, locative)
    )


def _prohibition_relation_argument(mode: str, action: str) -> str | None:
    predicates = {
        "substitution": r"replac(?:e|ing)\s+(.+?)\s+with\s+.+",
        "assignment": r"assign(?:ing)?\s+.+?\s+to\s+(.+)",
        "inference": r"infer(?:ring)?\s+.+?\s+from\s+(.+)",
        "classification": r"count(?:ing)?\s+.+?\s+as\s+(.+)",
    }
    source = re.fullmatch(predicates[mode], action, re.I)
    return source.group(1) if source else None


def _prohibition_action_target(argument: str, action: str) -> bool:
    gerund, _, requested_object = argument.partition(" ")
    verb, _, _ = action.strip().partition(" ")
    if not verb or not requested_object:
        return False
    compatible = {
        verb.casefold(),
        _regular_gerund(verb.casefold()),
        (verb + verb[-1] + "ing").casefold(),
    }
    return gerund.casefold() in compatible and _prohibition_action_object_bound(
        requested_object, action, between=True
    )


def _prohibition_target_matches(req: Requirement, action: str) -> bool:
    for question in (req.original_text, req.question):
        target = _requested_prohibition_target(req, question)
        if target is None:
            continue  # Complete non-target frames are checked independently.
        mode, argument = target
        if mode == "action":
            if not _prohibition_action_target(argument, action):
                return False
        elif mode == "object":
            if not _prohibition_action_object_bound(argument, action):
                return False
        else:
            source_argument = _prohibition_relation_argument(mode, action)
            if source_argument is None or not _prohibition_argument_bound(
                argument, source_argument
            ):
                return False
    return True


def _boolean_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    if binding.negative_hypothesis is not None:
        return binding.negative_hypothesis, None
    if binding.req.relation == "count_as":
        return _count_as_hypothesis(binding)
    req = binding.req
    body = _without_preface(req.question).strip()
    if re.match(r"(?:is|are)\s+", body, re.I):
        return _copular_boolean_hypothesis(binding)
    if re.match(r"(?:does|do)\s+", body, re.I):
        return _factual_boolean_hypothesis(binding)
    value = binding.value
    topic = binding.topic
    present = _words(binding.premise)
    action = _action(req)
    if action is None:
        return None, "unsupported_polarity_transformation"
    if re.search(r"\b(?:and|but|or|neither|nor)\b", value, re.I):
        return None, "selected_multiple_actions"
    action_words = _words(action) - _GRAMMAR
    if not action_words.issubset(present):
        return None, "requested_action_missing"
    negative = _negated_fact(binding)
    selected_words = _words(value)
    if not action_words.issubset(selected_words) or (
        negative
        and not re.search(r"\b(?:not|never|cannot|forbidden|prohibited)\b", value, re.I)
    ):
        return None, "selected_action_or_polarity_missing"
    hypothesis = f"{topic} {'must not' if negative else 'may'} {action}"
    return hypothesis, None


def _boolean_namespace(req: Requirement) -> str:
    prefix = re.match(
        r"\s*(?:for|in|at|on|regarding)\s+[^,;?!]+[,;:]\s*", req.question, re.I
    )
    return prefix.group().strip() + " " if prefix else ""


def _boolean_local(binding: _Binding) -> str:
    left, right = _clause(binding.context, binding.start, binding.end)
    return _without_preface(binding.context[left:right].strip()).strip()


def _copular_source_subject(binding: _Binding, actual: str, expected: str) -> str:
    """Resolve only an exact, adjacent source copular subject in saved context."""
    if actual.casefold() not in {"it", "they"}:
        return actual
    left, _ = _clause(binding.context, binding.start, binding.end)
    preceding = binding.context[:left].rstrip()
    # No search across another clause or paragraph, and no descriptive object
    # becomes the subject merely because it contains the requested noun.
    end = len(preceding.rstrip(".!?;"))
    prior_start = max(
        (m.end() for m in re.finditer(r"[.!?;\n]", preceding[:end])), default=0
    )
    prior = preceding[prior_start:end].strip()
    source = re.fullmatch(r"(.+?)\s+(is|are)\s+.+", _without_preface(prior), re.I)
    if (
        source is None
        or prior not in binding.premise
        or _canonical_argument(source.group(1)) != _canonical_argument(expected)
        or source.group(2).casefold() != ("is" if actual.casefold() == "it" else "are")
    ):
        return actual
    return expected


def _copular_boolean_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    question = _without_preface(binding.req.question).strip().rstrip("?. ")
    request = re.fullmatch(r"(is|are)\s+(.+?)\s+((?:an?|the)\s+.+)", question, re.I)
    if request is None:
        return _passive_classification_hypothesis(binding, question)
    copula, subject, predicate = request.groups()
    if subject.casefold() in {"it", "they", "this", "that", "these", "those"}:
        return None, "unresolved_boolean_subject"
    source = re.fullmatch(
        r"(.+?)\s+(is|are)\s+(not\s+)?(.+)", _boolean_local(binding), re.I
    )
    if source is None:
        return None, "copular_boolean_relation_missing"
    actual, actual_copula, negative, classification = source.groups()
    actual = _copular_source_subject(binding, actual, subject)
    choices = re.split(r"\s+or\s+", predicate, flags=re.I)
    if (
        _canonical_argument(actual) != _canonical_argument(subject)
        or actual_copula.casefold() != copula.casefold()
        or _canonical_argument(classification)
        not in {_canonical_argument(c) for c in choices}
        or (len(choices) > 1 and negative)
    ):
        return None, "copular_boolean_subject_or_class_mismatch"
    return (
        f"{_boolean_namespace(binding.req)}{subject} {copula} "
        f"{'not ' if negative else ''}{classification}",
        None,
    )


def _factual_boolean_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    question = _without_preface(binding.req.question).strip().rstrip("?. ")
    request = re.fullmatch(
        rf"(does|do)\s+(?:the\s+)?{re.escape(binding.topic)}\s+([\w-]+)\s+(.+)",
        question,
        re.I,
    )
    if request is None:
        return None, "factual_boolean_request_missing"
    auxiliary, verb, obj = request.groups()
    auxiliary = auxiliary.casefold()
    if binding.topic.casefold() in {"it", "they", "this", "that", "these", "those"}:
        return None, "unresolved_boolean_subject"
    source = re.fullmatch(
        rf"(.+?)\s+(does|do)\s+(not\s+)?{re.escape(verb)}\s+(.+)",
        _boolean_local(binding),
        re.I,
    )
    if source is None:
        return None, "factual_boolean_relation_missing"
    actor, source_aux, negative, actual_obj = source.groups()
    if source_aux.casefold() != auxiliary or _canonical_argument(
        actual_obj
    ) != _canonical_argument(obj):
        return None, "factual_boolean_object_mismatch"
    actor = _copular_source_subject(binding, actor, binding.topic)
    if _canonical_argument(actor) != _canonical_argument(binding.topic):
        return None, "factual_boolean_subject_mismatch"
    polarity = " not" if negative else ""
    return f"{binding.topic} {auxiliary}{polarity} {verb} {obj}", None


def _relative_boolean_subject(text: str) -> str:
    text = _canonical_argument(text)
    relative = re.search(r"\bthat\s+([\w-]+)\s+", text)
    if relative:
        finite = relative.group(1)
        base = (
            finite[:-2]
            if re.search(r"(?:ch|sh|[sxzo])es$", finite)
            else finite[:-1]
            if finite.endswith("s")
            else finite
        )
        text = (
            text[: relative.start()]
            + _regular_gerund(base)
            + " "
            + text[relative.end() :]
        )
    return re.sub(r"(\bwithout\s+\w+ing)\s+it$", r"\1", text)


def _passive_classification_hypothesis(
    binding: _Binding, question: str
) -> tuple[str | None, str | None]:
    request = re.fullmatch(r"(?:is|are)\s+(.+?)\s+([\w-]+)", question, re.I)
    source = re.fullmatch(
        r"(.+?)\s+treats\s+(.+?)\s+as\s+(.+)", _boolean_local(binding), re.I
    )
    if request is None or source is None:
        return None, "unsupported_copular_boolean"
    subject, predicate = request.groups()
    actor, actual, classification = source.groups()
    if _canonical_argument(actor) != _canonical_argument(
        binding.topic
    ) or _relative_boolean_subject(subject) != _relative_boolean_subject(actual):
        return None, "passive_boolean_subject_or_condition_mismatch"
    head = _canonical_argument(subject).split()[0]
    classified = re.fullmatch(
        rf"(?:{_CARDINAL}\s+)?(un)?{re.escape(predicate)}\s+{re.escape(head)}s?",
        _canonical_argument(classification),
        re.I,
    )
    if classified is None:
        return None, "passive_boolean_class_mismatch"
    return (
        f"{_boolean_namespace(binding.req)}{subject} is "
        f"{'not ' if classified.group(1) else ''}{predicate}",
        None,
    )


def _procedure_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    req = binding.req
    value = binding.value
    topic = binding.topic
    if not _ordered_steps(value) and not _unnumbered_blocks(req, value):
        return None, "ordered_instruction_block_missing"
    scope = re.match(r"\s*(?:(?:for|procedure\s+for)\s+)?([^,:;.?!]+)[,:]", value, re.I)
    if scope and not _procedure_action_target(
        req, scope.group(1), value[scope.end() :]
    ):
        return None, "procedure_action_target_mismatch"
    if _procedure_heading_conflict(req, value):
        return None, "procedure_activity_mismatch"
    if _procedure_scope_prohibited(req, value):
        return None, "procedure_scope_prohibited"
    if not _procedure_constraints(req.original_text, value):
        return None, "procedure_original_constraint_missing"
    if not _procedure_numbers_present(req.original_text, value):
        return None, "procedure_parameter_missing"
    hypothesis = f"The procedure for {topic} is: {value}"
    if _phrasal_action(topic):
        hypothesis = f"The procedure to {topic} is: {value}"
    qualifier = re.match(r"(standard|ordinary|normal)\s+", topic, re.I)
    if qualifier and _condition_header(req, binding.context):
        hypothesis = (
            f"For {qualifier.group(1).casefold()} conditions, the procedure "
            f"for {_the(topic[qualifier.end() :])} is: {value}"
        )
    parameters = re.search(
        r"\b(?:with|including|covering|using)\s+.+", req.original_text, re.I
    )
    if parameters:
        modifier = parameters.group().rstrip("?. ")
        hypothesis = hypothesis.replace(" is:", f", {modifier}, is:", 1)
    return hypothesis, None


def _generic_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    req, premise, topic, value = (
        binding.req,
        binding.premise,
        binding.topic,
        binding.value,
    )
    if re.match(r"\s*who\b", req.original_text, re.I):
        return _transitive_hypothesis(binding)
    if req.relation.startswith("identity_"):
        return _identity_hypothesis(binding)
    question = re.fullmatch(
        r"\s*(?:which|what)\s+([\w\s-]+?)\s+(is|are)\s+(.+?)[?.]*\s*",
        req.original_text,
        re.I,
    )
    if question is None:
        return relation_hypothesis(binding)
    attribute, copula, complement = question.groups()
    complement = complement.rstrip("?. ")
    subject = re.search(rf"(?:the\s+)?{re.escape(topic)}$", complement, re.I)
    if subject is None:
        return None, "unsupported_question_transformation"
    relation = complement[: subject.start()].strip()
    if not re.fullmatch(r"[\w\s-]+\s+(?:for|to|in|of|by|on|at)", relation, re.I):
        return None, "unsupported_question_transformation"
    predicate = re.search(rf"\b(?:is|are)\s+{re.escape(relation)}\s+", premise, re.I)
    if (
        predicate is None or binding.end - binding.clause_start > predicate.start()
    ) and not _named_argument(binding):
        return None, "requested_relation_not_selected_argument"
    target = (
        premise
        if predicate is None
        else re.split(
            r"\s+(?:and|but)\s+|[,;.!?]",
            premise[predicate.end() :],
            maxsplit=1,
            flags=re.I,
        )[0]
    )
    if not set(req.anchors).issubset(_words(target)):
        return None, "relationship_subject_missing"
    if not (_words(attribute) - _GRAMMAR).issubset(_words(premise)):
        return None, "requested_attribute_missing"
    return f"{value} {copula} the {attribute} {complement}", None


def _named_argument(binding: _Binding) -> bool:
    named = re.search(
        r"\b(?:is|are)\s+(?:named|called)\s+([^.;]+)", binding.premise, re.I
    )
    return bool(
        named
        and named.start(1)
        <= binding.start - binding.clause_start
        < binding.end - binding.clause_start
        <= named.end(1)
    )


def _identity_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    if not _named_argument(binding):
        return None, "identity_argument_missing"
    head = re.findall(r"\w[\w-]*", binding.topic)[-1]
    if not re.search(rf"\b{re.escape(head)}\b", binding.premise, re.I):
        return None, "requested_identity_type_missing"
    if binding.req.relation == "identity_name":
        return f"The name of {_the(binding.topic)} is {binding.value}", None
    if binding.req.relation == "identity_called":
        subject = _the(binding.topic)
        return f"{subject[0].upper() + subject[1:]} is called {binding.value}", None
    return f"{binding.value} is {_the(binding.topic)}", None


def _transitive_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    request = re.fullmatch(
        r"\s*who\s+([\w-]+)\s+(.+?)[?.]*\s*", binding.req.original_text, re.I
    )
    if request is None or request.group(1).casefold() in {
        "is",
        "are",
        "was",
        "were",
        "does",
        "do",
        "did",
        "may",
        "must",
        "can",
    }:
        return None, "unsupported_question_transformation"
    verb, topic = request.groups()
    topic = topic.rstrip("?. ")
    source = re.search(
        rf"(?P<value>[^.;]+?)\s+{re.escape(verb)}\s+(?:the\s+)?{re.escape(topic)}\s*$",
        binding.premise,
        re.I,
    )
    if source is None or re.search(
        r"\b(?:never|not|neither|nor|cannot)\b", source.group("value"), re.I
    ):
        return None, "requested_relation_not_selected_argument"
    if not (
        source.start("value")
        <= binding.start - binding.clause_start
        < binding.end - binding.clause_start
        <= source.end("value")
    ):
        return None, "requested_relation_not_selected_argument"
    argument = re.sub(
        r"^(?:the|a|an)\s+", "", source.group("value").strip(), flags=re.I
    )
    selected = re.sub(r"^(?:the|a|an)\s+", "", binding.value.strip(), flags=re.I)
    if argument.casefold() != selected.casefold():
        return None, "selected_subject_is_not_complete_argument"
    return f"{binding.value} {verb} {topic}", None


def _canonical_argument(text: str) -> str:
    return re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.I).casefold()


def role_argument_identity(text: str) -> str:
    """Reuse existing literal article/case identity for duplicate/conflict checks."""
    return _canonical_argument(text)


def non_role_attribute_context(requirement: Requirement, context: str) -> bool:
    """Recognize another existing typed field for role-inspection irrelevance.

    This does not establish that field's truth and never calls NLI. Unknown
    imperatives/cross-references cannot be excluded by missing role keywords.
    """
    from app.services.answer_requirements import plan_requirements

    questions = (
        f"How long does {requirement.topic} last?",
        f"What is the maximum participant count for {requirement.topic}?",
        f"What day does {requirement.topic} start?",
        f"What time does {requirement.topic} start?",
    )
    values = tuple(
        re.finditer(
            rf"\d{{1,2}}:\d{{2}}|\d+(?:\s+{_DURATION_UNIT})?|\b{_WEEKDAY}\b",
            context,
            re.I,
        )
    )
    for question in questions:
        try:
            prepared = plan_requirements(question)
        except ValueError:
            continue
        if len(prepared) != 1:
            continue
        if any(
            support_claim(prepared[0], context, value.start(), value.end()).rejection
            is None
            for value in values
        ):
            return True
    return False


def _expanded_argument(binding: _Binding) -> _Binding:
    interval = None
    operation = _operation_deputy_context(
        binding.req, binding.context, binding.start, binding.end
    )
    if operation:
        first, last = operation[4:6]
        return replace(
            binding, start=first, end=last, value=binding.context[first:last]
        )
    if binding.req.kind in {"owner", "deputy"}:
        interval = _role_argument(binding.req, binding.premise)
    elif binding.req.kind == "generic" and re.match(
        r"\s*who\b", binding.req.original_text, re.I
    ):
        request = re.fullmatch(
            r"\s*who\s+([\w-]+)\s+(.+?)[?.]*\s*", binding.req.original_text, re.I
        )
        if request:
            source = re.search(
                rf"(?P<value>[^.;]+?)\s+{re.escape(request.group(1))}\s+"
                rf"(?:the\s+)?{re.escape(request.group(2).rstrip('?. '))}\s*$",
                binding.premise,
                re.I,
            )
            interval = source.span("value") if source else None
    if interval is None:
        return binding
    first, last = interval
    while first < last and binding.premise[first].isspace():
        first += 1
    while first < last and binding.premise[last - 1].isspace():
        last -= 1
    full = binding.premise[first:last]
    if _canonical_argument(full) == _canonical_argument(binding.value):
        return binding
    start, end = binding.clause_start + first, binding.clause_start + last
    if start <= binding.start < binding.end <= end:
        return replace(binding, start=start, end=end, value=binding.context[start:end])
    return binding


def _operation_deputy_context(req, context: str, start: int, end: int):
    """One adjacent literal operation declaration in the same source context.

    No lookup across other paragraphs/documents, competing antecedents or role
    equivalence is permitted. The caller still checks current source authority,
    conditions and every separate NLI obligation.
    """
    if req.kind != "deputy" or req.relation != "deputy" or req.depends_on:
        return None
    from app.services.role_scope_inspection import _complete_role_designator

    left, right = _clause(context, start, end)
    left += len(context[left:right]) - len(context[left:right].lstrip())
    text = context[left:right].rstrip()
    right = left + len(text)
    local = re.fullmatch(
        r"(?:the\s+)?deputy\s+for\s+that\s+operation\s+is\s+(?P<value>.+)", text, re.I
    )
    if local is None:
        return None
    first, last = (left + point for point in local.span("value"))
    if not first <= start < end <= last:
        return None
    before = context[:left].rstrip()
    if not before.endswith((".", "!", "?")):
        return None
    prior_end = len(before) - 1
    prior_start = max(
        (m.end() for m in re.finditer(r"[.!?;\n]", context[:prior_end])), default=0
    )
    prior_start += len(context[prior_start:prior_end]) - len(
        context[prior_start:prior_end].lstrip()
    )
    prior = context[prior_start:prior_end].rstrip()
    prior_end = prior_start + len(prior)
    owner = re.fullmatch(
        r"(?:the\s+)?owner\s+of\s+(?P<target>.+?)\s+is\s+(?P<value>.+)", prior, re.I
    )
    if (
        owner is None
        or not _complete_role_designator(owner.group("value"))
        or not _complete_role_designator(local.group("value"))
        or not owner.group("target").casefold().endswith(" ordinary operation")
        or _canonical_argument(owner.group("target")) != _canonical_argument(req.topic)
        or _role_argument(replace(req, kind="owner", relation="owner"), prior)
        != owner.span("value")
        or _role_argument(replace(req, topic="that operation", anchors=()), text)
        is None
        or "\n\n" in context[prior_end:left]
    ):
        return None
    return prior_start, prior_end, left, right, first, last


def _operation_deputy_proof(binding: _Binding) -> _AtomicProof | None:
    coordinates = _operation_deputy_context(
        binding.req, binding.context, binding.start, binding.end
    )
    if coordinates is None:
        return None
    first, middle, local, last, _, _ = coordinates
    owner = binding.context[first:middle]
    deputy = binding.context[local:last]
    return _AtomicProof(
        f"{binding.value} is the deputy for {binding.topic}",
        binding.context[first:last],
        first,
        last,
        (
            SupportCheck("operation_owner_antecedent", owner, owner, first, middle),
            SupportCheck("operation_deputy_assignment", deputy, deputy, local, last),
        ),
        (
            SupportEdge(
                "operation_antecedent_to_deputy",
                first,
                middle,
                local,
                last,
                binding.req.id,
                binding.req.depends_on,
            ),
        ),
    )


def _instruction_clauses(block: str) -> list[str]:
    return [
        piece.strip()
        for piece in re.split(
            r"[.;!?]|,\s*(?:(?:and|then|finally|next)\s+)?|\b(?:first|then|finally|next)\b",
            block,
            flags=re.I,
        )
        if piece.strip()
    ]


def _positive_instruction(prefix: str) -> bool:
    return not re.search(r"\b(?:not|never|cannot|if|when|unless)\b", prefix, re.I)


def _configuration_bound(configuration: str, clauses: list[str]) -> bool:
    for clause in clauses:
        match = re.search(
            r"\b(?:select|choose|use|load|apply|open|run\s+with)\s+(.+)$", clause, re.I
        )
        if (
            match
            and _positive_instruction(clause[: match.start()])
            and _canonical_argument(match.group(1))
            == _canonical_argument(configuration)
        ):
            return True
    return False


def _destination_bound(
    operation: str, obj: str, destination: str, clauses: list[str]
) -> bool:
    stem = operation[:-3]
    for clause in clauses:
        match = re.search(rf"\b{re.escape(stem)}e?\s+(.+?)\s+to\s+(.+)$", clause, re.I)
        if (
            match
            and _positive_instruction(clause[: match.start()])
            and _canonical_argument(match.group(1)) == _canonical_argument(obj)
            and _canonical_argument(match.group(2)) == _canonical_argument(destination)
        ):
            return True
    return False


def _procedure_constraints(question: str, block: str) -> bool:
    clauses = _instruction_clauses(block)
    configured = re.search(
        r"\bwith\s+(.+?)(?=,\s*(?:including|covering)|[?.]|$)", question, re.I
    )
    if configured and "," not in configured.group(1):
        for configuration in re.split(r"\s+and\s+", configured.group(1), flags=re.I):
            if not re.search(r"\d", configuration):
                negative = _negative_mark(configuration)
                if negative:
                    if not _worksheet_negative_mark_bound(negative, block):
                        return False
                elif not _configuration_bound(configuration, clauses):
                    return False
    negative = _negative_mark(question)
    if negative and not _worksheet_negative_mark_bound(negative, block):
        return False
    for destination in re.finditer(
        r"\b((?!(?:including|covering)\b)\w+ing)\s+(.+?)\s+to\s+(.+?)(?=[,.?!]|$)",
        question,
        re.I,
    ):
        if not _destination_bound(
            destination.group(1), destination.group(2), destination.group(3), clauses
        ):
            return False
    return True


def _procedure_heading_conflict(req: Requirement, block: str) -> bool:
    heading = _SECTION_HEAD.search(block)
    if heading is None:
        return False
    scope = heading.group("scope") or heading.group("title")
    action = _phrasal_action(req.topic)
    if action and (
        (action[0] + action[1]).casefold() in _words(scope)
        or (req.anchors and set(req.anchors).issubset(_words(scope)))
    ):
        return not _procedure_scope_matches(req, scope, block[heading.end() :])
    if not req.anchors or not set(req.anchors).issubset(_words(scope)):
        return False
    subject = re.sub(
        r"\b(?:complete|ordered|procedure|steps|instructions)\b", "", scope, flags=re.I
    )
    return _activity_conflict(req, subject)


def _procedure_numbers_present(question: str, block: str) -> bool:
    requested = set(re.findall(r"\b\d+\b", question))
    if not requested.issubset(set(re.findall(r"\b\d+\b", block))):
        return False
    for number, unit in re.findall(r"\b(\d+(?:\.\d+)?)\s+([\w-]+)", question):
        unit_pattern = re.escape(unit.rstrip("s")) + "s?"
        if not re.search(rf"\b{re.escape(number)}\s+{unit_pattern}\b", block, re.I):
            return False
    return True


def _procedure_scope_prohibited(req: Requirement, block: str) -> bool:
    requested = _words(req.topic) - _GRAMMAR
    restrictions = (
        *_PROCEDURE_RESTRICTION.finditer(block),
        *_SCOPED_PROCEDURE_RESTRICTION.finditer(block),
    )
    for restriction in restrictions:
        scope = restriction.group("scope")
        if scope is None or (_words(scope) - _GRAMMAR).issubset(requested):
            return True
    return False


def _procedure_goal_window(block: str) -> str:
    # One fixed source rule, independent of NLI scores: heading and prerequisites
    # through the first governing instruction sentence. Numeric list-marker
    # periods are punctuation within that sentence, not sentence boundaries.
    heading = _SECTION_HEAD.search(block)
    markers = _step_markers(block)
    instruction = heading.end() if heading else (markers[0].end() if markers else 0)
    marker_ends = {marker.end() for marker in markers if marker.group(1)}
    for ending in re.finditer(r"[.!?](?=\s|$)", block):
        if ending.end() > instruction and ending.end() not in marker_ends:
            return block[: ending.end()]
    return block


def _procedure_checks(binding: _Binding) -> tuple[SupportCheck, ...]:
    req, block = binding.req, binding.value
    checks = []
    configured = re.search(
        r"\bwith\s+(.+?)(?=,\s*(?:including|covering)|[?.]|$)", req.original_text, re.I
    )
    if configured and "," not in configured.group(1):
        for index, configuration in enumerate(
            re.split(r"\s+and\s+", configured.group(1), flags=re.I)
        ):
            if re.search(r"\d", configuration) or _negative_mark(configuration):
                continue
            literal = (
                r"\b"
                + r"\s+".join(
                    re.escape(word)
                    for word in _canonical_argument(configuration).split()
                )
                + r"\b"
            )
            for occurrence in re.finditer(literal, block, re.I):
                # Heading through governing clause is a literal contiguous source
                # window. Never begin at an embedded positive verb after denial.
                stop = re.search(r"[,;.!?](?=\s|$)", block[occurrence.end() :])
                right = occurrence.end() + stop.end() if stop else len(block)
                checks.append(
                    SupportCheck(
                        f"procedure_configuration_{index + 1}",
                        block[:right],
                        f"The instructions for {req.topic} "
                        f"require using {configuration}.",
                        binding.start,
                        binding.start + right,
                    )
                )
                break
    if _negative_mark(req.original_text):
        declaration = _worksheet_declaration(block)
        if declaration is not None:
            checks.append(
                SupportCheck(
                    "procedure_applicability",
                    declaration.group().strip(),
                    f"The procedure applies to {declaration.group('conditions')}.",
                    binding.start
                    + declaration.start()
                    + len(declaration.group())
                    - len(declaration.group().lstrip()),
                    binding.start + declaration.end(),
                )
            )
    if _phrasal_action(req.topic):
        checks.append(
            SupportCheck(
                "procedure_action_target",
                _procedure_goal_window(block),
                f"The instructions describe how to {req.topic}.",
                binding.start,
                binding.start + len(_procedure_goal_window(block)),
            )
        )
    for index, destination in enumerate(
        re.finditer(
            r"\b((?!(?:including|covering)\b)\w+ing)\s+(.+?)\s+to\s+(.+?)(?=[,.?!]|$)",
            req.original_text,
            re.I,
        )
    ):
        checks.append(
            SupportCheck(
                f"procedure_destination_{index + 1}",
                block,
                f"The instructions for {req.topic} require {destination.group(0)}.",
                binding.start,
                binding.end,
            )
        )
    return tuple(checks)


def _the(text: str) -> str:
    return text if re.match(r"the\s+", text, re.I) else "the " + text


def _condition_header(req: Requirement, context: str) -> str:
    qualifier = re.match(r"(standard|ordinary|normal)\s+", req.topic, re.I)
    first = re.match(r"[^.!?]*(?:[.!?]|$)", context)
    if qualifier is None or first is None:
        return ""
    condition = r"(?:standard|ordinary|normal)"
    return (
        first.group().strip()
        if re.search(rf"\b{condition}\s+(?:conditions|sessions)\b", first.group(), re.I)
        else ""
    )


def _header_rejection(req: Requirement, context: str) -> str | None:
    header = _condition_header(req, context)
    if not header:
        return None
    if re.search(
        r"\b(?:(?:does|do|is|are)\s+not|never|no\s+longer)\s+(?:apply|applies|applicable|applying)\b",
        header,
        re.I,
    ):
        return "condition_header_application_negated"
    if _foreign_qualifier(req, header):
        return "condition_header_subject_mismatch"
    return None


def _verification_premise(
    req: Requirement, context: str, premise: str, start: int = 0
) -> str:
    # A governing header may be needed for meaning, but adding it must not
    # fabricate a noncontiguous source passage or omit intervening qualifiers.
    occurrences = [
        m
        for m in re.finditer(re.escape(premise), context)
        if m.start() <= start < m.end()
    ]
    if not occurrences:
        return premise
    selected = occurrences[-1]
    left, right = selected.span()
    scope = _scope_prefix(req, context, start, premise)
    expected = re.match(r"\s*(?:for|in|at|regarding)\s+([^,;:.]+)[,:]", req.topic, re.I)
    if expected and (_words(expected.group(1)) - _GRAMMAR).issubset(_words(premise)):
        scope = ""
    header = _condition_header(req, context)
    qualifier = re.match(r"(standard|ordinary|normal)\s+", req.topic, re.I)
    if qualifier and qualifier.group(1).casefold() in _words(premise):
        header = ""
    for prefix in (scope, header):
        if prefix:
            governing = context.rfind(prefix, 0, selected.start() + len(prefix))
            if 0 <= governing <= selected.start():
                left = min(left, governing)
    if req.kind == "prohibition" and _worksheet_scope_prefix(
        req, context, start, premise
    ):
        following = _worksheet_following_declaration(context, selected.start(), premise)
        if following is not None:
            right = following[1]
    return context[left:right]


_HYPOTHESES = {
    "owner": _role_hypothesis,
    "deputy": _role_hypothesis,
    "duration": _duration_hypothesis,
    "start_time": _start_hypothesis,
    "weekday": _weekday_hypothesis,
    "availability": _availability_hypothesis,
    "quantity": _quantity_hypothesis,
    "prohibition": _prohibition_hypothesis,
    "boolean": _boolean_hypothesis,
    "procedure": _procedure_hypothesis,
    "generic": _generic_hypothesis,
}


def _applicability_topic(req: Requirement) -> str:
    if req.relation in {"owner_relative_deputy", "cover_window"}:
        scope = re.match(r"\s*For\s+([^,;?!]+),\s*", req.question, re.I)
        if scope is not None:
            return scope.group(1)
    return req.topic or req.question


def condition_relation(req: Requirement, context: str, metadata: dict) -> str:
    """Literal explicit conditions only; never a broad contradiction verdict."""
    condition = metadata.get("condition")
    if not isinstance(condition, str) or not condition.strip():
        leading = re.match(r"\s*(?:for|when|if)\s+([^,;:.]+)[,;:]", context, re.I)
        if leading is None:
            leading = re.match(
                r"\s*((?:exception|retest)\b[^,;:.]*)[,;:]", context, re.I
            )
        condition = leading.group(1) if leading else ""
    if not metadata.get("condition") and req.kind == "procedure":
        topic_header = re.match(r"\s*for\s+([^,;:.]+)[,;:]", context, re.I)
        if topic_header and _procedure_scope_matches(
            req, topic_header.group(1), context[topic_header.end() :]
        ):
            return "applies"
    requested = _words(_applicability_topic(req)) - _GRAMMAR
    conditional = _words(condition) - _GRAMMAR
    if conditional:
        if {"exception", "retest"} & conditional and not (
            {"exception", "retest"} & requested
        ):
            return "irrelevant"
        if conditional.issubset(requested):
            return "applies"
        # Shared names alone do not demonstrate matching activities.
        if requested and not (requested & conditional):
            return "irrelevant"
        return "unknown"
    # No applicability condition was stated. Subject, relation and actual
    # entailment are separate checks; this is not another literal topic gate.
    return "applies"


def _literal_workspace(text: str) -> str | None:
    match = re.search(r"\bworkspace\s+[\"']?([\w-]+)", text, re.I)
    return match.group(1) if match else None


_DECLARED_SCOPE = re.compile(r"^\s*for\s+(.+?)[,:]", re.I)
_SCOPE_ONLY = re.compile(r"\bapplies\s+only\s+to\s+([^,;.!?]+)", re.I)
_SCOPE_DENIAL = re.compile(
    r"\b(?:does|do|did)\s+not\s+(?:govern|apply\s+to)\s+([^,;.!?]+)", re.I
)
_SCOPE_POSITIVE = re.compile(r"\b(?:governs?|applies\s+to)\s+([^,;.!?]+)", re.I)
_NEGATED = re.compile(r"\b(?:does|do|did|will|would|may|can|shall)\s+not\s+$", re.I)


def _declared_clause_scope(req: Requirement, clause: str) -> list[str] | None:
    """One clause's declaration decisions; None keeps coverage possible."""
    decisions = []
    for match in _SCOPE_ONLY.finditer(clause):
        decision = _scope_target(req, match.group(1))
        if decision == "applies":
            return None  # Declared coverage of the requested scope.
        decisions.append(decision)
    for match in _SCOPE_DENIAL.finditer(clause):
        decision = _scope_target(req, match.group(1))
        # Only a denial of the requested scope excludes; denying another
        # scope carries no applicability information. The denied target
        # naming the same activity modulo its class suffix (e.g. "the
        # standard <activity> routine") denies the requested scope too.
        denied_same = _without_class(_canonical_argument(match.group(1)))
        requested_same = _without_class(_canonical_argument(req.topic))
        if decision == "applies" or denied_same == requested_same:
            decisions.append("irrelevant")
        elif decision == "unknown":
            decisions.append("unknown")
    for match in _SCOPE_POSITIVE.finditer(clause):
        if _NEGATED.search(clause[: match.start()]):
            continue
        decision = _scope_target(req, match.group(1))
        if decision == "applies":
            return None  # Declared coverage of the requested scope.
        decisions.append(decision)
    return decisions


def _declared_source_scope(req: Requirement, content: str) -> str | None:
    """Literal whole-source scope declarations; None leaves kind dispatch.

    A "For <scope>," clause header scopes its clause, and a source's own
    "applies only to <scope>" / "does not govern <scope>" declarations bound
    its coverage. Ambiguous scopes and declared coverage of the requested
    scope keep the source unclassified here.
    """
    topic = _applicability_topic(req)
    scoped = (
        req
        if topic == req.topic
        else replace(req, topic=topic, anchors=named_anchors(topic))
    )
    decisions = []
    for piece in re.split(r"[.!?;\n]", content):
        clause = piece.strip()
        if not clause:
            continue
        declared = _declared_clause_scope(scoped, clause)
        if declared is None:
            return None
        lead = _DECLARED_SCOPE.match(clause)
        if lead is not None:
            decisions.append(_scope_target(scoped, lead.group(1)))
        elif not declared:
            # A header scopes only its own clause; an unheaded clause carrying
            # no declaration of its own cannot join a whole-source exclusion.
            decisions.append("unknown")
        decisions += declared
    if decisions and all(value == "irrelevant" for value in decisions):
        return "irrelevant"
    return None


def source_relation_scope(req: Requirement, content: str) -> str:
    """Body-only relation scope, never support, authority or group inheritance.

    A named activity elsewhere in the chunk cannot scope another predicate.
    Missing/abbreviated targets stay unknown; explicit other targets exclude.
    Applicability conditions and accepted evidence remain independent guards.
    """
    declared = _declared_source_scope(req, content)
    if declared is not None:
        return declared
    if req.kind in {"owner", "deputy"}:
        return _role_source_scope(req, content)
    if req.kind == "procedure":
        return _procedure_source_scope(req, content)
    return "unknown"


def _scope_union(scopes: list[str]) -> str:
    if "applies" in scopes:
        return "applies"
    return "unknown" if not scopes or "unknown" in scopes else "irrelevant"


def _without_class(text: str) -> str:
    text = re.sub(r"^(?:ordinary|standard|normal)\s+", "", text)
    return re.sub(
        r"\s+(?:sessions?|routines?|procedures?|instructions?|steps?|methods?)$",
        "",
        text,
    )


def _scope_target(req: Requirement, target: str) -> str:
    target = re.sub(
        r"\s+is\s+(?:not\s+)?(?:led|owned)\s+by\s*$", "", target, flags=re.I
    )
    target = re.sub(r"\s+is\s*$", "", target, flags=re.I)
    target = re.sub(r"\s+only\s*$", "", target, flags=re.I)
    target = re.sub(
        r"^(?:the\s+)?(?:owner|deputy)\s+(?:of|for)\s+", "", target, flags=re.I
    )
    target = re.sub(r"\s+(?:owner|deputy)\s*$", "", target, flags=re.I)
    actual, expected = _canonical_argument(target), _canonical_argument(req.topic)
    if actual == expected or (
        req.kind == "deputy"
        and req.depends_on
        and _authorized_owner_target(req, target)
    ):
        return "applies"
    actual_words = _words(actual)
    if actual_words.issubset(
        _GRAMMAR
        | {
            "complete",
            "ordered",
            "procedure",
            "method",
            "steps",
            "instructions",
            "following",
        }
    ):
        return "unknown"
    names = set(named_anchors(target))
    anchors = set(req.anchors)
    if names and anchors and not anchors.issubset(actual_words):
        return "irrelevant"
    if not anchors or not anchors.issubset(actual_words):
        return "unknown"
    if actual_words.issubset(anchors):
        return "unknown"

    if _without_class(actual) == _without_class(expected):
        return "unknown"  # No implicit activity/session or condition bridge.
    return "irrelevant"


def _event_target_scope(req: Requirement, clause: str, target: str) -> str:
    workspace = _literal_workspace(clause)
    if (
        req.source_workspace
        and workspace
        and workspace.casefold() != req.source_workspace.casefold()
    ):
        return "irrelevant"
    return _scope_target(req, target)


def _role_scope_events(req: Requirement, clause: str) -> list[str]:
    strict = (
        replace(req, relation="owns")
        if req.kind == "owner" and req.relation == "owner"
        else req
    )
    scopes = []
    for pattern, after in _role_patterns(strict, for_scope=True):
        for match in re.finditer(pattern, clause, re.I):
            target = _role_target(match, clause, after)
            scopes.append(_event_target_scope(strict, clause, target))
    return scopes


def _role_field_scope_events(req: Requirement, clause: str) -> list[str]:
    if req.kind == "deputy":
        requested = "deputy"
    elif req.relation == "leads":
        requested = "lead"
    elif req.relation in {"owner", "owns"}:
        requested = "owner"
    else:
        return []
    scopes = []
    for pattern, _ in _role_field_patterns(None):
        for match in re.finditer(pattern, clause, re.I):
            label = _canonical_argument(match.group("field"))
            current = re.sub(r"^(?:current|actual)\s+", "", label)
            if current == requested:
                scopes.append(_event_target_scope(req, clause, match.group("target")))
            elif label.endswith(" " + requested) and not re.search(
                r"\b(?:to|of)\b", label
            ):
                scopes.append("unknown")
            else:
                scopes.append("irrelevant")
    return scopes


def _other_role_predicate(req: Requirement, clause: str) -> bool:
    return any(
        (kind, relation) != (req.kind, req.relation)
        and _role_scope_events(replace(req, kind=kind, relation=relation), clause)
        for kind, relation in (
            ("owner", "leads"),
            ("owner", "owns"),
            ("deputy", "deputy"),
        )
    )


def _role_source_scope(req: Requirement, content: str) -> str:
    scopes = []
    for piece in re.split(r"[.!?;\n]", content):
        clause = piece.strip()
        if not clause:
            continue
        found = _role_scope_events(req, clause) + _role_field_scope_events(req, clause)
        if found:
            scopes.extend(found)
        elif _other_role_predicate(req, clause):
            scopes.append("irrelevant")
    return _scope_union(scopes)


def _worksheet_source_scope(
    req: Requirement, content: str, left: int, declaration: re.Match[str]
) -> str:
    ancestors = list(
        _WORKSHEET_NAMESPACE.finditer(content, 0, left + declaration.start())
    )
    if not ancestors:
        return "unknown"
    base = re.sub(r"^(?:ordinary|standard|normal)\s+", "", req.topic, flags=re.I)
    base = re.split(r"\s+worksheet\b|\s+with\s+no\b", base, maxsplit=1, flags=re.I)[0]
    scope = _scope_target(replace(req, topic=base), ancestors[-1].group("scope"))
    if scope != "applies":
        return scope
    mark = _negative_mark(req.topic)
    if mark and re.search(
        rf"\bwith\s+(?:an?|the)\s+{re.escape(mark)}\b",
        declaration.group("conditions"),
        re.I,
    ):
        return "irrelevant"
    if _worksheet_namespace(req, content, left + declaration.start()) is None:
        return "unknown"
    return "applies"


def _procedure_source_scope(req: Requirement, content: str) -> str:
    scopes = []
    for left, right in _procedure_blocks(req, content):
        block = content[left:right]
        marker = _STEP.search(block)
        headings = list(
            _SECTION_HEAD.finditer(block, 0, marker.end() if marker else len(block))
        )
        if headings:
            heading = headings[-1]
            scope = heading.group("scope") or heading.group("title")
            scopes.append(
                "applies"
                if _procedure_scope_matches(req, scope, block[heading.end() :])
                else _scope_target(req, scope)
            )
        else:
            declaration = _worksheet_declaration(block)
            scopes.append(
                _worksheet_source_scope(req, content, left, declaration)
                if declaration is not None
                else "unknown"
            )
    return _scope_union(scopes)


def relation_present(req: Requirement, context: str) -> bool:
    """Exclude explicit other fact types; ambiguous language stays for NLI.

    This does not produce an answer or certify support. It is also deliberately
    independent of condition matching: callers must perform both checks.
    """
    signals = {
        "owner": r"\b(?:leads|owns|manages|owner|responsible\s+for)\b",
        "deputy": r"\b(?:deputy|deputizes|deputises)\b",
        "duration": rf"\b(?:lasts?|duration|takes?)\b.+\d|\d\s*{_DURATION_UNIT}\b",
        "start_time": r"\b(?:starts?|begins?|start\s+time)\b|\d{1,2}:\d{2}",
        "weekday": _WEEKDAY,
        "availability": r"\b(?:available|present|availability|hours)\b",
        "quantity": r"\b(?:count|number\s+of|maximum|quantity)\b",
        "prohibition": r"\b(?:prohibits?|forbidden|must\s+not)\b",
        "procedure": r"\bfirst\b.+\bthen\b",
    }
    if req.kind == "generic":
        property_question = re.match(
            r"\s*(?:which|what)\s+(.+?)\s+(?:is|are)\s+", req.original_text, re.I
        )
        if property_question:
            attribute = _words(property_question.group(1)) - _GRAMMAR
            return attribute.issubset(_words(context))
        if req.relation.startswith("identity_"):
            attribute = _words(req.topic) - set(req.anchors) - _GRAMMAR
            return not attribute or attribute.issubset(_words(context))
        return True
    if req.kind not in signals:
        return True
    if re.search(signals[req.kind], context, re.I | re.S):
        return True
    body = re.sub(r"^\s*(?:for|when|if)\s+[^,;]+[,;]\s*", "", context, flags=re.I)
    imperative = bool(re.match(r"[a-z]+\s+(?:the|a|an|by)\b", body, re.I))
    other_type = any(
        re.search(pattern, context, re.I | re.S)
        for kind, pattern in signals.items()
        if kind != req.kind
    )
    return not (imperative or other_type)


_DURATION_UNIT = r"(?:seconds?|minutes?|hours?|days?|weeks?)"
_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?"
_GRAMMAR = frozenset("the a an of for its it that in on at is are does do with".split())
_STEP = re.compile(
    r"(?:^|(?<=[.!?;:])\s*)(?:step\s+)?([1-9]\d*)\.(?=\s+[A-Za-z])"
    r"|(?:^|(?<=[.!?;,:])\s*)(?P<label>first|next|then|finally)\b",
    re.I,
)
_SECTION_HEAD = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:(?:for|procedure\s+for)\s+"
    r"(?P<scope>[^,:;.?!]+)[,:]|(?P<title>[^,:;.?!\n]+):)\s+",
    re.I,
)

_PROCEDURE_RESTRICTION = re.compile(
    r"(?:^|(?<=[.!?;])\s+)(?:never|do\s+not|must\s+not)\s+use\s+"
    r"(?:this|the)\s+procedure(?:\s+for\s+(?P<scope>[^.!?;]+))?\s*(?:[.!?;]|$)",
    re.I,
)

_SCOPED_PROCEDURE_RESTRICTION = re.compile(
    r"(?:^|(?<=[.!?;])\s+)for\s+(?P<scope>[^,;.!?]+),\s+"
    r"(?:the\s+)?(?:instructions|procedure)\s+(?:below|that\s+follow)\s+"
    r"(?:is|are)\s+prohibited\s*(?:[.!?;]|$)",
    re.I,
)


def _step_markers(value: str) -> list[re.Match[str]]:
    """Keep comma-linked discourse inside an established numeric outline."""
    markers = []
    numeric_start = None
    for marker in _STEP.finditer(value):
        if marker.group(1):
            if marker.group(1) == "1":
                numeric_start = marker
        else:
            inline = (
                numeric_start is not None
                and (marker.group("label") or "").casefold()
                in {"then", "next", "finally"}
                and value[: marker.start()].rstrip().endswith(",")
                and _SECTION_HEAD.search(value, numeric_start.end(), marker.start())
                is None
            )
            if inline:
                continue
            numeric_start = None
        markers.append(marker)
    return markers


def _ordered_steps(value: str) -> bool:
    markers = _step_markers(value)
    if len(markers) < 2:
        return False
    numbers = [int(m.group(1)) for m in markers if m.group(1)]
    if numbers:
        return len(numbers) == len(markers) and numbers == list(
            range(1, len(numbers) + 1)
        )
    return (markers[0].group("label") or "").casefold() == "first"


_WORKSHEET_DECLARATION = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:(?:the\s+)?following|this)\s+complete\s+"
    r"(?:procedure|method)\s+applies\s+to\s+(?P<conditions>[^.!?]+)[.!?]",
    re.I,
)
_WORKSHEET_NAMESPACE = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:this\s+is\s+(?:an?|the)\s+(?:invented\s+)?)?"
    r"(?P<scope>[^.!?;]+?)\s+worksheet\s+convention[.!?]",
    re.I,
)


def _worksheet_declaration(text: str) -> re.Match[str] | None:
    declarations = list(_WORKSHEET_DECLARATION.finditer(text))
    return declarations[-1] if declarations else None


def _negative_mark(text: str) -> str:
    normalized = text.replace("-", " ")
    match = re.search(
        r"\bno\s+(.+?)(?=\s+(?:procedure|method|worksheet)\b|[,?.]|$)",
        normalized,
        re.I,
    )
    return _canonical_argument(match.group(1)) if match else ""


def _worksheet_negative_mark_bound(mark: str, block: str) -> bool:
    declaration = _worksheet_declaration(block)
    return bool(
        declaration
        and _negative_mark(declaration.group("conditions")) == mark
        and not re.search(r"\b(?:unless|except|not|never)\b", declaration.group(), re.I)
    )


def _worksheet_following_declaration(
    context: str, start: int, premise: str
) -> tuple[int, int] | None:
    right = start + len(premise)
    if context[start:right] != premise:
        return None
    declaration = _worksheet_declaration(context[right:])
    if declaration is None or context[right : right + declaration.start()].strip(
        ".!? \r\n"
    ):
        return None
    return right + declaration.start(), right + declaration.end()


def _worksheet_governing_start(
    req: Requirement, context: str, start: int, premise: str
) -> int | None:
    block_start = context.rfind(premise, 0, start + len(premise))
    if block_start < 0:
        return None
    if req.kind == "prohibition":
        if not re.match(r"(?:do|must|should)\s+not\s+", premise, re.I):
            return None
        following = _worksheet_following_declaration(context, block_start, premise)
        return following[0] if following else None
    declaration = _worksheet_declaration(premise)
    return block_start + declaration.start() if declaration else None


def _worksheet_namespace(
    req: Requirement, context: str, declaration_start: int
) -> re.Match[str] | None:
    ancestors = list(_WORKSHEET_NAMESPACE.finditer(context, 0, declaration_start))
    if not ancestors:
        return None
    ancestor = ancestors[-1]
    scope = _canonical_argument(ancestor.group("scope"))
    requested = _canonical_argument(req.topic)
    if not re.search(rf"(?:^|\s){re.escape(scope)}(?:\s|$)", requested):
        return None
    if req.anchors and not set(req.anchors).issubset(_words(scope)):
        return None
    between = context[ancestor.end() : declaration_start]
    if declaration_start - ancestor.start() > 4096 or _worksheet_scope_reset(between):
        return None
    foreign = set(named_anchors(between)) - set(req.anchors)
    if foreign - {"ordinary", "standard", "normal", "before", "prerequisite"}:
        return None
    return ancestor


def _worksheet_scope_reset(between: str) -> bool:
    return bool(
        _WORKSHEET_DECLARATION.search(between)
        or _STEP.search(between)
        or _SECTION_HEAD.search(between)
        or re.search(
            r"(?:^|[.!?;:])\s*(?:when|if|unless|exception|retest)\b", between, re.I
        )
    )


def _worksheet_scope_prefix(
    req: Requirement, context: str, start: int, premise: str
) -> str:
    if req.kind not in {"procedure", "prohibition"}:
        return ""
    declaration_start = _worksheet_governing_start(req, context, start, premise)
    if declaration_start is None:
        return ""
    ancestor = _worksheet_namespace(req, context, declaration_start)
    return ancestor.group().strip() if ancestor else ""


def _worksheet_governance_rejection(binding: _Binding) -> str | None:
    if binding.req.kind not in {"procedure", "prohibition"}:
        return None
    declaration_start = _worksheet_governing_start(
        binding.req, binding.context, binding.start, binding.premise
    )
    if declaration_start is None or not _WORKSHEET_NAMESPACE.search(binding.context):
        return None
    ancestor = _worksheet_namespace(binding.req, binding.context, declaration_start)
    if ancestor is None or binding.end - ancestor.start() > 4096:
        return "worksheet_governance_not_established"
    if binding.req.kind == "procedure":
        declaration = _worksheet_declaration(binding.value)
        markers = _step_markers(binding.value)
        if (
            declaration is None
            or not markers
            or not _procedure_declaration_bridge(
                binding.req, binding.value, declaration.end(), markers[0].start()
            )
        ):
            return "worksheet_governance_not_established"
    return None


def _trimmed_range(context: str, start: int, end: int) -> tuple[int, int]:
    text = context[start:end]
    return start + len(text) - len(text.lstrip()), end - len(text) + len(text.rstrip())


def _worksheet_request_frame(binding: _Binding) -> bool:
    original = (
        _canonical_argument(binding.req.original_text).replace("-", " ").rstrip("?., ")
    )
    topic = _canonical_argument(binding.req.topic).replace("-", " ")
    condition_first = re.fullmatch(
        r"(?P<qualifier>ordinary|standard|normal)\s+(?P<scope>.+?)\s+"
        r"no\s+(?P<mark>.+?)\s+(?P<noun>procedure|method)",
        topic,
    )
    if condition_first is not None:
        requested = (
            rf"for\s+{re.escape(condition_first.group('scope'))},\s*"
            rf"take\s+me\s+through\s+every\s+step\s+of\s+the\s+"
            rf"{re.escape(condition_first.group('qualifier'))}\s+no\s+"
            rf"{re.escape(condition_first.group('mark'))}\s+"
            rf"{condition_first.group('noun')}\s+in\s+order"
        )
        if re.fullmatch(requested, original):
            return True
    if not original.endswith(topic):
        return False
    frame = original[: -len(topic)]
    grammar = _GRAMMAR | {
        "list",
        "give",
        "provide",
        "show",
        "describe",
        "explain",
        "what",
        "full",
        "complete",
        "ordered",
        "method",
        "procedure",
        "steps",
        "worksheet",
        "all",
        "each",
        "sequence",
        "order",
        "take",
        "me",
        "through",
        "every",
        "please",
    }
    return _words(frame).issubset(grammar)


def _worksheet_factorable(binding: _Binding, scope: str, conditions: str) -> bool:
    if not _worksheet_request_frame(binding):
        return False
    topic = _canonical_argument(binding.req.topic).replace("-", " ")
    scope = scope.replace("-", " ")
    mark = _negative_mark(binding.req.original_text)
    qualifier = re.match(r"(ordinary|standard|normal)\s+", topic, re.I)
    if not qualifier or not mark:
        return False
    condition = _canonical_argument(conditions)
    if condition != f"{qualifier.group(1)} worksheets with no {mark}":
        return False
    prefix = f"{qualifier.group(1)} {scope} "
    endings = {
        f"worksheet with no {mark}",
        f"worksheet bearing no {mark}",
        f"with no {mark}",
        f"no {mark} procedure",
        f"no {mark} method",
    }
    if not topic.startswith(prefix) or topic[len(prefix) :] not in endings:
        return False
    return not re.search(
        r"\b(?:including|covering|using)\b", binding.req.original_text, re.I
    )


def _worksheet_prohibitions(
    binding: _Binding,
    declaration_start: int,
    declaration_end: int,
    namespace_start: int,
    namespace_end: int,
) -> tuple[list[SupportCheck], list[SupportEdge]] | None:
    checks, edges = [], []
    cursor = binding.start
    while cursor < declaration_start:
        while cursor < declaration_start and binding.context[cursor].isspace():
            cursor += 1
        if cursor == declaration_start:
            break
        match = re.match(
            r"(?:(?:do|must)\s+not|never)\s+(?P<action>[^.!?]+)[.!?]",
            binding.context[cursor:declaration_start],
            re.I,
        )
        if match is None:
            return None
        verb, _, rest = match.group("action").partition(" ")
        checks.append(
            SupportCheck(
                f"procedure_prohibition_{len(checks) + 1}",
                binding.context[cursor:declaration_end],
                f"The complete procedure prohibits {_regular_gerund(verb)} {rest}.",
                cursor,
                declaration_end,
            )
        )
        edges.append(
            SupportEdge(
                "worksheet_namespace_to_prohibition",
                namespace_start,
                namespace_end,
                cursor,
                cursor + match.end(),
                binding.req.id,
                binding.req.depends_on,
            )
        )
        cursor += match.end()
    return checks, edges


def _worksheet_atomic_proof(binding: _Binding) -> _AtomicProof | None:
    if binding.req.kind != "procedure":
        return None
    declaration = _worksheet_declaration(binding.value)
    if declaration is None:
        return None
    declaration_start, declaration_end = _trimmed_range(
        binding.context,
        binding.start + declaration.start(),
        binding.start + declaration.end(),
    )
    ancestor = _worksheet_namespace(binding.req, binding.context, declaration_start)
    if ancestor is None or not _worksheet_factorable(
        binding,
        _canonical_argument(ancestor.group("scope")),
        declaration.group("conditions"),
    ):
        return None
    markers = _step_markers(binding.value)
    if not markers or binding.value[declaration.end() : markers[0].start()].strip():
        return None
    namespace_start, namespace_end = _trimmed_range(
        binding.context, ancestor.start(), ancestor.end()
    )
    prohibitions = _worksheet_prohibitions(
        binding, declaration_start, declaration_end, namespace_start, namespace_end
    )
    if prohibitions is None:
        return None  # Unknown prerequisites retain the original complete proof.
    instruction_start = binding.start + markers[0].start()
    while binding.context[instruction_start].isspace():
        instruction_start += 1
    checks = [
        SupportCheck(
            "procedure_namespace",
            binding.context[namespace_start:namespace_end],
            f"This is a {ancestor.group('scope').strip()} worksheet convention.",
            namespace_start,
            namespace_end,
        ),
        SupportCheck(
            "procedure_applicability",
            binding.context[declaration_start:declaration_end],
            f"The complete procedure applies to {declaration.group('conditions')}.",
            declaration_start,
            declaration_end,
        ),
        *prohibitions[0],
    ]
    edges = [
        SupportEdge(
            "worksheet_namespace_to_applicability",
            namespace_start,
            namespace_end,
            declaration_start,
            declaration_end,
            binding.req.id,
            binding.req.depends_on,
        ),
        SupportEdge(
            "worksheet_applicability_to_instructions",
            declaration_start,
            declaration_end,
            instruction_start,
            binding.end,
            binding.req.id,
            binding.req.depends_on,
        ),
        *prohibitions[1],
    ]
    instructions = binding.context[instruction_start : binding.end]
    return _AtomicProof(
        f"The complete procedure requires the following steps in order: {instructions}",
        binding.value,
        binding.start,
        binding.end,
        tuple(checks),
        tuple(edges),
    )


def _worksheet_prelude_start(req: Requirement, context: str, left: int) -> int:
    while left:
        preceding = context[:left].rstrip()
        previous_start = max(
            (m.end() for m in re.finditer(r"[.!?](?=\s|$)", preceding[:-1])), default=0
        )
        sentence = context[previous_start : len(preceding)].strip()
        negative = re.match(r"(?:do\s+not|never|must\s+not)\s+", sentence, re.I)
        prerequisite = re.match(r"(?:before|prerequisite)\b", sentence, re.I)
        if not negative and not (
            prerequisite and set(req.anchors).issubset(_words(sentence))
        ):
            break
        left = previous_start
    return left


def _procedure_declaration_bridge(
    req: Requirement, context: str, start: int, end: int
) -> bool:
    """Retain a complete declaration across a narrow mandatory prelude.

    This recognizes complete source sentences only; it never erases them or
    supplies factual support. The procedure plan must verify every sentence.
    """
    bridge = context[start:end].strip()
    if not bridge:
        return True
    if (
        any(c in bridge for c in '"“”')
        or _PROCEDURE_RESTRICTION.search(bridge)
        or _SCOPED_PROCEDURE_RESTRICTION.search(bridge)
    ):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", bridge):
        if (
            not re.search(r"[.!?]$", sentence)
            or not re.match(
                r"(?:verify|check|confirm|(?:do\s+not|never)\s+(?:skip|omit|reopen|use))\s+",
                sentence,
                re.I,
            )
            or not _imperative(sentence)
            or _foreign_qualifier(req, sentence)
        ):
            return False
    return True


def _instruction_start(req: Requirement, context: str, marker: int) -> int:
    boundaries = list(re.finditer(r"[.!?](?=\s|$)", context[:marker]))
    left = boundaries[-1].end() if boundaries else 0
    declaration = _worksheet_declaration(context[:marker])
    if declaration is not None and _procedure_declaration_bridge(
        req, context, declaration.end(), marker
    ):
        left = declaration.start()
        left = _worksheet_prelude_start(req, context, left)
    previous = [0, *(boundary.end() for boundary in boundaries)]
    for index in range(len(previous) - 1, 0, -1):
        start, end = previous[index - 1], previous[index]
        preceding = context[start:end].strip()
        if _procedure_scope_prohibited(req, preceding):
            left = start
            break
        if re.search(r"\b(?:before|prerequisite|requires)\b", preceding, re.I) and set(
            req.anchors
        ).issubset(_words(preceding)):
            left = start
            break
        if not _imperative(preceding):
            break
    while left < marker and context[left].isspace():
        left += 1
    return left


def _imperative(text: str) -> bool:
    return bool(
        re.match(
            r"(?!(?:the|a|an|this|that|it|they|he|she)\b)[a-z][\w-]*\s+"
            r"(?:the|a|an|all|this|that|both|it|them|\d+)\b|(?:do\s+not|never)\s+\w+",
            text.strip(),
            re.I,
        )
    )


def _instruction_end(req: Requirement, context: str, right: int, limit: int) -> int:
    while right < limit:
        following = re.match(
            r"\s*(\S.*?(?:[.!?](?=\s|$)|$))", context[right:limit], re.S
        )
        if (
            following is None
            or not _imperative(following.group(1))
            or _foreign_qualifier(req, following.group(1))
        ):
            break
        right += following.end()
    return right


def _foreign_qualifier(req: Requirement, text: str) -> bool:
    for qualifier in re.finditer(r"\b(?:for|in|at)\s+([^,;.!?]+)", text, re.I):
        anchors = set(named_anchors(qualifier.group(1)))
        if anchors and not anchors.issubset(req.anchors):
            return True
    return False


def _procedure_blocks(req: Requirement, context: str) -> list[tuple[int, int]]:
    markers = _step_markers(context)
    starts = [
        i
        for i, marker in enumerate(markers)
        if (marker.group("label") or "").casefold() == "first" or marker.group(1) == "1"
    ]
    blocks = []
    for ordinal, index in enumerate(starts):
        stop = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(markers)
        selected = markers[index:stop]
        if stop < len(markers):
            boundary_start, boundary_end = selected[-1].end(), markers[stop].end()
            if not _SECTION_HEAD.search(
                context, boundary_start, boundary_end
            ) and not _WORKSHEET_DECLARATION.search(
                context, boundary_start, boundary_end
            ):
                continue  # An unscoped restart cannot silently truncate a method.
        left = _instruction_start(req, context, selected[0].start())
        limit = (
            _instruction_start(req, context, markers[stop].start())
            if stop < len(markers)
            else len(context)
        )
        sentence_end = re.search(r"[.!?](?=\s|$)", context[selected[-1].end() : limit])
        right = selected[-1].end() + sentence_end.end() if sentence_end else limit
        right = _instruction_end(req, context, right, limit)
        headings = list(_SECTION_HEAD.finditer(context, left, selected[0].end()))
        heading = headings[-1] if headings else None
        if heading and heading.group().rstrip().endswith(":"):
            scope = heading.group("scope") or heading.group("title")
            if _procedure_scope_matches(req, scope, context[heading.end() : right]):
                right = _section_continuation_end(req, context, right, limit)
        if _ordered_steps(context[left:right]):
            blocks.append((left, right))
    return blocks


def _expand_procedure(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    for left, right in [
        *_procedure_blocks(req, context),
        *_unnumbered_blocks(req, context),
    ]:
        if (
            left <= start < end <= right
            and condition_relation(req, context[left:right], {}) != "irrelevant"
        ):
            return left, right
    return None


def procedure_discovery_ranges(
    req: Requirement, context: str
) -> tuple[tuple[int, int], ...]:
    """Expose the existing typed structural grammar, without accepting evidence."""
    return tuple(
        dict.fromkeys(
            [*_procedure_blocks(req, context), *_unnumbered_blocks(req, context)]
        )
    )


def role_discovery_ranges(
    req: Requirement, context: str
) -> tuple[tuple[int, int], ...]:
    """Only existing literal lead/deputy grammar; the ordinary binder still decides."""
    if req.kind != "deputy" and not (req.kind == "owner" and req.relation == "leads"):
        return ()
    return tuple(
        dict.fromkeys(
            (item["value_range"]["start"], item["value_range"]["end"])
            for item in role_discovery_candidates(req, context)
        )
    )


def _activity_role_kind(req: Requirement) -> str | None:
    return {
        ("owner", "leads"): "owner",
        ("owner", "lead"): "owner",
        ("owner", "role"): "owner",
        ("owner", "roles"): "owner",
        ("owner", "is"): "owner",
        ("owner", "staffing"): "owner",
        ("deputy", "deputy"): "deputy",
        ("deputy", "deputizes"): "deputy",
        ("deputy", "role"): "deputy",
        ("deputy", "roles"): "deputy",
        ("deputy", "is"): "deputy",
        ("deputy", "staffing"): "deputy",
    }.get((req.kind, req.relation))


def _activity_role_fields(req: Requirement, context: str) -> tuple[dict, ...]:
    """Literal coordinated activity fields; no actor alias or fact acceptance."""
    if req.depends_on or _activity_role_kind(req) is None:
        return ()
    result = []
    for sentence in re.finditer(r"[^.!?;\n]+", context):
        prefix = re.match(r"\s*for\s+(?P<target>[^,;]+),\s*", sentence.group(), re.I)
        if prefix is None:
            continue
        tail = sentence.group()[prefix.end() :]
        fields = list(
            re.finditer(
                r"(?:^|\s+and\s+)(?:the\s+)?(?P<scope>activity|assigned)\s+(?P<label>lead|deputy)\s+"
                r"is\s+(?P<value>(?:(?!\s+(?:and|but|or)\b|\b(?:and|but|or)\b|[,;]).)+)",
                tail,
                re.I,
            )
        )
        complete = bool(fields) and "".join(m.group() for m in fields) == tail
        wanted = "lead" if req.kind == "owner" else "deputy"
        for match in fields:
            if match["label"].casefold() != wanted:
                continue
            left, right = match.span("value")
            left += sentence.start() + prefix.end()
            right += sentence.start() + prefix.end()
            while right > left and context[right - 1].isspace():
                right -= 1
            target_left, target_right = prefix.span("target")
            result.append(
                {
                    "value": context[left:right],
                    "target": prefix["target"].strip(),
                    "value_range": {"start": left, "end": right},
                    "target_range": {
                        "start": sentence.start() + target_left,
                        "end": sentence.start() + target_right,
                    },
                    "source_range": {"start": sentence.start(), "end": sentence.end()},
                    "declared_role_scope": "activity"
                    if match["scope"].casefold() == "activity"
                    else "session",
                    "frame_complete": complete,
                }
            )
    return tuple(result)


def activity_role_claim(
    req: Requirement, context: str, start: int, end: int
) -> SupportClaim | None:
    """Opt-in literal field proposition; NI/metadata/permission stay external."""
    from app.services.role_scope_policy import canonical_role_scope

    if not re.search(r"\b(?:activity|assigned)\s+(?:lead|deputy)\b", context, re.I):
        return None
    value = context[start:end] if type(start) is type(end) is int else ""
    rejected = SupportClaim(
        None, context, value, start, end, "activity_role_field_unbound"
    )
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return rejected
    if _cover_requested(req):
        return rejected
    rows = [
        r
        for r in _activity_role_fields(req, context)
        if (
            r["value_range"]["start"] <= start < end <= r["value_range"]["end"]
            or r["value_range"]["start"] <= start < r["value_range"]["end"]
            and end == r["value_range"]["end"] + 1
            and context[end - 1] == "."
        )
    ]
    if len(rows) != 1 or not rows[0]["frame_complete"]:
        return rejected
    row = rows[0]
    start, end = row["value_range"]["start"], row["value_range"]["end"]
    value = context[start:end]
    first, last = row["source_range"]["start"], row["source_range"]["end"]
    if last < len(context) and context[last] == ".":
        last += 1
    premise = context[first:last]
    if re.search(
        r"\b(?:not|never|former|previous|if|when|unless|except|only|must|may|can|before|after|until|during|without|pending)\b",
        premise,
        re.I,
    ):
        return rejected
    actual, expected = (
        canonical_role_scope(row["target"]),
        canonical_role_scope(req.topic),
    )
    ordinary = re.match(r"(?:ordinary|normal|standard)\s+", row["target"], re.I)
    if actual != expected and not (ordinary and actual == expected + " session"):
        return rejected
    label = "lead" if req.kind == "owner" else "deputy"
    declared = "activity" if row["declared_role_scope"] == "activity" else "assigned"
    hypothesis = f"The {declared} {label} for {row['target']} is {row['value']}"
    return SupportClaim(
        hypothesis,
        premise,
        value,
        start,
        end,
        None,
        first,
        last,
        premise_start=first,
        premise_end=last,
    )


def role_discovery_candidates(  # noqa: C901 - exact typed candidate coordinates
    req: Requirement,
    context: str,
    *,
    include_ownership: bool = False,
    activity_fields: bool = False,
) -> tuple[dict, ...]:
    """Enumerate literal typed assignments with source coordinates for inspection.

    Rejected/foreign targets remain visible to the caller. No source discovery
    record proves entailment or makes a session/activity interpretation.
    """
    if req.kind != "deputy" and not (
        req.kind == "owner" and (req.relation == "leads" or include_ownership)
    ):
        return ()
    result = []
    seen = set()
    if activity_fields:
        for row in _activity_role_fields(req, context):
            first, last = row["value_range"]["start"], row["value_range"]["end"]
            claim = activity_role_claim(req, context, first, last)
            assert claim is not None
            result.append(
                {
                    **row,
                    "relation_scope": _event_target_scope(req, context, row["target"]),
                    "rejection": claim.rejection,
                }
            )
            seen.add((first, last))
    for sentence in re.finditer(r"[^.!?;\n]+", context):
        premise = sentence.group()
        for pattern, target_after in _role_patterns(req, for_scope=True):
            for match in re.finditer(pattern, premise, re.I):
                first, last = match.span("value")
                while first < last and premise[first].isspace():
                    first += 1
                while last > first and premise[last - 1].isspace():
                    last -= 1
                target = _role_target(match, premise, target_after)
                if "target" in match.groupdict():
                    left, right = match.span("target")
                elif target_after:
                    left, right = match.end(), len(premise)
                else:
                    left, right = 0, match.start("value")
                while left < right and premise[left].isspace():
                    left += 1
                while right > left and premise[right - 1].isspace():
                    right -= 1
                start, end = sentence.start() + first, sentence.start() + last
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                claim = support_claim(req, context, start, end)
                result.append(
                    {
                        "value": context[start:end],
                        "target": target,
                        "value_range": {"start": start, "end": end},
                        "target_range": {
                            "start": sentence.start() + left,
                            "end": sentence.start() + right,
                        },
                        "source_range": {
                            "start": sentence.start(),
                            "end": sentence.end(),
                        },
                        "relation_scope": _event_target_scope(req, premise, target),
                        "rejection": claim.rejection,
                    }
                )
    return tuple(result)


def _unnumbered_blocks(req: Requirement, context: str) -> list[tuple[int, int]]:
    result = []
    headings = list(_SECTION_HEAD.finditer(context))
    for index, match in enumerate(headings):
        limit = (
            headings[index + 1].start() if index + 1 < len(headings) else len(context)
        )
        ending = re.search(r"[.!?](?=\s|$)", context[match.end() : limit])
        right = match.end() + ending.end() if ending else limit
        body = context[match.end() : right].strip(" .!?")
        scope = match.group("scope") or match.group("title")
        if not _procedure_scope_matches(req, scope, body):
            continue
        instructions = re.split(r",\s*(?:and\s+)?|\s+and\s+", body, flags=re.I)
        if len(instructions) < 2 or not all(
            _plain_instruction(part) for part in instructions
        ):
            continue
        left = match.start()
        while left < right and context[left].isspace():
            left += 1
        if match.group("title"):
            # A colon title governs its section's instructions, prose
            # prerequisites, approval roles, parameters and prohibitions.
            right = _section_continuation_end(req, context, right, limit)
        else:
            right = _instruction_end(req, context, right, limit)
        result.append((left, right))
    return result


def _section_continuation_end(
    req: Requirement, context: str, right: int, limit: int
) -> int:
    next_heading = _SECTION_HEAD.search(context, right, limit)
    if next_heading:
        limit = next_heading.start()
    while right < limit:
        following = re.match(
            r"\s*(\S.*?(?:[.!?](?=\s|$)|$))", context[right:limit], re.S
        )
        if following is None:
            break
        sentence = following.group(1)
        if _foreign_qualifier(req, sentence) and not _PROCEDURE_RESTRICTION.match(
            sentence
        ):
            break
        right += following.end()
    while right > 0 and context[right - 1].isspace():
        right -= 1
    return right


def _procedure_action_target(req: Requirement, scope: str, body: str) -> bool:
    action = _phrasal_action(req.topic)
    if action is None:
        return True
    verb, particle, obj = action
    expected = _canonical_argument(obj)
    # The heading may supply the omitted entity/modifier, never the object head.
    qualifiers = _words(scope) - {(verb + particle).casefold()} - _GRAMMAR
    expected_words = expected.split()
    core = " ".join(
        w
        for i, w in enumerate(expected_words)
        if i == len(expected_words) - 1 or w not in qualifiers
    )
    governing = list(
        re.finditer(
            r"(?:^\s*|[,:;.!?]\s*|\band\s+)"
            r"(?:first\s+|next\s+|then\s+|finally\s+)?"
            r"(?P<polarity>(?:(?:do|must|should)\s+not|never)\s+)?"
            rf"{re.escape(verb)}\s+{re.escape(particle)}\s+"
            r"(?P<object>.+?)(?=[,;.!?]|\s+and\s+|$)",
            body,
            re.I,
        )
    )
    if governing:
        return all(
            not m.group("polarity")
            and _canonical_argument(m.group("object")) in {expected, core}
            for m in governing
        )
    if re.search(rf"\b{re.escape(verb)}\s+{re.escape(particle)}\b", body, re.I):
        return False
    # A scoped method can decompose its goal into several different actions.
    # Its full requested goal is independently assessed by a supplementary check.
    return bool(expected_words and expected_words[-1] in _words(body))


def _procedure_scope_matches(req: Requirement, scope: str, body: str) -> bool:
    scoped = _words(scope) - _GRAMMAR
    requested = _words(req.topic) - _GRAMMAR
    if scoped and scoped == requested:
        return _procedure_action_target(req, scope, body)
    action = _phrasal_action(req.topic)
    if not action:
        return False
    verb, particle, obj = action
    words = [
        word.casefold()
        for word in re.findall(r"\w[\w-]*", obj)
        if word.casefold() not in _GRAMMAR
    ]
    return bool(
        words
        and scoped == {*words[:-1], (verb + particle).casefold()}
        and _procedure_action_target(req, scope, body)
    )


def _plain_instruction(text: str) -> bool:
    return bool(
        re.match(r"(?!(?:the|a|an|this|that|it|they|he|she)\b)[a-z][\w-]+\s+\S", text)
    ) and not bool(re.search(r"\b(?:is|are|was|were)\b", text))


_PROHIBITION_SENTENCE_END = re.compile(r"(?<!\d)\.|\.(?!\d)|[!?;\n]")


def _contained_command_bounds(
    context: str, start: int, end: int
) -> tuple[int, int] | None:
    raw = context[start:end]
    if re.match(r"\s*(?:do|must|should)\s+not\b", raw, re.I):
        return None  # Existing within-command argument normalization is unchanged.
    commands = list(re.finditer(r"\bdo\s+not\s+", raw, re.I))
    if len(commands) != 1:
        return None
    command = commands[0]
    left = start + command.start()
    previous = list(_PROHIBITION_SENTENCE_END.finditer(context, 0, left))
    head = previous[-1].end() if previous else 0
    if context[head:left].strip():
        return None  # Do not remove a conditional, quoted or descriptive prefix.
    ending = _PROHIBITION_SENTENCE_END.search(raw, command.end())
    right = start + ending.start() if ending else end
    right -= len(context[left:right]) - len(context[left:right].rstrip())
    if (
        not ending
        and right < len(context)
        and _PROHIBITION_SENTENCE_END.match(context, right) is None
    ):
        return None  # Never extend the raw range to complete or find a command.
    if not start <= left < right <= end or not _words(
        context[start + command.end() : right]
    ):
        return None
    return left, right


def _complete_prohibition_request(req: Requirement) -> bool:
    original = prohibition_request(req.original_text, req.topic)
    prepared = prohibition_request(req.question, req.topic)
    return original is not None and original == prepared


def _first_worksheet_instruction(context: str, declaration: tuple[int, int]) -> bool:
    first_step = _STEP.match(context, declaration[1])
    return bool(
        first_step
        and (
            first_step.group(1) == "1"
            or (first_step.group("label") or "").casefold() == "first"
        )
    )


def _contained_prohibition_applicability(
    req: Requirement,
    context: str,
    command_start: int,
    declaration_range: tuple[int, int],
) -> bool:
    qualifier = re.match(r"(ordinary|standard|normal)\s+", req.topic, re.I)
    declaration = _WORKSHEET_DECLARATION.fullmatch(
        context[declaration_range[0] : declaration_range[1]].strip()
    )
    if qualifier is None or declaration is None:
        return False
    condition = _canonical_argument(declaration.group("conditions"))
    mark = _negative_mark(condition)
    if (
        not mark
        or condition != f"{qualifier.group(1).casefold()} worksheets with no {mark}"
    ):
        return False
    ancestor = _worksheet_namespace(req, context, declaration_range[0])
    if ancestor is None:
        return False
    expected_scope = (
        qualifier.group(1).casefold()
        + " "
        + _canonical_argument(ancestor.group("scope"))
    )
    if _canonical_argument(
        req.topic
    ) != expected_scope or not _complete_prohibition_request(req):
        return False  # Unknown request words/conditions must not disappear.
    # This explicit body fact establishes that the requested ordinary class
    # satisfies the declaration's negative mark; no class/default is invented.
    before = context[ancestor.end() : command_start]
    if re.search(
        r"\b(?:if|when|unless|until|provided|before|after|only)\b", before, re.I
    ):
        return False
    carry = (
        rf"(?:^|(?<=[.!?])\s+)\s*{re.escape(qualifier.group(1))}"
        rf"\s+worksheets\s+carry\s+no\s+{re.escape(mark)}[.!?]"
    )
    return re.search(carry, before, re.I) is not None


def _contained_prohibition(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    candidate = _contained_command_bounds(context, start, end)
    if candidate is None:
        return None
    left, right = candidate
    value = context[left:right]
    instruction = re.fullmatch(r"do\s+not\s+(.+)", value, re.I)
    if instruction is None or not _prohibition_target_matches(
        req, instruction.group(1)
    ):
        return None
    if not _worksheet_scope_prefix(req, context, left, value):
        return None
    declaration = _worksheet_following_declaration(context, left, value)
    if declaration is None or not _contained_prohibition_applicability(
        req, context, left, declaration
    ):
        return None
    ancestor = _worksheet_namespace(req, context, declaration[0])
    if ancestor is None or start < ancestor.start() or end > declaration[1]:
        return None  # The literal primary must contain the entire accepted raw.
    if not _first_worksheet_instruction(context, declaration):
        return None  # No skipped clause between applicability and instructions.
    return candidate


def _expand_prohibition(context: str, start: int, end: int) -> tuple[int, int]:
    left, right = _clause(context, start, end)
    for instruction in re.finditer(
        r"\b(?:do|must|should)\s+not\s+[^.!?;]+", context[left:right], re.I
    ):
        first, last = left + instruction.start(), left + instruction.end()
        if first <= start < end <= last:
            return first, last
    return start, end


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w[\w-]*", text.casefold()))


def _attach_unit(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int]:
    if req.relation == "operand_count" and re.fullmatch(
        _CARDINAL, context[start:end], re.I
    ):
        unit = re.match(
            rf"\s+{re.escape(req.attribute.rstrip('s'))}s?\b", context[end:], re.I
        )
        if unit:
            return start, end + unit.end()
    if req.kind == "duration" and re.fullmatch(r"\d+(?:\.\d+)?", context[start:end]):
        unit = re.match(rf"\s+{_DURATION_UNIT}\b", context[end:], re.I)
        if unit:
            end += unit.end()
    return start, end


def _clause(context: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    for boundary in re.finditer(
        r"(?<!\d)\.|\.(?!\d)|[!?;\n]|,\s*(?:and|but|whereas|while)\b|\b(?:and|but|whereas)\b",
        context,
        re.I,
    ):
        if left <= start < end <= boundary.start():
            return left, boundary.start()
        left = boundary.end()
    # A multi-step procedure can span punctuation. Other kinds still validate
    # their own relation instead of borrowing arbitrary facts from this block.
    return (left, len(context)) if left <= start < end <= len(context) else (start, end)


def _bound_predicate(binding: _Binding, predicate: str) -> bool:
    prefix = binding.premise[: binding.start - binding.clause_start]
    match = re.search(rf"(?:{predicate})\s+$", prefix, re.I)
    return bool(match and not _activity_conflict(binding.req, prefix[: match.start()]))


def _quantity_predicate(binding: _Binding, noun: str) -> bool:
    named = (
        rf"{re.escape(noun)}s?\s+count\s+(?:of|is)|(?:maximum|limit|number)"
        rf"\s+(?:of\s+)?{re.escape(noun)}s?\s*(?:is|:)?"
    )
    if _bound_predicate(binding, named):
        return True
    direct = r"(?:has|allows|contains|consists\s+of)(?:\s+up\s+to)?"
    counted = rf"\d+\s+{re.escape(noun)}s?\b"
    return _bound_predicate(binding, direct) and bool(
        re.match(counted, binding.context[binding.start :], re.I)
    )


def _negated_fact(binding: _Binding) -> bool:
    left, right = _clause(binding.context, binding.start, binding.end)
    return bool(
        re.search(
            r"\b(?:never|not|neither|nor|cannot|no\s+longer)\b",
            binding.context[left:right],
            re.I,
        )
    )


def _role_field_patterns(field: str | None) -> list[tuple[str, bool]]:
    label = re.escape(field) if field else r"(?P<field>[\w-]+(?:\s+[\w-]+){0,5})"
    return [
        (
            rf"^\s*for\s+(?P<target>[^,.;]+),\s+(?:the\s+)?{label}\s+is\s+(?P<value>[^.;]+)",
            False,
        ),
        (
            rf"^\s*(?:the\s+)?{label}\s+for\s+(?P<target>[^,.;]+?)\s+is\s+(?P<value>[^.;]+)",
            False,
        ),
    ]


def _role_patterns(
    req: Requirement, *, for_scope: bool = False
) -> list[tuple[str, bool]]:
    argument = r"(?P<value>(?:(?!\band\b|\bbut\b|[.;]).)+?)"
    if req.kind == "owner":
        relation = (
            re.escape(req.relation) if req.relation != "owner" else r"(?:owns|leads)"
        )
        if req.relation == "owner" and req.topic.casefold().endswith(
            " ordinary operation"
        ):
            relation = "owns"
        if for_scope and req.relation in {"leads", "owns"}:
            relation = rf"(?:{relation}|does\s+not\s+{re.escape(req.relation[:-1])})"
        patterns = [(rf"{argument}\s+{relation}\s+", True)]
        if req.relation in {"owner", "owns"}:
            patterns.append(
                (r"\bowner\s+of\s+(?P<target>[^.;]+?)\s+is\s+(?P<value>[^.;]+)", False)
            )
            patterns.append((r"\bowner\b.+?\bis\s+(?P<value>[^.;]+)", False))
        if req.relation == "leads":
            patterns.extend(
                [
                    (r"\bis\s+led\s+by\s+(?P<value>[^.;]+)", False),
                    *_role_field_patterns("lead"),
                ]
            )
        if req.relation in {"owner", "owns"}:
            patterns.append((r"\bis\s+owned\s+by\s+(?P<value>[^.;]+)", False))
            patterns.append(
                (r"(?P<target>.+?)\s+belongs\s+to\s+(?P<value>[^.;]+)", False)
            )
    else:
        patterns = [
            (
                rf"{argument}\s+(?:is|serves\s+as)\s+(?:the\s+)?deputy\s+for\s+(?P<target>[^.;]+?)(?=\s+and\b|$)",
                False,
            ),
            (
                rf"{argument}\s+(?:is|serves\s+as)\s+(?:the\s+)?(?P<target>.+?)['’]s\s+deputy\b",
                False,
            ),
            (r"(?P<target>.+?)['’]s\s+deputy\s+is\s+(?P<value>[^.;]+)", False),
            (r"\bdeputy\s+(?:for\s+.+?\s+)?is\s+(?P<value>[^.;]+)", False),
            (rf"{argument}\s+deputi[sz]es\s+for\b", True),
        ]
    if for_scope and req.kind == "owner":
        if req.relation == "leads":
            patterns.append((r"\bis\s+not\s+led\s+by\s+(?P<value>[^.;]+)", False))
        elif req.relation in {"owner", "owns"}:
            patterns.extend(_role_field_patterns("owner"))
            patterns.append((r"\bis\s+not\s+owned\s+by\s+(?P<value>[^.;]+)", False))
    return patterns


def _role_argument(req: Requirement, premise: str) -> tuple[int, int] | None:
    patterns = _role_patterns(req)
    for pattern, target_after in patterns:
        match = re.search(pattern, premise, re.I)
        if match:
            role_start, role_end = match.span("value")
            tail = re.search(
                r",\s*not\b|\s+(?:and|but)\s+", premise[role_start:role_end], re.I
            )
            if tail:
                role_end = role_start + tail.start()
            role = premise[role_start:role_end]
            if re.search(r"\b(?:not|never|former|previous|no\s+longer)\b", role, re.I):
                continue
            target = _role_target(match, premise, target_after)
            if req.topic.casefold().endswith(" ordinary operation") and (
                _scope_target(req, target) != "applies"
            ):
                continue
            if (
                not req.depends_on
                and req.anchors
                and not set(req.anchors).issubset(_words(target))
            ):
                continue
            if (
                req.kind == "deputy"
                and req.depends_on
                and not _authorized_owner_target(req, target)
            ):
                continue
            if re.search(
                r"\b(?:not|never|neither|nor|no\s+longer)\b", target, re.I
            ) or (not req.depends_on and _activity_conflict(req, target)):
                continue
            return role_start, role_end
    return None


def _role_target(match: re.Match[str], premise: str, target_after: bool) -> str:
    if "target" in match.groupdict():
        return _without_preface(match.group("target").strip()).strip()
    if not target_after:
        return premise[: match.start("value")].strip()
    return re.split(
        r"\s+(?:and|but)\s+|[,;.!?]", premise[match.end() :], maxsplit=1, flags=re.I
    )[0].strip()


def _authorized_owner_target(req: Requirement, target: str) -> bool:
    actual, expected = _canonical_argument(target), _canonical_argument(req.topic)
    if actual == expected:
        return True
    if not actual.endswith(" " + expected):
        return False
    prefix = actual[: -(len(expected) + 1)]
    prefix = re.sub(r"['’]s\b", "", prefix)
    namespace = set(req.anchors) - set(named_anchors(req.topic))
    return bool(namespace and _words(prefix) and _words(prefix).issubset(namespace))


def _selected_role_target(binding: _Binding) -> str:
    for pattern, after in _role_patterns(binding.req):
        match = re.search(pattern, binding.premise, re.I)
        if (
            match
            and match.start("value")
            <= binding.start - binding.clause_start
            < binding.end - binding.clause_start
            <= match.end("value")
        ):
            target = _role_target(match, binding.premise, after)
            if _authorized_owner_target(binding.req, target):
                return (
                    binding.topic
                    if _canonical_argument(target) == _canonical_argument(binding.topic)
                    else target
                )
    return binding.topic


def _activity_conflict(req: Requirement, target: str) -> bool:
    if not req.anchors or re.search(r"[.!?]", target):
        return False
    expected = _activity_tail(req.topic, req.anchors)
    observed = _activity_tail(target, req.anchors)
    if not expected or not observed:
        return False
    expected_head, observed_head = expected[-1].rstrip("s"), observed[-1].rstrip("s")
    expected_set = {w.rstrip("s") for w in expected}
    observed_set = {w.rstrip("s") for w in observed}
    if observed_set.issubset(expected_set):
        return False
    if (
        observed_head == "session"
        and observed_set - {"session"}
        and (observed_set - {"session"}).issubset(expected_set)
    ):
        return False
    return expected_head != observed_head


def _activity_tail(text: str, anchors: tuple[str, ...]) -> list[str]:
    words = re.findall(r"\w[\w-]*", re.sub(r"(?<=\w)['\u2019]s\b", "", text.casefold()))
    position = max((i for i, w in enumerate(words) if w in anchors), default=len(words))
    remaining = words[position + 1 :]
    for i, word in enumerate(remaining):
        if word in {"is", "are", "was", "were", "has", "have", "in", "with"}:
            remaining = remaining[:i]
            break
    ignored = _GRAMMAR | {"deputy", "owner", "current", "normal", "standard", "actual"}
    return [w for w in remaining if w not in ignored]


def _action(req: Requirement) -> str | None:
    if req.kind == "boolean":
        subject = re.escape(req.topic)
        match = re.match(
            rf"\s*(?:may|can|must|should|does|do)\s+(?:the\s+)?{subject}\s+(.+?)[?.]*$",
            _without_preface(req.question),
            re.I,
        )
        if match:
            return match.group(1).rstrip("?.")
    return None


_NUMBER_WORDS = frozenset(
    (
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    ).split()
)
_CARDINAL = r"(?:\d+|" + "|".join(sorted(_NUMBER_WORDS)) + r")"


def _terminal_end(context: str, end: int) -> int:
    while end < len(context) and context[end] in ".!?":
        end += 1
    return end


def _scope_prefix(req: Requirement, context: str, start: int, premise: str) -> str:
    worksheet = _worksheet_scope_prefix(req, context, start, premise)
    if worksheet:
        return worksheet
    expected = re.match(r"\s*(?:for|in|at|regarding)\s+([^,;:.]+)[,:]", req.topic, re.I)
    if expected is None:
        return ""
    candidates = list(
        re.finditer(
            r"(?:^|(?<=[.!?])\s+)(?:for|in|at|regarding)\s+([^,;:.]+)[,:]",
            context[:start],
            re.I,
        )
    )
    if not candidates:
        return ""
    source = candidates[-1]
    if (_words(source.group(1)) - _GRAMMAR) != (_words(expected.group(1)) - _GRAMMAR):
        return ""
    foreign = (
        set(named_anchors(premise))
        - set(req.anchors)
        - _NUMBER_WORDS
        - {"no", "never", "neither", "both", "then", "next", "finally"}
    )
    return source.group().strip() if not foreign else ""


def _operand_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    operand = re.sub(
        r"^(?:the|a|an)\s+", "", _without_preface(binding.req.topic), flags=re.I
    )
    noun = re.escape(binding.req.attribute.rstrip("s")) + "s?"
    if not re.fullmatch(rf"{_CARDINAL}\s+{noun}", binding.value, re.I):
        return None, "operand_count_unit_missing"
    prefix = binding.premise[: binding.start - binding.clause_start]
    if not re.search(rf"\b{re.escape(operand)}\s+(?:is|are)\s+$", prefix, re.I):
        return None, "requested_operand_not_selected_subject"
    return f"{binding.topic} has {binding.value}", None


def _count_as_hypothesis(binding: _Binding) -> tuple[str | None, str | None]:
    subject = re.sub(
        r"^(?:the|a|an)\s+", "", _without_preface(binding.topic), flags=re.I
    )
    target = re.sub(r"^(?:the|a|an)\s+", "", binding.req.attribute, flags=re.I)
    predicate = (
        r"(?P<predicate>(?:(?:does|do)\s+not\s+count\s+as|counts?\s+as|"
        r"(?:is|are)(?:\s+not)?))"
    )
    clause_start, clause_end = _clause(binding.context, binding.start, binding.end)
    source = binding.context[clause_start:clause_end].strip()
    body = _without_preface(source)
    expression = re.fullmatch(
        rf"(?P<subject>.+?)\s+{predicate}\s+(?P<target>.+)", body, re.I
    )
    if (
        expression is None
        or _count_as_subject(binding.req, expression.group("subject"))
        != _directional_subject(subject)
        or not _count_as_target(target, expression.group("target"))
    ):
        return None, "requested_count_as_relation_missing"
    source_start = (
        clause_start
        + len(binding.context[clause_start:clause_end])
        - len(binding.context[clause_start:clause_end].lstrip())
        + len(source)
        - len(body)
    )
    selected_start, selected_end = (
        binding.start - source_start,
        binding.end - source_start,
    )
    if not expression.start() <= selected_start < selected_end <= expression.end():
        return None, "selected_span_not_in_count_as_fact"
    parts = _count_as_parts(binding.req.question)
    auxiliary = parts[0].casefold() if parts else "does"
    negative = bool(re.search(r"\bnot\b", expression.group("predicate"), re.I))
    verb = (
        ("do not count as" if auxiliary == "do" else "does not count as")
        if negative
        else ("count as" if auxiliary == "do" else "counts as")
    )
    return f"{binding.topic} {verb} {binding.req.attribute}", None


def _directional_subject(text: str) -> str:
    text = _canonical_argument(text)
    adjective = re.fullmatch(r"(.+?)\s+([\w-]+)-direction\s+(.+?)(\s+alone)?", text)
    if adjective:
        prefix, direction, noun, tail = adjective.groups()
        return f"{prefix} {noun} in the {direction} direction{tail or ''}"
    return text


def _count_as_subject(req: Requirement, source: str) -> str:
    actual = _canonical_argument(source)
    scope = re.match(r"\s*(?:for|in)\s+([^,;:]+)[,:]", req.topic, re.I)
    if scope:
        namespace = _canonical_argument(scope.group(1))
        if actual.startswith(namespace + " "):
            actual = actual[len(namespace) + 1 :]
    return _directional_subject(actual)


def _count_as_target(requested: str, source: str) -> bool:
    requested, actual = _canonical_argument(requested), _canonical_argument(source)
    if requested == actual:
        return True
    prefix = requested + " of "
    return actual.startswith(prefix) and bool(
        re.fullmatch(rf"{_CARDINAL}\s+[\w-]+", actual[len(prefix) :], re.I)
    )


def _count_as_scope_context(
    req: Requirement, context: str, left: int, right: int, premise: str
) -> tuple[str, int]:
    scope = re.match(r"\s*(?:for|in)\s+([^,;:]+)[,:]", req.topic, re.I)
    separator = re.search(r";\s*$", context[:left])
    if (
        scope is None
        or separator is None
        or set(named_anchors(premise)) - set(req.anchors)
    ):
        return premise, left
    previous = max(
        (m.end() for m in re.finditer(r"[.!?]", context[: separator.start()])),
        default=0,
    )
    preceding = context[previous : separator.start()]
    required = _words(scope.group(1)) - _GRAMMAR
    if (
        not required
        or not required.issubset(_words(preceding))
        or re.search(r"\b(?:if|when|unless|tagged)\b", preceding, re.I)
    ):
        return premise, left
    while previous < right and context[previous].isspace():
        previous += 1
    return context[previous:right].strip(), previous
