import { describe, expect, it } from "vitest";
import { actionRegistry, planHasErrors } from "../index";

describe("@chart", () => {
  it("accepts bar chart with x/y", () => {
    const plan = actionRegistry.finalize("SELECT category, count FROM t\n@chart bar x=category y=count");

    expect(planHasErrors(plan)).toBe(false);
    actionRegistry.applyPhase(plan, "afterExecute");

    expect(plan.context.chartConfig).toEqual({
      enabled: true,
      type: "bar",
      x: "category",
      y: "count",
    });
  });

  it("rejects invalid chart type", () => {
    const plan = actionRegistry.finalize("SELECT category, count FROM t\n@chart radar");

    expect(planHasErrors(plan)).toBe(true);
    expect(plan.issues.some((i) => i.code === "INVALID_CHART_TYPE")).toBe(true);
  });
});
