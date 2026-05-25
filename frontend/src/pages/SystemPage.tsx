import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export function SystemPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="System" subtitle="Understand how ShelfTxt thinks." />
      <Card>
        <p className="text-sm text-text-muted">Model notes and roadmap — next pass.</p>
      </Card>
    </div>
  );
}
