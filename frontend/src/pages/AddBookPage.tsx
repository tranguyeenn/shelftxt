import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { fetchJson } from "@/lib/api";

type BookSearchResult = {
  title: string;
  authors: string[];
  isbn_uid: string | null;
  description: string | null;
  cover_url: string | null;
  total_pages: number | null;
  subjects: string[];
  genres: string[];
  first_publish_year: number | null;
  metadata_source: string;
  work_key: string | null;
  edition_key: string | null;
  publisher: string | null;
  publish_date: string | null;
  related_isbns: string[];
  already_in_library: boolean;
  confidence_score: number;
  canonical_title: string | null;
  canonical_author: string | null;
  edition_count: number;
  editions_loaded: boolean;
  edition_type: "original" | "translation" | "illustrated" | "adaptation" | "unknown";
  primary_edition: BookSearchResult | null;
  editions: BookSearchResult[];
};

type BookSearchResponse = {
  status: "ok" | "empty" | "degraded";
  results: BookSearchResult[];
  message: string | null;
};

type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";

type WorkEditionsResponse = {
  status: "ok" | "empty";
  work_id: string;
  edition_count: number;
  editions_loaded: boolean;
  primary_edition: BookSearchResult | null;
  editions: BookSearchResult[];
  message: string | null;
};

type ManualMetadataResponse = {
  metadata: BookSearchResult;
  duplicates: Array<{ id: string; title: string; author: string; reason: string }>;
};

const fieldClass =
  "rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2";

function editionTypeLabel(type: BookSearchResult["edition_type"]): string {
  const labels: Record<BookSearchResult["edition_type"], string> = {
    original: "Original",
    translation: "Translation",
    illustrated: "Illustrated",
    adaptation: "Adaptation",
    unknown: "Edition"
  };
  return labels[type];
}

