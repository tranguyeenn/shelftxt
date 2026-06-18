import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  padding?: "sm" | "md" | "lg";
};

const paddingClass = {
  sm: "p-4",
  md: "p-5",
  lg: "p-6"
};

export function Card({ padding = "md", className = "", children, ...props }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-border bg-surface ${paddingClass[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
