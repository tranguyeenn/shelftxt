import { fetchJson } from "@/lib/api";

export type MetadataJobState = "pending" | "processing" | "completed" | "failed";

export type MetadataStatus = {
  books_with_genres: number;
  total_books: number;
  job: {
    status: MetadataJobState;
    processed_count: number;
    total_count: number;
    error_message?: string | null;
  };
};

export function fetchMetadataStatus(): Promise<MetadataStatus> {
  return fetchJson<MetadataStatus>("/metadata/status", { skipClientCache: true });
}

export function startMetadataGeneration(): Promise<MetadataStatus> {
  return fetchJson<MetadataStatus>("/metadata/generate", {
    method: "POST",
    skipClientCache: true
  });
}

export function metadataStatusLabel(status: MetadataJobState): string {
  if (status === "pending") return "Pending";
  if (status === "processing") return "Processing";
  if (status === "failed") return "Failed";
  return "Completed";
}
