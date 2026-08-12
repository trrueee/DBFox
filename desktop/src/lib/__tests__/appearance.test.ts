import { describe, expect, it } from "vitest";

import {
  APPEARANCE_STORAGE_KEY,
  DEFAULT_APPEARANCE,
  applyAppearanceToRoot,
  loadAppearancePreferences,
  resolveTheme,
  saveAppearancePreferences,
  parseAppearancePreferences,
  serializeAppearancePreferences,
} from "../appearance";

class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  removeItem(key: string) {
    this.values.delete(key);
  }
}

describe("appearance preferences", () => {
  it("rejects malformed or out-of-contract persisted values", () => {
    const storage = new MemoryStorage();
    storage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify({
      ...DEFAULT_APPEARANCE,
      accentColor: "arbitrary-css",
    }));

    expect(loadAppearancePreferences(storage)).toEqual(DEFAULT_APPEARANCE);
  });

  it("migrates the previous two-value theme once", () => {
    const storage = new MemoryStorage();
    storage.setItem("dbfox-theme", "dark");

    expect(loadAppearancePreferences(storage)).toEqual({
      ...DEFAULT_APPEARANCE,
      themeMode: "dark",
    });
    expect(storage.getItem("dbfox-theme")).toBeNull();
  });

  it("round-trips the versioned preference contract", () => {
    const storage = new MemoryStorage();
    const preferences = {
      ...DEFAULT_APPEARANCE,
      accentColor: "teal" as const,
      dataFontSize: 14,
    };

    saveAppearancePreferences(storage, preferences);
    expect(loadAppearancePreferences(storage)).toEqual(preferences);
  });

  it("exports only the strict appearance contract and rejects unknown imported fields", () => {
    const serialized = serializeAppearancePreferences({
      ...DEFAULT_APPEARANCE,
      density: "compact",
      tableGridLines: false,
      sidebarWidth: 300,
    });

    expect(parseAppearancePreferences(serialized)).toEqual({
      ...DEFAULT_APPEARANCE,
      density: "compact",
      tableGridLines: false,
      sidebarWidth: 300,
    });
    expect(serialized).not.toMatch(/token|password|dsn|sql/i);
    expect(() => parseAppearancePreferences(JSON.stringify({
      ...DEFAULT_APPEARANCE,
      token: "must-not-import",
    }))).toThrow();
  });

  it("applies only closed attributes and resolves system mode", () => {
    const root = document.createElement("html");
    const preferences = {
      ...DEFAULT_APPEARANCE,
      themeMode: "system" as const,
      neutralTone: "warm" as const,
      codeFontSize: 22,
      density: "compact" as const,
      tableGridLines: false,
    };

    const theme = resolveTheme(preferences.themeMode, "dark");
    applyAppearanceToRoot(root, preferences, theme);

    expect(theme).toBe("dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.dataset.theme).toBe("dark");
    expect(root.dataset.neutralTone).toBe("warm");
    expect(root.dataset.codeFontSize).toBe("22");
    expect(root.dataset.density).toBe("compact");
    expect(root.dataset.tableGridLines).toBe("false");
  });
});
