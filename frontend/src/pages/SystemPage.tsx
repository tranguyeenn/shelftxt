import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

export function SystemPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="System" subtitle="Understand how ShelfTxt thinks." />

      <Card className="grid gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-dim">How ranking works</h2>
          <Badge tone="accent">Transparent</Badge>
        </div>
        <p className="text-sm text-text-muted">
          Recommendations are computed from your own library history. Scores are based on author
          affinity, rating patterns, and recency signals rather than a black-box external model.
        </p>
        <ul className="grid gap-1 text-sm text-text-muted">
          <li>- Rating signal: how strongly your read ratings suggest similar taste.</li>
          <li>- Author signal: preference strength for the same author.</li>
          <li>- Recency signal: spacing between completed reads.</li>
          <li>- Other factors: small stabilizing term while genre weighting is still evolving.</li>
        </ul>
      </Card>

      <Card className="grid gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-dim">API surface</h2>
        <div className="grid gap-2 text-sm text-text-muted">
          <p>
            Core read paths: <code className="font-mono text-text">GET /books</code>,{" "}
            <code className="font-mono text-text">GET /recommend</code>
          </p>
          <p>
            Mutations: <code className="font-mono text-text">POST /books</code>,{" "}
            <code className="font-mono text-text">PATCH /books</code>,{" "}
            <code className="font-mono text-text">POST /books/import</code>
          </p>
          <p>
            Cache reset: <code className="font-mono text-text">POST /recommend/refresh</code>
          </p>
        </div>
      </Card>

      <Card className="grid gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-dim">Current direction</h2>
        <p className="text-sm text-text-muted">
          The stack is intentionally simple today (FastAPI + CSV-backed repository). Planned
          improvements include stronger ranking features, better caching behavior, and a path toward
          PostgreSQL-backed persistence.
        </p>
      </Card>
    </div>
  );
}
