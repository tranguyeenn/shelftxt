import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variantClass: Record<Variant, string> = {
  primary:
    "bg-accent text-bg font-medium hover:bg-accent-dim disabled:opacity-50",
  secondary:
    "bg-surface border border-border text-text hover:bg-surface-hover disabled:opacity-50",
  ghost: "text-text-muted hover:text-text hover:bg-surface disabled:opacity-50",
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
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm transition-colors ${variantClass[variant]} ${className}`}
      {...props}
    />
  );
}
