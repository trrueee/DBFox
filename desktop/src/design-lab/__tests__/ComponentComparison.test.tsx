import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ComponentComparison } from "../ComponentComparison";

afterEach(() => cleanup());

describe("Design Lab verified source adoption", () => {
  it("renders only the actual adopted composer instead of handwritten lookalikes", () => {
    render(<ComponentComparison />);
    expect(screen.getByText("Prompt Kit PromptInput + Vercel AI Elements PromptInputSubmit")).toBeTruthy();
    expect(screen.getAllByText("ADOPT")).toHaveLength(1);
    expect(screen.queryByText("Candidate A")).toBeNull();
  });

  it("renders the adopted Agent Elements plan source", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Plan");
    expect(screen.getByLabelText("状态").textContent).toContain("Pending");
    expect(screen.getByText("Agent Elements PlanTool + TodoTool registry source")).toBeTruthy();
    expect(screen.getByLabelText("执行计划")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("exercises the 12-step long plan and its production evidence actions", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Plan");
    chooseSelectOption("状态", "Long content");

    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    expect(screen.getAllByRole("button", { name: /打开完成证据/ })).toHaveLength(1);
  });

  it("renders the adopted approval terminal matrix without treating expiration as rejection", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Approval");
    chooseSelectOption("状态", "Expired");

    expect(screen.getByText("Vercel AI Elements Confirmation")).toBeTruthy();
    expect(screen.getByText("批准请求已过期")).toBeTruthy();
    expect(screen.queryByText("已拒绝")).toBeNull();
  });

  it("renders the adopted question expiration state with no active submit action", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Question");
    chooseSelectOption("状态", "Expired");

    expect(screen.getByText("Agent Elements QuestionTool + Radix RadioGroup")).toBeTruthy();
    expect(screen.getByText("问题已过期")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "继续任务" })).toBeNull();
  });

  it("renders the production failed Run outcome with preserved Artifact recovery", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Run Outcome");

    expect(screen.getByText("shadcn/ui Alert + Fluent MessageBar behavior")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("任务未完成，已有结果仍可使用");
    expect(screen.getByRole("button", { name: "打开已保留工件：渠道转化查询结果" })).toBeTruthy();
  });

  it("renders bounded partial without a destructive alert or fictitious result", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Run Outcome");
    chooseSelectOption("状态", "Partial + no results");

    const outcome = screen.getByRole("status");
    expect(outcome.textContent).toContain("分析部分完成");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: /打开已保留工件/ })).toBeNull();
  });

  it("renders the production reconnect notice in the runtime matrix", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Runtime");
    chooseSelectOption("状态", "Stream reconnecting");

    expect(screen.getByText("shadcn/ui Alert + production SSE runtime state")).toBeTruthy();
    expect(screen.getByText("正在恢复实时连接")).toBeTruthy();
  });

  it("renders production cursor rejection and snapshot recovery states", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Runtime");
    chooseSelectOption("状态", "Cursor rejected");
    expect(screen.getByText("正在读取最新状态")).toBeTruthy();

    chooseSelectOption("状态", "Snapshot recovered");
    expect(screen.getByText("已恢复最新状态")).toBeTruthy();
  });

  it("renders adopted feedback primitives instead of drawing substitutes", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Feedback / Error");
    expect(screen.getByText(/shadcn\/ui Empty \+ Alert \+ Spinner \+ Skeleton/)).toBeTruthy();
    expect(screen.getByText("暂无查询结果")).toBeTruthy();
    expect(screen.queryByText("Candidate A")).toBeNull();
  });

  it("renders the production structured error disclosure in the feedback matrix", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Feedback / Error");
    chooseSelectOption("状态", "Error");

    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("RESULT_VIEW_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("lab-request-42")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private provider error");
  });

  it("renders the adopted JSON viewer and the actual production cell trigger", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Data Preview");
    expect(screen.getByText("react-json-view-lite + Radix Dialog / HoverCard + shadcn/ui Button")).toBeTruthy();
    expect(screen.getByRole("tree", { name: "JSON 结构" })).toBeTruthy();
    expect(screen.getByText("生产单元格触发器")).toBeTruthy();
  });

  it("renders the production image viewer with its real zoom controls", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Data Preview");
    chooseSelectOption("状态", "Image");
    fireEvent.click(screen.getByRole("button", { name: /预览图片/ }));
    const image = screen.getByRole("img", { name: "数据单元格中的图片预览" });
    fireEvent.load(image);

    expect(screen.getByRole("toolbar", { name: "图片查看控制" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "放大图片" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "实际大小" })).toBeTruthy();
  });

  it("renders the actual fatal boundary fallback in its runtime state", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Feedback / Error");
    chooseSelectOption("状态", "Fatal boundary");
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试渲染" })).toBeTruthy();
  });

  it("renders the adopted work surface with the production Host Tree primitive", () => {
    render(<ComponentComparison />);
    chooseSelectOption("组件", "Tree / Grid / Surface");
    expect(screen.getByText("Zag Tree View + react-resizable-panels + Radix Tabs + TanStack Table")).toBeTruthy();
    expect(screen.getByRole("separator", { name: "调整对象树与结果区宽度" })).toBeTruthy();
    expect(screen.getByRole("grid", { name: "查询结果" })).toBeTruthy();
    expect(screen.getByRole("tree", { name: "数据库对象树" })).toBeTruthy();
    expect(screen.getByRole("treeitem", { name: /public\.orders/ })).toBeTruthy();
  });

  it("applies and restores the high contrast fixture", () => {
    const root = document.documentElement;
    const previous = root.dataset.contrast;
    const view = render(<ComponentComparison />);
    chooseSelectOption("对比度", "High contrast");
    expect(root.dataset.contrast).toBe("high");
    view.unmount();
    expect(root.dataset.contrast).toBe(previous);
  });

  it("provides the 480px at 200% small-window inspection fixture", () => {
    const { container } = render(<ComponentComparison />);
    chooseSelectOption("视口", "480 × 800");
    chooseSelectOption("缩放", "200%");

    const viewport = container.querySelector(".component-comparison__viewport");
    expect(viewport?.classList.contains("component-comparison__viewport--480")).toBe(true);
    expect(viewport?.classList.contains("component-comparison__viewport--scale-200")).toBe(true);
  });

  it("exposes the production 500-node Tree virtualization fixture", async () => {
    const { container } = render(<ComponentComparison />);
    chooseSelectOption("组件", "Tree / Grid / Surface");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "状态" }).textContent).toContain("Grid"));
    const stateSelect = screen.getByRole("combobox", { name: "状态" });
    stateSelect.focus();
    fireEvent.keyDown(stateSelect, { key: "Enter", code: "Enter" });
    fireEvent.click(await screen.findByRole("option", { name: "Tree · 500 nodes" }));

    await waitFor(() => expect(container.querySelector(".dbfox-tree.is-virtualized")).toBeTruthy());
    expect(container.querySelector(".dbfox-tree__virtual-canvas")).toBeTruthy();
  });

  it("exposes bounded history prepend and terminal pagination states", async () => {
    const { container } = render(<ComponentComparison />);
    chooseSelectOption("组件", "Conversation History");

    expect(screen.getByText("TanStack Virtual Chat + generated bounded history endpoint")).toBeTruthy();
    expect(container.querySelector(".conv-message-column.is-virtualized")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "载入更早消息" }));
    expect(await screen.findByText("已载入全部消息")).toBeTruthy();
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
