import { describe, expect, it } from "vitest";
import { splitMarkdownTables } from "../MarkdownContent";

describe("splitMarkdownTables", () => {
  it("extracts pipe tables from agent markdown answers", () => {
    const segments = splitMarkdownTables([
      "已找到用户数据表 `id_users`。",
      "",
      "| id | username | status |",
      "|----|----------|--------|",
      "| 1 | admin | active |",
      "| 2 | demo | active |",
      "",
      "如果需要更多筛选，请继续提问。",
    ].join("\n"));

    expect(segments).toHaveLength(3);
    expect(segments[0]).toEqual({ type: "markdown", content: "已找到用户数据表 `id_users`。" });
    expect(segments[1]).toEqual({
      type: "table",
      headers: ["id", "username", "status"],
      rows: [
        ["1", "admin", "active"],
        ["2", "demo", "active"],
      ],
    });
    expect(segments[2]).toEqual({ type: "markdown", content: "如果需要更多筛选，请继续提问。" });
  });
});
