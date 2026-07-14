import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent
} from "react";
import { Link } from "react-router-dom";

import { BookLibraryCard } from "@/components/books/BookLibraryCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { BookCover } from "@/components/ui/BookCover";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { fetchAllLibraryBooks, parseDate, recordToApiBook } from "@/lib/books";
import { readingProgressLabel, statusLabel } from "@/lib/bookProgress";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery, type RecommendationFilters } from "@/lib/userSettings";
import type { ApiBook, ReadingStatus, RecommendationItem } from "@/lib/types";

type StatusFilter = "all" | ReadingStatus;
type SortOption = "updated" | "added" | "title" | "author" | "rating" | "progress";
type DisplayMode = "grid" | "list";

const FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All Books" },
  { value: "reading", label: "Reading" },
  { value: "completed", label: "Completed" },
  { value: "not_started", label: "Plan To Read" },
  { value: "dnf", label: "DNF" }
];

const DISPLAY_MODE_KEY = "shelftxt.library.displayMode";

function loadDisplayMode(): DisplayMode {
  if (typeof window === "undefined") return "grid";
  return window.localStorage.getItem(DISPLAY_MODE_KEY) === "list" ? "list" : "grid";
}

function searchableText(book: ApiBook): string {
  return [
    book.title,
    book.author,
    book.id,
    ...(book.genres ?? []),
    ...(book.subjects ?? [])
  ].join(" ").toLowerCase();
}

function activityTime(book: ApiBook): number {
  return (
    parseDate(book.end_date)?.getTime() ??
    parseDate(book.start_date)?.getTime() ??
    0
  );
}

