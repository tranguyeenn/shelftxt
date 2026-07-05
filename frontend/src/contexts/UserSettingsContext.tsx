import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import {
  initUserSettings,
  saveUserSettings,
  type RecommendationFilters,
  type UserSettings
} from "@/lib/userSettings";

type UserSettingsContextValue = {
  settings: UserSettings;
  updateSettings: (patch: Partial<UserSettings>) => void;
  recommendationFilters: RecommendationFilters;
  setRecommendationFilters: (filters: RecommendationFilters) => void;
};

const UserSettingsContext = createContext<UserSettingsContextValue | null>(null);

export function UserSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<UserSettings>(() => initUserSettings());
  const [recommendationFilters, setRecommendationFilters] = useState<RecommendationFilters>({});

  const updateSettings = useCallback((patch: Partial<UserSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveUserSettings(next);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ settings, updateSettings, recommendationFilters, setRecommendationFilters }),
    [settings, updateSettings, recommendationFilters]
  );

  return (
    <UserSettingsContext.Provider value={value}>{children}</UserSettingsContext.Provider>
  );
}

export function useUserSettings(): UserSettingsContextValue {
  const ctx = useContext(UserSettingsContext);
  if (!ctx) {
    throw new Error("useUserSettings must be used within UserSettingsProvider");
  }
  return ctx;
}
