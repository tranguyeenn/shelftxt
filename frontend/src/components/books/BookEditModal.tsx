import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { StarRatingInput } from "@/components/ui/StarRatingInput";
import { patchBook } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { statusLabel } from "@/lib/bookProgress";
import type { ApiBook, ReadingStatus, TrackingMode } from "@/lib/types";

type BookEditModalProps = {
  book: ApiBook;
  onClose: () => void;
  onUpdated: (book: ApiBook) => void;
};

export function BookEditModal({ book, onClose, onUpdated }: BookEditModalProps) {
  const [title, setTitle] = useState(book.title);
  const [author, setAuthor] = useState(book.author);
  const [isbnUid, setIsbnUid] = useState(book.id);
  const [totalPages, setTotalPages] = useState(book.total_pages?.toString() ?? "");
  const [rating, setRating] = useState<number | null>(book.rating ?? null);
  const [status, setStatus] = useState<ReadingStatus>(book.status);
  const [trackingMode, setTrackingMode] = useState<TrackingMode>(book.tracking_mode);
  const [pagesRead, setPagesRead] = useState(book.pages_read.toString());
  const [progressPercent, setProgressPercent] = useState(String(Math.round(book.progress_pct)));
  const [startDate, setStartDate] = useState(book.start_date ?? "");
  const [endDate, setEndDate] = useState(book.end_date ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setTitle(book.title);
    setAuthor(book.author);
    setIsbnUid(book.id);
    setTotalPages(book.total_pages?.toString() ?? "");
    setRating(book.rating ?? null);
    setStatus(book.status);
    setTrackingMode(book.tracking_mode);
    setPagesRead(book.pages_read.toString());
    setProgressPercent(String(Math.round(book.progress_pct)));
    setStartDate(book.start_date ?? "");
    setEndDate(book.end_date ?? "");
    setError("");
  }, [book]);

  if (isReadOnlyDemo) {
    return null;
  }

  function handleStatusChange(next: ReadingStatus) {
    setStatus(next);
    const parsedTotal = parsePositiveInt(totalPages);

    if (next === "completed" && parsedTotal !== null) {
      setPagesRead(String(parsedTotal));
    }

    if (next === "completed") {
      setProgressPercent("100");
    }

    if (next === "not_started") {
      setPagesRead("0");
      setProgressPercent("0");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const cleanTitle = title.trim();
    const cleanAuthor = author.trim() || "Unknown";
    const cleanIsbn = isbnUid.trim();
    const parsedTotal = parsePositiveInt(totalPages);
    const parsedRating = rating;
    const parsedPages = parseNonNegativeInt(pagesRead);
    const parsedProgress = parseProgressPercent(progressPercent);

    if (!cleanTitle) {
      setError("Title is required.");
      return;
    }

    if (!cleanIsbn) {
      setError("ISBN/UID is required.");
      return;
    }

    if (totalPages.trim() && parsedTotal === null) {
      setError("Total pages must be positive or blank.");
      return;
    }

    if (parsedRating !== null && (parsedRating < 0 || parsedRating > 5)) {
      setError("Rating must be between 0 and 5.");
      return;
    }

    if (trackingMode === "pages" && parsedPages === null) {
      setError("Pages read cannot be negative.");
      return;
    }

    if (trackingMode === "percentage" && parsedProgress === null) {
      setError("Progress must be between 0 and 100%.");
      return;
    }

    const finalPagesRead =
      status === "completed" && parsedTotal !== null ? parsedTotal : parsedPages;
    const finalProgressPercent = status === "completed" ? 100 : parsedProgress;

    if (
      trackingMode === "pages" &&
      parsedTotal !== null &&
      finalPagesRead !== null &&
      finalPagesRead > parsedTotal
    ) {
      setError("Pages read cannot exceed total pages.");
      return;
    }

    if (startDate && endDate && startDate > endDate) {
      setError("Start date cannot be after end date.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const updated = await patchBook(book.id, {
        title: cleanTitle,
        author: cleanAuthor,
        isbn_uid: cleanIsbn,
        total_pages: parsedTotal,
        status,
        tracking_mode: trackingMode,
        ...(trackingMode === "pages"
          ? { pages_read: finalPagesRead ?? 0 }
          : { progress_percent: finalProgressPercent ?? 0 }),
        start_date: startDate || null,
        end_date: endDate || null,
        star_rating: parsedRating
      });

      onUpdated(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save book");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid items-start justify-items-center overflow-y-auto bg-black/60 p-2 sm:place-items-center sm:p-4">
      <div
        className="my-1 max-h-[calc(100dvh-1rem)] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-bg-elevated p-4 shadow-xl [-webkit-overflow-scrolling:touch] sm:my-0 sm:max-h-[calc(100dvh-2rem)] sm:p-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-book-title"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="edit-book-title" className="text-lg font-semibold text-text">
              Edit book
            </h2>
            <p className="mt-1 text-sm text-text-muted">{book.title}</p>
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close edit form">
            Close
          </Button>
        </div>

        <form className="grid gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Title" value={title} onChange={setTitle} required />
            <TextField label="Author" value={author} onChange={setAuthor} />
            <TextField label="ISBN/UID" value={isbnUid} onChange={setIsbnUid} required />

            <TextField
              label="Total pages"
              value={totalPages}
              onChange={setTotalPages}
              type="number"
              min={1}
            />

            <div className="grid min-w-0 gap-1.5 text-sm sm:col-span-2">
              <span className="text-text-muted">Rating</span>
              <StarRatingInput
                value={rating}
                onChange={setRating}
                ariaLabel={`Rating for ${book.title}`}
              />
            </div>

            <label className="grid gap-1.5 text-sm">
              <span className="text-text-muted">Status</span>
              <select
                value={status}
                onChange={(e) => handleStatusChange(e.target.value as ReadingStatus)}
                className="cursor-pointer rounded-lg border border-border bg-surface px-3 py-2 text-text"
              >
                <option value="not_started">{statusLabel("not_started")}</option>
                <option value="reading">{statusLabel("reading")}</option>
                <option value="completed">{statusLabel("completed")}</option>
                <option value="dnf">{statusLabel("dnf")}</option>
              </select>
            </label>

            <div className="grid gap-1.5 text-sm">
              <span className="text-text-muted">Progress mode</span>
              <div className="grid gap-1 rounded-lg border border-border bg-surface p-1 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setTrackingMode("percentage")}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    trackingMode === "percentage"
                      ? "bg-accent text-text"
                      : "text-text-muted hover:text-text"
                  }`}
                >
                  Track by percentage
                </button>
                <button
                  type="button"
                  onClick={() => setTrackingMode("pages")}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    trackingMode === "pages"
                      ? "bg-accent text-text"
                      : "text-text-muted hover:text-text"
                  }`}
                >
                  Track by pages
                </button>
              </div>
            </div>

            {trackingMode === "pages" ? (
              <TextField
                label="Pages read"
                value={pagesRead}
                onChange={setPagesRead}
                type="number"
                min={0}
              />
            ) : (
              <TextField
                label="Progress percent"
                value={progressPercent}
                onChange={setProgressPercent}
                type="number"
                min={0}
                max={100}
              />
            )}

            <TextField
              label="Start Date"
              value={startDate}
              onChange={setStartDate}
              type="date"
            />

            <TextField
              label="End Date"
              value={endDate}
              onChange={setEndDate}
              type="date"
            />
          </div>

          {error ? (
            <p
              className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  min,
  max,
  step,
  required = false
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  min?: number;
  max?: number;
  step?: number;
  required?: boolean;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="text-text-muted">{label}</span>
      <input
        type={type}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="rounded-lg border border-border bg-surface px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
      />
    </label>
  );
}

function parsePositiveInt(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.round(parsed);
}

function parseNonNegativeInt(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return Math.round(parsed);
}

function parseProgressPercent(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) return null;
  return parsed;
}
