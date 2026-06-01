import { describe, expect, it } from "vitest";
import { isNumericLike, toChartNumber } from "../chart-utils";

describe("chart utils", () => {
  it("detects numeric strings", () => {
    expect(isNumericLike("12")).toBe(true);
    expect(isNumericLike("1,234.56")).toBe(true);
    expect(isNumericLike("abc")).toBe(false);
  });

  it("converts numeric strings", () => {
    expect(toChartNumber("1,234.56")).toBe(1234.56);
    expect(toChartNumber("abc")).toBe(0);
  });
});
