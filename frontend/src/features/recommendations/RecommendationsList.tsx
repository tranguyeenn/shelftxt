import { RecommendationCard } from "@/features/recommendations/RecommendationCard";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { stableRecommendationId, submitRecommendationFeedback } from "@/lib/recommendationFeedback";
import type { RecommendationItem } from "@/lib/types";
import { useEffect, useState } from "react";

type RecommendationsListProps = {
  items: RecommendationItem[];
  limit?: number;
};

export function RecommendationsList({ items, limit = 10 }: RecommendationsListProps) {
  const { settings } = useUserSettings();
  const [displayItems, setDisplayItems] = useState<RecommendationItem[]>(items);
  const [message, setMessage] = useState("");
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const slice = displayItems.slice(0, limit);

  useEffect(() => {
    setDisplayItems(items);
  }, [items]);

  async function handleNotInterested(item: RecommendationItem) {
    const key = itemKey(item);
    if (pendingIds.has(key)) return;
    const previous = displayItems;
    const index = previous.findIndex((candidate) => itemKey(candidate) === key);
    const currentIds = previous.slice(0, limit).map(stableRecommendationId);
    setPendingIds((current) => new Set(current).add(key));
    setDisplayItems((current) => current.filter((candidate) => itemKey(candidate) !== key));
    try {
      const response = await submitRecommendationFeedback(
        item,
        "not_interested",
        currentIds,
        settings.recommendationStyle
      );
      setMessage("Got it. We replaced that recommendation.");
      if (response.replacement) {
        setDisplayItems((current) => {
          const next = [...current];
          next.splice(Math.max(0, index), 0, response.replacement as RecommendationItem);
          return dedupeItems(next).slice(0, limit);
        });
      }
    } catch (error) {
      setDisplayItems(previous);
      setMessage("");
      throw error;
    } finally {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    }
  }

  return (
    <div className="grid gap-4">
      {message ? (
        <p className="text-sm text-text-muted" role="status">{message}</p>
      ) : null}
      {slice.map((item, index) => (
        <RecommendationCard
          key={itemKey(item) || `${item.book.title}-${index}`}
          item={item}
          rank={index + 1}
          onNotInterested={handleNotInterested}
        />
      ))}
    </div>
  );
}

function itemKey(item: RecommendationItem): string {
  return stableRecommendationId(item);
}

function dedupeItems(items: RecommendationItem[]): RecommendationItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = itemKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
