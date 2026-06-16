import { apiFetch, fetchJson } from "@/lib/api";
import { assertDemoWritable } from "@/lib/demoMode";

export async function downloadLibraryCsv(): Promise<void> {
  const response = await apiFetch("/books/export");
  if (!response.ok) {
    let message = `Export failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "shelftxt-library.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function deleteBook(bookId: string): Promise<{ message: string }> {
  assertDemoWritable();
  const encodedId = encodeURIComponent(bookId);
  return fetchJson<{ message: string }>(`/books/${encodedId}`, { method: "DELETE" });
}

export async function clearLibrary(): Promise<{ message: string; deleted: number }> {
  assertDemoWritable();
  const response = await apiFetch("/books/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true })
  });

  if (!response.ok) {
    let message = `Clear failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }

  return response.json() as Promise<{ message: string; deleted: number }>;
}
