import { EmptyState } from "@/components/ui/EmptyState";
import type { CompletionChartData } from "@/lib/insights";

type MonthlyBooksChartProps = {
  data: CompletionChartData;
};

export function MonthlyBooksChart({ data }: MonthlyBooksChartProps) {
  if (data.completedCount === 0) {
    return (
      <EmptyState
        title="No completed books yet."
        description="Finish a book to see monthly reading stats."
      />
    );
  }

  if (data.datedCompletedCount === 0) {
    return (
      <EmptyState
        title="Completed books found, but no completion dates yet."
        description="Add completion dates to completed books to populate this chart."
      />
    );
  }

  const max = Math.max(...data.months.map((item) => item.count), 1);

  return (
    <div className="grid gap-3">
      <div
        className="grid min-h-48 grid-cols-12 items-end gap-1 sm:gap-2"
        role="img"
        aria-label="Books read per month chart"
      >
        {data.months.map((item) => {
          const height = item.count === 0 ? 0 : Math.max(12, (item.count / max) * 100);
          return (
            <div key={item.month} className="grid h-48 min-w-0 grid-rows-[1fr_auto] gap-2">
              <div className="flex items-end justify-center border-b border-border-subtle">
                <div
                  className="w-full rounded-t bg-accent"
                  style={{ height: `${height}%` }}
                  aria-label={`${item.month}: ${item.count} completed book${item.count === 1 ? "" : "s"}`}
                  title={`${item.month}: ${item.count}`}
                >
                  {item.count > 0 ? (
                    <span className="block -translate-y-6 text-center text-xs text-text">
                      {item.count}
                    </span>
                  ) : null}
                </div>
              </div>
              <span className="truncate text-center text-[10px] text-text-muted sm:text-xs">
                {item.month}
              </span>
            </div>
          );
        })}
      </div>
      {data.undatedCompletedCount > 0 ? (
        <p className="text-xs text-text-muted">
          {data.undatedCompletedCount} completed book{data.undatedCompletedCount === 1 ? "" : "s"} excluded because completion dates are missing.
        </p>
      ) : null}
      {data.futureDatedCount > 0 ? (
        <p className="text-xs text-text-muted">
          {data.futureDatedCount} completed book{data.futureDatedCount === 1 ? " has" : "s have"} a future completion date and {data.futureDatedCount === 1 ? "was" : "were"} excluded.
        </p>
      ) : null}
    </div>
  );
}
