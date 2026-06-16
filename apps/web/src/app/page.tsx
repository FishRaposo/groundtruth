import Link from "next/link";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <section className="mb-16 text-center">
        <h1 className="mb-4 text-5xl font-bold tracking-tight text-gray-900">
          GroundTruth
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-gray-600">
          A production-minded RAG assistant template for teams that need grounded
          answers, citations, and transparent retrieval behavior.
        </p>
      </section>

      <section className="mb-12 grid gap-6 md:grid-cols-3">
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h3 className="mb-2 font-semibold text-gray-900">Grounded Answers</h3>
          <p className="text-sm text-gray-600">
            Every answer is generated from retrieved document context — no hallucination.
          </p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h3 className="mb-2 font-semibold text-gray-900">Source Citations</h3>
          <p className="text-sm text-gray-600">
            Every factual claim links to the source chunk with relevance scores.
          </p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h3 className="mb-2 font-semibold text-gray-900">Graceful Refusal</h3>
          <p className="text-sm text-gray-600">
            When evidence is insufficient, the system says so rather than guessing.
          </p>
        </div>
      </section>

      <section className="mb-12 rounded-lg border border-gray-200 bg-white p-8">
        <h2 className="mb-4 text-2xl font-bold text-gray-900">Quick Start</h2>
        <ol className="list-inside list-decimal space-y-2 text-gray-700">
          <li>
            Upload documents via the{" "}
            <Link href="/documents" className="text-brand-600 underline">
              Documents
            </Link>{" "}
            page
          </li>
          <li>
            Ask questions in the{" "}
            <Link href="/chat" className="text-brand-600 underline">
              Chat
            </Link>{" "}
            interface
          </li>
          <li>Review cited answers with source links and retrieval traces</li>
        </ol>
      </section>

      <section className="text-center">
        <div className="flex justify-center gap-4">
          <Link
            href="/chat"
            className="rounded-lg bg-brand-600 px-6 py-3 font-medium text-white hover:bg-brand-700"
          >
            Start Chatting
          </Link>
          <Link
            href="/documents"
            className="rounded-lg border border-gray-300 bg-white px-6 py-3 font-medium text-gray-700 hover:bg-gray-50"
          >
            Upload Documents
          </Link>
        </div>
      </section>
    </div>
  );
}
