import { assertDemoWritable, resolveApiBase } from "@/lib/demoMode";
import { supabase } from "@/lib/supabase";

export const AUTH_REQUIRED_MESSAGE = "Please sign in to view your library.";

export class AuthRequiredError extends Error {
  constructor(message = AUTH_REQUIRED_MESSAGE) {
    super(message);
    this.name = "AuthRequiredError";
  }
}

type ApiFetchInit = RequestInit & {
  requireAuth?: boolean;
};

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

async function authHeaders(initHeaders?: HeadersInit, requireAuth = true): Promise<Headers> {
  const headers = new Headers(initHeaders);
  const {
    data: { session },
    error
  } = await supabase.auth.getSession();

  if (session?.access_token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
    return headers;
  }

  if (requireAuth && !headers.has("Authorization")) {
    throw new AuthRequiredError(error?.message ? AUTH_REQUIRED_MESSAGE : undefined);
  }

  return headers;
}

export async function apiFetch(path: string, init?: ApiFetchInit): Promise<Response> {
  const { requireAuth = true, ...fetchInit } = init ?? {};
  const method = (init?.method ?? "GET").toUpperCase();
  if (MUTATING_METHODS.has(method)) {
    assertDemoWritable();
  }

  return fetch(apiUrl(path), {
    cache: "no-store",
    ...fetchInit,
    headers: await authHeaders(fetchInit.headers, requireAuth)
  });
}

export async function getApiErrorMessage(
  response: Response,
  fallback = `Request failed (${response.status})`
): Promise<string> {
  if (response.status === 401 || response.status === 403) {
    return AUTH_REQUIRED_MESSAGE;
  }

  try {
    const body = (await response.json()) as { detail?: string };
    if (typeof body?.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    /* keep fallback */
  }

  return fallback;
}

export async function fetchJson<T>(path: string, init?: ApiFetchInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response));
  }
  return response.json() as Promise<T>;
}
