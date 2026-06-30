import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { clearLibrary, downloadLibraryCsv } from "@/lib/libraryExport";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { backfillMissingPages } from "@/lib/pageCounts";

type LibraryActionsProps = {
  onCleared?: () => void;
};

export function LibraryActions({ onCleared }: LibraryActionsProps) {
  const [exporting, setExporting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [backfillingPages, setBackfillingPages] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function handleExport() {
    setExporting(true);
    setError("");
    setMessage("");
    try {
      await downloadLibraryCsv();
      setMessage("Library exported to shelftxt-library.csv");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleClear() {
    const confirmed = window.confirm(
      "Clear your entire library? This removes all books and cannot be undone."
    );
    if (!confirmed) return;

    setClearing(true);
    setError("");
    setMessage("");
    try {
      const result = await clearLibrary();
      setMessage(`Removed ${result.deleted} book${result.deleted === 1 ? "" : "s"} from your library.`);
      onCleared?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clear failed");
    } finally {
      setClearing(false);
    }
  }

  async function handleBackfillPages() {
    setBackfillingPages(true);
    setError("");
    setMessage("");
    try {
      const result = await backfillMissingPages();
      setMessage(
        `Page lookup updated ${result.updated} of ${result.processed} processed book${result.processed === 1 ? "" : "s"}.` +
          (result.unresolved > 0 ? ` ${result.unresolved} had no reliable match.` : "")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Page backfill failed");
    } finally {
      setBackfillingPages(false);
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button variant="secondary" onClick={() => void handleExport()} disabled={exporting}>
          {exporting ? "Exporting…" : "Export library"}
        </Button>
        {!isReadOnlyDemo ? (
          <>
            <Button
              variant="secondary"
              onClick={() => void handleBackfillPages()}
              disabled={backfillingPages}
            >
              {backfillingPages ? "Finding pages…" : "Backfill missing pages"}
            </Button>
            <Button variant="danger" onClick={() => void handleClear()} disabled={clearing}>
              {clearing ? "Clearing…" : "Clear library"}
            </Button>
          </>
        ) : null}
      </div>

      {message ? (
        <p className="rounded-lg border border-accent/30 bg-accent-muted px-3 py-2 text-sm text-accent">
          {message}
        </p>
      ) : null}
      {error ? (
        <p
          className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
