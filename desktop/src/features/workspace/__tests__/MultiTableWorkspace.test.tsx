import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MultiTableWorkspace } from "../MultiTableWorkspace";

function renderWorkspace(tables = ["users", "orders"]) {
  const onOpenQueryResult = vi.fn();
  const onToast = vi.fn();
  render(<MultiTableWorkspace tables={tables} onOpenQueryResult={onOpenQueryResult} onToast={onToast} />);
  return { onOpenQueryResult, onToast };
}

describe("MultiTableWorkspace", () => {
  beforeEach(() => {
    cleanup();
  });

  it("opens canned multi-table analysis queries from action buttons", () => {
    const { onOpenQueryResult } = renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: /分析表关联拓扑图/ }));
    fireEvent.click(screen.getByRole("button", { name: /联合数据趋势统计/ }));

    expect(onOpenQueryResult).toHaveBeenNthCalledWith(1, "查询这 2 张表的关联性，并给出数据字典");
    expect(onOpenQueryResult).toHaveBeenNthCalledWith(2, "统计所选表在最近一月的联合活动数据量");
  });

  it("submits custom joint analysis from Enter and the action button", () => {
    const { onOpenQueryResult } = renderWorkspace();
    const input = screen.getByRole("textbox", { name: "联合分析问题" });

    fireEvent.change(input, { target: { value: "比较 users 和 orders 的转化率" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onOpenQueryResult).toHaveBeenCalledWith("比较 users 和 orders 的转化率");
    expect((input as HTMLInputElement).value).toBe("");

    fireEvent.change(input, { target: { value: "列出两个表的关键字段" } });
    fireEvent.click(screen.getByRole("button", { name: "联合分析" }));
    expect(onOpenQueryResult).toHaveBeenLastCalledWith("列出两个表的关键字段");
  });

  it("shows a local empty state when no tables are selected", () => {
    renderWorkspace([]);

    expect(screen.getByText("还没有选择表")).toBeTruthy();
    expect(screen.getByText("从左侧数据源树选择多个表后，可以在这里发起联合分析。")).toBeTruthy();
  });

  it("keeps empty custom analysis submissions as a toast instead of opening a blank query", () => {
    const { onOpenQueryResult, onToast } = renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "联合分析" }));

    expect(onOpenQueryResult).not.toHaveBeenCalled();
    expect(onToast).toHaveBeenCalledWith("请输入联合分析问题");
  });
});
