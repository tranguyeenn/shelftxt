export type OpenLibraryCoverSize = "S" | "M" | "L";

function hasValidIsbn10Checksum(isbn: string): boolean {
  const total = [...isbn].reduce((sum, character, index) => {
    const value = character === "X" ? 10 : Number(character);
    return sum + value * (10 - index);
  }, 0);
  return total % 11 === 0;
}

function hasValidIsbn13Checksum(isbn: string): boolean {
  const total = [...isbn.slice(0, 12)].reduce(
    (sum, character, index) => sum + Number(character) * (index % 2 === 0 ? 1 : 3),
    0
  );
  const checkDigit = (10 - (total % 10)) % 10;
  return checkDigit === Number(isbn[12]);
}

export function normalizeIsbn(value: string | null | undefined): string | null {
  const normalized = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/^ISBN(?:-1[03])?:?\s*/i, "")
    .replace(/[\s-]/g, "");

  if (/^\d{9}[\dX]$/.test(normalized) && hasValidIsbn10Checksum(normalized)) {
    return normalized;
  }
  if (/^\d{13}$/.test(normalized) && hasValidIsbn13Checksum(normalized)) {
    return normalized;
  }
  return null;
}

export function openLibraryCoverUrl(
  value: string | null | undefined,
  size: OpenLibraryCoverSize = "M"
): string | null {
  const isbn = normalizeIsbn(value);
  if (!isbn) return null;
  return `https://covers.openlibrary.org/b/isbn/${encodeURIComponent(isbn)}-${size}.jpg?default=false`;
}
