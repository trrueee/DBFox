import { describe, expect, it } from "vitest";
import { actionRegistry, planHasErrors } from "../index";

describe("@export", () => {
  it("accepts csv", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@export csv");

    expect(planHasErrors(plan)).toBe(false);
    actionRegistry.applyPhase(plan, "afterExecute");
    expect(plan.context.exportConfig).toMatchObject({
      enabled: true,
      format: "csv",
    });
  });

  it("accepts json", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@export json");

    expect(planHasErrors(plan)).toBe(false);
    actionRegistry.applyPhase(plan, "afterExecute");
    expect(plan.context.exportConfig).toMatchObject({
      enabled: true,
      format: "json",
    });
  });

  it("rejects unsupported xlsx until implemented", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@export xlsx");

    expect(planHasErrors(plan)).toBe(true);
    expect(plan.issues.some((i) => i.code === "INVALID_EXPORT_FORMAT")).toBe(true);
  });
});
