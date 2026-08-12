import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsSidebar } from "../SettingsSidebar";

describe("SettingsSidebar", () => {
  afterEach(cleanup);

  it("provides an explicit return path and changes settings sections", () => {
    const onClose = vi.fn();
    const onSectionChange = vi.fn();

    render(
      <SettingsSidebar
        section="model"
        onSectionChange={onSectionChange}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole("button", { name: /模型服务/ }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(screen.getByRole("button", { name: "诊断与日志" }));
    expect(onSectionChange).toHaveBeenCalledWith("diagnostics");

    fireEvent.click(screen.getByRole("button", { name: "返回工作区" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps the navigation limited to implemented settings", () => {
    render(
      <SettingsSidebar
        section="model"
        onSectionChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.getByRole("navigation").querySelectorAll("button")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "外观与字号" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "模型服务" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "更新与恢复" })).toBeNull();
    expect(screen.getByRole("button", { name: "诊断与日志" })).toBeTruthy();
  });
});
