import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variantClass: Record<Variant, string> = {
  primary:
    "bg-accent text-bg font-semibold shadow-soft hover:bg-accent-dim disabled:opacity-50",
  secondary:
    "border border-border bg-bg-elevated text-text-muted hover:border-white/15 hover:text-text disabled:opacity-50",
  ghost: "text-text-muted hover:text-text hover:bg-white/[0.05] disabled:opacity-50",
  danger:
    "bg-danger-muted text-danger border border-danger/30 hover:border-danger/60 disabled:opacity-50"
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-[14px] px-4 py-2 text-sm transition-colors disabled:cursor-not-allowed ${variantClass[variant]} ${className}`}
      {...props}
    />
  );
}
