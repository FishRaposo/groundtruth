import AdminConsole from "@/components/AdminConsole";

export default function AdminPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-600">Operations</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-gray-900">Admin evidence</h1>
        <p className="mt-2 max-w-2xl text-sm text-gray-600">Usage and audit visibility without mutation controls.</p>
      </div>
      <AdminConsole />
    </div>
  );
}
