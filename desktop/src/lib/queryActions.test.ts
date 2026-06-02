/**
 * queryActions.ts unit tests
 * Run: npx tsx --test src/lib/queryActions.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  actionRegistry,
  registerActionProcessor,
  planHasErrors,
  planWarnings,
  type ActionProcessor,
} from "./query-actions";

// ── Scenario 1: @limit 100 ──
describe("@limit", () => {
  it("parses @limit 100 and appends LIMIT to compiledSql", () => {
    const plan = actionRegistry.finalize(`@limit 100\nSELECT * FROM users;`);

    assert.equal(planHasErrors(plan), false);
    assert.equal(plan.pureSql, "SELECT * FROM users;");
    assert.equal(plan.compiledSql, "SELECT * FROM users LIMIT 100;");
    assert.equal(plan.sourceText, "@limit 100\nSELECT * FROM users;");
    assert.equal(plan.actions.length, 1);
    assert.equal(plan.actions[0].type, "limit");
    assert.equal(plan.actions[0].label, "LIMIT 100");
  });

  it("does not double-add LIMIT when SQL already has one", () => {
    const plan = actionRegistry.finalize(
      "@limit 100\nSELECT * FROM users LIMIT 50;",
    );

    assert.equal(plan.compiledSql, "SELECT * FROM users LIMIT 50;");
    assert.equal(
      planWarnings(plan).some((w) => w.code === "LIMIT_ALREADY_EXISTS"),
      true,
    );
  });

  it("defaults to LIMIT 100 when no number specified", () => {
    const plan = actionRegistry.finalize("@limit\nSELECT * FROM users;");

    assert.equal(plan.compiledSql, "SELECT * FROM users LIMIT 100;");
  });
});

// ── Scenario 2: @timeout 30s ──
describe("@timeout", () => {
  it("sets context.timeoutMs from @timeout", () => {
    const plan = actionRegistry.finalize("@timeout 30s\nSELECT * FROM users;");

    assert.equal(planHasErrors(plan), false);
    // finalize only does build→validate→compile, timeout is beforeExecute
    assert.equal(plan.context.timeoutMs, 30000); // default

    // Apply beforeExecute phase
    actionRegistry.applyPhase(plan, "beforeExecute");
    assert.equal(plan.context.timeoutMs, 30000);
  });

  it("handles @timeout without 's' suffix", () => {
    const plan = actionRegistry.finalize("@timeout 60\nSELECT 1;");
    actionRegistry.applyPhase(plan, "beforeExecute");

    assert.equal(plan.context.timeoutMs, 60000);
  });
});

// ── Scenario 3: @explain + @limit order ──
describe("@explain + @limit ordering", () => {
  it("compiles to EXPLAIN SELECT ... LIMIT (limit first, explain after)", () => {
    const plan = actionRegistry.finalize(
      "@explain\n@limit 100\nSELECT * FROM users;",
    );

    assert.equal(planHasErrors(plan), false);
    // @limit (order 100) applies first, @explain (order 900) wraps after
    assert.equal(
      plan.compiledSql,
      "EXPLAIN SELECT * FROM users LIMIT 100;",
    );
  });

  it("still works when written in reverse order (@limit then @explain in source)", () => {
    const plan = actionRegistry.finalize(
      "@limit 50\n@explain\nSELECT * FROM users;",
    );

    assert.equal(
      plan.compiledSql,
      "EXPLAIN SELECT * FROM users LIMIT 50;",
    );
  });
});

// ── Scenario 4: @explain + @export conflict ──
describe("@explain + @export conflict", () => {
  it("blocks execution when @explain and @export are used together", () => {
    const plan = actionRegistry.finalize(
      '@explain\n@export csv "./out.csv"\nSELECT * FROM users;',
    );

    assert.equal(planHasErrors(plan), true);
    assert.equal(
      plan.issues.some(
        (i) => i.code === "CONFLICTING_ACTIONS" && i.level === "error",
      ),
      true,
    );
  });
});

// ── Scenario 5: @export config ──
describe("@export config", () => {
  it("generates exportConfig in execution plan", () => {
    const plan = actionRegistry.finalize(
      '@export csv "./exports/users.csv"\nSELECT * FROM users;',
    );

    assert.equal(planHasErrors(plan), false);
    // exportConfig is set during afterExecute phase
    actionRegistry.applyPhase(plan, "afterExecute");

    assert.equal(plan.context.exportConfig?.enabled, true);
    assert.equal(plan.context.exportConfig?.format, "csv");
    assert.equal(
      plan.context.exportConfig?.path,
      "./exports/users.csv",
    );
  });

  it("uses key=value syntax", () => {
    const plan = actionRegistry.finalize(
      '@export type=json path="./data.json" chunk=2000\nSELECT * FROM users;',
    );

    actionRegistry.applyPhase(plan, "afterExecute");

    assert.equal(plan.context.exportConfig?.format, "json");
    assert.equal(plan.context.exportConfig?.path, "./data.json");
    assert.equal(plan.context.exportConfig?.chunkSize, 2000);
  });

  it("rejects unknown export format", () => {
    const plan = actionRegistry.finalize(
      '@export pdf "./out.pdf"\nSELECT * FROM users;',
    );

    assert.equal(planHasErrors(plan), true);
    assert.equal(
      plan.issues.some((i) => i.code === "INVALID_EXPORT_FORMAT"),
      true,
    );
  });
});

// ── Scenario 6: sourceText never polluted ──
describe("sourceText preservation", () => {
  it("keeps sourceText unchanged after finalize + execute", () => {
    const sql = "@limit 100\n@timeout 30s\nSELECT * FROM users;";
    const plan = actionRegistry.finalize(sql);
    actionRegistry.applyPhase(plan, "beforeExecute");

    assert.equal(plan.sourceText, sql);
    assert.equal(plan.pureSql, "SELECT * FROM users;");
    assert.equal(plan.compiledSql, "SELECT * FROM users LIMIT 100;");
    assert.notEqual(plan.sourceText, plan.compiledSql);
  });
});

// ── Scenario 7: repeatable actions ──
describe("repeatable actions", () => {
  it("applies all instances of a repeatable action", () => {
    // Register a test processor that is repeatable
    const applied: string[] = [];
    const testProcessor: ActionProcessor = {
      name: "mask",
      meta: {
        phase: "compile",
        order: 50,
        repeatable: true,
        conflictsWith: [],
        description: "Test mask directive",
        usage: "@mask",
        examples: ["@mask"],
      },
      parse(rest) {
        return { column: rest.trim() };
      },
      apply(action) {
        applied.push(action.args.column);
      },
      formatLabel(args) {
        return `脱敏 ${args.column ?? ""}`;
      },
    };

    registerActionProcessor(testProcessor);

    const plan = actionRegistry.finalize(
      "@mask phone\n@mask email\nSELECT * FROM users;",
    );

    assert.equal(planHasErrors(plan), false);
    assert.deepEqual(applied, ["phone", "email"]);
  });

  it("errors on duplicate non-repeatable actions", () => {
    const plan = actionRegistry.finalize(
      "@limit 10\n@limit 20\nSELECT * FROM users;",
    );

    assert.equal(planHasErrors(plan), true);
    assert.equal(
      plan.issues.some(
        (i) => i.code === "DUPLICATE_ACTION" && i.level === "error",
      ),
      true,
    );
  });
});

// ── Scenario 8: unknown actions ──
describe("unknown actions", () => {
  it("warns but does not error on unknown @ directive", () => {
    const plan = actionRegistry.finalize("@unknown_arg\nSELECT 1;");

    assert.equal(planHasErrors(plan), false);
    assert.equal(
      planWarnings(plan).some((w) => w.code === "UNKNOWN_ACTION"),
      true,
    );
  });
});

// ── Scenario 9: previewPlan ──
describe("previewPlan", () => {
  it("returns the same plan as finalize (identical behavior)", () => {
    const sql = "@limit 100\n@timeout 30s\nSELECT * FROM users;";
    const finalPlan = actionRegistry.finalize(sql);
    const previewPlan = actionRegistry.previewPlan(sql);

    assert.equal(previewPlan.compiledSql, finalPlan.compiledSql);
    assert.equal(previewPlan.pureSql, finalPlan.pureSql);
    assert.equal(previewPlan.actions.length, finalPlan.actions.length);
    assert.equal(planHasErrors(previewPlan), planHasErrors(finalPlan));
  });
});
