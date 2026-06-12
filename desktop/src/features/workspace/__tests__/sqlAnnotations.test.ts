import { describe, expect, it } from "vitest";
import { parseAnnotatedSql, summarizeAnnotations } from "../sqlAnnotations";

describe("sql annotations", () => {
  it("strips annotation lines and applies limit", () => {
    const plan = parseAnnotatedSql(`@limit 20
SELECT id, name FROM users;`);

    expect(plan.executableSql).toBe("SELECT id, name FROM users\nLIMIT 20");
    expect(plan.limit).toBe(20);
    expect(plan.annotations).toHaveLength(1);
  });

  it("keeps existing LIMIT instead of duplicating it", () => {
    const plan = parseAnnotatedSql(`@limit 50
SELECT * FROM orders LIMIT 10;`);

    expect(plan.executableSql).toBe("SELECT * FROM orders LIMIT 10;");
    expect(plan.warnings).toContain("SQL 已包含 LIMIT，已跳过 @limit 自动追加。");
  });

  it("builds explain, export and chart directives", () => {
    const plan = parseAnnotatedSql(`@explain
@export csv
@chart line x=month y=amount title="月销售额"
SELECT month, amount FROM sales`);

    expect(plan.executableSql).toBe("EXPLAIN SELECT month, amount FROM sales");
    expect(plan.exportCsv).toBe(true);
    expect(plan.chart).toEqual({ enabled: true, type: "line", x: "month", y: "amount", title: "月销售额", limit: undefined });
    expect(summarizeAnnotations(plan)).toEqual(["EXPLAIN", "CSV 导出", "line chart"]);
  });

  it("parses timeout units", () => {
    const plan = parseAnnotatedSql(`@timeout 3s
SELECT 1`);

    expect(plan.timeoutMs).toBe(3000);
  });

  it("warns for unknown annotations", () => {
    const plan = parseAnnotatedSql(`@foo bar
SELECT 1`);

    expect(plan.executableSql).toBe("SELECT 1");
    expect(plan.warnings).toContain("忽略未知 SQL 注解 @foo");
  });
});
