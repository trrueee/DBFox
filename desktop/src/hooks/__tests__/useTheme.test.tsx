import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { APPEARANCE_STORAGE_KEY } from "../../lib/appearance";
import { useTheme } from "../themeContext";
import { ThemeProvider } from "../useTheme";

let systemDark = false;
let systemListener: ((event: MediaQueryListEvent) => void) | undefined;

function installMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({
      matches: systemDark,
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
        systemListener = listener;
      },
      removeEventListener: () => {
        systemListener = undefined;
      },
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function Probe() {
  const { appearance, mode, theme, setThemeMode, updateAppearance, resetAppearance } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="mode">{mode}</span>
      <span data-testid="accent">{appearance.accentColor}</span>
      <button type="button" onClick={() => setThemeMode("dark")}>dark</button>
      <button type="button" onClick={() => updateAppearance({ accentColor: "blue", dataFontSize: 13 })}>customize</button>
      <button type="button" onClick={resetAppearance}>reset</button>
    </div>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    systemDark = false;
    systemListener = undefined;
    installMatchMedia();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.classList.remove("dark");
    for (const attribute of [...document.documentElement.attributes]) {
      if (attribute.name.startsWith("data-")) document.documentElement.removeAttribute(attribute.name);
    }
  });

  it("follows the system and reacts to system theme changes", () => {
    systemDark = true;
    render(<ThemeProvider><Probe /></ThemeProvider>);

    expect(screen.getByTestId("mode").textContent).toBe("system");
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    systemDark = false;
    act(() => systemListener?.({ matches: false } as MediaQueryListEvent));
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("applies and persists closed appearance choices", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);

    fireEvent.click(screen.getByRole("button", { name: "dark" }));
    fireEvent.click(screen.getByRole("button", { name: "customize" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.accent).toBe("blue");
    expect(document.documentElement.dataset.dataFontSize).toBe("13");
    expect(JSON.parse(localStorage.getItem(APPEARANCE_STORAGE_KEY) ?? "{}")).toMatchObject({
      themeMode: "dark",
      accentColor: "blue",
      dataFontSize: 13,
    });

    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    expect(screen.getByTestId("mode").textContent).toBe("system");
    expect(screen.getByTestId("accent").textContent).toBe("violet");
  });
});
