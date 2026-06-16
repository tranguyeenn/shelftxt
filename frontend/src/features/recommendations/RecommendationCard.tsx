import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { formatScore } from "@/lib/scoring";
import type { RecommendationItem } from "@/lib/types";

type RecommendationCardProps = {
  item: RecommendationItem;
  rank: number;
};

export function RecommendationCard({ item, rank }: RecommendationCardProps) {
  const { settings } = useUserSettings();
  const { book, score, explanation, similar_books } = item;
  const showExplanation = settings.showRecommendationExplanations;

  return (
    <Card className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-muted font-mono text-sm font-semibold text-accent">
            #{rank}
          </span>
          <div>
            <h3 className="text-lg font-semibold text-text">
              <Link
                to={`/book/${encodeURIComponent(book.id)}`}
                className="hover:text-accent hover:underline"
              >
                {book.title}
              </Link>
            </h3>
            <p className="mt-0.5 text-sm text-text-muted">{book.author}</p>
          </div>
        </div>
        <Badge tone={rank <= 3 ? "success" : "neutral"}>Score {formatScore(score)}</Badge>
      </div>

      {showExplanation ? (
        <blockquote className="border-l-2 border-accent/40 pl-4 text-sm leading-relaxed text-text-muted">
          {explanation}
        </blockquote>
      ) : null}

      {showExplanation && similar_books.length > 0 ? (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-text-dim">Similar to</p>
          <ul className="mt-2 grid gap-1 text-sm text-text-muted">
            {similar_books.map((similar) => (
              <li key={similar.id || `${similar.title}-${similar.author}`}>
                <span className="text-text">{similar.title}</span>
                <span className="text-text-dim"> — {similar.author}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}
