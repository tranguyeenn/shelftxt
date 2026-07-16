import { useState } from "react";
import { Link } from "react-router-dom";

import { BookCover } from "@/components/ui/BookCover";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MoodTags } from "@/components/ui/MoodTags";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import {
  recommendationMatchLabel,
  recommendationSignals,
  readerFacingExplanation
} from "@/lib/recommendationDisplay";
import type { RecommendationItem } from "@/lib/types";
import { openLibraryCoverUrl } from "@/lib/coverUrl";

type RecommendationCardProps = {
  item: RecommendationItem;
  rank: number;
  onNotInterested?: (item: RecommendationItem) => Promise<void>;
};

export function RecommendationCard({ item, rank, onNotInterested }: RecommendationCardProps) {
  const { settings } = useUserSettings();
  const [showWhy, setShowWhy] = useState(false);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const book = item.recommended_book ?? item.book;
  const {
    score,
    similar_books,
    matched_genres = [],
    matched_subjects = [],
    matched_liked_books = [],
  } = item;
  const showExplanation = settings.showRecommendationExplanations;
  const tags = [...matched_genres, ...matched_subjects].slice(0, 5);
  const matchLabel = item.qualitative_match_label ?? recommendationMatchLabel(score);
  const signals = recommendationSignals(item);
  const relatedBooks = (item.related_books ?? item.recommendation_breakdown?.inspired_by ?? matched_liked_books).slice(0, 3);
  const explanation = readerFacingExplanation(item);
  const description = book.description?.trim();
  const bookIdentity = book.id ?? book.work_id ?? item.work_id ?? item.recommendation_id ?? "";
  const detailPath = item.in_library && bookIdentity ? `/app/book/${encodeURIComponent(bookIdentity)}` : "/app/add";

  return (
    <Card className="grid gap-4 md:grid-cols-[72px_1fr]">
      <BookCover
        title={book.title}
        coverUrl={book.cover_url ?? openLibraryCoverUrl(bookIdentity, "S")}
        className="w-[72px]"
      />
      <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-muted text-sm font-semibold text-accent-readable">
            #{rank}
          </span>
          <div>
            <h3 className="text-lg font-semibold text-text">
              <Link
                to={detailPath}
                className="hover:text-accent hover:underline"
              >
                {book.title}
              </Link>
            </h3>
            <p className="mt-0.5 text-sm text-text-muted">{book.author}</p>
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Badge tone={rank <= 3 ? "success" : "neutral"}>{matchLabel}</Badge>
          <Badge tone={item.in_library ? "accent" : "neutral"}>
            {item.in_library ? "On your shelf" : "New discovery"}
          </Badge>
        </div>
      </div>

      {showExplanation ? (
        <div className="grid gap-3 rounded-lg border border-border-subtle bg-bg-elevated p-3">
          <div>
            <p className="text-sm font-medium text-text">Why this book</p>
            {description ? (
              <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-text-muted">
                {description}
              </p>
            ) : null}
            <p className="mt-2 text-sm leading-relaxed text-text-muted">{explanation}</p>
            {relatedBooks.length > 0 ? (
              <div className="mt-3">
                <p className="text-xs font-medium text-text-dim">Related books</p>
                <ul className="mt-1 grid gap-1 text-sm text-text-muted">
                  {relatedBooks.map((book) => (
                    <li key={book.id || `${book.title}-${book.author}`}>{book.title}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => setShowWhy((current) => !current)}
            className="justify-self-start rounded-lg px-3 py-1.5 text-sm text-accent-readable hover:bg-accent-muted"
          >
            why this book?
          </button>
          {showWhy ? (
            <div className="rounded-lg border border-border bg-surface p-4">
              <h4 className="text-sm font-medium text-text">Recommendation Breakdown</h4>
              <p className="mt-2 text-sm leading-relaxed text-text-muted">{explanation}</p>
              {signals.length > 0 ? (
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  {signals.map((signal) => (
                    <div key={signal.label}>
                      <dt className="text-text-dim">{signal.label}</dt>
                      <dd className="text-text">{signal.display}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-2 text-sm text-text-muted">ShelfTxt has a pick here, but not enough visible signals to explain it well yet.</p>
              )}
              {relatedBooks.length > 0 ? (
                <div className="mt-4 border-t border-border-subtle pt-4">
                  <p className="text-xs font-medium text-text-dim">Related books</p>
                  <ul className="mt-2 grid gap-1 text-sm text-text-muted">
                    {relatedBooks.map((book) => (
                      <li key={book.id || `${book.title}-${book.author}`}>{book.title}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {showExplanation && tags.length > 0 ? (
        <MoodTags tags={tags} />
      ) : null}

      {showExplanation && similar_books.length > 0 ? (
        <div>
          <p className="text-xs font-medium uppercase text-text-dim">Similar to</p>
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
      <div className="flex flex-wrap gap-2">
        <Link
          to={item.in_library ? detailPath : "/app/add"}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-dim"
        >
          {item.in_library ? "Start Reading" : "Add to Library"}
        </Link>
        <Link
          to={detailPath}
          className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-muted hover:text-text"
        >
          View Details
        </Link>
        {onNotInterested ? (
          <button
            type="button"
            disabled={submittingFeedback}
            aria-label={`Not interested in ${book.title}`}
            title="This recommendation may not match what you want right now."
            onClick={async () => {
              setSubmittingFeedback(true);
              setFeedbackError("");
              try {
                await onNotInterested(item);
              } catch (err) {
                setFeedbackError(err instanceof Error ? err.message : "Could not update recommendations.");
                setSubmittingFeedback(false);
              }
            }}
            className="rounded-lg px-3 py-1.5 text-sm text-text-dim hover:bg-bg-elevated hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submittingFeedback ? "Adjusting..." : "Not interested"}
          </button>
        ) : null}
      </div>
      {feedbackError ? (
        <p className="text-sm text-danger" role="alert">{feedbackError}</p>
      ) : null}
      </div>
    </Card>
  );
}
