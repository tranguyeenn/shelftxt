import { Badge } from "@/components/ui/Badge";

type MoodTagsProps = {
  tags: string[];
};

export function MoodTags({ tags }: MoodTagsProps) {
  if (tags.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => (
        <Badge key={tag} tone="neutral">
          {tag}
        </Badge>
      ))}
    </div>
  );
}
