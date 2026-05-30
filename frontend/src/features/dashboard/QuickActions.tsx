import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { isReadOnlyDemo } from "@/lib/demoMode";

const actionLink =
  "inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm transition-colors";

export function QuickActions() {
  return (
    <Card padding="sm" className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-text-muted">Quick actions</p>
      <div className="flex flex-wrap gap-2">
        {!isReadOnlyDemo ? (
          <Link to="/add" className={`${actionLink} bg-accent font-medium text-bg hover:bg-accent-dim`}>
            Add book
          </Link>
        ) : null}
        <Link
          to="/ranking"
          className={`${actionLink} border border-border bg-surface text-text hover:bg-surface-hover`}
        >
          Open TBR ranking
        </Link>
        <Link
          to="/insights"
          className={`${actionLink} text-text-muted hover:bg-surface hover:text-text`}
        >
          View insights
        </Link>
      </div>
    </Card>
  );
}
