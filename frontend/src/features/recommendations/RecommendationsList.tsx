import { RecommendationCard } from "@/features/recommendations/RecommendationCard";
import type { RecommendationItem } from "@/lib/types";

type RecommendationsListProps = {
  items: RecommendationItem[];
  limit?: number;
};

export function RecommendationsList({ items, limit = 10 }: RecommendationsListProps) {
  const slice = items.slice(0, limit);

  return (
    <div className="grid gap-4">
      {slice.map((item, index) => (
        <RecommendationCard key={item.book.id || `${item.book.title}-${index}`} item={item} rank={index + 1} />
      ))}
    </div>
  );
}
