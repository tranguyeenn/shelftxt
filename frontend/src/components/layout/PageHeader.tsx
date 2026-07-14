type PageHeaderProps = {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  actions?: React.ReactNode;
};

export function PageHeader({ title, subtitle, eyebrow, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        {eyebrow ? (
          <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-accent-readable">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="font-serif text-5xl font-semibold leading-none tracking-[-0.025em] text-text sm:text-[56px]">
          {title}
        </h1>
        {subtitle ? <p className="mt-3 max-w-2xl text-[15px] leading-6 text-text-muted">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}
