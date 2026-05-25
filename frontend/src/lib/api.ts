/**
 * Browser fetch target for the FastAPI backend.
 *
 * Dev: `/api/*` via Vite proxy → `127.0.0.1:8000`.
 * Production: `VITE_API_BASE_URL` or Render default.
 */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const publicBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (publicBase) {
    return `${publicBase}${normalized}`;
  }
  if (import.meta.env.PROD) {
    return `https://shelftxt.onrender.com${normalized}`;
  }
  return `/api${normalized}`;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
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
