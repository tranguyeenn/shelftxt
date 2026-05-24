"use client";

import Papa from "papaparse";
import { ChangeEvent, DragEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl } from "../lib/apiUrl";

type ApiBook = {
  Title?: string | null;
  Authors?: string | null;
  score?: number;
};

type BackendBook = {
  Title?: string | null;
  Authors?: string | null;
  "Read Status"?: string | null;
  "Progress (%)"?: number | null;
  "Star Rating"?: number | null;
  "Total Pages"?: number | null;
  "Pages Read"?: number | null;
};

type TabId = "library" | "import" | "discover";
type ShelfKind = "want" | "reading" | "read" | "dnf";

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(String(value).trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function progressPct(book: BackendBook): number {
  const p = toNumber(book["Progress (%)"]);
  return p === null ? 0 : Math.min(100, Math.max(0, p));
}

function statusNorm(s: string | null | undefined): string {
  return String(s ?? "")
    .trim()
    .toLowerCase();
}

function shelfLabel(book: BackendBook): ShelfKind {
  const st = statusNorm(book["Read Status"]);
  const prog = progressPct(book);
  if (st === "dnf") return "dnf";
  if (st === "read") return "read";
  if (st === "to-read" && prog > 0) return "reading";
  return "want";
}

async function patchBook(body: Record<string, unknown>): Promise<Response> {
  return fetch(apiUrl("/books"), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store"
  });
}

