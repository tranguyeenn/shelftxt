import { NavLink } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { to: "/app", label: "Home", icon: DashboardIcon },
  { to: "/app/library", label: "Library", icon: LibraryIcon },
  { to: "/app/ranking", label: "Recommendations", icon: RankingIcon },
  { to: "/app/insights", label: "Stats", icon: InsightsIcon },
  { to: "/app/profile", label: "Profile", icon: ProfileIcon },
  { to: "/app/settings", label: "Settings", icon: SettingsIcon }
] as const;

function linkClass({ isActive }: { isActive: boolean }) {
  return [
    "flex items-center justify-center rounded-lg px-3 py-2.5 text-sm transition-colors md:w-full md:justify-start md:gap-3",
    isActive
      ? "bg-accent-muted text-accent"
      : "text-text-muted hover:bg-surface-hover hover:text-text"
  ].join(" ");
}

export function Sidebar() {
  const { logout, user } = useAuth();

  return (
    <aside className="md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-r md:border-border md:bg-bg-elevated">
      <div className="hidden border-b border-border-subtle px-4 py-5 md:block">
        <p className="text-base font-semibold tracking-tight text-text">ShelfTxt</p>
        <p className="mt-1 text-sm text-text-muted">read this next</p>
      </div>
      <nav
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-border bg-bg-elevated/95 px-1 py-2 backdrop-blur md:static md:flex md:flex-1 md:grid-cols-none md:flex-col md:gap-1 md:border-t-0 md:bg-transparent md:p-3"
        aria-label="Main"
      >
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/app"} className={linkClass} aria-label={label} title={label}>
            <Icon className="h-5 w-5 shrink-0 opacity-80 md:h-4 md:w-4" />
            <span className="hidden md:inline">{label}</span>
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
        <p className="mt-3 text-[10px] leading-relaxed text-text-dim">v0.2.0 · focused reading</p>
      </div>
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

function ProfileIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M20 21a8 8 0 0 0-16 0" />
      <circle cx="12" cy="7" r="4" />
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
