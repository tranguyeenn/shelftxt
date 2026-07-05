import { FormEvent, useState } from "react";
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
};

type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";

const fieldClass =
  "rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2";

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    open_library: "Open Library",
    google_books: "Google Books",
    librarything: "LibraryThing",
    local: "Local"
  };
  return labels[source] ?? source.replaceAll("_", " ");
}

export function AddBookPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<BookSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<BookSearchResult | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [totalPages, setTotalPages] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState<ReadingStatus>("not_started");
  const [rating, setRating] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    setSearching(true);
    setSearched(false);
    setError("");
    setMessage("");
    try {
      const data = await fetchJson<BookSearchResult[]>(
        `/books/search?q=${encodeURIComponent(cleanQuery)}`,
        { skipClientCache: true }
      );
      setResults(Array.isArray(data) ? data : []);
    } catch (err) {
      setResults([]);
      setError(err instanceof Error ? err.message : "Book search is unavailable.");
    } finally {
      setSearching(false);
      setSearched(true);
    }
  }

  function openManualForm() {
    setSelected(null);
    setTitle("");
    setAuthor("");
    setTotalPages("");
    setStartDate("");
    setEndDate("");
    setStatus("not_started");
    setRating("");
    setError("");
    setMessage("");
    setShowForm(true);
  }

  function chooseBook(book: BookSearchResult) {
    setSelected(book);
    setTitle(book.title);
    setAuthor(book.authors.join(", "));
    setTotalPages(book.total_pages ? String(book.total_pages) : "");
    setStartDate("");
    setEndDate("");
    setStatus("not_started");
    setRating("");
    setError("");
    setMessage("");
    setShowForm(true);
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
      await fetchJson<{ message: string }>("/books", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: cleanTitle,
          author: cleanAuthor,
          isbn_uid: selected?.isbn_uid ?? null,
          total_pages: pagesNum === null ? null : Math.round(pagesNum),
          start_date: startDate || null,
          end_date: endDate || null,
          status,
          star_rating: status === "completed" ? ratingNum : null,
          description: selected?.description ?? null,
          cover_url: selected?.cover_url ?? null,
          subjects: selected?.subjects ?? [],
          genres: selected?.genres ?? [],
          first_publish_year: selected?.first_publish_year ?? null,
          metadata_source: selected?.metadata_source ?? null,
          work_key: selected?.work_key ?? null,
          edition_key: selected?.edition_key ?? null,
          related_isbns: selected?.related_isbns ?? []
        })
      });
      setMessage("Book added to your library.");
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
                className="absolute right-2.5 top-2.5 grid h-11 w-11 cursor-pointer place-items-center rounded-xl bg-accent text-bg transition-colors hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
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
                      <h2 className="font-serif text-xl leading-tight text-text">{book.title}</h2>
                      <span className="rounded-full border border-border bg-bg-elevated px-2 py-0.5 text-[11px] font-medium text-text-muted">
                        {sourceLabel(book.metadata_source)}
                      </span>
                    </div>
                    <p className="text-sm text-text-muted">{book.authors.join(", ") || "Unknown author"}</p>
                    <p className="mt-1 text-xs text-text-dim">
                      {[book.first_publish_year, book.total_pages ? `${book.total_pages} pages` : null].filter(Boolean).join(" · ") || "Edition details unavailable"}
                    </p>
                    {book.description ? <p className="mt-3 line-clamp-2 text-sm leading-6 text-text-muted">{book.description}</p> : null}
                  </div>
                  <div className="col-span-2 flex items-center sm:col-span-1 sm:pl-3">
                    {book.already_in_library ? (
                      <span className="rounded-xl border border-border bg-bg-elevated px-3 py-2 text-sm text-text-dim">Already in library</span>
                    ) : (
                      <Button variant="primary" onClick={() => chooseBook(book)}>Add book</Button>
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
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm sm:col-span-2"><span className="text-text-muted">Title</span><input className={fieldClass} value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
              <label className="grid gap-1.5 text-sm sm:col-span-2"><span className="text-text-muted">Author</span><input className={fieldClass} value={author} onChange={(e) => setAuthor(e.target.value)} required /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Start date</span><input type="date" className={fieldClass} value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">End date</span><input type="date" className={fieldClass} value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Total pages</span><input type="number" min={1} className={fieldClass} value={totalPages} onChange={(e) => setTotalPages(e.target.value)} /></label>
              <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Status</span><select className={fieldClass} value={status} onChange={(e) => setStatus(e.target.value as ReadingStatus)}><option value="not_started">Want to read</option><option value="reading">Currently reading</option><option value="completed">Completed</option><option value="dnf">Did not finish</option></select></label>
              {status === "completed" ? <label className="grid gap-1.5 text-sm"><span className="text-text-muted">Rating (optional)</span><input type="number" min={0} max={5} step={0.25} className={fieldClass} value={rating} onChange={(e) => setRating(e.target.value)} placeholder="4.5" /></label> : null}
            </div>

            {error ? <p className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">{error}</p> : null}
            {message ? <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent">{message}</p> : null}

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
