import type { ReactNode } from "react";

type AppLayoutProps = {
  sidebar: ReactNode;
  banner?: ReactNode;
  children: ReactNode;
};

export function AppLayout({ sidebar, banner, children }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-bg text-text md:flex">
      {sidebar}
      <div className="flex min-w-0 flex-1 flex-col pb-20 md:pb-0">
        {banner}
        <main className="flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,var(--color-accent-glow),transparent_34rem)] px-4 py-5 sm:px-6 md:p-8 lg:p-10">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
