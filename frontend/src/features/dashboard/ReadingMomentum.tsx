import { Card } from "@/components/ui/Card";
import { getReadingMomentum } from "@/lib/dashboardMetrics";
import type { BookRecord } from "@/lib/books";

type ReadingMomentumProps = {
  library: BookRecord[];
};

export function ReadingMomentum({ library }: ReadingMomentumProps) {
  const momentum = getReadingMomentum(library);
  const lastCompleted = momentum.lastCompletedDate?.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric"
  });

  return (
    <Card className="grid gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">Reading momentum</p>
          <h2 className="mt-1 text-lg font-semibold text-text">This month’s activity</h2>
        </div>
        <div className="grid h-11 w-11 place-items-center rounded-full border border-accent/30 bg-accent-muted text-xl text-accent" aria-hidden>
          ↗
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-border-subtle bg-bg-elevated p-3">
          <dd className="font-mono text-xl font-semibold text-text">{momentum.currentlyReading}</dd>
          <dt className="mt-1 text-xs text-text-muted">reading now</dt>
        </div>
        <div className="rounded-lg border border-border-subtle bg-bg-elevated p-3">
          <dd className="font-mono text-xl font-semibold text-text">{momentum.completedThisMonth}</dd>
          <dt className="mt-1 text-xs text-text-muted">finished</dt>
        </div>
        <div className="rounded-lg border border-border-subtle bg-bg-elevated p-3">
          <dd className="font-mono text-xl font-semibold text-text">
            {momentum.trackedPagesThisMonth.toLocaleString()}
          </dd>
          <dt className="mt-1 text-xs text-text-muted">tracked pages</dt>
        </div>
      </dl>

      <div className="border-t border-border-subtle pt-3 text-sm text-text-muted">
        {lastCompleted ? `Last finish recorded ${lastCompleted}.` : "No completed book date recorded yet."}
        <p className="mt-1 text-xs text-text-dim">
          Pages include books finished this month and progress on books started this month.
        </p>
      </div>
    </Card>
  );
}
