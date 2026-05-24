/**
 * Browser fetch target for the FastAPI backend.
 *
 * Dev: `/api/*` via Next.js route handlers (no CORS setup needed).
 * Production (e.g. Vercel): direct to Render — avoids broken serverless `/api` routes.
 */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const publicBase = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (publicBase) {
    return `${publicBase}${normalized}`;
  }
  if (process.env.NODE_ENV === "production") {
    return `https://shelftxt.onrender.com${normalized}`;
  }
  return `/api${normalized}`;
}
