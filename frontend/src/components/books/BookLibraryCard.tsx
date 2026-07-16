import { Link } from "react-router-dom";
import { useState } from "react";

import { BookEditModal } from "@/components/books/BookEditModal";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { BookCover } from "@/components/ui/BookCover";
import { Button } from "@/components/ui/Button";
import { StarRatingDisplay } from "@/components/ui/StarRatingDisplay";
import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { pagesLabel, readingProgressLabel, statusLabel } from "@/lib/bookProgress";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { formatDisplayDate } from "@/lib/books";
import { recommendationMatchLabel } from "@/lib/recommendationDisplay";
import type { ApiBook } from "@/lib/types";

type BookLibraryCardProps = {
  book: ApiBook;
  onUpdated: (book: ApiBook) => void;
  onDeleted?: (bookId: string) => void;
  recommendationScore?: number;
};

export function BookLibraryCard({ book, onUpdated, onDeleted, recommendationScore }: BookLibraryCardProps) {
  const [editing, setEditing] = useState(false);
  const [editingProgress, setEditingProgress] = useState(false);
  const statusClass = {
    reading: "border-[#C77D92]/25 bg-[#C77D92]/12 text-[#D88FA4]",
    completed: "border-[#6FAE81]/25 bg-[#6FAE81]/12 text-[#87C397]",
    not_started: "border-white/[0.08] bg-white/[0.04] text-[#A9A39A]",
    dnf: "border-[#C96A6A]/25 bg-[#C96A6A]/10 text-[#D47C7C]"
  }[book.status];

  return (
    <article className="group relative grid min-h-[280px] grid-cols-[104px_minmax(0,1fr)] gap-4 rounded-[20px] border border-white/[0.08] bg-[#171719] p-5 shadow-[0_10px_40px_rgba(0,0,0,0.35)] transition-colors hover:border-white/[0.14]">
      {recommendationScore !== undefined ? (
        <span className="absolute right-4 top-4 rounded-full border border-[#C77D92]/25 bg-[#C77D92]/12 px-2.5 py-1 text-[11px] font-medium text-[#D88FA4]">
          {recommendationMatchLabel(recommendationScore)}
        </span>
      ) : null}
      <BookCover
        title={book.title}
        coverUrl={book.cover_url}
        className="w-[104px] self-start rounded-xl"
      />
      <div className="flex min-w-0 flex-col">
        <div className="min-w-0">
          <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusClass}`}>
            {statusLabel(book.status)}
          </span>
          <h3 className="mt-3 line-clamp-2 font-['Cormorant_Garamond',Georgia,serif] text-[22px] font-semibold leading-[1.05] text-[#F5F1EA]">
            <Link
              to={`/app/book/${encodeURIComponent(book.id)}`}
              className="transition-colors hover:text-[#D88FA4]"
            >
              {book.title}
            </Link>
          </h3>
          <p className="mt-1.5 line-clamp-1 text-[15px] text-[#A9A39A]">{book.author}</p>
        </div>

        <div className="mt-auto grid gap-3 pt-4">
          <div>
            <div className="mb-2 flex items-center justify-between gap-2 text-[11px] uppercase tracking-[0.08em] text-[#7B756D]">
              <span>Progress</span>
              <span className="text-right normal-case tracking-normal text-[#A9A39A]">{readingProgressLabel(book)}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className={`h-full rounded-full ${book.status === "completed" ? "bg-[#6FAE81]" : "bg-[#C77D92]"}`}
                style={{ width: `${Math.min(100, Math.max(0, book.progress_pct))}%` }}
              />
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
            <Metadata label="Pages" value={book.tracking_mode === "pages" ? pagesLabel(book) : book.total_pages ? `${book.total_pages} total` : "—"} />
            <Metadata label="Started" value={formatDisplayDate(book.start_date)} />
            <Metadata label="Finished" value={formatDisplayDate(book.end_date)} />
            <div className="min-w-0">
              <dt className="text-[11px] uppercase tracking-[0.08em] text-[#7B756D]">Rating</dt>
              <dd className="mt-1 min-w-0 text-[12px] text-[#A9A39A]">
                <StarRatingDisplay value={book.rating ?? null} size="sm" showValue />
              </dd>
            </div>
          </dl>
        </div>

        {!isReadOnlyDemo ? (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.08] pt-3">
            <Button
              variant="ghost"
              onClick={() => setEditing(true)}
              className="rounded-xl px-3 py-1.5 text-xs text-[#A9A39A] hover:bg-white/[0.05] hover:text-[#F5F1EA]"
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              onClick={() => setEditingProgress(true)}
              className="rounded-xl px-3 py-1.5 text-xs text-[#A9A39A] hover:bg-white/[0.05] hover:text-[#F5F1EA]"
            >
              Progress
            </Button>
            <BookDeleteButton
              bookId={book.id}
              bookTitle={book.title}
              onDeleted={() => onDeleted?.(book.id)}
              compact
            />
          </div>
        ) : null}
      {editing ? (
        <BookEditModal
          book={book}
          onClose={() => setEditing(false)}
          onUpdated={onUpdated}
        />
      ) : null}
      {editingProgress ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <div
            className="w-full max-w-2xl rounded-[20px] border border-white/[0.08] bg-[#121214] p-5 shadow-[0_10px_40px_rgba(0,0,0,0.35)]"
            role="dialog"
            aria-modal="true"
            aria-label={`Update progress for ${book.title}`}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#C77D92]">
                  Reading progress
                </p>
                <h2 className="mt-1 font-['Cormorant_Garamond',Georgia,serif] text-2xl font-semibold text-[#F5F1EA]">
                  {book.title}
                </h2>
              </div>
              <Button variant="ghost" onClick={() => setEditingProgress(false)}>
                Close
              </Button>
            </div>
            <BookProgressEditor book={book} onUpdated={onUpdated} />
          </div>
        </div>
      ) : null}
      </div>
    </article>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-[0.08em] text-[#7B756D]">{label}</dt>
      <dd className="mt-1 truncate text-[#A9A39A]">{value}</dd>
    </div>
  );
}
