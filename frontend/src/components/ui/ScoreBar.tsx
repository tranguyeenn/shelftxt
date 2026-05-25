import { formatScore } from "@/lib/scoring";

const barFill: Record<string, string> = {
  "score-rating": "bg-score-rating",
  "score-recency": "bg-score-recency",
  "score-author": "bg-score-author",
  "score-other": "bg-score-other"
};

type ScoreBarProps = {
  label: string;
  value: number;
  weight: number;
  color: string;
  explanation: string;
};

export function ScoreBar({ label, value, weight, color, explanation }: ScoreBarProps) {
  const pct = Math.round(value * 100);
  const fill = barFill[color] ?? "bg-accent";

  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-text">{label}</span>
        <span className="font-mono text-text-muted">
          {formatScore(value)}{" "}
          <span className="text-text-dim">· weight {Math.round(weight * 100)}%</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-bg-elevated">
        <div className={`h-full rounded-full transition-all ${fill}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-text-muted">{explanation}</p>
    </div>
  );
}
