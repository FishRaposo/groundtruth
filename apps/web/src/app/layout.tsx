import type { Metadata } from "next";
import ErrorBoundary from "@/components/ErrorBoundary";
import PortfolioProvider from "@/components/PortfolioProvider";
import PortfolioShell from "@/components/PortfolioShell";
import "./globals.css";
export const metadata: Metadata = {
  title: "GroundTruth — Evidence before answers",
  description:
    "Ask an operational question. Inspect the evidence before trusting the answer.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ErrorBoundary>
          <PortfolioProvider>
            <PortfolioShell>{children}</PortfolioShell>
          </PortfolioProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
