import { isDemoMode } from "@/lib/demoMode";

export function DemoBanner() {
  if (!isDemoMode) {
    return null;
  }

  return (
    <aside
      role="note"
      aria-label="Demo mode"
      className="border-b border-score-recency/30 bg-score-recency/10 px-4 py-3 sm:px-6 md:px-8"
    >
      <div className="mx-auto max-w-5xl">
        <p className="text-sm font-semibold text-score-recency">⚠️ Demo Mode — Read Only</p>
        <p className="mt-1 text-sm leading-relaxed text-text">
          This public demo uses a shared library. You can browse rankings and export data, but
          adding, editing, importing, and deleting books is disabled.
        </p>
        <p className="mt-1 text-sm leading-relaxed text-text-muted">
          Demo data may reset at any time. For a private library, self-host your own instance.
        </p>
      </div>
    </aside>
  );
}
