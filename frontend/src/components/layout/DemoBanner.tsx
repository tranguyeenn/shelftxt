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
        <p className="text-sm font-semibold text-score-recency">⚠️ Demo Mode</p>
        <p className="mt-1 text-sm leading-relaxed text-text">
          This public demo uses a shared library. Changes may affect data visible to other
          visitors and demo data may be reset at any time.
        </p>
        <p className="mt-1 text-sm leading-relaxed text-text-muted">
          For a private library, self-host your own instance.
        </p>
      </div>
    </aside>
  );
}
