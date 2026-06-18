import { useCallback, useEffect, useMemo, useState } from "react";

import { BookLibraryCard } from "@/components/books/BookLibraryCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { fetchAllLibraryBooks, recordToApiBook } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
import type { ApiBook, ReadingStatus } from "@/lib/types";

type StatusFilter = "all" | ReadingStatus;

export function LibraryPage() {
  const [books, setBooks] = useState<ApiBook[]>([]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await fetchAllLibraryBooks();
      const mapped = rows.map(recordToApiBook);
      setBooks(mapped);
    } catch (err) {
      setBooks([]);
      setError(err instanceof Error ? err.message : "Failed to load library");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return books.filter((book) => {
      const matchesFilter = filter === "all" ? true : book.status === filter;
      const matchesSearch =
        !query ||
        book.title.toLowerCase().includes(query) ||
        book.author.toLowerCase().includes(query);
      return matchesFilter && matchesSearch;
    });
  }, [books, filter, search]);

  function handleBookUpdated(updated: ApiBook) {
    setBooks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  }

  function handleBookDeleted(bookId: string) {
    setBooks((prev) => prev.filter((b) => b.id !== bookId));
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Library"
        subtitle={
          isReadOnlyDemo
            ? "Browse books and reading progress (read-only demo)."
            : "Search, filter, and update reading status for every book."
        }
        actions={
          <Button variant="secondary" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <div className="grid gap-3">
        <label className="sr-only" htmlFor="library-search">
          Search library
        </label>
        <input
          id="library-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="search by title or author"
          className="w-full rounded-lg border border-border bg-bg-elevated px-4 py-2 text-sm text-text placeholder:text-text-dim focus:border-accent focus:outline-none"
        />
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border-subtle pb-2">
        {(
          [
            ["all", "all"],
            ["reading", "currently reading"],
            ["not_started", "want to read"],
            ["completed", "completed"],
            ["dnf", "dnf"]
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={[
              "cursor-pointer rounded-lg px-3 py-1.5 text-sm transition-colors",
              filter === value
                ? "bg-accent-muted text-accent"
                : "text-text-muted hover:bg-surface-hover hover:text-text"
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? <p className="text-sm text-text-muted">Loading library…</p> : null}

      {!loading && !error && filtered.length === 0 ? (
        <EmptyState
          title="No books in this view"
          description="Add books or change the filter to see your shelf."
        />
      ) : null}

      <div className="grid gap-3">
        {filtered.map((book) => (
          <BookLibraryCard
            key={book.id}
            book={book}
            onUpdated={handleBookUpdated}
            onDeleted={handleBookDeleted}
          />
        ))}
      </div>
    </div>
  );
}
