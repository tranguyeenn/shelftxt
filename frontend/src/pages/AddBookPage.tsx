import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export function AddBookPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="Add Book" subtitle="Simple input flow for new library entries." />
      <Card className="mx-auto w-full max-w-lg">
        <p className="text-sm text-text-muted">Form fields (title, author, ISBN, status, rating, progress) — next pass.</p>
      </Card>
    </div>
  );
}
