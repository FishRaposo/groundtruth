"""Q-only partial compiler compiler prototype; never a resolved v2 projection."""

from .request_grammar import compile_partial
from .request_obligations import PartialRequest, canonical


def compile_request(question: str, capture: dict) -> PartialRequest:
    return compile_partial(question, capture)


def validate_partial_request(record: object, *, question: str, capture: dict) -> bool:
    try:
        return type(record) is dict and canonical(record) == canonical(
            compile_request(question, capture).record()
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ):
        return False