export function LibraryPage() {
  const {
    settings,
    recommendationFilters: appliedFilters,
    setRecommendationFilters: setAppliedFilters
  } = useUserSettings();
  const [books, setBooks] = useState<ApiBook[]>([]);
  const [recommendationScores, setRecommendationScores] = useState<Map<string, number>>(
    () => new Map()
  );
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOption>("updated");
  const [displayMode, setDisplayMode] = useState<DisplayMode>(() => loadDisplayMode());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [genre, setGenre] = useState(appliedFilters.genre ?? "");
  const [minPages, setMinPages] = useState(
    appliedFilters.min_pages === undefined ? "" : String(appliedFilters.min_pages)
  );
  const [maxPages, setMaxPages] = useState(
    appliedFilters.max_pages === undefined ? "" : String(appliedFilters.max_pages)
  );
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError("");
    setRecommendationScores(new Map());
    try {
      const [rows, ranked] = await Promise.all([
        fetchAllLibraryBooks(),
        fetchJson<RecommendationItem[]>(
          recommendQuery(settings, false, [], appliedFilters)
        )
      ]);
      if (requestId !== requestIdRef.current) return;

      const mapped = rows.map(recordToApiBook);
      const nextScores = new Map<string, number>();
      for (const recommendation of (Array.isArray(ranked) ? ranked : []).slice(0, 10)) {
        const id = (recommendation.recommended_book ?? recommendation.book).id;
        if (id && Number.isFinite(recommendation.score) && recommendation.score > 0) {
          nextScores.set(id, recommendation.score);
        }
      }
      setBooks(mapped);
      setRecommendationScores(nextScores);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;

      setBooks([]);
      setRecommendationScores(new Map());
      setError(err instanceof Error ? err.message : "Failed to load library");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [settings.recommendationStyle, appliedFilters]);

  useLayoutEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    const matching = books.filter((book) => {
      const matchesFilter = filter === "all" ? true : book.status === filter;
      const matchesSearch =
        !query ||
        searchableText(book).includes(query);
      return matchesFilter && matchesSearch;
    });
    return [...matching].sort((a, b) => {
      if (sort === "updated") return activityTime(b) - activityTime(a) || a.title.localeCompare(b.title);
      if (sort === "added") return b.id.localeCompare(a.id) || a.title.localeCompare(b.title);
      if (sort === "author") return a.author.localeCompare(b.author) || a.title.localeCompare(b.title);
      if (sort === "rating") return (b.rating ?? -1) - (a.rating ?? -1) || a.title.localeCompare(b.title);
      if (sort === "progress") return b.progress_pct - a.progress_pct || a.title.localeCompare(b.title);
      return a.title.localeCompare(b.title);
    });
  }, [books, filter, search, sort]);

  function handleBookUpdated(updated: ApiBook) {
    setBooks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  }

  function handleBookDeleted(bookId: string) {
    setBooks((prev) => prev.filter((b) => b.id !== bookId));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsedMin = minPages === "" ? undefined : Number(minPages);
    const parsedMax = maxPages === "" ? undefined : Number(maxPages);
    if (
      (parsedMin !== undefined && (!Number.isFinite(parsedMin) || parsedMin < 0)) ||
      (parsedMax !== undefined && (!Number.isFinite(parsedMax) || parsedMax < 0))
    ) {
      setFilterError("Page values must be nonnegative numbers.");
      return;
    }
    if (parsedMin !== undefined && parsedMax !== undefined && parsedMin > parsedMax) {
      setFilterError("Minimum pages cannot be greater than maximum pages.");
      return;
    }

    const filters: RecommendationFilters = {
      ...(genre.trim() ? { genre: genre.trim() } : {}),
      ...(parsedMin !== undefined ? { min_pages: parsedMin } : {}),
      ...(parsedMax !== undefined ? { max_pages: parsedMax } : {})
    };
    setFilterError("");
    requestIdRef.current += 1;
    setRecommendationScores(new Map());
    setAppliedFilters(filters);
  }

  function clearFilters() {
    setGenre("");
    setMinPages("");
    setMaxPages("");
    setFilterError("");
    requestIdRef.current += 1;
    setRecommendationScores(new Map());
    setAppliedFilters({});
  }

  function changeDisplayMode(next: DisplayMode) {
    setDisplayMode(next);
    window.localStorage.setItem(DISPLAY_MODE_KEY, next);
  }

  return (
    <div className="grid gap-7">
      <PageHeader
        eyebrow="Library"
        title="My Library"
        subtitle={
          isReadOnlyDemo
            ? "Browse your books and reading progress in this read-only collection."
            : `${books.length} book${books.length === 1 ? "" : "s"} collected.`
        }
        actions={!isReadOnlyDemo ? <Button variant="primary" onClick={() => window.location.assign("/app/add")}>Add Book</Button> : null}
      />

      {error ? (
        <div className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger" role="alert">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[minmax(260px,1fr)_auto_auto_auto_auto_auto]">
        <label className="relative block min-w-0">
          <span className="sr-only">Search library</span>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-dim"
            aria-hidden
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            id="library-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title, author, ISBN, genre"
            className="h-12 w-full rounded-lg border border-border bg-bg-elevated pl-11 pr-4 text-sm text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>

        <label className="relative">
          <span className="sr-only">Filter books</span>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as StatusFilter)}
            className="h-12 w-full cursor-pointer appearance-none rounded-lg border border-border bg-bg-elevated px-4 pr-10 text-sm font-medium text-text-muted outline-none hover:border-white/15 focus:border-accent/70 xl:w-auto"
          >
            {FILTERS.map((item) => (
              <option key={item.value} value={item.value}>Filter: {item.label}</option>
            ))}
          </select>
          <Chevron />
        </label>

        <label className="relative">
          <span className="sr-only">Sort books</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortOption)}
            className="h-12 w-full cursor-pointer appearance-none rounded-lg border border-border bg-bg-elevated px-4 pr-10 text-sm font-medium text-text-muted outline-none hover:border-white/15 focus:border-accent/70 xl:w-auto"
          >
            <option value="updated">Sort: Recently Updated</option>
            <option value="added">Sort: Recently Added</option>
            <option value="title">Sort: Title</option>
            <option value="author">Sort: Author</option>
            <option value="rating">Sort: Rating</option>
            <option value="progress">Sort: Progress</option>
          </select>
          <Chevron />
        </label>

        <div className="grid h-12 grid-cols-2 rounded-lg border border-border bg-bg-elevated p-1">
          <button
            type="button"
            onClick={() => changeDisplayMode("grid")}
            className={`rounded-md px-3 text-sm ${displayMode === "grid" ? "bg-accent text-on-accent" : "text-text-muted hover:text-text"}`}
          >
            Grid
          </button>
          <button
            type="button"
            onClick={() => changeDisplayMode("list")}
            className={`rounded-md px-3 text-sm ${displayMode === "list" ? "bg-accent text-on-accent" : "text-text-muted hover:text-text"}`}
          >
            List
          </button>
        </div>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="h-12 cursor-pointer rounded-lg border border-border bg-bg-elevated px-4 text-sm font-medium text-text-muted transition-colors hover:border-white/15 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>

        {!isReadOnlyDemo ? (
          <Link
            to="/app/add"
            className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-accent px-5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-dim"
          >
            <span className="text-lg leading-none">+</span>
            Add Book
          </Link>
        ) : null}
      </div>

      <form
        className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-3 lg:grid-cols-[minmax(180px,1fr)_160px_160px_auto_auto]"
        onSubmit={applyFilters}
        noValidate
      >
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Genre</span>
          <input
            type="text"
            value={genre}
            onChange={(event) => setGenre(event.target.value)}
            placeholder="e.g. romance"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Min pages</span>
          <input
            type="number"
            min="0"
            value={minPages}
            onChange={(event) => setMinPages(event.target.value)}
            placeholder="0"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Max pages</span>
          <input
            type="number"
            min="0"
            value={maxPages}
            onChange={(event) => setMaxPages(event.target.value)}
            placeholder="Any"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Applying…" : "Apply filters"}
        </button>
        <button
          type="button"
          onClick={clearFilters}
          className="self-end rounded-lg border border-border bg-bg-elevated px-4 py-2 text-sm font-medium text-text-muted transition-colors hover:border-white/15 hover:text-text"
        >
          Clear
        </button>
        {filterError ? (
          <p className="text-xs text-danger sm:col-span-3 lg:col-span-5" role="alert">
            {filterError}
          </p>
        ) : null}
      </form>

      <nav className="flex gap-7 overflow-x-auto border-b border-border-subtle" aria-label="Library filters">
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={[
              "relative shrink-0 cursor-pointer pb-3 text-[13px] font-medium transition-colors after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 after:rounded-full",
              filter === value
                ? "text-text after:bg-accent"
                : "text-text-dim after:bg-transparent hover:text-text-muted"
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </nav>

      {loading ? <p className="text-sm text-text-muted">Loading library...</p> : null}

      {!loading && !error && filtered.length === 0 ? (
        <EmptyState
          title="Nothing matches this shelf view."
          description="Try a different filter or add a book you already meant to read."
        />
      ) : null}

      {displayMode === "grid" ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((book) => (
            <BookLibraryCard
              key={book.id}
              book={book}
              onUpdated={handleBookUpdated}
              onDeleted={handleBookDeleted}
              recommendationScore={recommendationScores.get(book.id)}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((book) => (
            <LibraryListItem key={book.id} book={book} recommendationScore={recommendationScores.get(book.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function Chevron() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-dim"
      aria-hidden
    >
      <path d="m6 8 4 4 4-4" />
    </svg>
  );
}

function LibraryListItem({ book, recommendationScore }: { book: ApiBook; recommendationScore?: number }) {
  return (
    <Card className="grid gap-3 sm:grid-cols-[56px_minmax(0,1fr)_180px] sm:items-center">
      <BookCover title={book.title} coverUrl={book.cover_url} className="w-14 rounded-md" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link className="line-clamp-1 font-semibold text-text hover:text-accent" to={`/app/book/${encodeURIComponent(book.id)}`}>
            {book.title}
          </Link>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
            {statusLabel(book.status)}
          </span>
        </div>
        <p className="mt-1 truncate text-sm text-text-muted">{book.author}</p>
        <p className="mt-1 text-xs text-text-dim">
          {book.id ? `Edition ID: ${book.id}` : "Edition ID unavailable"}
          {book.first_publish_year ? ` · ${book.first_publish_year}` : ""}
        </p>
      </div>
      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-3 text-xs text-text-muted">
          <span>{readingProgressLabel(book)}</span>
          {recommendationScore !== undefined ? <span>{Math.round(recommendationScore * 100)}% match</span> : null}
        </div>
        <ProgressBar value={book.progress_pct} />
      </div>
    </Card>
  );
}
