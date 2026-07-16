import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatCard } from "@/components/ui/StatCard";
import { useAuth } from "@/contexts/AuthContext";
import { fetchAllLibraryBooks, type BookRecord } from "@/lib/books";
import { computeReadingPatterns, computeReadingSummary } from "@/lib/insights";
import {
  fetchProfile,
  loadCachedProfile,
  profileDisplayName,
  profileInitials,
  saveProfile,
  uploadAvatar,
  validateAvatarFile,
  type UserProfile
} from "@/lib/profile";

export function ProfilePage() {
  const { user } = useAuth();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [profile, setProfile] = useState<UserProfile>(() => loadCachedProfile());
  const [draft, setDraft] = useState<UserProfile>(() => loadCachedProfile());
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [books, loadedProfile] = await Promise.all([
        fetchAllLibraryBooks({ details: true }),
        fetchProfile(user)
      ]);
      setLibrary(books);
      setProfile(loadedProfile);
      setDraft(loadedProfile);
    } catch (err) {
      setLibrary([]);
      setError(err instanceof Error ? err.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    return () => {
      if (avatarPreview) {
        URL.revokeObjectURL(avatarPreview);
      }
    };
  }, [avatarPreview]);

  const summary = useMemo(() => computeReadingSummary(library), [library]);
  const patterns = useMemo(() => computeReadingPatterns(library), [library]);
  const averageRating = summary.averageRating !== null ? summary.averageRating.toFixed(1) : "—";
  const displayName = profileDisplayName(profile);
  const favoriteAuthor =
    patterns.find(
      (pattern): pattern is Extract<typeof pattern, { kind: "value" }> =>
        pattern.label === "Most read author" && pattern.kind === "value"
    )
      ?.value ?? "not enough data";
  const favoriteGenre =
    patterns.find(
      (pattern): pattern is Extract<typeof pattern, { kind: "value" }> =>
        pattern.label === "Favorite genre" && pattern.kind === "value"
    )
      ?.value ?? "not enough data";

  async function handleSaveProfile() {
    if (!user) {
      setError("You must be signed in to save your profile.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      let avatarUrl = draft.avatarUrl;
      if (avatarFile) {
        setUploading(true);
        avatarUrl = await uploadAvatar(user, avatarFile);
      }
      const saved = await saveProfile(user, {
        ...draft,
        avatarUrl,
        readingGoal:
          draft.readingGoal !== null && Number.isFinite(draft.readingGoal)
            ? Math.max(0, Math.floor(draft.readingGoal))
            : null
      });
      setProfile(saved);
      setDraft(saved);
      setAvatarFile(null);
      setAvatarPreview("");
      setEditing(false);
      setMessage("Profile saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setUploading(false);
      setSaving(false);
    }
  }

  function handleAvatarSelected(file: File | undefined) {
    if (!file) return;
    const validation = validateAvatarFile(file);
    if (validation) {
      setError(validation);
      return;
    }
    setError("");
    setAvatarFile(file);
    if (avatarPreview) {
      URL.revokeObjectURL(avatarPreview);
    }
    setAvatarPreview(URL.createObjectURL(file));
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Profile"
        subtitle="Your reading identity and goals."
        actions={
          <Button
            variant="secondary"
            onClick={() => {
              setDraft(profile);
              setAvatarFile(null);
              setAvatarPreview("");
              setEditing(true);
              setMessage("");
            }}
          >
            Edit profile
          </Button>
        }
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-text-muted">Loading profile…</p> : null}
      {message ? (
        <p className="rounded-lg border border-accent/30 bg-accent-muted px-4 py-3 text-sm text-accent-readable">
          {message}
        </p>
      ) : null}

      {!loading ? (
        <>
          <Card padding="lg" className="grid gap-5 md:grid-cols-[72px_1fr] md:items-center">
            {profile.avatarUrl ? (
              <img
                src={profile.avatarUrl}
                alt={`${displayName} avatar`}
                className="h-16 w-16 rounded-full border border-border object-cover"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-bg-elevated text-xl font-semibold text-accent-readable">
                {profileInitials(profile)}
              </div>
            )}
            <div>
              <h2 className="text-xl font-semibold text-text">{displayName}</h2>
              <p className="mt-1 text-sm text-text-muted">
                {profile.username ? `@${profile.username}` : user?.email ?? "reader"}
              </p>
              {profile.bio ? <p className="mt-3 max-w-2xl text-sm text-text-muted">{profile.bio}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {profile.readingGoal != null && profile.readingGoal > 0 ? (
                  <Badge tone="accent">reading goal: {profile.readingGoal} books</Badge>
                ) : (
                  <Badge tone="neutral">no reading goal set</Badge>
                )}
              </div>
            </div>
          </Card>

          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="books count" value={String(summary.totalBooks)} />
            <StatCard label="pages count" value={summary.totalPagesRead.toLocaleString()} />
            <StatCard label="average rating" value={averageRating} />
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <Card className="grid gap-3">
              <h3 className="text-sm font-medium text-text">reading preferences</h3>
              {profile.favoriteGenres ? (
                <div className="flex flex-wrap gap-2">
                  {profile.favoriteGenres.split(",").map((tag) => tag.trim()).filter(Boolean).map((tag) => (
                    <Badge key={tag} tone="neutral">
                      {tag}
                    </Badge>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No profile preferences yet."
                  description="Edit your profile to add favorite genres."
                />
              )}
            </Card>
            <Card className="grid gap-3">
              <h3 className="text-sm font-medium text-text">favorites</h3>
              <dl className="grid gap-3 text-sm">
                <div>
                  <dt className="text-text-dim">genres</dt>
                  <dd className="mt-1 text-text">{favoriteGenre}</dd>
                </div>
                <div>
                  <dt className="text-text-dim">authors</dt>
                  <dd className="mt-1 text-text">{favoriteAuthor}</dd>
                </div>
              </dl>
            </Card>
          </section>
        </>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-bg/80 p-4">
          <Card className="max-h-[90vh] w-full max-w-lg overflow-auto">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-text">Edit profile</h2>
                <p className="mt-1 text-sm text-text-muted">Update your public reading profile.</p>
              </div>
              <Button variant="ghost" onClick={() => setEditing(false)} disabled={saving}>
                Close
              </Button>
            </div>
            <div className="grid gap-4">
              <div className="grid gap-3">
                <span className="text-sm text-text-dim">Avatar</span>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex w-fit items-center gap-3 rounded-lg border border-border bg-bg-elevated p-3 text-left hover:border-accent"
                >
                  {avatarPreview || draft.avatarUrl ? (
                    <img
                      src={avatarPreview || draft.avatarUrl}
                      alt=""
                      className="h-14 w-14 rounded-full object-cover"
                    />
                  ) : (
                    <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface text-lg font-semibold text-accent-readable">
                      {profileInitials(draft)}
                    </span>
                  )}
                  <span className="grid gap-1">
                    <span className="text-sm font-medium text-text">Upload avatar</span>
                    <span className="text-xs text-text-muted">JPG, PNG, or WebP. 5 MB max.</span>
                  </span>
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(event) => handleAvatarSelected(event.target.files?.[0])}
                />
              </div>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Display name</span>
                <input
                  value={draft.displayName}
                  onChange={(event) => setDraft((prev) => ({ ...prev, displayName: event.target.value }))}
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Username</span>
                <input
                  value={draft.username}
                  onChange={(event) => setDraft((prev) => ({ ...prev, username: event.target.value }))}
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Bio</span>
                <textarea
                  value={draft.bio}
                  onChange={(event) => setDraft((prev) => ({ ...prev, bio: event.target.value }))}
                  rows={3}
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Reading goal</span>
                <input
                  type="number"
                  min={0}
                  value={draft.readingGoal ?? ""}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      readingGoal: event.target.value === "" ? null : Number(event.target.value)
                    }))
                  }
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Avatar URL</span>
                <input
                  value={draft.avatarUrl}
                  onChange={(event) => setDraft((prev) => ({ ...prev, avatarUrl: event.target.value }))}
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-text-dim">Favorite genres</span>
                <input
                  value={draft.favoriteGenres}
                  onChange={(event) => setDraft((prev) => ({ ...prev, favoriteGenres: event.target.value }))}
                  placeholder="literary fiction, memoir"
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text"
                />
              </label>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setEditing(false)} disabled={saving}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={() => void handleSaveProfile()} disabled={saving}>
                  {uploading ? "Uploading…" : saving ? "Saving…" : "Save profile"}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
