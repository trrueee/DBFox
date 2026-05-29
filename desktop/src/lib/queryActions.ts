/**
 * DataBox 查询动作系统 — Spring Boot 注解架构 (v2)
 *
 * 管线：
 *   sourceText
 *     → parseAll()         扫描 @ 指令
 *     → buildPlan()        构建 ExecutionPlan
 *     → validate()         冲突 / 语法 / 语义校验
 *     → compile()          compile 阶段 Processor 改写 compiledSql
 *     → previewPlan()      可选：执行前预览计划
 *     → applyPhase("beforeExecute")   设置执行参数
 *     → applyPhase("aroundExecute")   边执行边处理（流式导出等）
 *     → executeSQL(plan.compiledSql)  发送到数据库
 *     → applyPhase("afterExecute")    后处理（图表等）
 */

// ═══════════════════════════════════════
// Types
// ═══════════════════════════════════════

/** 处理器执行阶段 */
export type ActionPhase =
  | "compile"        // 改写 SQL（@limit, @explain）
  | "beforeExecute"  // 设置执行参数（@timeout）
  | "aroundExecute"  // 边执行边处理（@export 流式导出）
  | "afterExecute";  // 结果后处理（@chart）

/** 处理器元数据 */
export interface ActionMeta {
  phase: ActionPhase;
  /** 同阶段内排序，数字越小越先执行 */
  order: number;
  /** 同一 SQL 中是否允许重复出现 */
  repeatable: boolean;
  /** 与哪些 action 互斥 */
  conflictsWith: string[];
}

/** 单个 @ 指令的解析结果 */
export interface ParsedAction {
  type: string;
  raw: string;
  args: Record<string, string>;
  label: string;
}

/** 统一的 issue 类型 — 替代之前的 warnings[] + QueryActionError */
export interface QueryActionIssue {
  code: string;
  level: "warning" | "error";
  action?: string;
  message: string;
  stage: "parse" | "validate" | "compile" | "execute";
}

/** 执行上下文 — Processors 通过它传递副作用 */
export interface ExecutionContext {
  timeoutMs: number;
  exportConfig: {
    enabled: boolean;
    format: "csv" | "xlsx" | "json";
    path: string;
    chunkSize: number;
  } | null;
  chartConfig: {
    enabled: boolean;
    type: string;
    x: string;
    y: string;
  } | null;
  extras: Record<string, unknown>;
}

/** 查询执行计划 — 整个管道的中枢数据结构 */
export interface QueryExecutionPlan {
  sourceText: string;
  actions: ParsedAction[];
  pureSql: string;
  compiledSql: string;
  context: ExecutionContext;
  issues: QueryActionIssue[];
}

/** 便捷：从 issues 中提取 errors */
export function planErrors(plan: QueryExecutionPlan): QueryActionIssue[] {
  return plan.issues.filter((i) => i.level === "error");
}

/** 便捷：从 issues 中提取 warnings */
export function planWarnings(plan: QueryExecutionPlan): QueryActionIssue[] {
  return plan.issues.filter((i) => i.level === "warning");
}

/** 便捷：是否有致命错误 */
export function planHasErrors(plan: QueryExecutionPlan): boolean {
  return plan.issues.some((i) => i.level === "error");
}

// ═══════════════════════════════════════
// ActionProcessor
// ═══════════════════════════════════════

export interface ActionProcessor {
  readonly name: string;
  readonly meta: ActionMeta;

  parse(rest: string): Record<string, string> | null;

  /** 返回 issues（可以是 warning 或 error） */
  validate?(action: ParsedAction, plan: QueryExecutionPlan): QueryActionIssue[];

  /** 按阶段修改 plan */
  apply(action: ParsedAction, plan: QueryExecutionPlan): void;

  formatLabel(args: Record<string, string>): string;
}

// ═══════════════════════════════════════
// Registry
// ═══════════════════════════════════════

const defaultContext = (): ExecutionContext => ({
  timeoutMs: 30000,
  exportConfig: null,
  chartConfig: null,
  extras: {},
});

/** 按 meta.order 排序 processors */
function sortByOrder(processors: ActionProcessor[]): ActionProcessor[] {
  return [...processors].sort((a, b) => a.meta.order - b.meta.order);
}

class ActionRegistry {
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

  /** 获取指定阶段的 processors，按 order 排序 */
  private getPhaseProcessors(phase: ActionPhase): ActionProcessor[] {
    return sortByOrder(
      Array.from(this.processors.values()).filter((p) => p.meta.phase === phase),
    );
  }

  // ── parseAll — 扫描全部 @ 指令 ──

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

