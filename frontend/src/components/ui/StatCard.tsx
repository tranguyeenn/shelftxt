type StatCardProps = {
  label: string;
  value: string;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-elevated px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-text-dim">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-text">{value}</p>
      {hint ? <p className="mt-1 text-xs text-text-muted">{hint}</p> : null}
    </div>
  );
}
