export type SqlAnnotationName = "limit" | "timeout" | "explain" | "export" | "chart" | "unknown";

export interface SqlAnnotation {
  raw: string;
  name: SqlAnnotationName;
  value?: string;
}

export interface SqlChartDirective {
  enabled: boolean;
  type: "bar" | "line" | "pie";
  x?: string;
  y?: string;
  title?: string;
  limit?: number;
}

export interface AnnotatedSqlPlan {
  originalSql: string;
  executableSql: string;
  annotations: SqlAnnotation[];
  limit?: number;
  timeoutMs?: number;
  explain: boolean;
  exportCsv: boolean;
  chart?: SqlChartDirective;
  warnings: string[];
}

const KNOWN_ANNOTATIONS = new Set(["limit", "timeout", "explain", "export", "chart"]);

export function parseAnnotatedSql(input: string): AnnotatedSqlPlan {
  const annotations: SqlAnnotation[] = [];
  const sqlLines: string[] = [];
  const warnings: string[] = [];

  for (const line of input.split(/\r?\n/)) {
    const match = line.match(/^\s*@(\w+)(?:\s+(.*))?\s*$/);
    if (!match) {
      sqlLines.push(line);
      continue;
    }

    const annotationName = match[1].toLowerCase();
    const value = (match[2] || "").trim();
    const name = KNOWN_ANNOTATIONS.has(annotationName) ? annotationName as SqlAnnotationName : "unknown";
    annotations.push({ raw: line.trim(), name, value });
    if (name === "unknown") warnings.push(`忽略未知 SQL 注解 @${annotationName}`);
  }

  const directives = buildDirectives(annotations, warnings);
  const baseSql = sqlLines.join("\n").trim();
  const limitedSql = applyLimitDirective(baseSql, directives.limit, warnings);
  const executableSql = applyExplainDirective(limitedSql, directives.explain);

  return {
    originalSql: input,
    executableSql,
    annotations,
    limit: directives.limit,
    timeoutMs: directives.timeoutMs,
    explain: directives.explain,
    exportCsv: directives.exportCsv,
    chart: directives.chart,
    warnings,
  };
}

function buildDirectives(annotations: SqlAnnotation[], warnings: string[]) {
  let limit: number | undefined;
  let timeoutMs: number | undefined;
  let explain = false;
  let exportCsv = false;
  let chart: SqlChartDirective | undefined;

  for (const annotation of annotations) {
    switch (annotation.name) {
      case "limit": {
        const parsedLimit = parsePositiveInt(readSingleValue(annotation.value) ?? readKeyValues(annotation.value).rows ?? readKeyValues(annotation.value).limit);
        if (parsedLimit) limit = parsedLimit;
        else warnings.push(`无法识别 @limit 参数：${annotation.value || "空"}`);
        break;
      }
      case "timeout": {
        const parsedTimeout = parseDurationMs(readSingleValue(annotation.value) ?? readKeyValues(annotation.value).ms ?? readKeyValues(annotation.value).timeout);
        if (parsedTimeout) timeoutMs = parsedTimeout;
        else warnings.push(`无法识别 @timeout 参数：${annotation.value || "空"}`);
        break;
      }
      case "explain":
        explain = true;
        break;
      case "export":
        exportCsv = true;
        break;
      case "chart": {
        const args = readKeyValues(annotation.value);
        const firstValue = readSingleValue(annotation.value);
        const chartType = normalizeChartType(args.type || firstValue);
        chart = {
          enabled: true,
          type: chartType,
          x: args.x,
          y: args.y,
          title: args.title,
          limit: parsePositiveInt(args.limit || args.rows),
        };
        break;
      }
    }
  }

  return { limit, timeoutMs, explain, exportCsv, chart };
}

function applyLimitDirective(sql: string, limit: number | undefined, warnings: string[]) {
  if (!limit || !sql) return sql;
  const trimmed = stripTrailingSemicolon(sql);
  if (!/^\s*(select|with)\b/i.test(trimmed)) {
    warnings.push("@limit 只会自动改写 SELECT / WITH 查询，本次未追加 LIMIT。");
    return sql;
  }
  if (/\blimit\s+\d+(?:\s*,\s*\d+)?\s*$/i.test(trimmed)) {
    warnings.push("SQL 已包含 LIMIT，已跳过 @limit 自动追加。");
    return sql;
  }
  return `${trimmed}\nLIMIT ${limit}`;
}

function applyExplainDirective(sql: string, explain: boolean) {
  if (!explain || !sql) return sql;
  const trimmed = stripTrailingSemicolon(sql);
  if (/^\s*explain\b/i.test(trimmed)) return trimmed;
  return `EXPLAIN ${trimmed}`;
}

function stripTrailingSemicolon(sql: string) {
  return sql.replace(/[;\s]+$/g, "");
}

function normalizeChartType(value?: string): SqlChartDirective["type"] {
  const normalized = value?.toLowerCase();
  if (normalized === "line" || normalized === "pie" || normalized === "bar") return normalized;
  return "bar";
}

function parsePositiveInt(value?: string) {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parseDurationMs(value?: string) {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase();
  const match = normalized.match(/^(\d+(?:\.\d+)?)(ms|s|sec|m|min)?$/);
  if (!match) return undefined;
  const amount = Number(match[1]);
  const unit = match[2] || "ms";
  if (!Number.isFinite(amount) || amount <= 0) return undefined;
  if (unit === "m" || unit === "min") return Math.round(amount * 60_000);
  if (unit === "s" || unit === "sec") return Math.round(amount * 1_000);
  return Math.round(amount);
}

function readSingleValue(value?: string) {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (!trimmed || trimmed.includes("=")) return undefined;
  return trimmed.split(/\s+/)[0];
}

function readKeyValues(value?: string): Record<string, string> {
  if (!value) return {};
  const args: Record<string, string> = {};
  const pattern = /(\w+)=((?:"[^"]+")|(?:'[^']+')|[^\s]+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    args[match[1].toLowerCase()] = match[2].replace(/^['"]|['"]$/g, "");
  }
  return args;
}

export function summarizeAnnotations(plan: AnnotatedSqlPlan) {
  const parts: string[] = [];
  if (plan.limit) parts.push(`LIMIT ${plan.limit}`);
  if (plan.timeoutMs) parts.push(`timeout ${plan.timeoutMs}ms`);
  if (plan.explain) parts.push("EXPLAIN");
  if (plan.exportCsv) parts.push("CSV 导出");
  if (plan.chart) parts.push(`${plan.chart.type} chart`);
  return parts;
}
