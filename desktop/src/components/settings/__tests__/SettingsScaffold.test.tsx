import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SettingsField } from "../SettingsScaffold";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../ui/select";

describe("SettingsField", () => {
  afterEach(cleanup);

  it("connects field hints to the input", () => {
    render(
      <SettingsField label="模型地址" htmlFor="model-url" hint="请输入完整的 HTTPS 地址">
        <input id="model-url" />
      </SettingsField>,
    );

    const input = screen.getByRole("textbox", { name: "模型地址" });
    const hint = screen.getByText("请输入完整的 HTTPS 地址");
    expect(input.getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("announces validation errors and marks the input invalid", () => {
    render(
      <SettingsField label="模型地址" htmlFor="model-url" error="地址格式不正确">
        <input id="model-url" />
      </SettingsField>,
    );

    const input = screen.getByRole("textbox", { name: "模型地址" });
    const error = screen.getByRole("alert");
    expect(input.getAttribute("aria-describedby")).toContain(error.id);
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("describes compound controls through an accessible group", () => {
    render(
      <SettingsField label="API Key" htmlFor="api-key" hint="凭据由系统安全存储管理">
        <div>
          <input id="api-key" />
          <button type="button">显示</button>
        </div>
      </SettingsField>,
    );

    const group = screen.getByRole("group", { name: "API Key" });
    const hint = screen.getByText("凭据由系统安全存储管理");
    expect(group.getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("associates a compound select label and hint with its real trigger", () => {
    render(
      <SettingsField label="默认模型" htmlFor="model-preset" hint="选择一个已配置的模型">
        <Select defaultValue="auto">
          <SelectTrigger id="model-preset" aria-describedby="model-preset-description">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">自动</SelectItem>
          </SelectContent>
        </Select>
      </SettingsField>,
    );

    const trigger = screen.getByRole("combobox", { name: "默认模型" });
    const hint = screen.getByText("选择一个已配置的模型");
    expect(trigger.getAttribute("aria-describedby")).toContain(hint.id);
  });
});
