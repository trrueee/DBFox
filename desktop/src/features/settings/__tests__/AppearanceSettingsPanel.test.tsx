import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../../../hooks/useTheme";
import { AppearanceSettingsPanel } from "../AppearanceSettingsPanel";

describe("AppearanceSettingsPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("exposes accessible theme, color and regional font controls", () => {
    render(
      <ThemeProvider>
        <AppearanceSettingsPanel showToast={vi.fn()} />
      </ThemeProvider>,
    );

    expect(screen.getByRole("radiogroup", { name: "主题模式" })).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "强调色" })).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "中性色调" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "界面基准字号" }).textContent).toContain("14 px（默认）");
    expect(screen.getByRole("combobox", { name: "数据字号" }).textContent).toContain("14 px（默认）");
    expect(screen.getByRole("combobox", { name: "SQL 与代码字号" }).textContent).toContain("14 px（默认）");
    expect(screen.getByRole("combobox", { name: "Agent 对话字号" }).textContent).toContain("14 px（默认）");
  });

  it("previews palette changes immediately and can reset them", () => {
    const showToast = vi.fn();
    render(
      <ThemeProvider>
        <AppearanceSettingsPanel showToast={showToast} />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole("radio", { name: "数据蓝" }));
    expect(document.documentElement.dataset.accent).toBe("blue");

    fireEvent.click(screen.getByRole("button", { name: /恢复默认/ }));
    expect(document.documentElement.dataset.accent).toBe("blue");
    expect(showToast).toHaveBeenCalledWith("外观设置已恢复默认值", "success");
  });

  it("maps explicit pixel choices onto the bounded typography contract", () => {
    render(
      <ThemeProvider>
        <AppearanceSettingsPanel showToast={vi.fn()} />
      </ThemeProvider>,
    );

    chooseSelectOption("数据字号", "15 px");

    expect(document.documentElement.dataset.dataFontSize).toBe("15");
    expect(screen.getByRole("combobox", { name: "数据字号" }).textContent).toContain("15 px");
  });
});

function chooseSelectOption(label: string, optionName: string) {
  fireEvent.pointerDown(screen.getByRole("combobox", { name: label }), {
    button: 0,
    ctrlKey: false,
    pointerId: 1,
    pointerType: "mouse",
  });
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}
