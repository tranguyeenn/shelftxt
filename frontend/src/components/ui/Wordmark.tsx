import { Link } from "react-router-dom";

type WordmarkProps = {
  to?: string;
  className?: string;
  darkText?: boolean;
};

export function Wordmark({ to, className = "", darkText = false }: WordmarkProps) {
  const content = (
    <span className={`inline-flex items-center gap-2 font-sans font-semibold ${className}`}>
      <span className="rounded-full bg-accent px-3 py-1 text-on-accent shadow-soft">shelf</span>
      <span className={darkText ? "text-[#191b19]" : "text-text"}>txt</span>
    </span>
  );

  if (to) {
    return (
      <Link to={to} aria-label="ShelfTxt home" className="inline-flex">
        {content}
      </Link>
    );
  }

  return content;
}
