"""Literal recorded-reference binding; never rewrite the requested attribute.

The caller must establish each preceding value from authorized supported
evidence. Output reconstruction repeats this operation from validated witnesses.
No inferred role alias, unit conversion or availability/presence substitution.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace

from app.request_parser_catalog import MAX_QUESTION_CHARS
from app.services.answer_requirements import Requirement, _requirement_anchors


@dataclass(frozen=True)
class BoundLinguisticRequirement(Requirement):
    """An effective property subject retains its original activity namespace."""

    dependency_scope: str = ""


def resolve_linguistic_requirement(requirement, plan, values):  # noqa: C901 - exact dependency gates
    if requirement not in plan.requirements:
        raise ValueError("Requirement is not in the immutable request plan")
    if not requirement.depends_on:
        return requirement, {}
    if len(requirement.depends_on) != 1:
        raise ValueError("unsupported_dependency")
    identifier = requirement.depends_on[0]
    value = values.get(identifier)
    if type(value) is not str or not value.strip():
        raise ValueError(f"missing_dependency:{identifier}")
    positions = {r.id: n for n, r in enumerate(plan.requirements)}
    if (
        identifier not in positions
        or positions[identifier] >= positions[requirement.id]
    ):
        raise ValueError("Dependency must reference preceding evidence")
    uses = [u for u in plan.uses if u.requirement_id == requirement.id]
    if len(uses) != 1 or not uses[0].references:
        raise ValueError("Dependency has no recorded literal reference")
    question, topic, attribute = (
        requirement.question,
        requirement.topic,
        requirement.attribute,
    )
    bindings = []
    seen = set()
    for reference in uses[0].references:
        if (
            type(reference.start) is not int
            or type(reference.end) is not int
            or not 0 <= reference.start < reference.end <= len(plan.question)
            or plan.question[reference.start : reference.end] != reference.text
            or reference.text.casefold() in seen
        ):
            raise ValueError("Invalid or ambiguous dependency reference")
        seen.add(reference.text.casefold())
        expression = re.compile(
            r"(?<!\w)" + re.escape(reference.text) + r"(?!\w)", re.I
        )
        matches = list(expression.finditer(question))
        if len(matches) != 1:
            raise ValueError(
                "Dependency reference is missing or ambiguous in prepared question"
            )
        replacement = value
        if reference.text.endswith(("'s", "’s")) and not value.endswith(("'s", "’s")):
            replacement += reference.text[-2:]
        found = matches[0]
        bindings.append(
            {
                "source_requirement_id": identifier,
                "source_value": value,
                "reference": {
                    "start": reference.start,
                    "end": reference.end,
                    "text": reference.text,
                },
                "question_reference_range": {
                    "start": found.start(),
                    "end": found.end(),
                },
                "replacement": replacement,
            }
        )
        question = expression.sub(lambda _, literal=replacement: literal, question)
        topic = expression.sub(lambda _, literal=replacement: literal, topic)
        attribute = expression.sub(lambda _, literal=replacement: literal, attribute)
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError("Resolved question exceeds the request budget")
    # A dependent property belongs to the validated role value, not the
    # activity that identified that role. The original scope stays in the plan
    # and binding record; its constraints are not rewritten as a new subject.
    if requirement.kind == "availability":
        topic = value
    resolved = replace(
        requirement,
        question=question,
        topic=topic,
        attribute=attribute,
        anchors=tuple(dict.fromkeys(requirement.anchors + _requirement_anchors(value))),
    )
    if requirement.kind == "availability":
        resolved = BoundLinguisticRequirement(
            **asdict(resolved), dependency_scope=requirement.topic
        )
    return resolved, {
        "contract": "literal-evidence-dependency-v1",
        "requirement_id": requirement.id,
        "bindings": bindings,
        "effective_question": question,
        "effective_topic": topic,
        "effective_attribute": attribute,
        "original_topic": requirement.topic,
        "authority": "preceding validated source value; not a new fact",
    }
