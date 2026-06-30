type StarRatingDisplayProps = {
  value: number | null;
  max?: number;
  size?: "sm" | "md" | "lg";
  showValue?: boolean;
  className?: string;
};

const sizeClass = {
  sm: "text-sm",
  md: "text-lg",
  lg: "text-2xl"
};

export function StarRatingDisplay({
  value,
  max = 5,
  size = "md",
  showValue = false,
  className = ""
}: StarRatingDisplayProps) {
  const rating = clampRating(value, max);

  if (rating === null) {
    return (
      <span className={`inline-flex items-center gap-2 text-text-muted ${className}`}>
        <span className="text-sm">Unrated</span>
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className={`inline-flex leading-none text-text-dim ${sizeClass[size]}`}
        aria-label={`${formatRating(rating)} out of ${max} stars`}
      >
        {Array.from({ length: max }, (_, index) => (
          <span key={index} className="relative inline-block">
            <span aria-hidden>☆</span>
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 overflow-hidden text-accent"
              style={{ width: `${starFillPercent(rating, index)}%` }}
            >
              ★
            </span>
          </span>
        ))}
      </span>
      {showValue ? (
        <span className="text-xs text-text-muted">{formatRating(rating)}</span>
      ) : null}
    </span>
  );
}

function starFillPercent(value: number, index: number): number {
  return Math.min(100, Math.max(0, (value - index) * 100));
}

function clampRating(value: number | null, max: number): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.min(max, Math.max(0, value));
}

function formatRating(value: number): string {
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}
