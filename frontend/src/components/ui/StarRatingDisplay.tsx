import { useId } from "react";

import { StarIcon } from "@/components/ui/StarIcon";
import {
  STAR_SIZES,
  clampRating,
  formatRatingValue,
  getStarFillLevel,
  ratingAriaLabel
} from "@/components/ui/starRating";

type StarRatingDisplayProps = {
  value: number | null;
  max?: number;
  size?: "sm" | "md" | "lg";
  showValue?: boolean;
  className?: string;
};

export function StarRatingDisplay({
  value,
  max = 5,
  size = "md",
  showValue = false,
  className = ""
}: StarRatingDisplayProps) {
  const baseId = useId();
  const rating = clampRating(value, max);
  const starSize = STAR_SIZES[size];

  if (rating === null) {
    return (
      <span className={`inline-flex min-w-0 max-w-full items-center gap-2 text-text-muted ${className}`}>
        <span className="text-sm">Unrated</span>
      </span>
    );
  }

  const stars = (
    <span
      className="flex min-w-0 max-w-full items-center gap-0.5"
      role="img"
      aria-label={ratingAriaLabel(rating, max)}
    >
      {Array.from({ length: max }, (_, index) => (
        <span
          key={index}
          className="min-w-0 flex-1"
          style={{ maxWidth: starSize }}
        >
          <StarIcon
            fillLevel={getStarFillLevel(rating, index)}
            size={starSize}
            gradientId={`${baseId}-star-${index}`}
            fluid
          />
        </span>
      ))}
    </span>
  );

  if (!showValue) {
    return (
      <span className={`inline-flex min-w-0 max-w-full ${className}`}>
        {stars}
      </span>
    );
  }

  return (
    <span className={`grid min-w-0 max-w-full gap-1 ${className}`}>
      {stars}
      <span className="text-xs tabular-nums text-text-muted">
        {formatRatingValue(rating)} / {max}
      </span>
    </span>
  );
}