export function AddBookPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<BookSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [extendedSearching, setExtendedSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<BookSearchResult | null>(null);
  const [selectedWork, setSelectedWork] = useState<BookSearchResult | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [totalPages, setTotalPages] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState<ReadingStatus>("not_started");
  const [rating, setRating] = useState("");
  const [isbn10, setIsbn10] = useState("");
  const [isbn13, setIsbn13] = useState("");
  const [publisher, setPublisher] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [publicationYear, setPublicationYear] = useState("");
  const [language, setLanguage] = useState("");
  const [editionType, setEditionType] = useState<BookSearchResult["edition_type"]>("unknown");
  const [originalTitle, setOriginalTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingEditions, setLoadingEditions] = useState(false);
  const [editionError, setEditionError] = useState("");
  const [manualDuplicates, setManualDuplicates] = useState<ManualMetadataResponse["duplicates"]>([]);
  const [confirmManualDuplicate, setConfirmManualDuplicate] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const searchAbortRef = useRef<AbortController | null>(null);
  const searchCacheRef = useRef<Map<string, BookSearchResponse>>(new Map());

  async function runSearch(cleanQuery: string) {
    if (cleanQuery.length < 3) {
      searchAbortRef.current?.abort();
      setResults([]);
      setSearched(false);
      setSearching(false);
      return;
    }
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;
    setSearching(true);
    setSearched(false);
    setError("");
    setMessage("");
    try {
      const cacheKey = cleanQuery.toLowerCase();
      const cached = searchCacheRef.current.get(cacheKey);
      if (cached) {
        setResults(Array.isArray(cached.results) ? cached.results : []);
        setSearching(false);
        setSearched(true);
        return;
      }

      const local = await fetchJson<BookSearchResponse>(
        `/books/search?q=${encodeURIComponent(cleanQuery)}&local_only=true`,
        { skipClientCache: true, signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      setResults(Array.isArray(local.results) ? local.results : []);
      setSearched(true);

      const data = await fetchJson<BookSearchResponse>(
        `/books/search?q=${encodeURIComponent(cleanQuery)}`,
        { skipClientCache: true, signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      searchCacheRef.current.set(cacheKey, data);
      setResults(Array.isArray(data.results) ? data.results : []);
      if (data.status === "degraded" && data.message && local.results.length === 0) {
        setError(data.message);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setResults([]);
      setError(err instanceof Error ? err.message : "Book search is unavailable.");
    } finally {
      if (!controller.signal.aborted) {
        setSearching(false);
        setSearched(true);
      }
    }
  }

  useEffect(() => {
    const cleanQuery = query.trim();
    if (cleanQuery.length < 3) return;
    const timeout = window.setTimeout(() => {
      void runSearch(cleanQuery);
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [query]);

  async function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    await runSearch(cleanQuery);
  }

  async function onExtendedSearch() {
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    setExtendedSearching(true);
    setError("");
    setMessage("");
    try {
      const data = await fetchJson<BookSearchResponse>(
        `/books/search/extended?q=${encodeURIComponent(cleanQuery)}`,
        { skipClientCache: true }
      );
      setResults(Array.isArray(data.results) ? data.results : []);
      if (data.status === "degraded" && data.message) {
        setError(data.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extended metadata discovery is unavailable.");
    } finally {
      setExtendedSearching(false);
      setSearched(true);
    }
  }

  function openManualForm() {
    setSelected(null);
    setSelectedWork(null);
    setTitle("");
    setAuthor("");
    setTotalPages("");
    setStartDate("");
    setEndDate("");
    setStatus("not_started");
    setRating("");
    setIsbn10("");
    setIsbn13("");
    setPublisher("");
    setPublicationDate("");
    setPublicationYear("");
    setLanguage("");
    setEditionType("unknown");
    setOriginalTitle("");
    setNotes("");
    setError("");
    setMessage("");
    setManualDuplicates([]);
    setConfirmManualDuplicate(false);
    setShowForm(true);
  }

  async function chooseBook(work: BookSearchResult) {
    setLoadingEditions(false);
    setEditionError("");
    setSelectedWork(work);
    setSelected(work.primary_edition ?? work);
    setTitle((work.primary_edition ?? work).title);
    setAuthor((work.primary_edition ?? work).authors.join(", ") || work.canonical_author || "");
    setTotalPages((work.primary_edition ?? work).total_pages ? String((work.primary_edition ?? work).total_pages) : "");
    setShowForm(true);
    let selectedWorkDetails = work;
    if (work.work_key && !work.editions_loaded) {
      setLoadingEditions(true);
      try {
        const workId = work.work_key.replace("/works/", "");
        const params = new URLSearchParams({
          q: query,
          title: work.canonical_title ?? work.title,
          author: work.canonical_author ?? work.authors[0] ?? "",
          limit: "20"
        });
        const response = await fetchJson<WorkEditionsResponse>(
          `/books/works/${encodeURIComponent(workId)}/editions?${params.toString()}`,
          { skipClientCache: true }
        );
        selectedWorkDetails = {
          ...work,
          edition_count: response.edition_count,
          editions_loaded: response.editions_loaded,
          primary_edition: response.primary_edition,
          editions: response.editions
        };
      } catch (err) {
        setEditionError(err instanceof Error ? err.message : "Could not load editions.");
      } finally {
        setLoadingEditions(false);
      }
    }
    const edition = selectedWorkDetails.primary_edition ?? selectedWorkDetails;
    setSelectedWork(selectedWorkDetails);
    setSelected(edition);
    setTitle(edition.title);
    setAuthor(edition.authors.join(", ") || selectedWorkDetails.canonical_author || "");
    setTotalPages(edition.total_pages ? String(edition.total_pages) : "");
    setIsbn13(edition.isbn_uid && edition.isbn_uid.length === 13 ? edition.isbn_uid : "");
    setIsbn10(edition.isbn_uid && edition.isbn_uid.length === 10 ? edition.isbn_uid : "");
    setPublisher(edition.publisher ?? "");
    setPublicationDate(edition.publish_date ?? "");
    setPublicationYear(edition.first_publish_year ? String(edition.first_publish_year) : "");
    setLanguage("");
    setEditionType(edition.edition_type);
    setOriginalTitle("");
    setNotes("");
    setStartDate("");
    setEndDate("");
    setStatus("not_started");
    setRating("");
    setError("");
    setMessage("");
    setManualDuplicates([]);
    setConfirmManualDuplicate(false);
    setShowForm(true);
  }

  function chooseEdition(index: number) {
    if (!selectedWork) return;
    const edition = selectedWork.editions[index] ?? selectedWork.primary_edition ?? selectedWork;
    setSelected(edition);
    setTitle(edition.title);
    setAuthor(edition.authors.join(", "));
    setTotalPages(edition.total_pages ? String(edition.total_pages) : "");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTitle = title.trim();
    const cleanAuthor = author.trim();
    if (!cleanTitle || !cleanAuthor) {
      setError("Title and author are required.");
      return;
    }

    const pagesNum = totalPages.trim() ? Number(totalPages) : null;
    if (pagesNum !== null && (!Number.isFinite(pagesNum) || pagesNum < 1)) {
      setError("Total pages must be a positive number.");
      return;
    }
    if (startDate && endDate && startDate > endDate) {
      setError("Start date cannot be after end date.");
      return;
    }
    const ratingNum = rating ? Number(rating) : null;
    if (status === "completed" && ratingNum !== null && (ratingNum < 0 || ratingNum > 5)) {
      setError("Rating must be between 0 and 5.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");
    try {
      let manualMetadata: BookSearchResult | null = null;
      if (!selected && !confirmManualDuplicate) {
        const normalized = await fetchJson<ManualMetadataResponse>("/books/metadata/manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: cleanTitle,
            authors: cleanAuthor.split(/[,;|]/).map((item) => item.trim()).filter(Boolean),
            isbn_10: isbn10.trim() || null,
            isbn_13: isbn13.trim() || null,
            cover_url: null,
            publisher: publisher.trim() || null,
            publication_date: publicationDate.trim() || null,
            publication_year: publicationYear.trim() ? Number(publicationYear) : null,
            page_count: pagesNum === null ? null : Math.round(pagesNum),
            language: language.trim() || null,
            edition_type: editionType,
            original_title: originalTitle.trim() || null,
            notes: notes.trim() || null
          })
        });
        manualMetadata = normalized.metadata;
        if (normalized.duplicates.length > 0) {
          setManualDuplicates(normalized.duplicates);
          setError("This looks similar to a book already in your library. Confirm if you still want to add it.");
          return;
        }
      }
      await fetchJson<{ message: string }>("/books", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: cleanTitle,
          author: cleanAuthor,
          isbn_uid: selected?.isbn_uid ?? manualMetadata?.isbn_uid ?? (isbn13.trim() || isbn10.trim() || null),
          total_pages: pagesNum === null ? null : Math.round(pagesNum),
          start_date: startDate || null,
          end_date: endDate || null,
          status,
          star_rating: status === "completed" ? ratingNum : null,
          description: selected?.description ?? null,
          cover_url: selected?.cover_url ?? null,
          subjects: selected?.subjects ?? [],
          genres: selected?.genres ?? [],
          first_publish_year: publicationYear.trim() ? Number(publicationYear) : selected?.first_publish_year ?? null,
          metadata_source: selected?.metadata_source ?? manualMetadata?.metadata_source ?? (selected ? null : "manual"),
          work_key: selected?.work_key ?? null,
          edition_key: selected?.edition_key ?? null,
          related_isbns: selected?.related_isbns ?? [],
          publisher: publisher.trim() || null,
          publish_date: publicationDate.trim() || null,
          language: language.trim() || null,
          edition_type: editionType,
          original_title: originalTitle.trim() || null,
          notes: notes.trim() || null
        })
      });
      setMessage("Book added to your library.");
      setManualDuplicates([]);
      setConfirmManualDuplicate(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add book");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader title="Add Book" subtitle="Find a book, review the details, and add it to your shelf." />

      {!showForm ? (
        <>
          <div className="mx-auto grid w-full max-w-4xl gap-3">
            <form onSubmit={onSearch} className="relative">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-16 w-full rounded-2xl border border-white/10 bg-surface px-5 pr-16 text-lg text-text shadow-card outline-none placeholder:text-text-dim focus:border-accent/50 focus:ring-2 focus:ring-accent/20"
                placeholder="Search books"
                aria-label="Search books"
                autoFocus
              />
              <button
                type="submit"
                disabled={searching || !query.trim()}
                aria-label="Search"
                className="absolute right-2.5 top-2.5 grid h-11 w-11 cursor-pointer place-items-center rounded-xl bg-accent text-on-accent transition-colors hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current" strokeWidth="2">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m16.5 16.5 4 4" strokeLinecap="round" />
                </svg>
              </button>
            </form>
            <div className="flex items-center justify-between gap-3 px-1 text-sm text-text-dim">
              <span>Search by title, author, ISBN, genre, or subject.</span>
              <button type="button" onClick={openManualForm} className="cursor-pointer text-text-muted underline decoration-border underline-offset-4 hover:text-text">
                Add manually
              </button>
            </div>
          </div>

          {error ? <p className="mx-auto w-full max-w-4xl rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">{error}</p> : null}
          {searching ? <p className="text-center text-sm text-text-muted">Searching across book catalogs…</p> : null}
          {searched ? (
            <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-center gap-2">
              <Button variant="secondary" onClick={() => void onExtendedSearch()} disabled={extendedSearching || !query.trim()}>
                {extendedSearching ? "Searching more sources..." : "Search more sources"}
              </Button>
              <Button variant="ghost" onClick={openManualForm}>
                Add manually
              </Button>
            </div>
          ) : null}
          {!searching && searched && results.length === 0 && !error ? (
            <Card className="mx-auto w-full max-w-4xl text-center text-text-muted">
              No books found. Try another search or add the book manually.
            </Card>
          ) : null}

          {results.length > 0 ? (
            <div className="mx-auto grid w-full max-w-4xl gap-3" aria-live="polite">
              {results.map((book, index) => (
                <Card key={`${book.isbn_uid ?? book.title}-${index}`} className="grid grid-cols-[72px_minmax(0,1fr)] gap-4 sm:grid-cols-[88px_minmax(0,1fr)_auto]">
                  <div className="h-28 w-[72px] overflow-hidden rounded-lg bg-bg-elevated sm:h-32 sm:w-[88px]">
                    {book.cover_url ? (
                      <img src={book.cover_url} alt={`Cover of ${book.title}`} className="h-full w-full object-cover" loading="lazy" />
                    ) : (
                      <div className="grid h-full place-items-center px-2 text-center font-serif text-xs text-text-dim">No cover</div>
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <h2 className="font-serif text-xl leading-tight text-text">{book.canonical_title ?? book.title}</h2>
                      <span className="rounded-full border border-border bg-bg-elevated px-2 py-0.5 text-[11px] font-medium text-text-muted">
                        {editionTypeLabel((book.primary_edition ?? book).edition_type)}
                      </span>
                    </div>
                    <p className="text-sm text-text-muted">{book.canonical_author ?? (book.authors.join(", ") || "Unknown author")}</p>
                    <p className="mt-1 text-xs text-text-dim">
                      {[
                        book.editions_loaded ? `${book.edition_count} edition${book.edition_count === 1 ? "" : "s"}` : "Editions not loaded",
                        book.first_publish_year,
                        book.total_pages ? `${book.total_pages} pages` : null
                      ].filter(Boolean).join(" · ") || "Edition details unavailable"}
                    </p>
                    {book.description ? <p className="mt-3 line-clamp-2 text-sm leading-6 text-text-muted">{book.description}</p> : null}
                  </div>
                  <div className="col-span-2 flex items-center sm:col-span-1 sm:pl-3">
                    {book.already_in_library ? (
                      <span className="rounded-xl border border-border bg-bg-elevated px-3 py-2 text-sm text-text-dim">Already in library</span>
                    ) : (
                      <Button variant="primary" onClick={() => void chooseBook(book)}>
                        {book.editions_loaded ? "Add book" : "View editions"}
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <Card className="mx-auto w-full max-w-2xl">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="font-serif text-2xl text-text">{selected ? "Review book details" : "Add manually"}</h2>
              <p className="mt-1 text-sm text-text-muted">You can edit these details before saving.</p>
            </div>
            <Button variant="ghost" onClick={() => { setShowForm(false); setError(""); setMessage(""); }}>Back to search</Button>
          </div>
          {selectedWork && selectedWork.editions.length > 1 ? (
            <label className="mb-4 grid gap-1 text-sm text-text-muted">
              Edition
              <select
                className={fieldClass}
                value={Math.max(0, selectedWork.editions.findIndex((edition) => edition === selected))}
                onChange={(event) => chooseEdition(Number(event.target.value))}
              >
                {selectedWork.editions.map((edition, index) => (
                  <option key={`${edition.isbn_uid ?? edition.title}-${index}`} value={index}>
                    {[edition.title, edition.authors.join(", "), edition.isbn_uid, editionTypeLabel(edition.edition_type)].filter(Boolean).join(" · ")}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {loadingEditions ? (
            <p className="mb-4 rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-text-muted" role="status">
              Loading editions...
            </p>
          ) : null}
          {editionError ? (
            <div className="mb-4 rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger" role="alert">
              <p>{editionError}</p>
              <Button variant="ghost" className="mt-2 px-2 py-1 text-xs" onClick={() => selectedWork && void chooseBook(selectedWork)}>
                Retry edition lookup
              </Button>
            </div>
          ) : null}
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm sm:col-span-2"><span className="text-text-muted">Title</span><input className={fieldClass} value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
              <label className="grid gap-1.5 text-sm sm:col-span-2"><span className="text-text-muted">Author</span><input className={fieldClass} value={author} onChange={(e) => setAuthor(e.target.value)} required /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Start date</span><input type="date" className={fieldClass} value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">End date</span><input type="date" className={fieldClass} value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Total pages</span><input type="number" min={1} className={fieldClass} value={totalPages} onChange={(e) => setTotalPages(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Status</span><select className={fieldClass} value={status} onChange={(e) => setStatus(e.target.value as ReadingStatus)}><option value="not_started">Want to read</option><option value="reading">Currently reading</option><option value="completed">Completed</option><option value="dnf">Did not finish</option></select></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">ISBN-13</span><input className={fieldClass} value={isbn13} onChange={(e) => setIsbn13(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">ISBN-10</span><input className={fieldClass} value={isbn10} onChange={(e) => setIsbn10(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Publisher</span><input className={fieldClass} value={publisher} onChange={(e) => setPublisher(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Publication date</span><input className={fieldClass} value={publicationDate} onChange={(e) => setPublicationDate(e.target.value)} placeholder="YYYY or YYYY-MM-DD" /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Publication year</span><input type="number" min={1} className={fieldClass} value={publicationYear} onChange={(e) => setPublicationYear(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Language</span><input className={fieldClass} value={language} onChange={(e) => setLanguage(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Edition type</span><select className={fieldClass} value={editionType} onChange={(e) => setEditionType(e.target.value as BookSearchResult["edition_type"])}><option value="unknown">Unknown</option><option value="original">Original</option><option value="translation">Translation</option><option value="illustrated">Illustrated</option><option value="adaptation">Adaptation</option></select></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Original title</span><input className={fieldClass} value={originalTitle} onChange={(e) => setOriginalTitle(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm sm:col-span-2"><span className="text-text-muted">Notes</span><textarea className={fieldClass} value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} /></label>
              {status === "completed" ? <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Rating (optional)</span><input type="number" min={0} max={5} step={0.25} className={fieldClass} value={rating} onChange={(e) => setRating(e.target.value)} placeholder="4.5" /></label> : null}
            </div>

            {error ? <p className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">{error}</p> : null}
            {manualDuplicates.length > 0 ? (
              <div className="rounded-lg border border-warning/30 bg-warning-muted px-3 py-2 text-sm text-text">
                <p className="font-medium">Possible duplicate</p>
                <ul className="mt-2 grid gap-1 text-text-muted">
                  {manualDuplicates.map((duplicate) => (
                    <li key={`${duplicate.id}-${duplicate.reason}`}>{duplicate.title} by {duplicate.author} ({duplicate.reason})</li>
                  ))}
                </ul>
                <label className="mt-3 flex items-center gap-2 text-sm text-text-muted">
                  <input type="checkbox" checked={confirmManualDuplicate} onChange={(event) => setConfirmManualDuplicate(event.target.checked)} />
                  Add this as a distinct edition anyway
                </label>
              </div>
            ) : null}
            {message ? <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent-readable">{message}</p> : null}

            <div className="flex flex-wrap gap-2 pt-1">
              <Button variant="primary" type="submit" disabled={loading || Boolean(message)}>{loading ? "Adding…" : message ? "Added" : "Add book"}</Button>
              <Button variant="ghost" type="button" onClick={() => navigate("/app/library")}>Go to library</Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
