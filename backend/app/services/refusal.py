from app.config import get_settings
from app.models.chunk import ChunkWithScore

settings = get_settings()

REFUSAL_MESSAGES: dict[str, str] = {
    "no_results": (
        "I couldn't find any relevant information in the uploaded documents "
        "for your question. Try uploading additional documents that cover this topic."
    ),
    "low_confidence": (
        "The information I found isn't detailed enough to give you a confident answer. "
        "Try rephrasing your question or providing more specific terms."
    ),
    "out_of_domain": (
        "Your question appears to be outside the scope of the uploaded documents. "
        "I can only answer based on the documents that have been provided."
    ),
    "safety": (
        "I'm not able to assist with that type of request."
    ),
}


class RefusalService:
    """Determines whether the system should refuse to answer a query.

    Checks retrieval results, confidence scores, and query content to
    decide whether a graceful refusal is more appropriate than a
    potentially unreliable answer.
    """

    def should_refuse(
        self,
        query: str,
        chunks: list[ChunkWithScore],
        confidence: float,
    ) -> tuple[bool, str]:
        """Evaluate whether the system should refuse to answer.

        Checks for empty results, low confidence, out-of-domain queries,
        and safety concerns.

        Args:
            query: The user's question.
            chunks: Retrieved chunks with relevance scores.
            confidence: Overall confidence score for the retrieval.

        Returns:
            A tuple of (should_refuse: bool, reason: str).
        """
        if not self._check_relevance(chunks):
            return True, REFUSAL_MESSAGES["no_results"]

        if not self._check_confidence(confidence):
            return True, REFUSAL_MESSAGES["low_confidence"]

        safety_result = self._check_safety(query)
        if safety_result:
            return True, REFUSAL_MESSAGES["safety"]

        return False, ""

    def _check_relevance(self, chunks: list[ChunkWithScore]) -> bool:
        """Check whether any chunks were retrieved with sufficient relevance.

        Args:
            chunks: Retrieved chunks with scores.

        Returns:
            True if at least one chunk meets the similarity threshold.
        """
        if not chunks:
            return False
        return any(chunk.relevance_score >= settings.SIMILARITY_THRESHOLD * 0.5 for chunk in chunks)

    def _check_confidence(self, confidence: float) -> bool:
        """Check whether the overall confidence meets the minimum threshold.

        Args:
            confidence: The computed confidence score.

        Returns:
            True if confidence is above the refusal threshold.
        """
        return confidence >= settings.REFUSAL_CONFIDENCE_THRESHOLD

    def _check_safety(self, query: str) -> bool:
        """Check the query for safety concerns or prompt injection patterns.

        Performs basic pattern matching for common injection attempts
        and harmful content indicators.

        Args:
            query: The user's question.

        Returns:
            True if a safety concern is detected.
        """
        injection_patterns = [
            "ignore previous instructions",
            "forget your instructions",
            "you are now",
            "system prompt",
            "jailbreak",
        ]
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in injection_patterns)


refusal_service = RefusalService()