  // ── buildPlan — 构建执行计划 ──

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

  // ── validate — 冲突检测 + 各 Processor 自定义校验 ──

  validate(plan: QueryExecutionPlan): QueryExecutionPlan {
    const typeCount = new Map<string, number>();
    const registeredTypes = new Set<string>();

    for (const action of plan.actions) {
      const proc = this.get(action.type);

      // 未知动作
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

      registeredTypes.add(action.type);
      typeCount.set(action.type, (typeCount.get(action.type) ?? 0) + 1);

      // 重复检测
      if (!proc.meta.repeatable && (typeCount.get(action.type) ?? 0) > 1) {
        plan.issues.push({
          code: "DUPLICATE_ACTION",
          level: "error",
          action: action.type,
          message: `@${action.type} 不允许重复出现`,
          stage: "validate",
        });
      }

      // 冲突检测
      for (const conflict of proc.meta.conflictsWith) {
        if (registeredTypes.has(conflict)) {
          plan.issues.push({
            code: "CONFLICTING_ACTIONS",
            level: "error",
            action: action.type,
            message: `@${action.type} 与 @${conflict} 冲突，不能同时使用`,
            stage: "validate",
          });
        }
      }

      // 自定义校验
      if (proc.validate) {
        const issues = proc.validate(action, plan);
        plan.issues.push(...issues);
      }
    }

    return plan;
  }

  // ── compile — compile 阶段 Processor 改写 compiledSql ──

  compile(plan: QueryExecutionPlan): QueryExecutionPlan {
    if (planHasErrors(plan)) return plan;

    for (const proc of this.getPhaseProcessors("compile")) {
      const action = plan.actions.find((a) => a.type === proc.name);
      if (action) proc.apply(action, plan);
    }

    return plan;
  }

  // ── applyPhase — 按阶段执行 processors ──

  applyPhase(plan: QueryExecutionPlan, phase: ActionPhase): void {
    for (const proc of this.getPhaseProcessors(phase)) {
      const action = plan.actions.find((a) => a.type === proc.name);
      if (action) proc.apply(action, plan);
    }
  }

  // ── finalize — buildPlan → validate → compile ──

  finalize(sql: string): QueryExecutionPlan {
    let plan = this.buildPlan(sql);
    plan = this.validate(plan);
    if (planHasErrors(plan)) return plan;
    plan = this.compile(plan);
    return plan;
  }

  // ── previewPlan — 执行前预览（等同 finalize，留给 UI 使用） ──

  previewPlan(sql: string): QueryExecutionPlan {
    return this.finalize(sql);
  }
}

// ═══════════════════════════════════════
// Built-in Processors
// ═══════════════════════════════════════

const LimitProcessor: ActionProcessor = {
  name: "limit",
  meta: { phase: "compile", order: 100, repeatable: false, conflictsWith: [] },

  parse(rest) {
    const n = parseInt(rest) || parseInt(rest.match(/(\d+)/)?.[0] ?? "100");
    return { rows: String(n) };
  },

  validate(_action, plan) {
    const issues: QueryActionIssue[] = [];
    if (/limit\s+\d+/i.test(plan.pureSql)) {
      issues.push({
        code: "LIMIT_ALREADY_EXISTS",
        level: "warning",
        action: "limit",
        message: "SQL 中已包含 LIMIT 子句，@limit 将被跳过",
        stage: "validate",
      });
    }
    return issues;
  },

  apply(action, plan) {
    const n = parseInt(action.args.rows ?? "100");
    if (!/limit\s+\d+/i.test(plan.compiledSql)) {
      plan.compiledSql = plan.compiledSql.replace(/;\s*$/, "");
      plan.compiledSql += ` LIMIT ${n};`;
    }
  },

  formatLabel(args) {
    return `LIMIT ${args.rows ?? "100"}`;
  },
};

const TimeoutProcessor: ActionProcessor = {
  name: "timeout",
  meta: { phase: "beforeExecute", order: 100, repeatable: false, conflictsWith: [] },

  parse(rest) {
    const sec = parseInt(rest) || 30;
    return { seconds: String(Math.max(1, sec)) };
  },

  apply(action, plan) {
    const sec = parseInt(action.args.seconds ?? "30");
    plan.context.timeoutMs = sec * 1000;
  },

  formatLabel(args) {
    return `超时 ${args.seconds ?? "30"}s`;
  },
};

