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
import { EmptyState } from "@/components/ui/EmptyState";
import { fetchAllLibraryBooks, parseDate, recordToApiBook } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery, type RecommendationFilters } from "@/lib/userSettings";
import type { ApiBook, ReadingStatus, RecommendationItem } from "@/lib/types";

type StatusFilter = "all" | ReadingStatus;
type SortOption = "title" | "author" | "rating" | "finished" | "progress";

const FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All Books" },
  { value: "reading", label: "Reading" },
  { value: "completed", label: "Completed" },
  { value: "not_started", label: "Plan To Read" },
  { value: "dnf", label: "DNF" }
];

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
  const [sort, setSort] = useState<SortOption>("title");
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
        book.title.toLowerCase().includes(query) ||
        book.author.toLowerCase().includes(query);
      return matchesFilter && matchesSearch;
    });
    return [...matching].sort((a, b) => {
      if (sort === "author") return a.author.localeCompare(b.author) || a.title.localeCompare(b.title);
      if (sort === "rating") return (b.rating ?? -1) - (a.rating ?? -1) || a.title.localeCompare(b.title);
      if (sort === "finished") {
        return (parseDate(b.end_date)?.getTime() ?? 0) - (parseDate(a.end_date)?.getTime() ?? 0);
      }
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

  return (
    <div className="grid min-h-[calc(100vh-5rem)] gap-8 bg-[#0B0B0D] font-['Inter',system-ui,sans-serif] text-[#F5F1EA] shadow-[0_0_0_100vmax_#0B0B0D] [clip-path:inset(0_-100vmax)] lg:gap-10">
      <header>
        <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-[#C77D92]">
          Your reading collection
        </p>
        <h1 className="font-['Cormorant_Garamond',Georgia,serif] text-5xl font-semibold leading-none tracking-[-0.025em] text-[#F5F1EA] sm:text-[56px]">
          My Library
        </h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-6 text-[#A9A39A]">
          {isReadOnlyDemo
            ? "Browse your books and reading progress in this read-only collection."
            : `${books.length} book${books.length === 1 ? "" : "s"} collected. Find your next chapter or revisit an old favorite.`}
        </p>
      </header>

      {error ? (
        <div
          className="rounded-[14px] border border-[#C96A6A]/30 bg-[#C96A6A]/10 px-4 py-3 text-sm text-[#C96A6A]"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[minmax(260px,1fr)_auto_auto_auto_auto]">
        <label className="relative block min-w-0">
          <span className="sr-only">Search library</span>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7B756D]"
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
            placeholder="Search by title or author"
            className="h-12 w-full rounded-[14px] border border-white/[0.08] bg-[#121214] pl-11 pr-4 text-sm text-[#F5F1EA] outline-none placeholder:text-[#7B756D] focus:border-[#C77D92]/70"
          />
        </label>

        <label className="relative">
          <span className="sr-only">Filter books</span>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as StatusFilter)}
            className="h-12 w-full cursor-pointer appearance-none rounded-[14px] border border-white/[0.08] bg-[#121214] px-4 pr-10 text-sm font-medium text-[#A9A39A] outline-none hover:border-white/15 focus:border-[#C77D92]/70 xl:w-auto"
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
            className="h-12 w-full cursor-pointer appearance-none rounded-[14px] border border-white/[0.08] bg-[#121214] px-4 pr-10 text-sm font-medium text-[#A9A39A] outline-none hover:border-white/15 focus:border-[#C77D92]/70 xl:w-auto"
          >
            <option value="title">Sort: Title</option>
            <option value="author">Sort: Author</option>
            <option value="rating">Sort: Rating</option>
            <option value="finished">Sort: Recently Finished</option>
            <option value="progress">Sort: Progress</option>
          </select>
          <Chevron />
        </label>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="h-12 cursor-pointer rounded-[14px] border border-white/[0.08] bg-[#121214] px-4 text-sm font-medium text-[#A9A39A] transition-colors hover:border-white/15 hover:text-[#F5F1EA] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>

        {!isReadOnlyDemo ? (
          <Link
            to="/app/add"
            className="inline-flex h-12 items-center justify-center gap-2 rounded-[14px] bg-[#C77D92] px-5 text-sm font-semibold text-[#0B0B0D] transition-colors hover:bg-[#D88FA4]"
          >
            <span className="text-lg leading-none">+</span>
            Add Book
          </Link>
        ) : null}
      </div>

      <form
        className="grid gap-3 rounded-[20px] border border-white/[0.08] bg-[#121214] p-4 sm:grid-cols-3 lg:grid-cols-[minmax(180px,1fr)_160px_160px_auto_auto]"
        onSubmit={applyFilters}
        noValidate
      >
        <label className="grid gap-1.5 text-sm">
          <span className="text-[#A9A39A]">Genre</span>
          <input
            type="text"
            value={genre}
            onChange={(event) => setGenre(event.target.value)}
            placeholder="e.g. romance"
            className="rounded-[14px] border border-white/[0.08] bg-[#121214] px-3 py-2 text-[#F5F1EA] outline-none placeholder:text-[#7B756D] focus:border-[#C77D92]/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-[#A9A39A]">Min pages</span>
          <input
            type="number"
            min="0"
            value={minPages}
            onChange={(event) => setMinPages(event.target.value)}
            placeholder="0"
            className="rounded-[14px] border border-white/[0.08] bg-[#121214] px-3 py-2 text-[#F5F1EA] outline-none placeholder:text-[#7B756D] focus:border-[#C77D92]/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-[#A9A39A]">Max pages</span>
          <input
            type="number"
            min="0"
            value={maxPages}
            onChange={(event) => setMaxPages(event.target.value)}
            placeholder="Any"
            className="rounded-[14px] border border-white/[0.08] bg-[#121214] px-3 py-2 text-[#F5F1EA] outline-none placeholder:text-[#7B756D] focus:border-[#C77D92]/70"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-[14px] bg-[#C77D92] px-4 py-2 text-sm font-semibold text-[#0B0B0D] transition-colors hover:bg-[#D88FA4] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Applying…" : "Apply filters"}
        </button>
        <button
          type="button"
          onClick={clearFilters}
          className="self-end rounded-[14px] border border-white/[0.08] bg-[#121214] px-4 py-2 text-sm font-medium text-[#A9A39A] transition-colors hover:border-white/15 hover:text-[#F5F1EA]"
        >
          Clear
        </button>
        {filterError ? (
          <p className="text-xs text-[#C96A6A] sm:col-span-3 lg:col-span-5" role="alert">
            {filterError}
          </p>
        ) : null}
      </form>

      <nav className="flex gap-7 overflow-x-auto border-b border-white/[0.08]" aria-label="Library filters">
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={[
              "relative shrink-0 cursor-pointer pb-3 text-[13px] font-medium transition-colors after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 after:rounded-full",
              filter === value
                ? "text-[#F5F1EA] after:bg-[#C77D92]"
                : "text-[#7B756D] after:bg-transparent hover:text-[#A9A39A]"
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </nav>

      {loading ? <p className="text-sm text-[#A9A39A]">Loading library…</p> : null}

      {!loading && !error && filtered.length === 0 ? (
        <EmptyState
          title="Nothing matches this shelf view."
          description="Try a different filter or add a book you already meant to read."
        />
      ) : null}

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
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
      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7B756D]"
      aria-hidden
    >
      <path d="m6 8 4 4 4-4" />
    </svg>
  );
}
