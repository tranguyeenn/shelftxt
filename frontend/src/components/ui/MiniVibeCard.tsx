type MiniVibeCardProps = {
  title?: string;
  mood: string;
  genre?: string;
  song?: string;
  spotifyUrl?: string;
};

export function MiniVibeCard({
  title = "current vibe",
  mood,
  genre,
  song,
  spotifyUrl
}: MiniVibeCardProps) {
  function openSong() {
    if (!spotifyUrl) return;
    window.open(spotifyUrl, "_blank", "noopener,noreferrer");
  }

  return (
    <aside className="rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium lowercase tracking-wide text-text-dim">{title}</p>
          <p className="mt-2 text-sm font-semibold text-text">{mood}</p>
          {genre ? <p className="mt-0.5 text-xs text-text-muted">{genre}</p> : null}
          {song ? <p className="mt-3 text-xs text-text-muted">song: {song}</p> : null}
        </div>
        {song ? (
          <button
            type="button"
            aria-label={spotifyUrl ? "Open song on Spotify" : "No music link available"}
            title={spotifyUrl ? "Open song on Spotify" : "No music link available"}
            onClick={openSong}
            disabled={!spotifyUrl}
            className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border text-accent transition-colors hover:border-accent hover:bg-accent-muted disabled:cursor-not-allowed disabled:text-text-dim disabled:hover:border-border disabled:hover:bg-transparent"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M7 17 17 7" />
              <path d="M9 7h8v8" />
            </svg>
          </button>
        ) : null}
      </div>
    </aside>
  );
}
