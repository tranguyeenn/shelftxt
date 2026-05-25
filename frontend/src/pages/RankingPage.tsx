import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export function RankingPage() {
  return (
    <div className="grid gap-6">
      <PageHeader
        title="TBR Ranking"
        subtitle="Your To-Be-Read books ranked by recommendation score."
      />
      <Card>
        <p className="text-sm text-text-muted">
          Ranking table coming next — scores will mirror the dashboard breakdown per row.
        </p>
      </Card>
    </div>
  );
}
