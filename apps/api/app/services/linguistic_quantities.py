"""Move a literal fronted quantity namespace without changing its relation.

This is a syntax transformation, never a support verdict. The original plan
remains immutable. Historical NLI stays unchanged; new typed candidates still
require the selected profile's separately mandatory semantic support.
"""

import re
from dataclasses import replace

from app.services.contextual_binding import contextual_support_claim
from app.services.requirement_binding import _canonical_argument


def scoped_quantity_claim(
    requirement, context, start, end, *, evidence_profile=None, request_plan=None
):
    if evidence_profile is not None and requirement.relation != "count":
        from app.services.literal_quantity import (
            QuantityUnresolved,
            _typed_mode,
            produce_quantity_candidate,
            typed_quantity_source,
        )
        from app.services.requirement_binding import SupportClaim

        if _typed_mode(evidence_profile):
            try:
                body, identity, offset = typed_quantity_source(
                    requirement,
                    context,
                    evidence_profile=evidence_profile,
                    request_plan=request_plan,
                )
                return produce_quantity_candidate(
                    requirement,
                    body,
                    source_identity=identity,
                    chunk_content=context,
                    chunk_start=offset,
                    raw_start=start,
                    raw_end=end,
                    evidence_profile=evidence_profile,
                    request_plan=request_plan,
                )[0]
            except QuantityUnresolved as exc:
                return SupportClaim(None, "", "", start, end, str(exc))
    match = re.fullmatch(
        r"(?:for|in|at|regarding)\s+([^,]+),\s*what\s+is\s+"
        r"(?:the\s+)?([\w -]+?)\s+count[?.!]?",
        requirement.question.strip(),
        re.I,
    )
    if match and _canonical_argument(match[1]) == _canonical_argument(
        requirement.topic
    ):
        question = f"What is the {match[2]} count for {match[1]}?"
        requirement = replace(requirement, question=question)
    return contextual_support_claim(requirement, context, start, end)


def _typed_count_claim(requirement, binding, context, offset):
    """Literal chunk claim after full count-field reconstruction, before NI."""
    from app.services.literal_quantity import QuantityUnresolved
    from app.services.requirement_binding import SupportClaim

    clause, amount = binding["source_clause"], binding["amount"]
    left, right = clause["start"] - offset, clause["end"] - offset
    start, end = amount["start"] - offset, amount["end"] - offset
    if not 0 <= left <= start < end <= right <= len(context) or (
        context[left:right] != clause["text"] or context[start:end] != amount["text"]
    ):
        raise QuantityUnresolved("typed_count_complete_clause_not_covered_by_chunk")
    if binding["method"] == "source_stated_qualified_quantity_v1":
        return SupportClaim(
            clause["text"],
            clause["text"],
            clause["text"],
            left,
            right,
            None,
            left,
            right,
            premise_start=left,
            premise_end=right,
        )
    return SupportClaim(
        f"The {requirement.attribute} for {requirement.topic} is {amount['text']}.",
        clause["text"],
        amount["text"],
        start,
        end,
        None,
        left,
        right,
        premise_start=left,
        premise_end=right,
    )
