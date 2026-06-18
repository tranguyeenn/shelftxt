type ProgressBarProps = {
  value: number;
  label?: string;
};

export function ProgressBar({ value, label }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));

  return (
    <div className="grid gap-1.5">
      {label ? <div className="text-xs text-text-muted">{label}</div> : null}
      <div className="h-2 overflow-hidden rounded-full bg-bg-elevated">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${clamped}%` }}
          aria-hidden
        />
      </div>
    </div>
  );
}