export default function HomePage() {
  const [tab, setTab] = useState<TabId>("library");

  const [library, setLibrary] = useState<BackendBook[]>([]);
  const [libraryLoading, setLibraryLoading] = useState<boolean>(true);
  const [libraryError, setLibraryError] = useState<string>("");

  const [bookTitle, setBookTitle] = useState<string>("");
  const [bookAuthor, setBookAuthor] = useState<string>("");
  const [bookPages, setBookPages] = useState<string>("");
  const [addMessage, setAddMessage] = useState<string>("");
  const [recommendation, setRecommendation] = useState<ApiBook | null>(null);
  const [apiMessage, setApiMessage] = useState<string>("");
  const [loadingAdd, setLoadingAdd] = useState<boolean>(false);
  const [loadingRecommend, setLoadingRecommend] = useState<boolean>(false);
  const [deletingTitle, setDeletingTitle] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const [editBook, setEditBook] = useState<BackendBook | null>(null);
  const [editForm, setEditForm] = useState({
    newTitle: "",
    author: "",
    totalPages: "",
    pagesRead: "",
    shelf: "want" as ShelfKind,
    rating: ""
  });
  const [editError, setEditError] = useState<string>("");

  const [csvRows, setCsvRows] = useState<Record<string, unknown>[]>([]);
  const [csvName, setCsvName] = useState<string>("");
  const [csvCols, setCsvCols] = useState({ title: "Title", author: "Authors", pages: "Total Pages" });
  const [importMsg, setImportMsg] = useState<string>("");
  const [importing, setImporting] = useState<boolean>(false);
  const [csvDrag, setCsvDrag] = useState<boolean>(false);

  const loadLibrary = useCallback(async () => {
    setLibraryError("");
    setLibraryLoading(true);
    try {
      const response = await fetch(apiUrl("/books"), { cache: "no-store" });
      if (!response.ok) {
        let message =
          response.status === 502
            ? "Library service unavailable."
            : `Couldn't load library (${response.status}).`;
        if (response.status !== 502) {
          try {
            const errBody = (await response.json()) as { detail?: string };
            if (typeof errBody?.detail === "string" && errBody.detail.trim()) {
              message = errBody.detail;
            }
          } catch {
            /* keep */
          }
        }
        setLibraryError(message);
        setLibrary([]);
        return;
      }
      const data = (await response.json()) as BackendBook[];
      const list = Array.isArray(data) ? data : [];
      setLibrary(list);
      if (list.length === 0) {
        setRecommendation(null);
      }
    } catch {
      setLibraryError("Couldn't load library.");
      setLibrary([]);
    } finally {
      setLibraryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  const shelves = useMemo(() => {
    const want: BackendBook[] = [];
    const reading: BackendBook[] = [];
    const read: BackendBook[] = [];
    const dnf: BackendBook[] = [];
    for (const b of library) {
      const s = shelfLabel(b);
      if (s === "want") want.push(b);
      else if (s === "reading") reading.push(b);
      else if (s === "read") read.push(b);
      else dnf.push(b);
    }
    return { want, reading, read, dnf };
  }, [library]);

  const openEdit = (book: BackendBook) => {
    const sk = shelfLabel(book);
    setEditBook(book);
    setEditError("");
    setEditForm({
      newTitle: String(book.Title ?? ""),
      author: String(book.Authors ?? ""),
      totalPages: toNumber(book["Total Pages"])?.toString() ?? "",
      pagesRead: toNumber(book["Pages Read"])?.toString() ?? "",
      shelf: sk,
      rating: toNumber(book["Star Rating"])?.toString() ?? ""
    });
  };

  const saveEdit = async () => {
    if (!editBook) return;
    const t = String(editBook.Title ?? "");
    setEditError("");
    const tp = editForm.totalPages.trim() ? parseInt(editForm.totalPages, 10) : null;
    const pr = editForm.pagesRead.trim() ? parseInt(editForm.pagesRead, 10) : null;
    const body: Record<string, unknown> = { title: t };
    if (editForm.newTitle.trim() && editForm.newTitle.trim() !== t) {
      body.new_title = editForm.newTitle.trim();
    }
    if (editForm.author.trim() !== String(editBook.Authors ?? "")) {
      body.author = editForm.author.trim();
    }
    if (tp !== null && !Number.isNaN(tp) && tp > 0) {
      body.total_pages = tp;
    }
    const initialShelf = shelfLabel(editBook);
    if (editForm.shelf !== initialShelf) {
      body.move_to =
        editForm.shelf === "want"
          ? "want"
          : editForm.shelf === "reading"
            ? "reading"
            : editForm.shelf === "read"
              ? "read"
              : "dnf";
      if (editForm.shelf === "read") {
        const r = parseFloat(editForm.rating);
        if (!Number.isFinite(r) || r < 1 || r > 5) {
          setEditError("Rating must be between 1 and 5 for Read.");
          return;
        }
        body.rating = r;
      }
      if (editForm.shelf === "reading") {
        body.pages_read = pr !== null && !Number.isNaN(pr) && pr > 0 ? pr : 1;
        const needTp = tp ?? toNumber(editBook["Total Pages"]);
        if (!needTp || needTp <= 0) {
          setEditError("Total pages is required for Currently reading.");
          return;
        }
        if (body.total_pages === undefined) body.total_pages = needTp;
      }
    } else if (editForm.shelf === "reading" && pr !== null && !Number.isNaN(pr)) {
      body.pages_read = pr;
    }
    if (editForm.shelf === "read" && initialShelf === "read") {
      const r = parseFloat(editForm.rating);
      if (Number.isFinite(r) && r >= 1 && r <= 5) {
        const prev = toNumber(editBook["Star Rating"]);
        if (prev !== r) {
          body.rating = r;
        }
      }
    }

    setActionBusy(t);
    try {
      const res = await patchBook(body);
      if (!res.ok) {
        const tx = await res.text();
        setEditError(tx.slice(0, 200));
        return;
      }
      setEditBook(null);
      await loadLibrary();
    } catch {
      setEditError("Save failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const runMove = async (book: BackendBook, move_to: "want" | "reading" | "read" | "dnf") => {
    const t = String(book.Title ?? "");
    setActionBusy(t);
    try {
      const body: Record<string, unknown> = { title: t, move_to };
      if (move_to === "read") {
        const r = window.prompt("Rating 1–5 for finished book:");
        if (r === null) return;
        const rating = parseFloat(r);
        if (!Number.isFinite(rating) || rating < 1 || rating > 5) return;
        body.rating = rating;
      }
      if (move_to === "reading") {
        let tp = toNumber(book["Total Pages"]);
        if (!tp || tp <= 0) {
          const v = window.prompt("Total number of pages (required):");
          if (v === null) return;
          tp = parseInt(v, 10);
          if (!tp || tp < 1) return;
          body.total_pages = tp;
        }
        body.pages_read = 1;
      }
      const res = await patchBook(body);
      if (!res.ok) {
        setLibraryError((await res.text()).slice(0, 120));
        return;
      }
      await loadLibrary();
    } finally {
      setActionBusy(null);
    }
  };

  const addBook = async () => {
    setAddMessage("");
    if (!bookTitle.trim() || !bookAuthor.trim()) {
      setAddMessage("Title and author are required.");
      return;
    }

    const pagesNum = bookPages.trim() ? Number(bookPages.trim()) : NaN;
    const total_pages =
      bookPages.trim() === "" || !Number.isFinite(pagesNum) || pagesNum <= 0 ? null : Math.round(pagesNum);

    setLoadingAdd(true);
    try {
      const body: { title: string; author: string; total_pages?: number } = {
        title: bookTitle.trim(),
        author: bookAuthor.trim()
      };
      if (total_pages !== null) body.total_pages = total_pages;

      const response = await fetch(apiUrl("/books"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        const errText = await response.text();
        setAddMessage(`Could not add book (${response.status}). ${errText.slice(0, 120)}`);
        return;
      }

      setBookTitle("");
      setBookAuthor("");
      setBookPages("");
      setAddMessage("Added to Want to Read.");
      await loadLibrary();
    } catch {
      setAddMessage("Couldn't add book.");
    } finally {
      setLoadingAdd(false);
    }
  };

  const deleteBook = async (title: string) => {
    if (!title) return;
    const confirmed = typeof window !== "undefined" ? window.confirm(`Remove “${title}” from your library?`) : true;
    if (!confirmed) return;

    setDeletingTitle(title);
    try {
      const response = await fetch(apiUrl("/books/remove"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ title })
      });
      if (!response.ok) {
        setLibraryError(`Delete failed (${response.status}).`);
        return;
      }
      setRecommendation((prev) => (prev?.Title === title ? null : prev));
      await loadLibrary();
    } catch {
      setLibraryError("Couldn't remove book.");
    } finally {
      setDeletingTitle(null);
    }
  };

  const getRecommendation = async () => {
    setApiMessage("");
    setLoadingRecommend(true);
    try {
      const response = await fetch(apiUrl("/recommend"));
      if (!response.ok) {
        setApiMessage(
          response.status === 502 ? "Suggestion service unavailable." : `Couldn't load suggestion (${response.status}).`
        );
        return;
      }
      const payload = (await response.json()) as ApiBook[];
      const first = payload?.[0] ?? null;
      setRecommendation(first);
      if (!first) {
        setApiMessage("No to-read books to recommend from. Add books first.");
      }
    } catch {
      setApiMessage("Couldn't load a suggestion.");
    } finally {
      setLoadingRecommend(false);
    }
  };

  const parseCsvFile = (file: File) => {
    setImportMsg("");
    Papa.parse<Record<string, unknown>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => {
        if (result.errors.length) {
          setImportMsg("Could not parse CSV.");
          return;
        }
        const rows = result.data.filter((r) => Object.keys(r).length > 0);
        setCsvRows(rows);
        setCsvName(file.name);
      },
      error: () => setImportMsg("Could not read file.")
    });
  };

  const onCsvInput = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) parseCsvFile(f);
  };

  const onCsvDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setCsvDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) parseCsvFile(f);
  };

  const resolveCol = (row: Record<string, unknown>, key: string): unknown => {
    if (key in row) return row[key];
    const lower = Object.keys(row).find((k) => k.toLowerCase() === key.toLowerCase());
    return lower ? row[lower] : undefined;
  };

  const doImport = async () => {
    if (csvRows.length === 0) {
      setImportMsg("Choose a CSV first.");
      return;
    }
    const books: { title: string; author?: string; total_pages?: number }[] = [];
    for (const row of csvRows) {
      const rawT = resolveCol(row, csvCols.title);
      const title = String(rawT ?? "").trim();
      if (!title) continue;
      const rawA = resolveCol(row, csvCols.author);
      const rawP = resolveCol(row, csvCols.pages);
      const author = rawA !== undefined ? String(rawA).trim() : undefined;
      let total_pages: number | undefined;
      if (rawP !== undefined && rawP !== null && String(rawP).trim() !== "") {
        const n = parseInt(String(rawP), 10);
        if (Number.isFinite(n) && n > 0) total_pages = n;
      }
      books.push({ title, author: author || undefined, total_pages });
    }
    if (books.length === 0) {
      setImportMsg("No rows with a title. Check column names.");
      return;
    }
    setImporting(true);
    setImportMsg("");
    try {
      const res = await fetch(apiUrl("/books/import"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ books })
      });
      const j = (await res.json()) as { imported?: number; skipped?: number; detail?: string };
      if (!res.ok) {
        setImportMsg(j.detail ?? `Import failed (${res.status}).`);
        return;
      }
      setImportMsg(`Imported ${j.imported ?? 0}, skipped ${j.skipped ?? 0} (duplicates or empty).`);
      setCsvRows([]);
      setCsvName("");
      await loadLibrary();
    } catch {
      setImportMsg("Import failed.");
    } finally {
      setImporting(false);
    }
  };

  const renderShelf = (label: string, books: BackendBook[]) => {
    if (books.length === 0) return null;
    return (
      <section className="shelf-block" key={label}>
        <h3 className="shelf-heading">{label}</h3>
        <ul className="shelf-list">
          {books.map((book, index) => {
            const title = String(book.Title ?? "Untitled");
            const author = String(book.Authors ?? "Unknown author");
            const prog = progressPct(book);
            const sk = shelfLabel(book);
            const rating = toNumber(book["Star Rating"]);
            const busy = actionBusy === title;
            return (
              <li className="shelf-row" key={`${title}-${index}`}>
                <div className="shelf-row-main">
                  <p className="book">{title}</p>
                  <p className="meta">{author}</p>
                  {sk === "reading" ? <p className="small muted">{prog}% read</p> : null}
                  {sk === "read" && rating !== null ? <p className="small muted">{rating.toFixed(1)} ★</p> : null}
                </div>
                <div className="shelf-actions">
                  <button type="button" className="button button-small" disabled={busy} onClick={() => openEdit(book)}>
                    Edit
                  </button>
                  {sk === "want" ? (
                    <>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={busy}
                        onClick={() => void runMove(book, "reading")}
                      >
                        Start reading
                      </button>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={busy}
                        onClick={() => void runMove(book, "dnf")}
                      >
                        Mark DNF
                      </button>
                    </>
                  ) : null}
                  {sk === "reading" ? (
                    <>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={busy}
                        onClick={() => void runMove(book, "read")}
                      >
                        Finish
                      </button>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={busy}
                        onClick={() => void runMove(book, "dnf")}
                      >
                        Mark DNF
                      </button>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={busy}
                        onClick={() => void runMove(book, "want")}
                      >
                        Back to want
                      </button>
                    </>
                  ) : null}
                  {sk === "dnf" ? (
                    <button
                      type="button"
                      className="button button-small"
                      disabled={busy}
                      onClick={() => void runMove(book, "want")}
                    >
                      Back to want
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="button button-danger button-small"
                    disabled={deletingTitle === title || busy}
                    onClick={() => void deleteBook(title)}
                  >
                    {deletingTitle === title ? "…" : "Remove"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    );
  };

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <h1 className="title">LibroRank</h1>
          <p className="tagline">Your shelves and next read — powered by your API library.</p>
        </div>
        <nav className="tabs" aria-label="Main">
          <button
            type="button"
            className={`tab ${tab === "library" ? "tab-active" : ""}`}
            onClick={() => setTab("library")}
          >
            My books
          </button>
          <button
            type="button"
            className={`tab ${tab === "import" ? "tab-active" : ""}`}
            onClick={() => setTab("import")}
          >
            Import CSV
          </button>
          <button
            type="button"
            className={`tab ${tab === "discover" ? "tab-active" : ""}`}
            onClick={() => setTab("discover")}
          >
            Next read
          </button>
        </nav>
      </header>

      <main className="main-content">
        {libraryError ? (
          <p className="banner banner-warn" role="status">
            {libraryError}
          </p>
        ) : null}

        {tab === "library" ? (
          <div className="tab-panel">
            <section className="card-elevated add-card">
              <h2 className="section-title">Add a book</h2>
              <p className="small muted">New titles go to Want to Read.</p>
              <div className="grid add-grid">
                <label className="field">
                  <span className="label">Title</span>
                  <input
                    className="input"
                    value={bookTitle}
                    onChange={(event) => setBookTitle(event.target.value)}
                    placeholder="Title"
                    autoComplete="off"
                  />
                </label>
                <label className="field">
                  <span className="label">Author</span>
                  <input
                    className="input"
                    value={bookAuthor}
                    onChange={(event) => setBookAuthor(event.target.value)}
                    placeholder="Author"
                    autoComplete="off"
                  />
                </label>
                <label className="field">
                  <span className="label">Total pages (optional)</span>
                  <input
                    className="input"
                    inputMode="numeric"
                    value={bookPages}
                    onChange={(event) => setBookPages(event.target.value)}
                    placeholder="e.g. 320"
                  />
                </label>
              </div>
              <div className="row">
                <button className="button button-primary" disabled={loadingAdd} onClick={() => void addBook()}>
                  {loadingAdd ? "Adding…" : "Add to Want to Read"}
                </button>
                <button
                  type="button"
                  className="button"
                  disabled={libraryLoading}
                  onClick={() => void loadLibrary()}
                >
                  {libraryLoading ? "Refreshing…" : "Refresh"}
                </button>
              </div>
              {addMessage ? <p className="small ok">{addMessage}</p> : null}
            </section>

            {libraryLoading ? (
              <p className="small muted">Loading your library…</p>
            ) : library.length === 0 ? (
              <div className="empty-library" aria-live="polite">
                <p className="empty-library-text">
                  Your shelves are empty. Add a book above or use the Import CSV tab — books are stored by the API.
                </p>
              </div>
            ) : (
              <div className="shelves">
                {renderShelf("Want to Read", shelves.want)}
                {renderShelf("Currently reading", shelves.reading)}
                {renderShelf("Read", shelves.read)}
                {renderShelf("Did not finish", shelves.dnf)}
              </div>
            )}
          </div>
        ) : null}

        {tab === "import" ? (
          <div className="tab-panel">
            <section className="card-elevated">
              <h2 className="section-title">Import CSV</h2>
              <p className="small muted">
                Rows are sent to your API as Want to Read. Duplicate titles are skipped. Map columns to your file’s
                headers.
              </p>
              <div
                className={`dropzone ${csvDrag ? "dropzone-active" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setCsvDrag(true);
                }}
                onDragLeave={() => setCsvDrag(false)}
                onDrop={onCsvDrop}
              >
                <p>Drop a CSV here</p>
                <label className="button button-primary">
                  Choose file
                  <input type="file" accept=".csv,text/csv" hidden onChange={onCsvInput} />
                </label>
              </div>
              <p className="small">{csvName ? `Loaded: ${csvName} (${csvRows.length} rows)` : "No file selected"}</p>
              <div className="grid add-grid">
                <label className="field">
                  <span className="label">Title column</span>
                  <input
                    className="input"
                    value={csvCols.title}
                    onChange={(e) => setCsvCols((c) => ({ ...c, title: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span className="label">Author column</span>
                  <input
                    className="input"
                    value={csvCols.author}
                    onChange={(e) => setCsvCols((c) => ({ ...c, author: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span className="label">Total pages column (optional)</span>
                  <input
                    className="input"
                    value={csvCols.pages}
                    onChange={(e) => setCsvCols((c) => ({ ...c, pages: e.target.value }))}
                  />
                </label>
              </div>
              <button type="button" className="button button-primary" disabled={importing} onClick={() => void doImport()}>
                {importing ? "Importing…" : "Import to library"}
              </button>
              {importMsg ? <p className="small muted">{importMsg}</p> : null}
            </section>
          </div>
        ) : null}

        {tab === "discover" ? (
          <div className="tab-panel">
            <section className="card-elevated">
              <h2 className="section-title">What should I read next?</h2>
              {!libraryLoading && library.length === 0 ? (
                <p className="small muted">
                  Add books under My books first — there is nothing to suggest yet.
                </p>
              ) : (
                <p className="small muted">
                  Picks one book from your to-read pile using the API (author affinity plus light randomness).
                </p>
              )}
              <button
                className="button button-primary"
                disabled={loadingRecommend || (!libraryLoading && library.length === 0)}
                onClick={() => void getRecommendation()}
              >
                {loadingRecommend ? "Choosing…" : "Suggest a book"}
              </button>
              {recommendation ? (
                <article className="item recommend-card">
                  <span className="rank">Pick</span>
                  <div>
                    <p className="book">{recommendation.Title ?? "Untitled"}</p>
                    <p className="meta">{recommendation.Authors ?? "Unknown author"}</p>
                  </div>
                  <span className="chip">{(recommendation.score ?? 0).toFixed(2)}</span>
                </article>
              ) : (
                <p className="small muted">Run a suggestion to see a title here.</p>
              )}
              {apiMessage ? <p className="small err">{apiMessage}</p> : null}
            </section>
          </div>
        ) : null}
      </main>

      {editBook ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setEditBook(null)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="edit-title" className="section-title">
              Edit book
            </h2>
            <div className="grid add-grid">
              <label className="field">
                <span className="label">Title</span>
                <input
                  className="input"
                  value={editForm.newTitle}
                  onChange={(e) => setEditForm((f) => ({ ...f, newTitle: e.target.value }))}
                />
              </label>
              <label className="field">
                <span className="label">Author</span>
                <input
                  className="input"
                  value={editForm.author}
                  onChange={(e) => setEditForm((f) => ({ ...f, author: e.target.value }))}
                />
              </label>
              <label className="field">
                <span className="label">Total pages</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={editForm.totalPages}
                  onChange={(e) => setEditForm((f) => ({ ...f, totalPages: e.target.value }))}
                />
              </label>
              <label className="field">
                <span className="label">Pages read</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={editForm.pagesRead}
                  onChange={(e) => setEditForm((f) => ({ ...f, pagesRead: e.target.value }))}
                />
              </label>
              <label className="field">
                <span className="label">Shelf</span>
                <select
                  className="select"
                  value={editForm.shelf}
                  onChange={(e) =>
                    setEditForm((f) => ({ ...f, shelf: e.target.value as ShelfKind }))
                  }
                >
                  <option value="want">Want to read</option>
                  <option value="reading">Currently reading</option>
                  <option value="read">Read</option>
                  <option value="dnf">Did not finish</option>
                </select>
              </label>
              {editForm.shelf === "read" ? (
                <label className="field">
                  <span className="label">Rating (1–5)</span>
                  <input
                    className="input"
                    inputMode="decimal"
                    value={editForm.rating}
                    onChange={(e) => setEditForm((f) => ({ ...f, rating: e.target.value }))}
                  />
                </label>
              ) : null}
            </div>
            {editError ? <p className="small err">{editError}</p> : null}
            <div className="row">
              <button type="button" className="button" onClick={() => setEditBook(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="button button-primary"
                disabled={actionBusy !== null}
                onClick={() => void saveEdit()}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
