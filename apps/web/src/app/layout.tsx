import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
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
            <Link href="/" className="text-xl font-bold text-brand-700">
              GroundTruth
            </Link>
            <div className="flex flex-wrap justify-end gap-x-4 gap-y-2 sm:gap-6">
              <Link
                href="/chat"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Chat
              </Link>
              <Link
                href="/documents"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Documents
              </Link>
              <Link
                href="/workflows"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Workflows
              </Link>
              <Link
                href="/admin"
                className="text-sm font-medium text-gray-600 hover:text-brand-600"
              >
                Admin
              </Link>
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
