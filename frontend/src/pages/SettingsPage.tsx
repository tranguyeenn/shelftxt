import { PageHeader } from "@/components/layout/PageHeader";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsSection";
import { CsvImportSection } from "@/features/settings/CsvImportSection";
import { LibraryActions } from "@/features/settings/LibraryActions";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import {
  ACCENT_PRESETS,
  type AccentColor,
  type AppTheme,
  type RecommendationStyle
} from "@/lib/userSettings";

const selectClass =
  "w-full rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-text sm:w-auto";

export function SettingsPage() {
  const { settings, updateSettings } = useUserSettings();

  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <PageHeader
        title="Settings"
        subtitle="Manage your library, reading preferences, and how ShelfTxt looks."
      />

      <SettingsSection
        title="Data management"
        description="Import, export, or reset your library."
      >
        <CsvImportSection />

        <div className="border-t border-border-subtle pt-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-text-dim">
            More actions
          </p>
          <LibraryActions />
        </div>
      </SettingsSection>

      <SettingsSection
        title="Reading preferences"
        description="These settings shape how recommendations are ranked."
      >
        <SettingRow
          label="Recommendation style"
          hint="Balanced mixes familiarity and variety; Popular favors authors you already love; Discovery surfaces newer picks."
        >
          <select
            value={settings.recommendationStyle}
            onChange={(e) =>
              updateSettings({ recommendationStyle: e.target.value as RecommendationStyle })
            }
            className={selectClass}
          >
            <option value="balanced">Balanced</option>
            <option value="popular">Popular</option>
            <option value="discovery">Niche / discovery</option>
          </select>
        </SettingRow>

        <SettingRow
          label="Recommendation explanations"
          hint="Show why a book was recommended when browsing picks."
        >
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={settings.showRecommendationExplanations}
              onChange={(e) =>
                updateSettings({ showRecommendationExplanations: e.target.checked })
              }
              className="h-4 w-4 rounded border-border bg-bg-elevated accent-accent"
            />
            <span>{settings.showRecommendationExplanations ? "Visible" : "Hidden"}</span>
          </label>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Appearance" description="Customize layout and colors.">
        <SettingRow label="Compact mode" hint="Tighter spacing across the app.">
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={settings.compactMode}
              onChange={(e) => updateSettings({ compactMode: e.target.checked })}
              className="h-4 w-4 rounded border-border bg-bg-elevated accent-accent"
            />
            <span>{settings.compactMode ? "On" : "Off"}</span>
          </label>
        </SettingRow>

        <SettingRow label="Accent color" hint="Highlight color for buttons and links.">
          <div className="flex flex-wrap gap-2">
            {(Object.keys(ACCENT_PRESETS) as AccentColor[]).map((key) => {
              const preset = ACCENT_PRESETS[key];
              const active = settings.accentColor === key;
              return (
                <button
                  key={key}
                  type="button"
                  title={preset.label}
                  aria-label={preset.label}
                  aria-pressed={active}
                  onClick={() => updateSettings({ accentColor: key })}
                  className={[
                    "h-9 w-9 rounded-full border-2 transition-transform",
                    active ? "scale-110 border-text" : "border-transparent hover:scale-105"
                  ].join(" ")}
                  style={{ backgroundColor: preset.accent }}
                />
              );
            })}
          </div>
        </SettingRow>

        <SettingRow label="Theme" hint="Dark is the default ShelfTxt look.">
          <select
            value={settings.theme}
            onChange={(e) => updateSettings({ theme: e.target.value as AppTheme })}
            className={selectClass}
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="About ShelfTxt">
        <div className="grid gap-2 text-sm text-text-muted">
          <p className="text-base font-semibold text-text">ShelfTxt</p>
          <p>
            ShelfTxt helps organize your reading and generate transparent recommendations from
            your own library patterns.
          </p>
          <p>
            Add books, track progress, and discover what to read next based on authors and ratings
            you already enjoy.
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
