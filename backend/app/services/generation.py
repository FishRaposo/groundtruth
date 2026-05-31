import asyncio
import threading
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

    Builds a structured prompt that includes only the retrieved chunks as context,
    then calls the configured LLM to produce an answer that cites its sources.
    """

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
        prompt = self._build_prompt(query, context)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
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
        prompt = self._build_prompt(query, context)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            completion_tokens = 0

            def _consume() -> None:
                nonlocal completion_tokens
                try:
                    stream = client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                        max_tokens=1024,
                        stream=True,
                    )
                    for chunk in stream:
                        if chunk.choices:
                            delta = chunk.choices[0].delta.content
                            if delta:
                                completion_tokens += 1
                                asyncio.run_coroutine_threadsafe(
                                    queue.put({"type": "token", "content": delta}), loop
                                )

                    asyncio.run_coroutine_threadsafe(
                        queue.put({
                            "type": "done",
                            "token_usage": {
                                "prompt_tokens": 0,
                                "completion_tokens": completion_tokens,
                                "total_tokens": completion_tokens,
                            },
                        }),
                        loop,
                    )
                except Exception:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "content": "Streaming failed"}), loop
                    )
                finally:
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

            thread = threading.Thread(target=_consume, daemon=True)
            thread.start()

            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        except Exception:
            yield {"type": "error", "content": "Unable to stream answer"}

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
