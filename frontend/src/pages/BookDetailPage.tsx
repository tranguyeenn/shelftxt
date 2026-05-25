import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export function BookDetailPage() {
  const { id } = useParams();

  return (
    <div className="grid gap-6">
      <Link to="/ranking" className="text-sm text-accent hover:underline">
        ← Back to TBR
      </Link>
      <PageHeader title="Book detail" subtitle={`ID: ${decodeURIComponent(id ?? "")}`} />
      <Card>
        <p className="text-sm text-text-muted">
          Tabs: Why Recommended · Details · Your Data — planned in the next implementation pass.
        </p>
      </Card>
    </div>
  );
}
