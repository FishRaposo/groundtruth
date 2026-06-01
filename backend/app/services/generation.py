import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from app.config import get_settings
from app.models.query import SourceCitation

settings = get_settings()

SYSTEM_PROMPT = """You are GroundTruth, a precise assistant that answers questions \
using ONLY the provided context. Follow these rules strictly:

1. Answer the question using only the information in the provided context.
2. If the context does not contain enough information to answer, say so explicitly.
3. Cite your sources by referencing [1], [2], etc. corresponding to the source indices.
4. Do not add any information that is not directly supported by the context.
5. Be concise and direct. Avoid hedging language when the evidence is clear.
6. When multiple sources provide complementary information, synthesize them.
7. If sources conflict, note the discrepancy and present both perspectives."""


class GenerationService:
    """Generates grounded answers using an LLM constrained to retrieved context.

    Offline-first: when no OPENAI_API_KEY is configured, produces deterministic
    simulated answers that cite sources and honor refusal thresholds.
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None and settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def generate_answer(
        self,
        query: str,
        context: list[str],
        sources: list[SourceCitation],
    ) -> tuple[str, dict[str, int]]:
        """Generate a grounded answer from retrieved context.

        Args:
            query: The user's question.
            context: List of retrieved chunk texts to use as evidence.
            sources: List of source citations for reference.

        Returns:
            A tuple of (generated_answer, token_usage_dict).
        """
        if not settings.OPENAI_API_KEY:
            answer = self._simulate_answer(query, context)
            return answer, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        client = self._get_client()
        if client is None:
            return "Unable to generate an answer at this time.", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

        prompt = self._build_prompt(query, context)
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            answer = response.choices[0].message.content or ""
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            return self._parse_response(answer), token_usage
        except Exception:
            return "Unable to generate an answer at this time.", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

    async def stream_answer(
        self,
        query: str,
        context: list[str],
        sources: list[SourceCitation],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a grounded answer token by token from retrieved context.

        Args:
            query: The user's question.
            context: List of retrieved chunk texts to use as evidence.
            sources: List of source citations for reference.

        Yields:
            SSE-compatible dicts with type "token", "done", or "error".
        """
        if not settings.OPENAI_API_KEY:
            async for event in self._simulate_stream(query, context):
                yield event
            return

        client = self._get_client()
        if client is None:
            yield {"type": "error", "content": "Unable to stream answer"}
            return

        prompt = self._build_prompt(query, context)
        try:
            completion_tokens = 0
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        completion_tokens += 1
                        yield {"type": "token", "content": delta}

            yield {
                "type": "done",
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": completion_tokens,
                    "total_tokens": completion_tokens,
                },
            }
        except Exception:
            yield {"type": "error", "content": "Unable to stream answer"}

    def _simulate_answer(self, query: str, context: list[str]) -> str:
        """Produce a deterministic simulated answer for offline/demo mode.

        Synthesizes a plausible response from the provided context chunks,
        citing sources. Falls back to a refusal when context is empty.
        """
        if not context:
            return (
                "I don't have sufficient information in the provided documents "
                "to answer this question. Please upload relevant documents or rephrase your query."
            )

        # Build a synthetic answer that quotes from each context chunk
        parts: list[str] = []
        for i, chunk in enumerate(context, 1):
            # Truncate long chunks for brevity
            excerpt = chunk[:200] + "..." if len(chunk) > 200 else chunk
            parts.append(f"According to source [{i}]: {excerpt}")

        answer = "Based on the retrieved context:\n\n" + "\n\n".join(parts)
        return self._parse_response(answer)

    async def _simulate_stream(
        self,
        query: str,
        context: list[str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a simulated answer word by word for offline/demo mode."""
        answer = self._simulate_answer(query, context)
        words = answer.split(" ")
        for word in words:
            yield {"type": "token", "content": word + " "}
            await asyncio.sleep(0.01)

        yield {
            "type": "done",
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": len(words),
                "total_tokens": len(words),
            },
        }

    def _build_prompt(self, query: str, context: list[str]) -> str:
        """Build the user prompt with numbered context chunks.

        Args:
            query: The user's question.
            context: List of context strings to include.

        Returns:
            Formatted prompt string with numbered context sections.
        """
        context_sections: list[str] = []
        for i, chunk in enumerate(context, 1):
            context_sections.append(f"[{i}] {chunk}")

        context_text = "\n\n".join(context_sections)
        return f"Context:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"

    def _parse_response(self, response: str) -> str:
        """Clean and validate the LLM response.

        Strips leading/trailing whitespace and ensures the response
        is non-empty.

        Args:
            response: Raw response text from the LLM.

        Returns:
            Cleaned response string.
        """
        cleaned = response.strip()
        return cleaned if cleaned else "No answer could be generated from the provided context."


generation_service = GenerationService()
