import { createContext, useContext } from "react";

import {
  DEFAULT_APPEARANCE,
  type AppearancePreferencePatch,
  type AppearancePreferences,
  type ResolvedTheme,
  type ThemeMode,
} from "../lib/appearance";

export type Theme = ResolvedTheme;

export interface ThemeContextValue {
  theme: Theme;
  mode: ThemeMode;
  appearance: AppearancePreferences;
  toggle: () => void;
  setTheme: (theme: Theme) => void;
  setThemeMode: (mode: ThemeMode) => void;
  updateAppearance: (patch: AppearancePreferencePatch) => void;
  replaceAppearance: (preferences: AppearancePreferences) => void;
  resetAppearance: () => void;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  mode: DEFAULT_APPEARANCE.themeMode,
  appearance: DEFAULT_APPEARANCE,
  toggle: () => {},
  setTheme: () => {},
  setThemeMode: () => {},
  updateAppearance: () => {},
  replaceAppearance: () => {},
  resetAppearance: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}
