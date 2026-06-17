/**
 * DBFox SQL Action Engine — Type Declarations (v2)
 */

/** Processor execution phases */
export type ActionPhase =
  | "compile"        // Pre-execution query rewriting (e.g. @limit, @explain)
  | "beforeExecute"  // Injects parameters right before execution (e.g. @timeout)
  | "aroundExecute"  // Lifecycle hooks wrapping query execution (e.g. @export streaming)
  | "afterExecute";  // Post-execution result processing and rendering (e.g. @chart)

/** Processor metadata configuration */
export interface ActionMeta {
  phase: ActionPhase;
  /** Execution order within the same phase (smaller runs first) */
  order: number;
  /** Whether the directive is allowed to repeat in the same query */
  repeatable: boolean;
  /** Directives that this processor is mutually exclusive with */
  conflictsWith: string[];

  // Autocomplete & Help metadata
  description: string;
  usage: string;
  examples: string[];
}

/** Parsed directive parameters */
export interface ParsedAction {
  type: string;
  raw: string;
  args: Record<string, string>;
  label: string;
}

/** Unified compile and execution diagnostics */
export interface QueryActionIssue {
  code: string;
  level: "warning" | "error";
  action?: string;
  message: string;
  stage: "parse" | "validate" | "compile" | "execute";
}

/** Shared execution context carrying pipeline side-effects */
export interface ExecutionContext {
  timeoutMs: number;
  exportConfig: {
    enabled: boolean;
    format: "csv" | "json";
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

/** Query execution plan containing directive and compilation stats */
export interface QueryExecutionPlan {
  sourceText: string;
  actions: ParsedAction[];
  pureSql: string;
  compiledSql: string;
  context: ExecutionContext;
  issues: QueryActionIssue[];
}

/** Filter errors from plan issues */
export function planErrors(plan: QueryExecutionPlan): QueryActionIssue[] {
  return plan.issues.filter((i) => i.level === "error");
}

/** Filter warnings from plan issues */
export function planWarnings(plan: QueryExecutionPlan): QueryActionIssue[] {
  return plan.issues.filter((i) => i.level === "warning");
}

/** Whether the plan has fatal validation errors */
export function planHasErrors(plan: QueryExecutionPlan): boolean {
  return plan.issues.some((i) => i.level === "error");
}

/** Processor interface implementing parsing, validation, and lifecycle hooks */
export interface ActionProcessor {
  readonly name: string;
  readonly meta: ActionMeta;

  parse(rest: string): Record<string, string> | null;

  /** Validates arguments and returns plan diagnostics */
  validate?(action: ParsedAction, plan: QueryExecutionPlan): QueryActionIssue[];

  /** Applies deterministic plan/context mutations only. Must not perform side effects. */
  apply(action: ParsedAction, plan: QueryExecutionPlan): void;

  formatLabel(args: Record<string, string>): string;
}
