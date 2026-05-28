import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { patchBookProgress, statusLabel, validatePagesRead } from "@/lib/bookProgress";
import type { ApiBook, ReadingStatus } from "@/lib/types";

type BookProgressEditorProps = {
  book: ApiBook;
  onUpdated: (book: ApiBook) => void;
  compact?: boolean;
};

export function BookProgressEditor({ book, onUpdated, compact = false }: BookProgressEditorProps) {
  const [status, setStatus] = useState<ReadingStatus>(book.status);
  const [pagesRead, setPagesRead] = useState(String(book.pages_read));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setStatus(book.status);
    setPagesRead(String(book.pages_read));
    setError("");
  }, [book.id, book.status, book.pages_read]);

  const totalPages = book.total_pages;
  const parsedPages = Number.parseInt(pagesRead, 10);
  const pagesValue = Number.isFinite(parsedPages) ? parsedPages : 0;

  const validation = validatePagesRead(pagesValue, totalPages, status);

  async function handleSave() {
    if (!validation.valid) {
      setError(validation.message ?? "Invalid progress");
      return;
    }

    let payloadPages = pagesValue;
    if (status === "completed" && totalPages !== null && totalPages > 0) {
      payloadPages = totalPages;
    }

    setSaving(true);
    setError("");
    try {
      const updated = await patchBookProgress(book.id, {
        status,
        pages_read: payloadPages
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
    if (next === "completed" && totalPages !== null && totalPages > 0) {
      setPagesRead(String(totalPages));
    }
    if (next === "not_started") {
      setPagesRead("0");
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
            className="rounded-lg border border-border bg-surface px-3 py-2 text-text"
          >
            <option value="not_started">{statusLabel("not_started")}</option>
            <option value="reading">{statusLabel("reading")}</option>
            <option value="completed">{statusLabel("completed")}</option>
          </select>
        </label>

        <label className="grid gap-1.5 text-sm">
          <span className="text-text-dim">Pages read</span>
          <input
            type="number"
            min={0}
            max={totalPages ?? undefined}
            value={pagesRead}
            onChange={(e) => setPagesRead(e.target.value)}
            disabled={status === "not_started"}
            className="rounded-lg border border-border bg-surface px-3 py-2 font-mono text-text disabled:opacity-50"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-text-muted">
        <span>
          Progress:{" "}
          <span className="font-mono text-text">{book.progress_pct.toFixed(0)}%</span>
          {totalPages !== null ? (
            <>
              {" "}
              · {book.pages_read} / {totalPages} pages
            </>
          ) : (
            " · Set total pages to track progress"
          )}
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
