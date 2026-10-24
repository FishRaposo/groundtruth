"""Source-grounded coverage contracts, separate from the frozen version-one judge.

Literal facts are authored expectations, not a generative judge. Whitespace and
case are normalized; numbers, units, entities, negations and order stay literal.
Both comparison arms use this same quality contract. Candidate span validation
is an additional integrity gate and never an advantage in answer quality.
"""

import re
from typing import Any


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def contains(answer: str, fragment: str) -> bool:
    # Avoid accepting 11 minutes inside 111 minutes, or a shorter entity token.
    return bool(
        re.search(r"(?<!\w)" + re.escape(normalized(fragment)) + r"(?!\w)", answer)
    )


def validate_coverage(
    documents: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    if manifest.get("score_contract") != "coverage-v2":
        raise ValueError("Version-two corpus requires coverage-v2 score contract")
    if manifest.get("corpus_role") not in ("development", "blind"):
        raise ValueError("Version-two corpus role must be development or blind")
    by_id = {document["id"]: document for document in documents}
    for document in documents:
        if document.get("current_version_number") != len(document["versions"]):
            raise ValueError("Current source version must be the latest snapshot")
        if document.get("owner") not in manifest["principals"]:
            raise ValueError("Document owner must be a declared principal")
        if document.get("visibility") not in ("public", "organization", "private"):
            raise ValueError("Document permission visibility is invalid")
    for case in cases:
        _validate_case(case, by_id)


def _validate_case(case: dict[str, Any], by_id: dict[str, Any]) -> None:
    if case.get("score_contract") != "coverage-v2":
        raise ValueError("Case requires coverage-v2 score contract")
    if case.get("expected_behavior") not in ("answer", "refuse", "review", "deny"):
        raise ValueError("Unknown expected behavior")
    answerable = case["expected_behavior"] == "answer"
    if answerable and (not case["expected_sources"] or not case.get("required_facts")):
        raise ValueError("Answerable case requires source and required facts")
    if not answerable and (
        case["expected_sources"]
        or case.get("required_facts")
        or case.get("ordered_steps")
    ):
        raise ValueError("Negative case cannot declare an answer contract")
    passages = _validate_expected_sources(case["expected_sources"], by_id)
    for name in ("required_facts", "ordered_steps"):
        _validate_grounded_groups(case.get(name, []), passages, name)


def _validate_expected_sources(
    sources: list[dict[str, Any]], by_id: dict[str, Any]
) -> list[str]:
    passages = []
    for source in sources:
        document = by_id[source["document_id"]]
        version = document["versions"][source["version_number"] - 1]
        if source.get("content_hash") != version["content_hash"]:
            raise ValueError("Expected source content hash mismatch")
        if source["version_number"] != document["current_version_number"]:
            raise ValueError("Expected answer must use current source version")
        alternatives = source.get("acceptable_answer_spans")
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or any(
                not isinstance(span, str)
                or not span
                or span not in source["quoted_text"]
                for span in alternatives
            )
        ):
            raise ValueError("Acceptable answer span must occur in expected quotation")
        passages.append(source["quoted_text"])
    return passages


def _validate_grounded_groups(groups: Any, passages: list[str], name: str) -> None:
    if not isinstance(groups, list):
        raise ValueError(f"Invalid {name} contract")
    for alternatives in groups:
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or any(
                not isinstance(fact, str)
                or not fact
                or not any(contains(normalized(p), fact) for p in passages)
                for fact in alternatives
            )
        ):
            raise ValueError(f"Unfounded required fact or step: {name}")


def _spans_valid(citations: list[dict[str, Any]], required: bool) -> bool:
    found = False
    for citation in citations:
        quote = citation.get("quoted_text")
        spans = citation.get("answer_spans", [])
        if not isinstance(spans, list) or (required and not spans):
            return False
        for span in spans:
            if not isinstance(span, dict) or not isinstance(quote, str):
                return False
            start, end, text = span.get("start"), span.get("end"), span.get("text")
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(quote)
                or not isinstance(text, str)
                or quote[start:end] != text
            ):
                return False
            found = True
    return found or not required


def _source_authorized(document: dict[str, Any], principal_alias: str | None) -> bool:
    """Match the seeded workspace/owner/visibility contract, failing closed.

    Corpus v2 seeds no collection shares. Group names in prose or metadata are
    not grants. Organization collections are seeded with the source workspace
    as organization, and seeded principals use that same organization identity.
    """
    principal = document.get("principals", {}).get(principal_alias, {})
    workspace = document.get("workspace_id")
    if not workspace or principal.get("workspace_id") != workspace:
        return False
    visibility = document.get("visibility")
    if visibility not in ("public", "organization", "private"):
        return False
    return (
        document.get("owner") == principal_alias
        or principal.get("role") == "admin"
        or visibility in ("public", "organization")
    )


