"""Lexical term extraction shared by keyword retrieval and reranking.

Keyword overlap feeds both the keyword leg of hybrid retrieval and the
reranker, and through them the refusal confidence. Matching raw
``query.split()`` terms as substrings let function words ("what", "are",
"the") and fragments ("are" inside "careful") count as evidence, so a
question with no support in the corpus could still clear the refusal
threshold. Terms here are whole words, lowercased, with a minimal plural fold
and common English function words removed.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "about",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "many",
        "may",
        "me",
        "might",
        "much",
        "must",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "shall",
        "should",
        "so",
        "some",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def _fold(token: str) -> str:
    """Fold a simple English plural ("refunds" -> "refund", not "business")."""
    if token in STOPWORDS:
        return token
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def content_terms(text: str) -> set[str]:
    """Return the folded whole-word terms present in ``text``."""
    return {_fold(token) for token in _TOKEN_RE.findall(text.lower())}


def query_terms(text: str) -> set[str]:
    """Return the folded content-bearing terms of a query.

    Function words are dropped. A query made only of function words keeps
    them, so it still matches literally instead of matching nothing.
    """
    tokens = set(_TOKEN_RE.findall(text.lower()))
    meaningful = {token for token in tokens if token not in STOPWORDS}
    return {_fold(token) for token in (meaningful or tokens)}
