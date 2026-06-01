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

  it("deduplicates conflict issues regardless of directive ordering", () => {
    const plan1 = actionRegistry.finalize("SELECT id FROM users\n@explain\n@export csv");
    const conflicts1 = plan1.issues.filter((i) => i.code === "CONFLICTING_ACTIONS");
    expect(conflicts1).toHaveLength(1);

    const plan2 = actionRegistry.finalize("SELECT id FROM users\n@export csv\n@explain");
    const conflicts2 = plan2.issues.filter((i) => i.code === "CONFLICTING_ACTIONS");
    expect(conflicts2).toHaveLength(1);
  });

  it("only parses independent line-start @ directives", () => {
    const sql = "SELECT id FROM users -- @limit 10\n/* @timeout 30 */\nSELECT @explain;";
    const plan = actionRegistry.finalize(sql);

    expect(plan.actions).toHaveLength(0);
    expect(plan.compiledSql).toBe(sql.trim());
  });

  it("validates @limit boundaries and rejects invalid values", () => {
    const plan1 = actionRegistry.finalize("SELECT * FROM t\n@limit 0");
    expect(planHasErrors(plan1)).toBe(true);
    expect(plan1.issues.some((i) => i.code === "INVALID_LIMIT_ROWS")).toBe(true);

    const plan2 = actionRegistry.finalize("SELECT * FROM t\n@limit -5");
    expect(planHasErrors(plan2)).toBe(true);
    expect(plan2.issues.some((i) => i.code === "INVALID_LIMIT_ROWS")).toBe(true);

    const plan3 = actionRegistry.finalize("SELECT * FROM t\n@limit 100000000");
    expect(planHasErrors(plan3)).toBe(true);
    expect(plan3.issues.some((i) => i.code === "INVALID_LIMIT_ROWS")).toBe(true);

    const plan4 = actionRegistry.finalize("SELECT * FROM t\n@limit abc");
    expect(planHasErrors(plan4)).toBe(true);
    expect(plan4.issues.some((i) => i.code === "INVALID_LIMIT_ROWS")).toBe(true);
  });

  it("validates @timeout boundaries and rejects invalid values", () => {
    const plan1 = actionRegistry.finalize("SELECT * FROM t\n@timeout 0");
    expect(planHasErrors(plan1)).toBe(true);
    expect(plan1.issues.some((i) => i.code === "INVALID_TIMEOUT_SECONDS")).toBe(true);

    const plan2 = actionRegistry.finalize("SELECT * FROM t\n@timeout -1");
    expect(planHasErrors(plan2)).toBe(true);
    expect(plan2.issues.some((i) => i.code === "INVALID_TIMEOUT_SECONDS")).toBe(true);

    const plan3 = actionRegistry.finalize("SELECT * FROM t\n@timeout 999999");
    expect(planHasErrors(plan3)).toBe(true);
    expect(plan3.issues.some((i) => i.code === "INVALID_TIMEOUT_SECONDS")).toBe(true);

    const plan4 = actionRegistry.finalize("SELECT * FROM t\n@timeout abc");
    expect(planHasErrors(plan4)).toBe(true);
    expect(plan4.issues.some((i) => i.code === "INVALID_TIMEOUT_SECONDS")).toBe(true);
  });
});
