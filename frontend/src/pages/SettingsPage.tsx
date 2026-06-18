import { PageHeader } from "@/components/layout/PageHeader";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsSection";
import { CsvImportSection } from "@/features/settings/CsvImportSection";
import { LibraryActions } from "@/features/settings/LibraryActions";
import { MetadataSection } from "@/features/settings/MetadataSection";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/contexts/AuthContext";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import {
  ACCENT_PRESETS,
  type AccentColor,
  type AppTheme,
  type RecommendationStyle
} from "@/lib/userSettings";

const selectClass =
  "w-full cursor-pointer rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-text sm:w-auto";

export function SettingsPage() {
  const { logout, user } = useAuth();
  const { settings, updateSettings } = useUserSettings();

  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <PageHeader
        title="Settings"
        subtitle="Manage your library, reading preferences, and how ShelfTxt looks."
      />

      <SettingsSection title="Account" description="Manage the signed-in ShelfTxt account.">
        <SettingRow label="Email">
          <p className="truncate text-sm text-text">{user?.email ?? "Unknown"}</p>
        </SettingRow>
        <SettingRow label="User ID">
          <p className="max-w-[16rem] truncate font-mono text-xs text-text-muted">{user?.id}</p>
        </SettingRow>
        <div>
          <Button variant="secondary" onClick={() => void logout()}>
            Log out
          </Button>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Preferences"
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

        <SettingRow
          label="Show reading vibe suggestions"
          hint="Small mood cues may appear beside recommendations and reading progress."
        >
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={settings.showVibeSuggestions}
              onChange={(e) =>
                updateSettings({ showVibeSuggestions: e.target.checked })
              }
              className="h-4 w-4 rounded border-border bg-bg-elevated accent-accent"
            />
            <span>{settings.showVibeSuggestions ? "On" : "Off"}</span>
          </label>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Theme" description="Customize layout and colors.">
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
                    "h-9 w-9 cursor-pointer rounded-full border-2 transition-transform",
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
            <option value="system">System</option>
          </select>
        </SettingRow>
      </SettingsSection>

      <SettingsSection
        title="Import/export data"
        description="Import, export, or reset your library."
      >
        <CsvImportSection />

        <div className="border-t border-border-subtle pt-4">
          <p className="mb-3 text-xs font-medium lowercase tracking-wide text-text-dim">
            more actions
          </p>
          <LibraryActions />
        </div>
      </SettingsSection>

      <MetadataSection />

      <SettingsSection title="Notifications" description="Reading reminders and quiet nudges.">
        <SettingRow label="Reading reminders">
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              disabled
              className="h-4 w-4 rounded border-border bg-bg-elevated accent-accent"
            />
            <span>Off - reminders are not available yet</span>
          </label>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Privacy" description="Control local account and library data.">
        <p className="text-sm text-text-muted">Your library data stays tied to your ShelfTxt account.</p>
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
