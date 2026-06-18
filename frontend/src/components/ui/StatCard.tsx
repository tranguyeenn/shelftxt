type StatCardProps = {
  label: string;
  value: string;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-bg-elevated px-4 py-3">
      <p className="text-xs font-medium lowercase tracking-wide text-text-dim">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-text">{value}</p>
      {hint ? <p className="mt-1 text-xs text-text-muted">{hint}</p> : null}
    </div>
  );
}
