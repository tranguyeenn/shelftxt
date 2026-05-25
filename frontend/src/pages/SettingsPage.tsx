import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export function SettingsPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="Settings" subtitle="Manage your preferences and data." />
      <Card>
        <p className="text-sm text-text-muted">Preferences, import/export, danger zone — next pass.</p>
      </Card>
    </div>
  );
}
