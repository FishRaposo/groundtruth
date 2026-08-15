"""GroundTruth demo — grounded retrieval with citations and graceful refusal.

Runs fully offline (no database, Redis, or LLM keys) using GroundTruth's internal
vendor core: it ingests a
policy document, retrieves the most relevant chunk for two questions using the lexical
(keyword) leg of hybrid retrieval, answers the in-corpus one with a citation, and
refuses the out-of-corpus one — then verifies both with the shared eval judges.
"""

import asyncio

from app.internal.vendor_core.docparse import ChunkStrategy, chunk_text, get_parser
from app.internal.vendor_core.embeddings import tfidf_cosine
from app.internal.vendor_core.evaljudge import CitationJudge, RefusalJudge
from app.internal.vendor_core.logging import setup_logging
from loguru import logger

CORPUS = b"""# Refund Policy

Customers may request a refund within 30 days of purchase. Refunds are issued to
the original payment method within 5 business days. Digital goods are non-refundable
once downloaded.

# Shipping

Standard shipping takes 5-7 business days. Expedited shipping is available at
checkout for an additional fee.
"""

REFUSAL_THRESHOLD = 0.15


def retrieve(question: str, chunks: list[str]) -> tuple[float, str]:
    """Return the best-scoring chunk for a question using lexical similarity."""
    scored = sorted(
        ((tfidf_cosine(question, c), c) for c in chunks),
        key=lambda x: x[0],
        reverse=True,
    )
    return scored[0]


def answer(question: str, chunks: list[str]) -> tuple[str, float]:
    """Ground an answer in the top chunk, or refuse when evidence is too weak."""
    top_score, top_chunk = retrieve(question, chunks)
    if top_score < REFUSAL_THRESHOLD:
        return ("I cannot answer that from the provided documents.", top_score)
    snippet = top_chunk.splitlines()[-1][:80]
    return (f"{snippet} [1]", top_score)


async def main() -> None:
    setup_logging(level="INFO", service_name="groundtruth-demo")
    logger.info("=== GroundTruth demo (offline grounded RAG) ===")

    doc = get_parser("refund_policy.md").parse(CORPUS, filename="policy.md")
    chunks = chunk_text(doc.text, strategy=ChunkStrategy.STRUCTURAL, chunk_size=200)
    logger.info("Ingested '{}' -> {} chunk(s)", doc.title, len(chunks))

    citation_judge = CitationJudge()
    refusal_judge = RefusalJudge()

    in_corpus = "How many days do I have to request a refund?"
    out_corpus = "What is the company's parental leave policy?"

    a1, s1 = answer(in_corpus, chunks)
    cited = (await citation_judge.evaluate(expected=None, actual=a1)).passed
    logger.info("Q: {}", in_corpus)
    logger.info("A (score {:.3f}): {}  [cited={}]", s1, a1, cited)

    a2, s2 = answer(out_corpus, chunks)
    refused = (await refusal_judge.evaluate(expected=None, actual=a2)).passed
    logger.info("Q: {}", out_corpus)
    logger.info("A (score {:.3f}): {}  [refused={}]", s2, a2, refused)

    logger.info(
        "=== Demo complete: grounded answer + cited source + graceful refusal ==="
    )


if __name__ == "__main__":
    asyncio.run(main())
