import { describe, expect, it } from "vitest";
import { actionRegistry, planHasErrors, planWarnings } from "../index";

describe("SQL Action Registry", () => {
  it("parses directive lines and strips them from pure SQL", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@limit 10");

    expect(plan.pureSql).toBe("SELECT id FROM users");
    expect(plan.actions).toHaveLength(1);
    expect(plan.actions[0].type).toBe("limit");
    expect(plan.compiledSql).toBe("SELECT id FROM users LIMIT 10;");
  });

  it("rejects duplicate non-repeatable directives", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@limit 10\n@limit 20");

    expect(planHasErrors(plan)).toBe(true);
    expect(plan.issues.some((i) => i.code === "DUPLICATE_ACTION")).toBe(true);
  });

  it("rejects conflicting explain and export directives", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@explain\n@export csv");

    expect(planHasErrors(plan)).toBe(true);
    expect(plan.issues.some((i) => i.code === "CONFLICTING_ACTIONS")).toBe(true);
  });

  it("keeps unknown directives as warnings and does not block execution", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users\n@unknown abc");

    expect(planHasErrors(plan)).toBe(false);
    expect(planWarnings(plan).some((i) => i.code === "UNKNOWN_ACTION")).toBe(true);
    expect(plan.compiledSql).toBe("SELECT id FROM users");
  });

  it("supports explain plus limit with normalized SQL", () => {
    const plan = actionRegistry.finalize("SELECT id FROM users;\n@limit 10\n@explain");

    expect(planHasErrors(plan)).toBe(false);
    expect(plan.compiledSql).toBe("EXPLAIN SELECT id FROM users LIMIT 10;");
  });
});
