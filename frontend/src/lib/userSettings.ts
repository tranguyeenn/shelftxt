export type RecommendationStyle = "balanced" | "popular" | "discovery";
export type AccentColor = "teal" | "blue" | "violet" | "amber" | "rose";
export type AppTheme = "dark" | "light";

export type UserSettings = {
  recommendationStyle: RecommendationStyle;
  showRecommendationExplanations: boolean;
  compactMode: boolean;
  accentColor: AccentColor;
  theme: AppTheme;
};

const STORAGE_KEY = "shelftxt.userSettings";

const DEFAULTS: UserSettings = {
  recommendationStyle: "balanced",
  showRecommendationExplanations: true,
  compactMode: false,
  accentColor: "teal",
  theme: "dark"
};

export const ACCENT_PRESETS: Record<
  AccentColor,
  { label: string; accent: string; accentDim: string; accentMuted: string }
> = {
  teal: {
    label: "Teal",
    accent: "#2dd4bf",
    accentDim: "#14b8a6",
    accentMuted: "rgba(45, 212, 191, 0.12)"
  },
  blue: {
    label: "Blue",
    accent: "#60a5fa",
    accentDim: "#3b82f6",
    accentMuted: "rgba(96, 165, 250, 0.14)"
  },
  violet: {
    label: "Violet",
    accent: "#a78bfa",
    accentDim: "#8b5cf6",
    accentMuted: "rgba(167, 139, 250, 0.14)"
  },
  amber: {
    label: "Amber",
    accent: "#fbbf24",
    accentDim: "#f59e0b",
    accentMuted: "rgba(251, 191, 36, 0.14)"
  },
  rose: {
    label: "Rose",
    accent: "#fb7185",
    accentDim: "#f43f5e",
    accentMuted: "rgba(251, 113, 133, 0.14)"
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
    theme: theme === "light" ? "light" : "dark"
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
  document.documentElement.dataset.theme = theme;
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
  excludeIds: string[] = []
): string {
  const params = new URLSearchParams({ style: settings.recommendationStyle });
  if (refresh) {
    params.set("refresh", "true");
  }
  if (excludeIds.length > 0) {
    params.set("exclude_ids", excludeIds.join(","));
  }
  return `/recommend?${params.toString()}`;
}
