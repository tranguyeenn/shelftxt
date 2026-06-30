import {
  ChangeEvent,
  KeyboardEvent,
  useEffect,
  useId,
  useState
} from "react";

import { StarRatingDisplay } from "@/components/ui/StarRatingDisplay";
import { StarIcon } from "@/components/ui/StarIcon";
import {
  STAR_SIZES,
  formatRatingValue,
  getStarFillLevel,
  parseRatingInput,
  ratingAriaLabel,
  roundToStep
} from "@/components/ui/starRating";

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
  sm: "max-h-7",
  md: "max-h-9",
  lg: "max-h-11"
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
  const baseId = useId();
  const starSize = STAR_SIZES[size];
  const [preview, setPreview] = useState<number | null>(null);
  const [inputText, setInputText] = useState(() => formatRatingValue(value));

  const displayValue = preview ?? value;

  useEffect(() => {
    setInputText(formatRatingValue(value));
  }, [value]);

  function commitInput(raw = inputText) {
    const next = parseRatingInput(raw, max, step);
    onChange(next === 0 ? null : next);
    setInputText(next == null ? "" : formatRatingValue(next));
    setPreview(null);
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    setInputText(event.target.value);
  }

  function handleInputBlur() {
    commitInput();
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      commitInput();
      event.currentTarget.blur();
    }
  }

  function handleStarClick(starIndex: number) {
    const next = starIndex + 1;
    onChange(next);
    setPreview(null);
    setInputText(formatRatingValue(next));
  }

  function handleStarHover(starIndex: number) {
    setPreview(starIndex + 1);
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
      setInputText(next == null ? "" : formatRatingValue(next));
    }
  }

  if (readOnly) {
    return <StarRatingDisplay value={value} max={max} size={size} showValue />;
  }

  return (
    <div className="grid min-w-0 max-w-full gap-2">
      <div
        role="group"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-valuenow={displayValue ?? undefined}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuetext={ratingAriaLabel(displayValue, max)}
        className="flex min-w-0 max-w-full items-center gap-0.5 overflow-hidden rounded-[14px] border border-border bg-bg-elevated p-1 outline-none ring-accent/40 transition-shadow focus:ring-2"
        onKeyDown={handleKeyDown}
        onPointerLeave={() => setPreview(null)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setPreview(null);
          }
        }}
      >
        {Array.from({ length: max }, (_, index) => (
          <button
            key={index}
            type="button"
            className={`group/star flex min-w-0 flex-1 cursor-pointer items-center justify-center rounded-xl px-0.5 py-1 transition-colors duration-150 ease-out hover:bg-white/[0.05] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 ${buttonSizeClass[size]}`}
            style={{ maxWidth: starSize + 8 }}
            aria-label={`Set rating to ${index + 1} stars`}
            onPointerEnter={() => handleStarHover(index)}
            onFocus={() => handleStarHover(index)}
            onClick={() => handleStarClick(index)}
          >
            <StarIcon
              fillLevel={getStarFillLevel(displayValue ?? 0, index)}
              size={starSize}
              gradientId={`${baseId}-input-${index}`}
              fluid
              className="transition-[filter] duration-150 group-hover/star:brightness-110"
            />
          </button>
        ))}
      </div>

      <div className="flex min-w-0 max-w-full flex-wrap items-center gap-x-3 gap-y-1">
        <label className="inline-flex min-w-0 items-center gap-1.5 text-sm text-text-muted">
          <span className="sr-only">Rating value</span>
          <input
            type="number"
            min={0}
            max={max}
            step={step}
            value={inputText}
            onChange={handleInputChange}
            onBlur={handleInputBlur}
            onKeyDown={handleInputKeyDown}
            aria-label="Rating value"
            className="w-[4.5rem] min-w-0 rounded-lg border border-border bg-surface px-2 py-1 text-center text-sm text-text tabular-nums outline-none transition-colors focus:border-accent/50 focus:ring-2 focus:ring-accent/30"
          />
          <span className="shrink-0 tabular-nums" aria-hidden>
            / {max}
          </span>
        </label>

        <span className="text-xs text-text-muted" aria-live="polite">
          {displayValue == null ? "Unrated" : `${formatRatingValue(displayValue)} / ${max}`}
        </span>

        <button
          type="button"
          className="shrink-0 cursor-pointer text-xs font-medium text-accent hover:text-accent-dim"
          onClick={() => {
            onChange(null);
            setPreview(null);
            setInputText("");
          }}
        >
          Clear rating
        </button>
      </div>
    </div>
  );
}