const ExplainProcessor: ActionProcessor = {
  name: "explain",
  meta: { phase: "compile", order: 900, repeatable: false, conflictsWith: ["export"] },

  parse(_rest) {
    return {};
  },

  validate(_action, plan) {
    if (/^\s*explain\s/i.test(plan.pureSql)) {
      return [{
        code: "ALREADY_EXPLAIN",
        level: "warning",
        action: "explain",
        message: "SQL 已是 EXPLAIN 查询",
        stage: "validate",
      }];
    }
    return [];
  },

  apply(_action, plan) {
    if (!/^\s*explain\s/i.test(plan.compiledSql)) {
      plan.compiledSql = `EXPLAIN ${plan.compiledSql}`;
    }
  },

  formatLabel() {
    return "执行计划";
  },
};

const ExportProcessor: ActionProcessor = {
  name: "export",
  meta: { phase: "aroundExecute", order: 100, repeatable: false, conflictsWith: ["explain"] },

  parse(rest) {
    const args: Record<string, string> = {};
    const parts = rest.split(/\s+/);
    let posIdx = 0;
    for (const part of parts) {
      const kv = part.match(/^(\w+)=(.+)$/);
      if (kv) {
        args[kv[1]] = kv[2].replace(/^["']|["']$/g, "");
      } else {
        const key = posIdx === 0 ? "type" : posIdx === 1 ? "path" : `_${posIdx}`;
        args[key] = part.replace(/^["']|["']$/g, "");
        posIdx++;
      }
    }
    return args;
  },

  validate(action, _plan) {
    const format = (action.args.type ?? "csv").toLowerCase();
    if (!["csv", "xlsx", "json", "sql"].includes(format)) {
      return [{
        code: "INVALID_EXPORT_FORMAT",
        level: "error",
        action: "export",
        message: `不支持的导出格式: ${format}，支持 csv / xlsx / json / sql`,
        stage: "validate",
      }];
    }
    return [];
  },

  apply(action, plan) {
    const format = (action.args.type ?? "csv") as "csv" | "xlsx" | "json";
    const path = action.args.path ?? `./exports/databox_export.${format}`;
    plan.context.exportConfig = {
      enabled: true,
      format,
      path,
      chunkSize: parseInt(action.args.chunk ?? action.args.chunkSize ?? "5000"),
    };
  },

  formatLabel(args) {
    const fmt = args.type ?? "csv";
    const p = args.path ?? "";
    const short = p.length > 30 ? "..." + p.slice(-25) : p;
    return `导出 ${fmt} → ${short}`;
  },
};

const ChartProcessor: ActionProcessor = {
  name: "chart",
  meta: { phase: "afterExecute", order: 100, repeatable: false, conflictsWith: ["explain"] },

  parse(rest) {
    const args: Record<string, string> = {};
    const parts = rest.split(/\s+/);
    for (const part of parts) {
      const kv = part.match(/^(\w+)=(.+)$/);
      if (kv) {
        args[kv[1]] = kv[2];
      } else if (!args.type) {
        args.type = part;
      } else if (!args.x) {
        args.x = part.replace(/^x=/i, "");
      } else if (!args.y) {
        args.y = part.replace(/^y=/i, "");
      }
    }
    return args;
  },

  validate(action, _plan) {
    const validTypes = ["line", "bar", "pie", "scatter", "area"];
    const chartType = (action.args.type ?? "bar").toLowerCase();
    if (!validTypes.includes(chartType)) {
      return [{
        code: "INVALID_CHART_TYPE",
        level: "error",
        action: "chart",
        message: `不支持的图表类型: ${chartType}，支持 ${validTypes.join(" / ")}`,
        stage: "validate",
      }];
    }
    return [];
  },

  apply(action, plan) {
    plan.context.chartConfig = {
      enabled: true,
      type: action.args.type ?? "bar",
      x: action.args.x ?? "",
      y: action.args.y ?? "",
    };
  },

  formatLabel(args) {
    const t = args.type ?? "bar";
    const x = args.x ? ` x=${args.x}` : "";
    const y = args.y ? ` y=${args.y}` : "";
    return `图表 ${t}${x}${y}`;
  },
};

// ═══════════════════════════════════════
// Global Registry — 启动自动装配
// ═══════════════════════════════════════

export const actionRegistry = new ActionRegistry()
  .register(LimitProcessor)    // compile,     order 100
  .register(TimeoutProcessor)  // beforeExecute, order 100
  .register(ExplainProcessor)  // compile,     order 900 (must be after limit)
  .register(ExportProcessor)   // aroundExecute, order 100
  .register(ChartProcessor);   // afterExecute,  order 100

export function registerActionProcessor(processor: ActionProcessor): void {
  actionRegistry.register(processor);
}
