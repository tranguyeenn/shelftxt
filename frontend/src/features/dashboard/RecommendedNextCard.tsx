import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Card } from "@/components/ui/Card";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { formatScore } from "@/lib/scoring";
import type { RecommendationItem } from "@/lib/types";

type RecommendedNextCardProps = {
  item: RecommendationItem;
};

export function RecommendedNextCard({ item }: RecommendedNextCardProps) {
  const { settings } = useUserSettings();
  const { book, score, explanation, similar_books } = item;
  const showExplanation = settings.showRecommendationExplanations;

  return (
    <Card padding="lg" className="grid gap-6 lg:grid-cols-[140px_1fr]">
      <div className="mx-auto w-full max-w-[140px] lg:mx-0">
        <BookCoverPlaceholder title={book.title} />
      </div>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-text">{book.title}</h2>
            <p className="mt-1 text-sm text-text-muted">{book.author}</p>
          </div>
          <div className="text-right">
            <p className="font-mono text-xs uppercase tracking-wide text-text-dim">
              Recommendation score
            </p>
            <p className="font-mono text-3xl font-semibold text-accent">{formatScore(score)}</p>
            <Badge tone="success">Top pick</Badge>
          </div>
        </div>
        <section className="rounded-lg border border-border-subtle bg-bg-elevated p-4">
          <h3 className="text-sm font-medium text-text">Why this book?</h3>
          {showExplanation ? (
            <p className="mt-2 text-sm leading-relaxed text-text-muted">{explanation}</p>
          ) : null}
          {showExplanation && similar_books.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-text-dim">Similar to</p>
              <ul className="mt-2 grid gap-1 text-sm text-text-muted">
                {similar_books.map((similar) => (
                  <li key={similar.id || similar.title}>
                    <span className="text-text">{similar.title}</span>
                    <span className="text-text-dim"> — {similar.author}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={`/book/${encodeURIComponent(book.id)}`}
              className="inline-flex items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-bg hover:bg-accent-dim"
            >
              View book
            </Link>
            <Link
              to="/ranking"
              className="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-surface hover:text-text"
            >
              See top 10
            </Link>
          </div>
        </section>
      </div>
    </Card>
  );
}
