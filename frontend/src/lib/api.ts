import { assertDemoWritable, resolveApiBase } from "@/lib/demoMode";

/**
 * Browser fetch target for the FastAPI backend.
 *
 * Dev: `/api/*` via Vite proxy → `127.0.0.1:8000`.
 * Production: `VITE_API_BASE_URL` or Render default.
 */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const base = resolveApiBase();
  if (base) {
    return `${base}${normalized}`;
  }
  return `/api${normalized}`;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (MUTATING_METHODS.has(method)) {
    assertDemoWritable();
  }

  const response = await fetch(apiUrl(path), { cache: "no-store", ...init });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body?.detail === "string" && body.detail.trim()) {
        message = body.detail;
      }
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
