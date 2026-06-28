import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownContent } from "../MarkdownContent";

describe("MarkdownContent rendering", () => {
  it("renders inline markdown and line breaks inside table cells", () => {
    render(
      <MarkdownContent
        content={[
          "| 维度 | DBFox | 普通 AI |",
          "| --- | --- | --- |",
          "| **SQL 能力** | 自动调用 `sql.validate`<br>执行只读查询 | 只能给示例 SQL |",
        ].join("\n")}
      />,
    );

    expect(screen.getByText("SQL 能力")).toBeTruthy();
    expect(screen.getByText("sql.validate")).toBeTruthy();
    expect(screen.getByText("执行只读查询")).toBeTruthy();
    expect(screen.queryByText(/\*\*SQL 能力\*\*/)).toBeNull();
    expect(screen.queryByText(/<br>/)).toBeNull();
  });
});
