import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { fetchJson } from "@/lib/api";

export function AddBookPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [totalPages, setTotalPages] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

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
          total_pages: pagesNum === null ? null : Math.round(pagesNum),
          start_date: startDate || null,
          end_date: endDate || null
        })
      });
      setMessage("Book added to your library.");
      setTitle("");
      setAuthor("");
      setTotalPages("");
      setStartDate("");
      setEndDate("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add book");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader title="Add Book" subtitle="Simple input flow for new library entries." />
      <Card className="mx-auto w-full max-w-lg">
        <form className="grid gap-4" onSubmit={onSubmit}>
          <label className="grid gap-1.5 text-sm">
            <span className="text-text-muted">Title</span>
            <input
              className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="The Left Hand of Darkness"
              required
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="text-text-muted">Start Date</span>
            <input
              type="date"
              className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="text-text-muted">End Date</span>
            <input
              type="date"
              className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="text-text-muted">Author</span>
            <input
              className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Ursula K. Le Guin"
              required
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="text-text-muted">Total pages (optional)</span>
            <input
              type="number"
              min={1}
              className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none ring-accent/40 focus:ring-2"
              value={totalPages}
              onChange={(e) => setTotalPages(e.target.value)}
              placeholder="304"
            />
          </label>

          {error ? (
            <p className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent">
              {message}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2 pt-1">
            <Button variant="primary" type="submit" disabled={loading}>
              {loading ? "Adding…" : "Add book"}
            </Button>
            <Button variant="ghost" type="button" onClick={() => navigate("/app/ranking")}>
              Go to ranking
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
