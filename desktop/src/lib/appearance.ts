import { z } from "zod";

export const THEME_MODES = ["system", "light", "dark"] as const;
export const ACCENT_COLORS = ["violet", "blue", "teal", "emerald", "rose"] as const;
export const NEUTRAL_TONES = ["cool", "neutral", "warm"] as const;
export const DENSITY_MODES = ["compact", "standard", "comfortable"] as const;
export const UI_FONT_FAMILIES = ["system", "humanist", "compact"] as const;
export const DATA_FONT_FAMILIES = ["system", "dense", "mono"] as const;
export const CODE_FONT_FAMILIES = ["system", "cascadia", "jetbrains"] as const;
export const NULL_STYLES = ["muted", "badge", "plain"] as const;
export const CONTRAST_MODES = ["system", "high"] as const;
export const MOTION_MODES = ["system", "reduce"] as const;

export const FONT_SIZE_RANGES = Object.freeze({
  ui: Object.freeze({ min: 11, max: 16, defaultValue: 12 }),
  data: Object.freeze({ min: 10, max: 18, defaultValue: 12 }),
  code: Object.freeze({ min: 11, max: 22, defaultValue: 13 }),
  agent: Object.freeze({ min: 13, max: 24, defaultValue: 16 }),
});

export const APPEARANCE_RANGES = Object.freeze({
  agentLineHeight: Object.freeze({ min: 1.4, max: 2, defaultValue: 1.7, step: 0.1 }),
  codeLineHeight: Object.freeze({ min: 1.3, max: 2, defaultValue: 1.6, step: 0.1 }),
  tableRowHeight: Object.freeze({ min: 24, max: 44, defaultValue: 32, step: 2 }),
  sidebarWidth: Object.freeze({ min: 220, max: 420, defaultValue: 260, step: 10 }),
  artifactDockWidth: Object.freeze({ min: 22, max: 50, defaultValue: 28, step: 2 }),
});

export type ThemeMode = (typeof THEME_MODES)[number];
export type ResolvedTheme = Exclude<ThemeMode, "system">;
export type AccentColor = (typeof ACCENT_COLORS)[number];
export type NeutralTone = (typeof NEUTRAL_TONES)[number];
export type DensityMode = (typeof DENSITY_MODES)[number];
export type UiFontFamily = (typeof UI_FONT_FAMILIES)[number];
export type DataFontFamily = (typeof DATA_FONT_FAMILIES)[number];
export type CodeFontFamily = (typeof CODE_FONT_FAMILIES)[number];
export type NullStyle = (typeof NULL_STYLES)[number];
export type ContrastMode = (typeof CONTRAST_MODES)[number];
export type MotionMode = (typeof MOTION_MODES)[number];

const integerRange = (min: number, max: number) => z.number().int().min(min).max(max);
const decimalRange = (min: number, max: number) => z.number().min(min).max(max);

const appearancePreferencesSchema = z.object({
  version: z.literal(1),
  themeMode: z.enum(THEME_MODES),
  accentColor: z.enum(ACCENT_COLORS),
  neutralTone: z.enum(NEUTRAL_TONES),
  density: z.enum(DENSITY_MODES),
  uiFontFamily: z.enum(UI_FONT_FAMILIES),
  dataFontFamily: z.enum(DATA_FONT_FAMILIES),
  codeFontFamily: z.enum(CODE_FONT_FAMILIES),
  uiFontSize: integerRange(FONT_SIZE_RANGES.ui.min, FONT_SIZE_RANGES.ui.max),
  dataFontSize: integerRange(FONT_SIZE_RANGES.data.min, FONT_SIZE_RANGES.data.max),
  codeFontSize: integerRange(FONT_SIZE_RANGES.code.min, FONT_SIZE_RANGES.code.max),
  agentFontSize: integerRange(FONT_SIZE_RANGES.agent.min, FONT_SIZE_RANGES.agent.max),
  agentLineHeight: decimalRange(APPEARANCE_RANGES.agentLineHeight.min, APPEARANCE_RANGES.agentLineHeight.max),
  codeLineHeight: decimalRange(APPEARANCE_RANGES.codeLineHeight.min, APPEARANCE_RANGES.codeLineHeight.max),
  tableRowHeight: integerRange(APPEARANCE_RANGES.tableRowHeight.min, APPEARANCE_RANGES.tableRowHeight.max),
  tableGridLines: z.boolean(),
  tableZebraStripes: z.boolean(),
  tableNullStyle: z.enum(NULL_STYLES),
  freezePrimaryKey: z.boolean(),
  contrastMode: z.enum(CONTRAST_MODES),
  motionMode: z.enum(MOTION_MODES),
  sidebarWidth: integerRange(APPEARANCE_RANGES.sidebarWidth.min, APPEARANCE_RANGES.sidebarWidth.max),
  artifactDockWidth: integerRange(APPEARANCE_RANGES.artifactDockWidth.min, APPEARANCE_RANGES.artifactDockWidth.max),
}).strict();

