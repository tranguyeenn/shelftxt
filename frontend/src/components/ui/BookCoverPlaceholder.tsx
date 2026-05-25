type BookCoverPlaceholderProps = {
  title?: string;
  className?: string;
};

/** Dark-theme cover stand-in until per-book cover art exists. */
export function BookCoverPlaceholder({ title, className = "" }: BookCoverPlaceholderProps) {
  const label = title?.trim().slice(0, 2).toUpperCase() || "—";

  return (
    <div
      className={`flex aspect-[2/3] flex-col overflow-hidden rounded-lg border border-border bg-bg-elevated ${className}`}
      aria-hidden
    >
      <div className="flex flex-1 flex-col justify-between p-3">
        <div className="h-px w-8 bg-accent/60" />
        <p className="font-mono text-[10px] uppercase tracking-widest text-text-dim">TBR</p>
        <p className="font-mono text-2xl font-semibold text-accent/80">{label}</p>
        <div className="grid gap-1">
          <div className="h-0.5 w-full bg-border" />
          <div className="h-0.5 w-4/5 bg-border" />
          <div className="h-0.5 w-3/5 bg-border" />
        </div>
      </div>
    </div>
  );
}
