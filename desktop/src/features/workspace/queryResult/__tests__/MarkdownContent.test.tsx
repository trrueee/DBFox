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

    fireEvent.click(screen.getByRole("link", { name: "查看证据：订单趋势" }));
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

    const source = screen.getByRole("link", { name: "查看证据：订单趋势" });
    expect(source.textContent).toContain("订单趋势");
    expect(source.querySelector(".hifi-md-citation__index")?.textContent).toBe("1");
    fireEvent.click(source);
    expect(onCitation).toHaveBeenCalledWith("artifact_result_1");
  });

  it("uses the canonical resource name and type instead of repeating a claim", () => {
    render(<MarkdownContent content="订单增长。{{cite:artifact_result_1}}"
      citations={[{ artifact_id: "artifact_result_1", label: "**数据质量**：无逻辑删除记录，并且本次查询覆盖全部有效订单。" }]}
      artifacts={[{ id: "artifact_result_1", type: "dbfox.data.result_view", title: "订单汇总" }]} />);
    const citation = screen.getByRole("link", { name: "查看证据：订单汇总" });
    expect(citation.querySelector(".resource-icon--table")).toBeTruthy();
    expect(citation.textContent).toBe("订单汇总1");
  });

  it("shows a compact document source for historical citations without metadata", () => {
    const label = "- **数据质量**：无逻辑删除记录（deleted_cnt = 0），覆盖全部订单。";
    render(<MarkdownContent content="历史结论。{{cite:artifact_result_1}}" citations={[{ artifact_id: "artifact_result_1", label }]} />);
    const citation = screen.getByRole("link", { name: `查看证据：${label}` });
    expect(citation.textContent).toBe("数据来源1");
    expect(citation.querySelector(".resource-icon--document")).toBeTruthy();
    expect(citation.getAttribute("aria-label")).toBe(`查看证据：${label}`);
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

  it("opens distinct evidence occurrences belonging to the same artifact", () => {
    const onEvidence = vi.fn();
    render(<MarkdownContent content="收入。{{cite:artifact_result_1}}\n\n成本。{{cite:artifact_result_1}}"
      citations={[
        { id: "evidence-revenue", artifact_id: "artifact_result_1", label: "收入依据" },
        { id: "evidence-cost", artifact_id: "artifact_result_1", label: "成本依据" },
      ]} onEvidence={onEvidence} />);
    fireEvent.click(screen.getByRole("link", { name: "查看证据：收入依据" }));
    fireEvent.click(screen.getByRole("link", { name: "查看证据：成本依据" }));
    expect(onEvidence.mock.calls).toEqual([["evidence-revenue"], ["evidence-cost"]]);
    expect(screen.getByRole("link", { name: "查看证据：成本依据" }).textContent).toContain("2");
  });

  it("renders Runtime-composed structured fragments as rich text with exact evidence actions", () => {
    const onEvidence = vi.fn();
    render(<MarkdownContent
      content={"**验证通过 ✅**。{{cite:artifact_test}}\n\n| 项目 | 结果 |\n|---|---|\n| 测试 | 通过 |\n\n文件已保存。{{cite:artifact_file}}"}
      citations={[
        { id: "test-evidence", artifact_id: "artifact_test", label: "**验证通过 ✅**。", locator: { value: { citation_index: 1 } } },
        { id: "file-evidence", artifact_id: "artifact_file", label: "文件已保存。", locator: { value: { citation_index: 2 } } },
      ]} onEvidence={onEvidence} />);
    expect(screen.getByText("验证通过 ✅").tagName).toBe("STRONG");
    expect(screen.getByRole("table")).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "查看证据：**验证通过 ✅**。" }));
    fireEvent.click(screen.getByRole("link", { name: "查看证据：文件已保存。" }));
    expect(onEvidence.mock.calls).toEqual([["test-evidence"], ["file-evidence"]]);
  });

  it("does not activate invented citations or parse citation examples inside code", () => {
    render(<MarkdownContent content="未知来源。{{cite:artifact_fabricated}}\n\n`{{cite:artifact_known}}`"
      citations={[{ artifact_id: "artifact_known", label: "真实来源" }]} />);
    expect(screen.queryByRole("link", { name: /fabricated/ })).toBeNull();
    expect(screen.getByText(/来源待确认/)).toBeTruthy();
    expect(screen.getByText("{{cite:artifact_known}}").closest("code")).toBeTruthy();
  });

  it("keeps numbered claims aligned after code examples, emoji and escaped Markdown", () => {
    const onEvidence = vi.fn();
    render(<MarkdownContent content="`{{cite:artifact_known}}`\n\n✅ A &amp; B \\* 数值。{{cite:artifact_known}}"
      citations={[
        { id: "example", artifact_id: "artifact_known", label: "示例", locator: { value: { citation_index: 1 } } },
        { id: "actual", artifact_id: "artifact_known", label: "实际依据", locator: { value: { citation_index: 2 } } },
      ]} onEvidence={onEvidence} />);
    fireEvent.click(screen.getByRole("link", { name: "查看证据：实际依据" }));
    expect(onEvidence).toHaveBeenCalledWith("actual");
    expect(screen.queryByRole("link", { name: "查看证据：示例" })).toBeNull();
  });

  it("hides an incomplete streaming marker without hiding the surrounding answer", () => {
    const view = render(<MarkdownContent content="已经核对交付清单。{{cite:artifact_incom" streaming />);
    expect(view.container.textContent).toBe("已经核对交付清单。");
  });

  it("retains focused links across callback changes instead of remounting the renderer", () => {
    const citations = [{ id: "evidence-1", artifact_id: "artifact_known", label: "核对记录" }];
    const first = vi.fn();
    const next = vi.fn();
    const view = render(<MarkdownContent content="已核对。{{cite:artifact_known}}" citations={citations} onEvidence={first} />);
    const source = screen.getByRole("link", { name: "查看证据：核对记录" });
    source.focus();
    view.rerender(<MarkdownContent content="已核对。{{cite:artifact_known}}" citations={citations} onEvidence={next} />);
    expect(screen.getByRole("link", { name: "查看证据：核对记录" }).isSameNode(source)).toBe(true);
    expect(document.activeElement).toBe(source);
    fireEvent.click(source);
    expect(next).toHaveBeenCalledWith("evidence-1");
    expect(first).not.toHaveBeenCalled();
  });
});
