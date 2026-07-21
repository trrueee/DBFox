import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsSection, SettingsStatus, SettingsToggle } from "../SettingsScaffold";

describe("SettingsScaffold", () => {
  it("exposes settings controls with product-facing accessibility semantics", async () => {
    const onCheckedChange = vi.fn();
    const { container } = render(
      <SettingsSection title="访问边界" description="控制当前连接的默认能力。">
        <SettingsToggle
          checked={false}
          label="启用只读模式"
          description="默认阻止写入操作。"
          onCheckedChange={onCheckedChange}
        />
        <SettingsStatus tone="success" label="连接正常" description="可以继续保存配置。" />
      </SettingsSection>,
    );

    const readOnlySwitch = screen.getByRole("switch", { name: "启用只读模式" });
    expect(readOnlySwitch.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(readOnlySwitch);
    expect(onCheckedChange).toHaveBeenCalledWith(true);

    const result = await axe.run(container, {
      rules: {
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations.map((violation) => violation.id)).toEqual([]);
  });

  it("announces destructive failures immediately", () => {
    render(<SettingsStatus tone="danger" label="保存失败" description="请检查配置后重试。" />);
    expect(screen.getByRole("alert").textContent).toContain("保存失败");
  });
});
