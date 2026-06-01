import {
  type ActionPhase,
  type ActionProcessor,
  type ExecutionContext,
  type ParsedAction,
  type QueryExecutionPlan,
  planHasErrors,
} from "./types";

const defaultContext = (): ExecutionContext => ({
  timeoutMs: 30000,
  exportConfig: null,
  chartConfig: null,
  extras: {},
});

/** Sort processors within the same phase by order key */
function sortByOrder(processors: ActionProcessor[]): ActionProcessor[] {
  return [...processors].sort((a, b) => a.meta.order - b.meta.order);
}

export class ActionRegistry {
  private processors = new Map<string, ActionProcessor>();

  register(processor: ActionProcessor): this {
    this.processors.set(processor.name, processor);
    return this;
  }

  get(name: string): ActionProcessor | undefined {
    return this.processors.get(name);
  }

  names(): string[] {
    return Array.from(this.processors.keys());
  }

  allProcessors(): ActionProcessor[] {
    return Array.from(this.processors.values());
  }

  /** Gets sorted processors assigned to a specific execution phase */
  private getPhaseProcessors(phase: ActionPhase): ActionProcessor[] {
    return sortByOrder(
      Array.from(this.processors.values()).filter((p) => p.meta.phase === phase),
    );
  }

  // ── parseAll — Scans all @ directives from lines ──
  parseAll(sql: string): { actions: ParsedAction[]; pureSql: string } {
    const lines = sql.split("\n");
    const actions: ParsedAction[] = [];
    const cleanLines: string[] = [];

    for (const line of lines) {
      const trimmed = line.trim();
      const m = trimmed.match(/^@(\w+)\s*(.*)$/);
      if (m) {
        const type = m[1].toLowerCase();
        const rest = m[2].trim();
        const processor = this.get(type);
        const args = processor?.parse(rest) ?? { _raw: rest };
        const label = processor?.formatLabel(args) ?? `${type} ${rest}`;
        actions.push({ type, raw: trimmed, args, label: label.trim() });
      } else {
        cleanLines.push(line);
      }
    }

    return { actions, pureSql: cleanLines.join("\n").trim() };
  }

  // ── buildPlan — Generates raw execution plan ──
  buildPlan(sql: string): QueryExecutionPlan {
    const { actions, pureSql } = this.parseAll(sql);
    return {
      sourceText: sql,
      actions,
      pureSql,
      compiledSql: pureSql,
      context: defaultContext(),
      issues: [],
    };
  }

  // ── validate — Dynamic directives validation and conflict audits ──
  validate(plan: QueryExecutionPlan): QueryExecutionPlan {
    const typeCount = new Map<string, number>();
    const presentTypes = new Set<string>();

    for (const action of plan.actions) {
      const proc = this.get(action.type);

      // Unknown directive warning
      if (!proc) {
        plan.issues.push({
          code: "UNKNOWN_ACTION",
          level: "warning",
          action: action.type,
          message: `未知查询动作: @${action.type}，已忽略`,
          stage: "parse",
        });
        continue;
      }

      presentTypes.add(action.type);
      typeCount.set(action.type, (typeCount.get(action.type) ?? 0) + 1);

      // Re-execution restriction audit
      if (!proc.meta.repeatable && (typeCount.get(action.type) ?? 0) > 1) {
        plan.issues.push({
          code: "DUPLICATE_ACTION",
          level: "error",
          action: action.type,
          message: `@${action.type} 不允许重复出现`,
          stage: "validate",
        });
      }

      // Custom validation rules
      if (proc.validate) {
        const issues = proc.validate(action, plan);
        plan.issues.push(...issues);
      }
    }

    // Two-stage conflict detection and de-duplication
    const conflictPairs = new Set<string>();
    for (const type1 of presentTypes) {
      const proc1 = this.get(type1)!;
      for (const type2 of proc1.meta.conflictsWith) {
        if (presentTypes.has(type2)) {
          const pairKey = [type1, type2].sort().join(":");
          if (!conflictPairs.has(pairKey)) {
            conflictPairs.add(pairKey);
            plan.issues.push({
              code: "CONFLICTING_ACTIONS",
              level: "error",
              action: type1,
              message: `@${type1} 与 @${type2} 冲突，不能同时使用`,
              stage: "validate",
            });
          }
        }
      }
    }

    return plan;
  }

  // ── compile — Allows processors to rewrite compiled SQL query ──
  compile(plan: QueryExecutionPlan): QueryExecutionPlan {
    if (planHasErrors(plan)) return plan;

    for (const proc of this.getPhaseProcessors("compile")) {
      for (const action of plan.actions) {
        if (action.type === proc.name) proc.apply(action, plan);
      }
    }

    return plan;
  }

  // ── applyPhase — Applies phase changes iteratively to the plan ──
  applyPhase(plan: QueryExecutionPlan, phase: ActionPhase): void {
    for (const proc of this.getPhaseProcessors(phase)) {
      for (const action of plan.actions) {
        if (action.type === proc.name) proc.apply(action, plan);
      }
    }
  }

  // ── finalize — Generates full compile-ready plan ──
  finalize(sql: string): QueryExecutionPlan {
    let plan = this.buildPlan(sql);
    plan = this.validate(plan);
    if (planHasErrors(plan)) return plan;
    plan = this.compile(plan);
    return plan;
  }

  // ── previewPlan — Simulates compiler for execution preview ──
  previewPlan(sql: string): QueryExecutionPlan {
    return this.finalize(sql);
  }
}

export const actionRegistry = new ActionRegistry();