def _unauthorized_exposures(
    case: dict[str, Any], response: dict[str, Any], documents: dict[str, Any]
) -> int:
    """Judge every exposed identity, including ranks beyond metric top-five."""
    reverse = {str(value["document_id"]): key for key, value in documents.items()}
    forbidden = {
        (source["document_id"], str(source["version_number"]))
        for source in case["forbidden_sources"]
    }
    ranks = (response.get("retrieval_trace") or {}).get("scores") or []
    exposed = {
        (
            str(item.get("document_id")),
            str(item.get("document_version", item.get("version_number"))),
        )
        for item in [*(response.get("sources") or []), *ranks]
    }
    unauthorized = 0
    for identifier, version in exposed:
        logical = reverse.get(identifier)
        document = documents.get(logical, {}) if logical is not None else {}
        if (
            not document
            or not _source_authorized(document, case.get("principal"))
            or version not in document.get("versions", {})
            or (logical, version) in forbidden
        ):
            unauthorized += 1
    return unauthorized


def score_coverage(
    case: dict[str, Any],
    response: dict[str, Any],
    documents: dict[str, Any],
    result: dict[str, Any],
    *,
    require_answer_spans: bool,
) -> dict[str, Any]:
    answer = normalized(response.get("answer") or "")
    citations = response.get("sources") or []
    expected = case["expected_behavior"] == "answer"
    facts_correct = all(
        any(contains(answer, fact) for fact in alternatives)
        for alternatives in case.get("required_facts", [])
    )
    cursor = 0
    order_correct = True
    for alternatives in case.get("ordered_steps", []):
        matches = [
            match
            for step in alternatives
            if (
                match := re.search(
                    r"(?<!\w)" + re.escape(normalized(step)) + r"(?!\w)",
                    answer[cursor:],
                )
            )
            is not None
        ]
        if not matches:
            order_correct = False
            break
        cursor += min(matches, key=lambda match: match.start()).end()
    spans_supported = all(
        any(contains(answer, span) for span in source["acceptable_answer_spans"])
        for source in case["expected_sources"]
    )
    answer_correct = (
        facts_correct and order_correct and spans_supported if expected else None
    )
    reverse = {str(value["document_id"]): key for key, value in documents.items()}
    citation_integrity = True
    for citation in citations:
        logical = reverse.get(str(citation.get("document_id")))
        versions = documents[logical].get("versions", {}) if logical is not None else {}
        version = str(citation.get("document_version"))
        snapshot = versions.get(version, {})
        quote = citation.get("quoted_text")
        if (
            not snapshot
            or not isinstance(quote, str)
            or not quote
            or quote not in snapshot.get("content", "")
            or citation.get("content_hash") != snapshot.get("content_hash")
            or version != str(max(map(int, versions), default=0))
        ):
            citation_integrity = False
    emitted = bool(answer) and not result["refused"]
    span_integrity = _spans_valid(citations, require_answer_spans and emitted)
    execution_error = result["execution_error"] or response.get("outcome") in (
        "error",
        "interrupted",
        "running",
        "pending",
    )
    source_correct = result["source_version_correct"]
    if expected:
        source_correct = bool(source_correct) and citation_integrity
    # Refusals must not carry an answer body (even when the refused flag is set).
    negative_clean = expected or not answer
    unauthorized = _unauthorized_exposures(case, response, documents)
    quality_passed = (
        result["behavior_correct"]
        and not execution_error
        and not unauthorized
        and citation_integrity
        and negative_clean
        and (not expected or (source_correct and answer_correct))
    )
    return {
        **result,
        "passed": bool(quality_passed and span_integrity),
        "score_contract": "coverage-v2",
        "answer_quality_passed": bool(quality_passed),
        "unauthorized_source_exposures": unauthorized,
        "execution_error": execution_error,
        "answer_contract_correct": answer_correct,
        "required_facts_correct": facts_correct if expected else None,
        "ordered_steps_correct": order_correct if expected else None,
        "source_version_correct": source_correct,
        "citation_integrity_correct": citation_integrity,
        "span_integrity_correct": span_integrity,
        "span_integrity_required": require_answer_spans,
    }