export type AppearancePreferences = z.infer<typeof appearancePreferencesSchema>;
export type AppearancePreferencePatch = Partial<Omit<AppearancePreferences, "version">>;

export const DEFAULT_APPEARANCE: AppearancePreferences = Object.freeze({
  version: 1,
  themeMode: "system",
  accentColor: "violet",
  neutralTone: "cool",
  density: "standard",
  uiFontFamily: "system",
  dataFontFamily: "dense",
  codeFontFamily: "system",
  uiFontSize: FONT_SIZE_RANGES.ui.defaultValue,
  dataFontSize: FONT_SIZE_RANGES.data.defaultValue,
  codeFontSize: FONT_SIZE_RANGES.code.defaultValue,
  agentFontSize: FONT_SIZE_RANGES.agent.defaultValue,
  agentLineHeight: APPEARANCE_RANGES.agentLineHeight.defaultValue,
  codeLineHeight: APPEARANCE_RANGES.codeLineHeight.defaultValue,
  tableRowHeight: APPEARANCE_RANGES.tableRowHeight.defaultValue,
  tableGridLines: true,
  tableZebraStripes: false,
  tableNullStyle: "badge",
  freezePrimaryKey: true,
  contrastMode: "system",
  motionMode: "system",
  sidebarWidth: APPEARANCE_RANGES.sidebarWidth.defaultValue,
  artifactDockWidth: APPEARANCE_RANGES.artifactDockWidth.defaultValue,
});

export const APPEARANCE_STORAGE_KEY = "dbfox-appearance-v1";
export const APPEARANCE_EXPORT_FILENAME = "dbfox-appearance.json";
const LEGACY_THEME_STORAGE_KEY = "dbfox-theme";

type AppearanceStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function copyDefaults(): AppearancePreferences {
  return { ...DEFAULT_APPEARANCE };
}

export function loadAppearancePreferences(
  storage: AppearanceStorage | null | undefined,
): AppearancePreferences {
  if (!storage) return copyDefaults();
  try {
    const stored = storage.getItem(APPEARANCE_STORAGE_KEY);
    if (stored) {
      const parsed = appearancePreferencesSchema.safeParse(JSON.parse(stored));
      if (parsed.success) return parsed.data;
    }

    const legacyTheme = storage.getItem(LEGACY_THEME_STORAGE_KEY);
    if (legacyTheme === "light" || legacyTheme === "dark") {
      storage.removeItem(LEGACY_THEME_STORAGE_KEY);
      return { ...DEFAULT_APPEARANCE, themeMode: legacyTheme };
    }
  } catch {
    // Restricted WebViews may deny localStorage. Defaults remain fully usable.
  }
  return copyDefaults();
}

export function saveAppearancePreferences(
  storage: AppearanceStorage | null | undefined,
  preferences: AppearancePreferences,
): void {
  if (!storage) return;
  try {
    storage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // Appearance changes still apply for the current process when storage is unavailable.
  }
}

export function serializeAppearancePreferences(preferences: AppearancePreferences): string {
  return `${JSON.stringify(appearancePreferencesSchema.parse(preferences), null, 2)}\n`;
}

export function parseAppearancePreferences(raw: string): AppearancePreferences {
  return appearancePreferencesSchema.parse(JSON.parse(raw));
}

export function resolveTheme(
  mode: ThemeMode,
  systemTheme: ResolvedTheme,
): ResolvedTheme {
  return mode === "system" ? systemTheme : mode;
}

export function applyAppearanceToRoot(
  root: HTMLElement,
  preferences: AppearancePreferences,
  theme: ResolvedTheme,
): void {
  root.classList.toggle("dark", theme === "dark");
  root.dataset.theme = theme;
  root.dataset.themeMode = preferences.themeMode;
  root.dataset.accent = preferences.accentColor;
  root.dataset.neutralTone = preferences.neutralTone;
  root.dataset.density = preferences.density;
  root.dataset.uiFontFamily = preferences.uiFontFamily;
  root.dataset.dataFontFamily = preferences.dataFontFamily;
  root.dataset.codeFontFamily = preferences.codeFontFamily;
  root.dataset.uiFontSize = String(preferences.uiFontSize);
  root.dataset.dataFontSize = String(preferences.dataFontSize);
  root.dataset.codeFontSize = String(preferences.codeFontSize);
  root.dataset.agentFontSize = String(preferences.agentFontSize);
  root.dataset.agentLineHeight = String(preferences.agentLineHeight);
  root.dataset.codeLineHeight = String(preferences.codeLineHeight);
  root.dataset.tableRowHeight = String(preferences.tableRowHeight);
  root.dataset.tableGridLines = String(preferences.tableGridLines);
  root.dataset.tableZebraStripes = String(preferences.tableZebraStripes);
  root.dataset.tableNullStyle = preferences.tableNullStyle;
  root.dataset.freezePrimaryKey = String(preferences.freezePrimaryKey);
  root.dataset.contrast = preferences.contrastMode;
  root.dataset.motion = preferences.motionMode;
}
