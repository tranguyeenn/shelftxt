export const STAR_PATH =
  "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z";

export const STAR_FILLED_COLOR = "#fbbf24";

export type StarFillLevel = 0 | 25 | 50 | 75 | 100;

export const STAR_SIZES = {
  sm: 24,
  md: 30,
  lg: 32
} as const;

export function getStarFillLevel(rating: number, starIndex: number): StarFillLevel {
  const portion = rating - starIndex;
  const clamped = Math.min(1, Math.max(0, portion));
  const quarters = Math.round(clamped * 4);
  return (quarters * 25) as StarFillLevel;
}

export function clampRating(value: number | null, max = 5): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.min(max, Math.max(0, value));
}

export function roundToStep(value: number, step: number, max: number): number {
  return Math.min(max, Math.max(0, Math.round(value / step) * step));
}

export function formatRatingValue(value: number | null): string {
  if (value == null) return "";
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function parseRatingInput(raw: string, max = 5, step = 0.25): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) return null;

  return roundToStep(parsed, step, max);
}

export function ratingAriaLabel(value: number | null, max = 5): string {
  if (value == null) return "Unrated";
  return `${formatRatingValue(value)} out of ${max} stars`;
}
