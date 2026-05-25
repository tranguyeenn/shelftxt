import { StatCard } from "@/components/ui/StatCard";
import { derivedShelf, starRating, type BookRecord } from "@/lib/books";

type ReadingStatsProps = {
  library: BookRecord[];
};

export function ReadingStats({ library }: ReadingStatsProps) {
  const tbr = library.filter((b) => derivedShelf(b) === "unread" || derivedShelf(b) === "reading");
  const completed = library.filter((b) => derivedShelf(b) === "completed");
  const ratings = completed
    .map((b) => starRating(b))
    .filter((r): r is number => r !== null);
  const avgRating =
    ratings.length > 0
      ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1)
      : "—";

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-text-dim">At a glance</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="TBR books" value={String(tbr.length)} hint="Unread + in progress" />
        <StatCard label="Completed" value={String(completed.length)} />
        <StatCard
          label="Avg rating given"
          value={avgRating === "—" ? "—" : `${avgRating} / 5`}
          hint={ratings.length > 0 ? `from ${ratings.length} rated` : "no ratings yet"}
        />
      </div>
    </section>
  );
}
