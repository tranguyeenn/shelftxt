import { useMemo, useState } from "react";
import Papa from "papaparse";

import { Button } from "@/components/ui/Button";
import { fetchJson } from "@/lib/api";
import { demoReadOnlyMessage, isReadOnlyDemo } from "@/lib/demoMode";

type ImportRow = {
  title: string;
  isbn_uid: string | null;
  author: string | null;
  total_pages: number | null;
  read_status: string | null;
  start_date: string | null;
  end_date: string | null;
  pages_read: number | null;
  progress_percent: number | null;
};

export function CsvImportSection() {
  const [fileName, setFileName] = useState("");
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function onCsvSelected(file: File | null) {
    setError("");
    setMessage("");
    setRows([]);
    if (!file) {
      setFileName("");
      return;
    }
    setFileName(file.name);

    const text = await file.text();
    const parsed = Papa.parse<Record<string, string>>(text, {
      header: true,
      skipEmptyLines: true
    });

    if (parsed.errors.length > 0) {
      setError(parsed.errors[0]?.message ?? "Could not parse CSV.");
      return;
    }

    const normalized = parsed.data
      .map((row): ImportRow | null => {
        const title = String(row.title ?? row.Title ?? "").trim();
        if (!title) return null;
        const isbnUid = String(
          row.isbn_uid ?? row.isbn ?? row.ISBN ?? row["ISBN/UID"] ?? ""
        ).trim();
        const author = String(row.author ?? row.authors ?? row.Author ?? row.Authors ?? "").trim();
        const pagesRaw = String(row.total_pages ?? row["Total Pages"] ?? "").trim();
        const pagesNum = pagesRaw ? Number(pagesRaw) : null;
        const status = String(row.read_status ?? row.status ?? row["Read Status"] ?? "").trim();
        const startDate = String(row.start_date ?? row["Start Date"] ?? "").trim();
        const endDate = String(row.end_date ?? row["End Date"] ?? row["Last Date Read"] ?? "").trim();
        const pagesReadRaw = String(row.pages_read ?? row["Pages Read"] ?? "").trim();
        const pagesReadNum = pagesReadRaw ? Number(pagesReadRaw) : null;
        const progressRaw = String(row.progress_percent ?? row["Progress (%)"] ?? "").trim();
        const progressNum = progressRaw ? Number(progressRaw) : null;

        return {
          title,
          isbn_uid: isbnUid || null,
          author: author || null,
          total_pages:
            Number.isFinite(pagesNum) && pagesNum && pagesNum > 0 ? Math.round(pagesNum) : null,
          read_status: status || null,
          start_date: startDate || null,
          end_date: endDate || null,
          pages_read:
            Number.isFinite(pagesReadNum) && pagesReadNum !== null && pagesReadNum >= 0
              ? Math.round(pagesReadNum)
              : null,
          progress_percent:
            Number.isFinite(progressNum) && progressNum !== null && progressNum >= 0
              ? Math.min(100, Math.max(0, progressNum))
              : null
        };
      })
      .filter((item): item is ImportRow => item !== null);

    if (normalized.length === 0) {
      setError("No usable rows found. Expected at least a `title` column.");
      return;
    }

    setRows(normalized);
  }

  async function importRows() {
    if (rows.length === 0) {
      setError("Upload a CSV with at least one valid row first.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await fetchJson<{
        imported_count: number;
        skipped_duplicates: number;
        enriched_count: number;
        enrichment_skipped_count: number;
        enrichment_failed_count: number;
      }>("/books/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ books: rows })
      });
      setMessage(
        `Imported ${result.imported_count} books, skipped ${result.skipped_duplicates}, enriched ${result.enriched_count}.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  const preview = useMemo(() => rows.slice(0, 8), [rows]);

  return (
    <div className="grid gap-4">
      {isReadOnlyDemo ? (
        <p className="rounded-lg border border-score-recency/30 bg-score-recency/10 px-3 py-2 text-sm text-text-muted">
          {demoReadOnlyMessage()}
        </p>
      ) : null}
      <div>
        <h3 className="text-sm font-medium text-text">CSV import</h3>
        <p className="mt-1 text-sm text-text-muted">
          Upload a CSV with <span className="font-mono text-text">title</span>,{" "}
          <span className="font-mono text-text">author</span>,{" "}
          <span className="font-mono text-text">total_pages</span>,{" "}
          <span className="font-mono text-text">read_status</span>,{" "}
          <span className="font-mono text-text">start_date</span>,{" "}
          <span className="font-mono text-text">end_date</span>,{" "}
          <span className="font-mono text-text">pages_read</span>, and{" "}
          <span className="font-mono text-text">progress_percent</span>.
        </p>
      </div>

      <input
        type="file"
        accept=".csv,text/csv"
        disabled={isReadOnlyDemo}
        onChange={(e) => void onCsvSelected(e.target.files?.[0] ?? null)}
        className="block w-full cursor-pointer rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-text file:mr-3 file:rounded-md file:border-0 file:bg-accent-muted file:px-3 file:py-1 file:text-accent disabled:cursor-not-allowed disabled:opacity-50"
      />

      {fileName ? <p className="text-xs text-text-dim">Selected: {fileName}</p> : null}

      {rows.length > 0 ? (
        <div className="rounded-lg border border-border-subtle bg-bg-elevated p-3">
          <p className="text-xs uppercase tracking-wide text-text-dim">
            Preview ({rows.length} rows)
          </p>
          <ul className="mt-2 grid gap-1 text-sm text-text-muted">
            {preview.map((row, idx) => (
              <li key={`${row.title}-${idx}`}>
                {row.title}
                {row.author ? ` — ${row.author}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {error ? (
        <p
          className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {message ? (
        <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent">
          {message}
        </p>
      ) : null}

      {!isReadOnlyDemo ? (
        <div>
          <Button variant="primary" onClick={() => void importRows()} disabled={loading}>
            {loading ? "Importing…" : "Import books"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
