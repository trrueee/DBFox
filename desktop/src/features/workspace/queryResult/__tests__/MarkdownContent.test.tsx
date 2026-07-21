import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkdownContent } from "../MarkdownContent";

describe("MarkdownContent", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders GFM tables through the standard Markdown AST", () => {
    render(<MarkdownContent content={[
      "| id | username | status |",
      "|----|----------|--------|",
      "| 1 | admin | active |",
      "| 2 | demo | active |",
    ].join("\n")} />);

    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "username" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "demo" })).toBeTruthy();
  });

  it("turns durable citation markers into accessible Artifact actions", () => {
    const onCitation = vi.fn();
    render(
      <MarkdownContent
        content="订单增长 12%。{{cite:artifact_result_1}}"
        citations={[{ artifact_id: "artifact_result_1", label: "订单趋势" }]}
        onCitation={onCitation}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看证据：订单趋势" }));
    expect(onCitation).toHaveBeenCalledWith("artifact_result_1");
  });

  it("keeps durable evidence visible when the model omitted an inline marker", () => {
    const onCitation = vi.fn();
    render(
      <MarkdownContent
        content="订单增长 12%。"
        citations={[{ artifact_id: "artifact_result_1", label: "订单趋势" }]}
        onCitation={onCitation}
      />,
    );

    const source = screen.getByRole("button", { name: "查看证据：订单趋势" });
    expect(source.textContent).toContain("[1] 订单趋势");
    fireEvent.click(source);
    expect(onCitation).toHaveBeenCalledWith("artifact_result_1");
  });

  it("does not render untrusted raw HTML", () => {
    const { container } = render(<MarkdownContent content={'<img src=x onerror="alert(1)">'} />);
    expect(container.querySelector("img")).toBeNull();
  });
});
