export type RecommendationStyle = "balanced" | "popular" | "discovery";
export type AccentColor = "teal" | "blue" | "violet" | "amber" | "rose";
export type AppTheme = "dark" | "light" | "system";

export type UserSettings = {
  recommendationStyle: RecommendationStyle;
  showRecommendationExplanations: boolean;
  compactMode: boolean;
  accentColor: AccentColor;
  theme: AppTheme;
  showVibeSuggestions: boolean;
};

const STORAGE_KEY = "shelftxt.userSettings";

const DEFAULTS: UserSettings = {
  recommendationStyle: "balanced",
  showRecommendationExplanations: true,
  compactMode: false,
  accentColor: "teal",
  theme: "dark",
  showVibeSuggestions: false
};

export const ACCENT_PRESETS: Record<
  AccentColor,
  { label: string; accent: string; accentDim: string; accentMuted: string }
> = {
  teal: {
    label: "Shelf green",
    accent: "#8EE88F",
    accentDim: "#6FDC72",
    accentMuted: "rgba(142, 232, 143, 0.14)"
  },
  blue: {
    label: "Sage",
    accent: "#7F9185",
    accentDim: "#9AA99D",
    accentMuted: "rgba(127, 145, 133, 0.14)"
  },
  violet: {
    label: "Olive",
    accent: "#A5A06B",
    accentDim: "#BBB57C",
    accentMuted: "rgba(165, 160, 107, 0.14)"
  },
  amber: {
    label: "Ochre",
    accent: "#B6A27C",
    accentDim: "#C9B891",
    accentMuted: "rgba(182, 162, 124, 0.14)"
  },
  rose: {
    label: "Clay",
    accent: "#B98275",
    accentDim: "#CC978B",
    accentMuted: "rgba(185, 130, 117, 0.14)"
  }
};

function normalizeSettings(parsed: Partial<UserSettings>): UserSettings {
  const accent = parsed.accentColor ?? DEFAULTS.accentColor;
  const theme = parsed.theme ?? DEFAULTS.theme;
  const style = parsed.recommendationStyle ?? DEFAULTS.recommendationStyle;

  return {
    recommendationStyle:
      style === "popular" || style === "discovery" ? style : "balanced",
    showRecommendationExplanations:
      parsed.showRecommendationExplanations ?? DEFAULTS.showRecommendationExplanations,
    compactMode: parsed.compactMode ?? DEFAULTS.compactMode,
    accentColor: accent in ACCENT_PRESETS ? accent : DEFAULTS.accentColor,
    theme: theme === "light" || theme === "system" ? theme : "dark",
    showVibeSuggestions: parsed.showVibeSuggestions ?? DEFAULTS.showVibeSuggestions
  };
}

export function loadUserSettings(): UserSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    return normalizeSettings(JSON.parse(raw) as Partial<UserSettings>);
  } catch {
    return { ...DEFAULTS };
  }
}

export function applyCompactMode(enabled: boolean): void {
  document.documentElement.dataset.compact = enabled ? "true" : "false";
}

export function applyAccentColor(accent: AccentColor): void {
  const preset = ACCENT_PRESETS[accent];
  const root = document.documentElement;
  root.style.setProperty("--color-accent", preset.accent);
  root.style.setProperty("--color-accent-dim", preset.accentDim);
  root.style.setProperty("--color-accent-muted", preset.accentMuted);
  root.dataset.accent = accent;
}

export function applyTheme(theme: AppTheme): void {
  const resolved =
    theme === "system" && window.matchMedia?.("(prefers-color-scheme: light)").matches
      ? "light"
      : theme === "system"
        ? "dark"
        : theme;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePreference = theme;
}

export function applyAppearance(settings: UserSettings): void {
  applyCompactMode(settings.compactMode);
  applyAccentColor(settings.accentColor);
  applyTheme(settings.theme);
}

export function saveUserSettings(next: UserSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  applyAppearance(next);
}

export function initUserSettings(): UserSettings {
  const settings = loadUserSettings();
  applyAppearance(settings);
  return settings;
}

export function recommendQuery(
  settings: UserSettings,
  refresh = false,
  excludeIds: string[] = [],
  filters: RecommendationFilters = {}
): string {
  const params = new URLSearchParams({
    style: settings.recommendationStyle,
    top_n: "10"
  });
  if (refresh) {
    params.set("refresh", "true");
  }
  if (excludeIds.length > 0) {
    params.set("exclude_ids", excludeIds.join(","));
  }
  const genre = filters.genre?.trim();
  if (genre) {
    params.set("genre", genre);
  }
  if (filters.min_pages !== undefined) {
    params.set("min_pages", String(filters.min_pages));
  }
  if (filters.max_pages !== undefined) {
    params.set("max_pages", String(filters.max_pages));
  }
  return `/recommend?${params.toString()}`;
}

export function recommendationSectionsQuery(
  settings: UserSettings,
  refresh = false,
  excludeIds: string[] = [],
  filters: RecommendationFilters = {}
): string {
  const params = new URLSearchParams({
    style: settings.recommendationStyle,
    limit: "10"
  });
  if (refresh) {
    params.set("refresh", "true");
  }
  if (excludeIds.length > 0) {
    params.set("exclude_ids", excludeIds.join(","));
  }
  const genre = filters.genre?.trim();
  if (genre) {
    params.set("genre", genre);
  }
  if (filters.min_pages !== undefined) {
    params.set("min_pages", String(filters.min_pages));
  }
  if (filters.max_pages !== undefined) {
    params.set("max_pages", String(filters.max_pages));
  }
  return `/recommendations/sections?${params.toString()}`;
}

export type RecommendationFilters = {
  genre?: string;
  min_pages?: number;
  max_pages?: number;
};
