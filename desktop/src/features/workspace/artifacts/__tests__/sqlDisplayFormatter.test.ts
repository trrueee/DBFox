import { describe, expect, it } from "vitest";
import { formatSqlForDisplay } from "../sqlDisplayFormatter";

describe("formatSqlForDisplay", () => {
  it("formats clauses and projections into a readable hierarchy", () => {
    expect(
      formatSqlForDisplay(
        "SELECT day, COUNT(*) AS order_count FROM orders WHERE deleted_at IS NULL GROUP BY day ORDER BY day LIMIT 1000",
        "mysql",
      ),
    ).toBe(
      [
        "SELECT",
        "  day,",
        "  COUNT(*) AS order_count",
        "FROM",
        "  orders",
        "WHERE",
        "  deleted_at IS NULL",
        "GROUP BY",
        "  day",
        "ORDER BY",
        "  day",
        "LIMIT",
        "  1000",
      ].join("\n"),
    );
  });

  it("preserves the original SQL when the display formatter cannot parse it", () => {
    const sql = "SELECT [unsupported_identifier FROM orders";
    expect(formatSqlForDisplay(sql, "unknown-dialect")).toBe(sql);
  });
});
