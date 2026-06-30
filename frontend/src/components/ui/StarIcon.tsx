import { STAR_FILLED_COLOR, STAR_PATH, type StarFillLevel } from "@/components/ui/starRating";

type StarIconProps = {
  fillLevel: StarFillLevel;
  size: number;
  gradientId: string;
  className?: string;
  fluid?: boolean;
};

export function StarIcon({
  fillLevel,
  size,
  gradientId,
  className = "",
  fluid = false
}: StarIconProps) {
  const fillStop = `${fillLevel}%`;

  return (
    <svg
      width={fluid ? undefined : size}
      height={fluid ? undefined : size}
      viewBox="0 0 24 24"
      style={fluid ? { maxHeight: size } : undefined}
      className={`block ${fluid ? "h-auto w-full max-w-full" : "shrink-0"} ${className}`}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset={fillStop} stopColor={STAR_FILLED_COLOR} />
          <stop offset={fillStop} stopColor="var(--color-star-empty)" />
        </linearGradient>
      </defs>
      <path d={STAR_PATH} fill={`url(#${gradientId})`} />
    </svg>
  );
}
