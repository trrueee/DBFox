import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

import {
  DEFAULT_APPEARANCE,
  applyAppearanceToRoot,
  loadAppearancePreferences,
  resolveTheme,
  saveAppearancePreferences,
  type AppearancePreferencePatch,
  type ResolvedTheme,
  type ThemeMode,
} from "../lib/appearance";
import { ThemeContext, type Theme } from "./themeContext";

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

function getStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function getSystemTheme(): ResolvedTheme {
  return typeof window !== "undefined" && window.matchMedia?.(SYSTEM_DARK_QUERY).matches
    ? "dark"
    : "light";
}

function subscribeToSystemTheme(onStoreChange: () => void): () => void {
  const query = window.matchMedia?.(SYSTEM_DARK_QUERY);
  if (!query) return () => undefined;
  query.addEventListener("change", onStoreChange);
  return () => query.removeEventListener("change", onStoreChange);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [appearance, setAppearance] = useState(() =>
    loadAppearancePreferences(getStorage()),
  );
  const systemTheme = useSyncExternalStore<ResolvedTheme>(
    subscribeToSystemTheme,
    getSystemTheme,
    (): ResolvedTheme => "light",
  );
  const theme = resolveTheme(appearance.themeMode, systemTheme);

  useLayoutEffect(() => {
    applyAppearanceToRoot(document.documentElement, appearance, theme);
    saveAppearancePreferences(getStorage(), appearance);
  }, [appearance, theme]);

  const updateAppearance = useCallback((patch: AppearancePreferencePatch) => {
    setAppearance((current) => ({ ...current, ...patch, version: 1 }));
  }, []);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    updateAppearance({ themeMode: mode });
  }, [updateAppearance]);

  const setTheme = useCallback((nextTheme: Theme) => {
    updateAppearance({ themeMode: nextTheme });
  }, [updateAppearance]);

  const toggle = useCallback(() => {
    updateAppearance({ themeMode: theme === "dark" ? "light" : "dark" });
  }, [theme, updateAppearance]);

  const resetAppearance = useCallback(() => {
    setAppearance({ ...DEFAULT_APPEARANCE });
  }, []);

  const replaceAppearance = useCallback((preferences: typeof appearance) => {
    setAppearance({ ...preferences });
  }, []);

  const value = useMemo(() => ({
    theme,
    mode: appearance.themeMode,
    appearance,
    toggle,
    setTheme,
    setThemeMode,
    updateAppearance,
    replaceAppearance,
    resetAppearance,
  }), [appearance, replaceAppearance, resetAppearance, setTheme, setThemeMode, theme, toggle, updateAppearance]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
