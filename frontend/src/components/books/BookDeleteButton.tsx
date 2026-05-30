import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { deleteBook } from "@/lib/libraryExport";
import { isReadOnlyDemo } from "@/lib/demoMode";

type BookDeleteButtonProps = {
  bookId: string;
  bookTitle: string;
  onDeleted?: () => void;
  compact?: boolean;
};

export function BookDeleteButton({
  bookId,
  bookTitle,
  onDeleted,
  compact = false
}: BookDeleteButtonProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  if (isReadOnlyDemo) {
    return null;
  }

  async function handleDelete() {
    const confirmed = window.confirm(
      `Delete "${bookTitle}" from your library? This cannot be undone.`
    );
    if (!confirmed) return;

    setDeleting(true);
    setError("");
    try {
      await deleteBook(bookId);
      onDeleted?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete book");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={compact ? "grid gap-2" : "grid gap-2 border-t border-border-subtle pt-4"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!compact ? (
          <p className="text-sm text-text-muted">Remove this book from your library.</p>
        ) : null}
        <Button variant="danger" onClick={() => void handleDelete()} disabled={deleting}>
          {deleting ? "Deleting…" : "Delete book"}
        </Button>
      </div>
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
