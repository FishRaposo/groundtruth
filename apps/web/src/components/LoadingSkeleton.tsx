export function MessageSkeleton() {
  return (
    <div className="mr-12 animate-pulse rounded-lg border border-gray-200 bg-white p-4">
      <div className="space-y-2">
        <div className="h-3 w-3/4 rounded bg-gray-200" />
        <div className="h-3 w-1/2 rounded bg-gray-200" />
        <div className="h-3 w-5/6 rounded bg-gray-200" />
      </div>
      <div className="mt-3 space-y-2">
        <div className="h-2 w-16 rounded bg-gray-100" />
        <div className="h-10 w-full rounded bg-gray-100" />
      </div>
    </div>
  );
}

export function DocumentListSkeleton() {
  return (
    <div className="mt-8 space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <DocumentListItemSkeleton key={i} />
      ))}
    </div>
  );
}

function DocumentListItemSkeleton() {
  return (
    <div className="card flex animate-pulse items-center justify-between">
      <div className="space-y-2">
        <div className="h-4 w-48 rounded bg-gray-200" />
        <div className="h-3 w-32 rounded bg-gray-100" />
      </div>
      <div className="flex items-center gap-3">
        <div className="h-5 w-16 rounded-full bg-gray-100" />
        <div className="h-4 w-12 rounded bg-gray-100" />
      </div>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card animate-pulse">
      <div className="space-y-3">
        <div className="h-4 w-1/3 rounded bg-gray-200" />
        <div className="h-3 w-full rounded bg-gray-100" />
        <div className="h-3 w-2/3 rounded bg-gray-100" />
      </div>
    </div>
  );
}
