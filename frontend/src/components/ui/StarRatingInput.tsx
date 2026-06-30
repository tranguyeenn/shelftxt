import { KeyboardEvent, MouseEvent, PointerEvent, useMemo, useState } from "react";

import { StarRatingDisplay } from "@/components/ui/StarRatingDisplay";

type StarRatingInputProps = {
  value: number | null;
  onChange: (value: number | null) => void;
  max?: number;
  step?: number;
  readOnly?: boolean;
  size?: "sm" | "md" | "lg";
  ariaLabel?: string;
};

const buttonSizeClass = {
  sm: "h-7 w-7 text-lg",
  md: "h-9 w-9 text-2xl",
  lg: "h-11 w-11 text-3xl"
};

export function StarRatingInput({
  value,
  onChange,
  max = 5,
  step = 0.25,
  readOnly = false,
  size = "md",
  ariaLabel = "Rating"
}: StarRatingInputProps) {
  const [preview, setPreview] = useState<number | null>(null);
  const displayValue = preview ?? value;
  const formattedValue = useMemo(() => formatRating(displayValue), [displayValue]);

  function valueFromPointer(
    event: PointerEvent<HTMLButtonElement> | MouseEvent<HTMLButtonElement>,
    starIndex: number
  ): number {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 1;
    const withinStar = Math.min(1, Math.max(step, Math.ceil(ratio / step) * step));
    return roundToStep(starIndex + withinStar, step, max);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (readOnly) return;

    const current = value ?? 0;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      next = roundToStep(current + step, step, max);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      next = Math.max(0, roundToStep(current - step, step, max));
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = max;
    } else if (event.key === "PageUp") {
      next = roundToStep(current + 1, step, max);
    } else if (event.key === "PageDown") {
      next = Math.max(0, roundToStep(current - 1, step, max));
    } else if (event.key === "Backspace" || event.key === "Delete") {
      next = null;
    }

    if (next !== null || event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      onChange(next === 0 ? null : next);
      setPreview(null);
    }
  }

  if (readOnly) {
    return <StarRatingDisplay value={value} max={max} size={size} showValue />;
  }

  return (
    <div className="grid gap-2">
      <div
        role="group"
        tabIndex={0}
        aria-label={ariaLabel}
        className="inline-flex w-fit items-center gap-0.5 rounded-[14px] border border-border bg-bg-elevated p-1 outline-none ring-accent/40 focus:ring-2"
        onKeyDown={handleKeyDown}
        onPointerLeave={() => setPreview(null)}
        onBlur={() => setPreview(null)}
      >
        {Array.from({ length: max }, (_, index) => (
          <button
            key={index}
            type="button"
            className={`relative cursor-pointer rounded-xl leading-none text-text-dim transition-colors hover:bg-white/[0.05] focus:outline-none ${buttonSizeClass[size]}`}
            aria-label={`Set rating to ${index + 1} stars`}
            onPointerMove={(event) => setPreview(valueFromPointer(event, index))}
            onFocus={() => setPreview(value ?? null)}
            onClick={(event) => onChange(valueFromPointer(event, index))}
          >
            <span aria-hidden>☆</span>
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 overflow-hidden text-accent"
              style={{ width: `${starFillPercent(displayValue, index)}%` }}
            >
              ★
            </span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-text-muted">
          {displayValue == null ? "Unrated" : `${formattedValue} / ${max}`}
        </span>
        <button
          type="button"
          className="cursor-pointer text-xs font-medium text-accent hover:text-accent-dim"
          onClick={() => {
            onChange(null);
            setPreview(null);
          }}
        >
          Clear rating
        </button>
      </div>
    </div>
  );
}

function starFillPercent(value: number | null, index: number): number {
  if (value == null) return 0;
  return Math.min(100, Math.max(0, (value - index) * 100));
}

function roundToStep(value: number, step: number, max: number): number {
  return Math.min(max, Math.max(0, Math.round(value / step) * step));
}

function formatRating(value: number | null): string {
  if (value == null) return "0";
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}
