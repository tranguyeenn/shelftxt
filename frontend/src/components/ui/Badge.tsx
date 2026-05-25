type BadgeProps = {
  children: React.ReactNode;
  tone?: "accent" | "neutral" | "success" | "warning";
};

const toneClass = {
  accent: "bg-accent-muted text-accent border-accent/20",
  neutral: "bg-bg-elevated text-text-muted border-border",
  success: "bg-score-rating/15 text-score-rating border-score-rating/25",
  warning: "bg-score-recency/15 text-score-recency border-score-recency/25"
};

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${toneClass[tone]}`}
    >
      {children}
    </span>
  );
}
