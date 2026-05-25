import { Card } from "@/components/ui/Card";
import { ScoreBar } from "@/components/ui/ScoreBar";
import type { ScoreBreakdown as Breakdown } from "@/lib/scoring";

type ScoreBreakdownProps = {
  breakdown: Breakdown;
};

export function ScoreBreakdownPanel({ breakdown }: ScoreBreakdownProps) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-text">Score breakdown</h2>
      <p className="mt-1 text-xs text-text-muted">
        Transparent signal weights used to explain this recommendation.
      </p>
      <div className="mt-5 grid gap-5">
        {breakdown.factors.map((factor) => (
          <ScoreBar
            key={factor.key}
            label={factor.label}
            value={factor.value}
            weight={factor.weight}
            color={factor.color}
            explanation={`${factor.explanation} Weight: ${Math.round(factor.weight * 100)}%.`}
          />
        ))}
      </div>
    </Card>
  );
}
