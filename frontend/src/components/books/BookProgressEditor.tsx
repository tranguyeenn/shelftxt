import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  patchBookProgress,
  pagesLabel,
  progressLabel,
  statusLabel,
  validatePagesRead,
  validateProgressPercent,
  validateTotalPages
} from "@/lib/bookProgress";
import { isReadOnlyDemo } from "@/lib/demoMode";
import type { ApiBook, ReadingStatus, TrackingMode } from "@/lib/types";

type BookProgressEditorProps = {
  book: ApiBook;
  onUpdated: (book: ApiBook) => void;
  compact?: boolean;
};

export function BookProgressEditor({ book, onUpdated, compact = false }: BookProgressEditorProps) {
  const [status, setStatus] = useState<ReadingStatus>(book.status);
  const [trackingMode, setTrackingMode] = useState<TrackingMode>(book.tracking_mode);
  const [pagesRead, setPagesRead] = useState(String(book.pages_read));
  const [totalPagesInput, setTotalPagesInput] = useState(book.total_pages?.toString() ?? "");
  const [progressPercent, setProgressPercent] = useState(String(Math.round(book.progress_pct)));
  const [startDate, setStartDate] = useState(book.start_date ?? "");
  const [endDate, setEndDate] = useState(book.end_date ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setStatus(book.status);
    setTrackingMode(book.tracking_mode);
    setPagesRead(String(book.pages_read));
    setTotalPagesInput(book.total_pages?.toString() ?? "");
    setProgressPercent(String(Math.round(book.progress_pct)));
    setStartDate(book.start_date ?? "");
    setEndDate(book.end_date ?? "");
    setError("");
  }, [
    book.id,
    book.status,
    book.pages_read,
    book.progress_pct,
    book.total_pages,
    book.tracking_mode,
    book.start_date,
    book.end_date
  ]);

  const parsedPages = Number.parseInt(pagesRead, 10);
  const pagesValue = Number.isFinite(parsedPages) ? parsedPages : 0;
  const parsedTotalPages = parsePositiveInt(totalPagesInput);
  const parsedProgress = Number.parseFloat(progressPercent);
  const progressValue = Number.isFinite(parsedProgress) ? parsedProgress : 0;

  const totalPagesValidation = validateTotalPages(parsedTotalPages);
  const progressValidation =
    trackingMode === "pages"
      ? validatePagesRead(pagesValue, parsedTotalPages, status)
      : validateProgressPercent(progressValue);
  const dateValidation =
    startDate && endDate && startDate > endDate
      ? { valid: false, message: "Start date cannot be after finish date." }
      : { valid: true };
  const validation = firstInvalid(totalPagesValidation, progressValidation, dateValidation);

  if (isReadOnlyDemo) {
    return (
      <div className={compact ? "grid gap-2 text-sm text-text-muted" : "grid gap-2 rounded-lg border border-border-subtle bg-bg-elevated p-4 text-sm text-text-muted"}>
        <p>
          <span className="text-text-dim">Status:</span> {statusLabel(book.status)}
        </p>
        <p>
          Progress:{" "}
          <span className="font-mono text-text">{progressLabel(book)}</span>
          {" · "}
          <span className="font-mono text-text">{pagesLabel(book)}</span>
        </p>
      </div>
    );
  }

  async function handleSave() {
    if (!validation.valid) {
      setError(validation.message ?? "Invalid progress");
      return;
    }

    let payloadPages = pagesValue;
    let payloadProgress = progressValue;
    if (status === "completed") {
      payloadProgress = 100;
    }
    if (trackingMode === "pages" && status === "completed" && parsedTotalPages !== null && parsedTotalPages > 0) {
      payloadPages = parsedTotalPages;
    }

    setSaving(true);
    setError("");
    try {
      const updated = await patchBookProgress(book.id, {
        status,
        tracking_mode: trackingMode,
        ...(trackingMode === "pages"
          ? { pages_read: payloadPages, total_pages: parsedTotalPages }
          : { progress_percent: payloadProgress }),
        start_date: startDate || null,
        end_date: endDate || null
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleStatusChange(next: ReadingStatus) {
    setStatus(next);
    if (next === "completed" && parsedTotalPages !== null && parsedTotalPages > 0) {
      setPagesRead(String(parsedTotalPages));
    }
    if (next === "completed") {
      setProgressPercent("100");
    }
    if (next === "not_started") {
      setPagesRead("0");
      setProgressPercent("0");
    }
  }

  return (
    <div className={compact ? "grid gap-3" : "grid gap-4 rounded-lg border border-border-subtle bg-bg-elevated p-4"}>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Reading status</span>
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
          <span className="text-text-dim">Progress mode</span>
          <div className="grid gap-1 rounded-lg border border-border bg-surface p-1 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => setTrackingMode("percentage")}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                trackingMode === "percentage" ? "bg-accent text-bg" : "text-text-muted hover:text-text"
              }`}
            >
              Track by percentage
            </button>
            <button
              type="button"
              onClick={() => setTrackingMode("pages")}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                trackingMode === "pages" ? "bg-accent text-bg" : "text-text-muted hover:text-text"
              }`}
            >
              Track by pages
            </button>
          </div>
        </div>
      </div>

      {trackingMode === "pages" ? (
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Pages read / total pages</span>
          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
            <input
              type="number"
              min={0}
              max={parsedTotalPages ?? undefined}
              value={pagesRead}
              onChange={(e) => setPagesRead(e.target.value)}
              disabled={status === "not_started"}
              className="min-w-0 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-text disabled:opacity-50"
            />
            <span className="text-text-muted">/</span>
            <input
              type="number"
              min={1}
              value={totalPagesInput}
              onChange={(e) => setTotalPagesInput(e.target.value)}
              className="min-w-0 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-text"
              placeholder="total"
            />
          </div>
        </label>
      ) : (
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Progress percent</span>
          <input
            type="number"
            min={0}
            max={100}
            value={progressPercent}
            onChange={(e) => setProgressPercent(e.target.value)}
            disabled={status === "not_started"}
            className="rounded-lg border border-border bg-surface px-3 py-2 font-mono text-text disabled:opacity-50"
          />
        </label>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Start date</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="rounded-lg border border-border bg-surface px-3 py-2 text-text"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Finish date</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="rounded-lg border border-border bg-surface px-3 py-2 text-text"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-text-muted">
        <span>
          Progress:{" "}
          <span className="font-mono text-text">{progressLabel(book)}</span>
          {" · "}
          <span className="font-mono text-text">{pagesLabel(book)}</span>
        </span>
        <Button variant="secondary" onClick={() => void handleSave()} disabled={saving || !validation.valid}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>

      {!validation.valid && validation.message ? (
        <p className="text-sm text-danger" role="alert">
          {validation.message}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function parsePositiveInt(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return Number.NaN;
  return Math.round(parsed);
}

function firstInvalid(...validations: Array<{ valid: boolean; message?: string }>) {
  return validations.find((validation) => !validation.valid) ?? { valid: true };
}
