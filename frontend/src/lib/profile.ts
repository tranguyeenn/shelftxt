import type { User } from "@supabase/supabase-js";

import { fetchJson } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export type UserProfile = {
  displayName: string;
  username: string;
  bio: string;
  readingGoal: number | null;
  avatarUrl: string;
  favoriteGenres: string;
};

const STORAGE_KEY = "shelftxt.profile";
const AVATAR_BUCKET = "avatars";
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const ALLOWED_AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

const DEFAULT_PROFILE: UserProfile = {
  displayName: "",
  username: "",
  bio: "",
  readingGoal: null,
  avatarUrl: "",
  favoriteGenres: ""
};

type ProfileRow = {
  id?: string;
  email?: string;
  display_name?: string | null;
  username?: string | null;
  bio?: string | null;
  reading_goal?: number | null;
  avatar_url?: string | null;
  favorite_genres?: string | null;
};

function userFallbackUsername(user: User | null): string {
  const metadataUsername =
    typeof user?.user_metadata?.username === "string" ? user.user_metadata.username : "";
  return metadataUsername || user?.email?.split("@")[0] || "";
}

function fromRow(row: ProfileRow | null | undefined, user: User | null): UserProfile {
  return {
    displayName: row?.display_name ?? "",
    username: row?.username ?? userFallbackUsername(user),
    bio: row?.bio ?? "",
    readingGoal: row?.reading_goal ?? null,
    avatarUrl: row?.avatar_url ?? "",
    favoriteGenres: row?.favorite_genres ?? ""
  };
}

function toPayload(profile: UserProfile, user: User) {
  return {
    username: profile.username.trim() || userFallbackUsername(user) || `reader-${user.id.slice(0, 8)}`,
    display_name: profile.displayName.trim() || null,
    bio: profile.bio.trim() || null,
    reading_goal: profile.readingGoal,
    avatar_url: profile.avatarUrl.trim() || null,
    favorite_genres: profile.favoriteGenres.trim() || null
  };
}

function cacheProfile(profile: UserProfile): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
}

export function loadCachedProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PROFILE };
    return { ...DEFAULT_PROFILE, ...(JSON.parse(raw) as Partial<UserProfile>) };
  } catch {
    return { ...DEFAULT_PROFILE };
  }
}

export async function fetchProfile(user: User | null): Promise<UserProfile> {
  if (!user) return loadCachedProfile();

  const data = await fetchJson<ProfileRow>("/profile/me");
  const profile = fromRow(data, user);
  cacheProfile(profile);
  return profile;
}

export async function saveProfile(user: User, profile: UserProfile): Promise<UserProfile> {
  const data = await fetchJson<ProfileRow>("/profile/me", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toPayload(profile, user))
  });
  const saved = fromRow(data, user);
  cacheProfile(saved);
  return saved;
}

export function validateAvatarFile(file: File): string | null {
  if (!ALLOWED_AVATAR_TYPES.has(file.type)) {
    return "Avatar must be a JPG, PNG, or WebP image.";
  }
  if (file.size > MAX_AVATAR_BYTES) {
    return "Avatar must be 5 MB or smaller.";
  }
  return null;
}

async function fileToWebp(file: File): Promise<Blob> {
  if (file.type === "image/webp") return file;

  const image = new Image();
  const objectUrl = URL.createObjectURL(file);
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Could not read avatar image."));
      image.src = objectUrl;
    });

    const canvas = document.createElement("canvas");
    const maxSize = 512;
    const scale = Math.min(1, maxSize / Math.max(image.width, image.height));
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not prepare avatar image.");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (blob) resolve(blob);
          else reject(new Error("Could not convert avatar image."));
        },
        "image/webp",
        0.88
      );
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function uploadAvatar(user: User, file: File): Promise<string> {
  const validation = validateAvatarFile(file);
  if (validation) throw new Error(validation);

  const webp = await fileToWebp(file);
  const path = `${user.id}/avatar.webp`;
  const { error } = await supabase.storage
    .from(AVATAR_BUCKET)
    .upload(path, webp, {
      cacheControl: "3600",
      contentType: "image/webp",
      upsert: true
    });

  if (error) {
    throw error;
  }

  const { data } = supabase.storage.from(AVATAR_BUCKET).getPublicUrl(path);
  return `${data.publicUrl}?v=${Date.now()}`;
}

export function profileDisplayName(profile: UserProfile): string {
  return profile.displayName.trim() || profile.username.trim() || "Reader";
}

export function profileInitials(profile: UserProfile): string {
  const source = profileDisplayName(profile);
  const parts = source.split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase()).join("") || "R";
}
