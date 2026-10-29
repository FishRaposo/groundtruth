"""Equivalence only inside an already supported, identical request obligation."""

import re

from app.services.answer_requirements import Requirement
from app.services.requirement_binding import role_argument_identity


def _words(value: str) -> str:
    # Unit symbols are case/punctuation sensitive (MW/mW, N/m/N m).
    return " ".join(value.split())


def contextual_value_identity(requirement: Requirement, value: str) -> str:
    if requirement.kind in {"owner", "deputy"}:
        return role_argument_identity(value)
    literal = "literal:" + " ".join(value.split())
    if requirement.kind != "quantity":
        return literal
    requested = re.search(
        r"how\s+many\s+(.+?)\s+(?:are|is|belong|does|do|can|must)\b",
        requirement.original_text,
        re.I,
    )
    number = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s+(.+))?", value.strip())
    if not requested or not number:
        return literal
    unit = _words(requested.group(1))
    if number.group(2) and _words(number.group(2)) != unit:
        return literal
    # No unit conversion, synonym expansion or cross-requirement merging.
    integer, _, fraction = number.group(1).partition(".")
    exact = integer.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    if fraction:
        exact += "." + fraction
    return f"quantity:{exact}:{unit}"
