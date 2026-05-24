/** Base URL for the FastAPI backend (used by Next.js route handlers). */
export function backendBaseUrl(): string {
  return (
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    (process.env.NODE_ENV === "development"
      ? "http://127.0.0.1:8000"
      : "https://shelftxt.onrender.com")
  );
}
