import { useCallback, useEffect, useState } from "react";

import { SettingRow, SettingsSection } from "@/components/settings/SettingsSection";
import { Button } from "@/components/ui/Button";
import {
  fetchMetadataStatus,
  metadataStatusLabel,
  startMetadataGeneration,
  type MetadataStatus
} from "@/lib/metadata";

function progressLabel(status: MetadataStatus | null): string {
  if (!status) return "Processed: 0 / 0 books";
  return `Processed: ${status.job.processed_count} / ${status.job.total_count} books`;
}

export function MetadataSection() {
  const [status, setStatus] = useState<MetadataStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const next = await fetchMetadataStatus();
      setStatus(next);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load metadata status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!status || !["pending", "processing"].includes(status.job.status)) return;
    const interval = window.setInterval(() => void loadStatus(), 2500);
    return () => window.clearInterval(interval);
  }, [loadStatus, status]);

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const next = await startMetadataGeneration();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start metadata generation");
    } finally {
      setGenerating(false);
    }
  }

  const busy = generating || status?.job.status === "pending" || status?.job.status === "processing";

  return (
    <SettingsSection
      title="Metadata"
      description="Generate genre metadata separately from import so normal actions stay fast."
    >
      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-3 py-2 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <div className="rounded-lg border border-border-subtle bg-bg-elevated px-3 py-3">
        <p className="text-sm font-medium text-text">Genre data powers:</p>
        <ul className="mt-2 grid gap-1 text-sm text-text-muted">
          <li>Favorite Genre</li>
          <li>Highest Rated Genre</li>
          <li>Improved Recommendations</li>
        </ul>
      </div>

      <SettingRow label="Status">
        <p className="text-sm text-text">
          Genres available for {status?.books_with_genres ?? 0} / {status?.total_books ?? 0} books
        </p>
      </SettingRow>

      <SettingRow label="Metadata Progress" hint={progressLabel(status)}>
        <p className="text-sm text-text">
          {loading ? "Loading" : metadataStatusLabel(status?.job.status ?? "completed")}
        </p>
      </SettingRow>

      <div>
        <Button
          variant="primary"
          onClick={() => void handleGenerate()}
          disabled={busy || loading || (status?.total_books ?? 0) === 0}
        >
          {busy ? "Generating" : "Generate Metadata"}
        </Button>
      </div>
    </SettingsSection>
  );
}
