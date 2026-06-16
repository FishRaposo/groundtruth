import type { Metadata } from "next";
import { Inter } from "next/font/google";
import ErrorBoundary from "@/components/ErrorBoundary";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GroundTruth — RAG Assistant",
  description:
    "A production-minded RAG assistant template for grounded answers with citations and transparent retrieval.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 text-gray-900 antialiased`}>
        <header className="border-b border-gray-200 bg-white">
          <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <a href="/" className="text-xl font-bold text-brand-700">
              GroundTruth
            </a>
            <div className="flex gap-6">
              <a
                href="/chat"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Chat
              </a>
              <a
                href="/documents"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Documents
              </a>
              <a
                href="/workflows"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Workflows
              </a>
            </div>
          </nav>
        </header>
        <main>
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </body>
    </html>
  );
}
