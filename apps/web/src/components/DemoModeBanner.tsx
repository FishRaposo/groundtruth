"use client";

import { DEMO_FORCED, DEMO_NOTICE } from "@/lib/demoMode";

export default function DemoModeBanner() {
  if (!DEMO_FORCED) return null;

  return (
    <div
      role="status"
      data-testid="demo-banner"
      className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800"
    >
      {DEMO_NOTICE}
    </div>
  );
}
