import { NavLink } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";
import { isReadOnlyDemo } from "@/lib/demoMode";

const navItems = [
  { to: "/", label: "Dashboard", icon: DashboardIcon },
  { to: "/library", label: "Library", icon: LibraryIcon },
  { to: "/ranking", label: "Recommendations", icon: RankingIcon },
  { to: "/add", label: "Add Book", icon: AddIcon, hideInDemo: true },
  { to: "/insights", label: "Insights", icon: InsightsIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon }
] as const;

function linkClass({ isActive }: { isActive: boolean }) {
  return [
    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
    isActive
      ? "bg-accent-muted text-accent"
      : "text-text-muted hover:bg-surface-hover hover:text-text"
  ].join(" ");
}

export function Sidebar() {
  const { logout, user } = useAuth();

  return (
    <aside className="flex w-full shrink-0 flex-row items-center gap-2 border-b border-border bg-bg-elevated px-3 py-2 md:w-56 md:flex-col md:items-stretch md:border-b-0 md:border-r md:px-0 md:py-0">
      <div className="hidden border-b border-border-subtle px-4 py-5 md:block">
        <p className="font-mono text-xs uppercase tracking-widest text-text-dim">ShelfTxt</p>
        <p className="mt-1 text-sm text-text-muted">Recommendation lab</p>
      </div>
      <p className="font-mono text-xs uppercase tracking-widest text-text-dim md:hidden">ShelfTxt</p>
      <nav
        className="flex flex-1 flex-row gap-1 overflow-x-auto p-1 md:flex-col md:overflow-visible md:p-3"
        aria-label="Main"
      >
        {navItems
          .filter((item) => !(isReadOnlyDemo && "hideInDemo" in item && item.hideInDemo))
          .map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={linkClass}>
            <Icon className="h-4 w-4 shrink-0 opacity-80" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="hidden border-t border-border-subtle px-4 py-3 md:block">
        <p className="truncate text-xs text-text-muted">{user?.email}</p>
        <button
          className="mt-2 cursor-pointer text-xs text-text-dim transition-colors hover:text-text"
          type="button"
          onClick={() => void logout()}
        >
          Log out
        </button>
        <p className="mt-3 font-mono text-[10px] leading-relaxed text-text-dim">v0.2.0 · rule-based ranker</p>
      </div>
      <button
        className="shrink-0 cursor-pointer rounded-lg px-3 py-2 text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-text md:hidden"
        type="button"
        onClick={() => void logout()}
      >
        Log out
      </button>
    </aside>
  );
}

function DashboardIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <rect x="3" y="3" width="8" height="8" rx="1" />
      <rect x="13" y="3" width="8" height="4" rx="1" />
      <rect x="13" y="9" width="8" height="12" rx="1" />
      <rect x="3" y="13" width="8" height="8" rx="1" />
    </svg>
  );
}

function LibraryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
    </svg>
  );
}

function RankingIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M4 6h16M4 12h16M4 18h10" />
      <path d="M18 15v6M15 18h6" />
    </svg>
  );
}

function AddIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function InsightsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M3 3v18h18" />
      <path d="M7 16l4-5 4 3 5-7" />
    </svg>
  );
}

function SettingsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}
