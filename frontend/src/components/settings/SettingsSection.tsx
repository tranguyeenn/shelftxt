import type { ReactNode } from "react";

import { Card } from "@/components/ui/Card";

type SettingsSectionProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export function SettingsSection({ title, description, children }: SettingsSectionProps) {
  return (
    <Card>
      <header className="border-b border-border-subtle pb-4">
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        {description ? <p className="mt-1 text-sm text-text-muted">{description}</p> : null}
      </header>
      <div className="mt-4 grid gap-4">{children}</div>
    </Card>
  );
}

type SettingRowProps = {
  label: string;
  hint?: string;
  children: ReactNode;
};

export function SettingRow({ label, hint, children }: SettingRowProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="sm:max-w-[55%]">
        <p className="text-sm font-medium text-text">{label}</p>
        {hint ? <p className="mt-1 text-sm text-text-muted">{hint}</p> : null}
      </div>
      <div className="shrink-0 sm:min-w-[12rem]">{children}</div>
    </div>
  );
}
