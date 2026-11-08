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
    expect(source.textContent).toContain("订单趋势");
    expect(source.querySelector(".hifi-md-citation__index")?.textContent).toBe("1");
    fireEvent.click(source);
    expect(onCitation).toHaveBeenCalledWith("artifact_result_1");
  });

  it("uses the canonical resource name and type instead of repeating a claim", () => {
    render(<MarkdownContent content="订单增长。{{cite:artifact_result_1}}"
      citations={[{ artifact_id: "artifact_result_1", label: "**数据质量**：无逻辑删除记录，并且本次查询覆盖全部有效订单。" }]}
      artifacts={[{ id: "artifact_result_1", type: "dbfox.data.result_view", title: "订单汇总" }]} />);
    const citation = screen.getByRole("button", { name: "查看证据：订单汇总" });
    expect(citation.querySelector(".resource-icon--table")).toBeTruthy();
    expect(citation.textContent).toBe("订单汇总1");
  });

  it("shows a compact document source for historical citations without metadata", () => {
    const label = "- **数据质量**：无逻辑删除记录（deleted_cnt = 0），覆盖全部订单。";
    render(<MarkdownContent content="历史结论。{{cite:artifact_result_1}}" citations={[{ artifact_id: "artifact_result_1", label }]} />);
    const citation = screen.getByRole("button", { name: `查看证据：${label}` });
    expect(citation.textContent).toBe("数据来源1");
    expect(citation.querySelector(".resource-icon--document")).toBeTruthy();
    expect(citation.getAttribute("title")).toBe(label);
  });

  it("renders an authorized Artifact at its exact Markdown block position", () => {
    const renderArtifact = vi.fn((artifactId: string) => (
      <section data-testid="embedded-artifact">Artifact {artifactId}</section>
    ));
    const { container } = render(
      <MarkdownContent
        content={[
          "正文第一段。",
          "",
          "{{artifact:artifact_visualization_1}}",
          "",
          "正文结论。",
        ].join("\n")}
        artifactRefs={[{ artifact_id: "artifact_visualization_1" }]}
        renderArtifact={renderArtifact}
      />,
    );

    expect(renderArtifact).toHaveBeenCalledWith("artifact_visualization_1");
    expect(screen.getByTestId("embedded-artifact")).toBeTruthy();
    const children = Array.from(
      container.querySelector(".hifi-markdown-content")?.children ?? [],
    );
    expect(children.map((node) => node.textContent)).toEqual([
      "正文第一段。",
      "Artifact artifact_visualization_1",
      "正文结论。",
    ]);
  });

  it("does not activate an Artifact marker absent from validated references", () => {
    const renderArtifact = vi.fn();
    render(
      <MarkdownContent
        content="{{artifact:artifact_fabricated}}"
        artifactRefs={[]}
        renderArtifact={renderArtifact}
      />,
    );

    expect(renderArtifact).not.toHaveBeenCalled();
    expect(screen.getByText("{{artifact:artifact_fabricated}}")).toBeTruthy();
  });

  it("does not render untrusted raw HTML", () => {
    const { container } = render(<MarkdownContent content={'<img src=x onerror="alert(1)">'} />);
    expect(container.querySelector("img")).toBeNull();
  });
});
