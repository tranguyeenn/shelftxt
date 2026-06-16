import { apiFetch, fetchJson, getApiErrorMessage } from "@/lib/api";
import { assertDemoWritable } from "@/lib/demoMode";

export async function downloadLibraryCsv(): Promise<void> {
  const response = await apiFetch("/books/export");
  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response, `Export failed (${response.status})`));
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
    throw new Error(await getApiErrorMessage(response, `Clear failed (${response.status})`));
  }

  return response.json() as Promise<{ message: string; deleted: number }>;
}
