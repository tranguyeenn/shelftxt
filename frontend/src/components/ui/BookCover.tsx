import { useEffect, useState } from "react";

import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";

type BookCoverProps = {
  title: string;
  coverUrl?: string | null;
  className?: string;
};

export function BookCover({ title, coverUrl, className = "" }: BookCoverProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [coverUrl]);

  if (!coverUrl || failed) {
    return <BookCoverPlaceholder title={title} className={className} />;
  }

  return (
    <img
      src={coverUrl}
      alt={`Cover of ${title}`}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`aspect-[2/3] rounded-lg border border-border bg-bg-elevated object-cover ${className}`}
    />
  );
}
