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
  skipClientCache?: boolean;
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
const GET_CACHE_TTL_MS = 15_000;
export const RECOMMENDATION_RESPONSE_SCHEMA_VERSION = 3;
const API_FETCH_TIMEOUT_MS = Number(
  import.meta.env.VITE_API_FETCH_TIMEOUT_MS ?? 20_000
);
let sessionPromise: ReturnType<typeof supabase.auth.getSession> | null = null;
let sessionCacheUntil = 0;
const jsonCache = new Map<string, { expiresAt: number; promise: Promise<unknown> }>();

function isRecommendationSectionsPath(path: string): boolean {
  return path.startsWith("/recommendations/sections");
}

function apiCacheKey(method: string, path: string): string {
  const schemaSegment = isRecommendationSectionsPath(path)
    ? `:schema=${RECOMMENDATION_RESPONSE_SCHEMA_VERSION}`
    : "";
  return `${method}${schemaSegment}:${path}`;
}

export function apiCacheKeyForTest(method: string, path: string): string {
  return apiCacheKey(method.toUpperCase(), path);
}

function validateRecommendationSectionsPayload(path: string, payload: unknown): void {
  if (!isRecommendationSectionsPath(path)) return;
  if (!payload || typeof payload !== "object") {
    throw new Error("Recommendation response was malformed.");
  }
  const response = payload as Record<string, unknown>;
  const hasSplitArrays =
    Array.isArray(response.shelf_recommendations) &&
    Array.isArray(response.popular_this_week) &&
    Array.isArray(response.newly_found);
  if (response.schema_version !== RECOMMENDATION_RESPONSE_SCHEMA_VERSION || !hasSplitArrays) {
    throw new Error("Recommendation response is stale. Please refresh Discover.");
  }
}

async function authHeaders(initHeaders?: HeadersInit, requireAuth = true): Promise<Headers> {
  const headers = new Headers(initHeaders);
  const now = Date.now();
  if (!sessionPromise || now >= sessionCacheUntil) {
    sessionPromise = supabase.auth.getSession();
    sessionCacheUntil = now + 30_000;
  }
  const {
    data: { session },
    error
  } = await sessionPromise;

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
  const { requireAuth = true, skipClientCache: _skipClientCache, ...fetchInit } = init ?? {};
  const method = (init?.method ?? "GET").toUpperCase();
  if (MUTATING_METHODS.has(method)) {
    assertDemoWritable();
    clearApiClientCache();
  }

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, API_FETCH_TIMEOUT_MS);
  fetchInit.signal?.addEventListener("abort", () => controller.abort(), {
    once: true
  });

  try {
    return await fetch(apiUrl(path), {
      cache: "no-store",
      ...fetchInit,
      headers: await authHeaders(fetchInit.headers, requireAuth),
      signal: controller.signal
    });
  } catch (error) {
    if (timedOut) {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
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
  const method = (init?.method ?? "GET").toUpperCase();
  const cacheable = method === "GET" && !init?.skipClientCache;
  const key = apiCacheKey(method, path);
  const now = Date.now();
  if (cacheable) {
    const cached = jsonCache.get(key);
    if (cached && cached.expiresAt > now) {
      return cached.promise as Promise<T>;
    }
  }

  const started = performance.now();
  const promise = (async () => {
    const response = await apiFetch(path, init);
    const duration = Math.round(performance.now() - started);
    if (path.startsWith("/books")) {
      console.info(`[timing] books fetch duration ${duration}ms`);
    } else if (path.startsWith("/recommend")) {
      console.info(`[timing] recommendation fetch duration ${duration}ms`);
    } else if (path.includes("profile")) {
      console.info(`[timing] profile fetch duration ${duration}ms`);
    }
    if (!response.ok) {
      throw new Error(await getApiErrorMessage(response));
    }
    const body = await response.json();
    validateRecommendationSectionsPayload(path, body);
    return body as T;
  })();

  if (cacheable) {
    jsonCache.set(key, { expiresAt: now + GET_CACHE_TTL_MS, promise });
    promise.catch(() => {
      if (jsonCache.get(key)?.promise === promise) {
        jsonCache.delete(key);
      }
    });
  }
  return promise;
}

export function clearApiClientCache(): void {
  jsonCache.clear();
}
