"""Lexical term extraction used by keyword retrieval and reranking."""

from app.utils.text import content_terms, query_terms


def test_query_terms_drop_function_words_and_punctuation() -> None:
    assert query_terms("What are the salary bands?") == {"salary", "band"}


def test_query_terms_keep_function_words_when_nothing_else_is_left() -> None:
    assert query_terms("What is this?") == {"what", "is", "this"}


def test_content_terms_match_whole_words_not_fragments() -> None:
    terms = content_terms("Be careful: refunds take 5 business days.")
    assert "are" not in terms
    assert {"refund", "business", "day", "5"} <= terms
