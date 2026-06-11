import { useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";
import { ImageCell, isImageUrl } from "../../components/ImageCell";
import { isNumericLike, toChartNumber } from "../../lib/chart-utils";
import { executeSql, getDefaultDatasource, type EngineSqlResult } from "../engine/engineApi";
import { parseAnnotatedSql, summarizeAnnotations, type AnnotatedSqlPlan, type SqlChartDirective } from "./sqlAnnotations";
import "./sqlConsoleAnnotations.css";

interface SqlConsoleWorkspaceProps {
  sqlQuery: string;
  onSqlQueryChange: (value: string) => void;
  onToast: (message: string) => void;
}

type ConsoleEntry =
  | { id: number; kind: "info"; text: string; time: string }
  | { id: number; kind: "annotations"; plan: AnnotatedSqlPlan; time: string }
  | { id: number; kind: "sql"; sql: string; executableSql?: string; time: string }
  | { id: number; kind: "result"; result: EngineSqlResult; plan?: AnnotatedSqlPlan; time: string }
  | { id: number; kind: "error"; message: string; time: string };

// Distributive omit: Omit over a discriminated union collapses variants,
// so map each variant separately.
type ConsoleEntryDraft = ConsoleEntry extends infer T
  ? T extends ConsoleEntry
    ? Omit<T, "id" | "time">
    : never
  : never;

let entrySeq = 0;
const nextEntryId = () => ++entrySeq;

export function SqlConsoleWorkspace({ sqlQuery, onSqlQueryChange, onToast }: SqlConsoleWorkspaceProps) {
  const [entries, setEntries] = useState<ConsoleEntry[]>([
    { id: nextEntryId(), kind: "info", text: "SQL Console 已就绪：支持 @limit、@timeout、@explain、@export、@chart 注解。按 F9 或 Ctrl+Enter 执行。", time: formatTime() },
  ]);
  const [running, setRunning] = useState(false);
  const [dbLabel, setDbLabel] = useState("local engine");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getDefaultDatasource()
      .then((datasource) => {
        if (datasource) setDbLabel(`${datasource.database_name} · ${datasource.db_type}`);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [entries, running]);

  const appendEntries = (items: ConsoleEntryDraft[]) => {
    const time = formatTime();
    setEntries((prev) => [...prev, ...items.map((item) => ({ ...item, id: nextEntryId(), time }) as ConsoleEntry)]);
  };

  const runSql = async () => {
    const rawSql = sqlQuery.trim();
    if (!rawSql) {
      onToast("SQL 不能为空");
      return;
    }
    if (running) return;

    const plan = parseAnnotatedSql(rawSql);
    if (!plan.executableSql.trim()) {
      onToast("SQL 注解后没有可执行语句");
      return;
    }

    setRunning(true);
    const annotationSummary = summarizeAnnotations(plan);
    appendEntries([
      { kind: "sql", sql: rawSql, executableSql: plan.executableSql !== rawSql ? plan.executableSql : undefined },
      ...(annotationSummary.length > 0 || plan.warnings.length > 0 ? [{ kind: "annotations", plan } as const] : []),
    ]);
    onSqlQueryChange("");

    try {
      const datasource = await getDefaultDatasource();
      if (!datasource) {
        throw new Error("暂无可用数据源，请先创建并同步数据源。");
      }
      setDbLabel(`${datasource.database_name} · ${datasource.db_type}`);
      const result = await withOptionalTimeout(
        executeSql(datasource.id, plan.executableSql, "SQL Console"),
        plan.timeoutMs,
      );
      const extras: ConsoleEntryDraft[] = [{ kind: "result", result, plan }];
      for (const warning of plan.warnings) {
        extras.push({ kind: "info", text: `[WARN] ${warning}` });
      }
      for (const warning of result.warnings ?? []) {
        extras.push({ kind: "info", text: `[WARN] ${warning}` });
      }
      for (const notice of result.notices ?? []) {
        extras.push({ kind: "info", text: `[INFO] ${notice}` });
      }
      appendEntries(extras);
    } catch (err) {
      const message = err instanceof Error ? err.message : "SQL 执行失败";
      appendEntries([{ kind: "error", message }]);
      onSqlQueryChange(rawSql);
    } finally {
      setRunning(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "F9" || (event.key === "Enter" && (event.ctrlKey || event.metaKey))) {
      event.preventDefault();
      void runSql();
    }
  };

  const clearConsole = () => {
    setEntries([{ id: nextEntryId(), kind: "info", text: "控制台已清屏。", time: formatTime() }]);
  };

  return (
    <div className="hifi-sql-workspace hifi-tab-pane flex flex-col h-full">
      <div className="hifi-panel-toolbar flex-shrink-0">
        <div className="hifi-toolbar-left">
          <span className="font-semibold text-[11px] text-slate-700">SQL Console / {dbLabel}</span>
          <span className="sql-console-toolbar-hint">@chart bar x=字段 y=数值 · @limit 100 · @export csv</span>
        </div>
        <div className="hifi-toolbar-right">
          <button className="hifi-guide-btn-primary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={runSql} disabled={running}>
            <Play size={10} />
            <span>{running ? "运行中..." : "运行 (F9)"}</span>
          </button>
          <button className="hifi-toolbar-btn" style={{ height: "24px" }} onClick={clearConsole}>清屏</button>
        </div>
      </div>

      <div className="sql-console" onClick={(event) => { if (event.target === event.currentTarget) inputRef.current?.focus(); }}>
        <div className="sql-console-scroll" ref={scrollRef}>
          {entries.map((entry) => renderEntry(entry))}

          {running && <div className="sql-console-running">执行中...</div>}

          <div className="sql-console-prompt">
            <span className="sql-console-prompt-label">sql&gt;</span>
            <textarea
              ref={inputRef}
              className="sql-console-input"
              value={sqlQuery}
              onChange={(event) => onSqlQueryChange(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={Math.min(12, Math.max(1, sqlQuery.split("\n").length))}
              placeholder={'输入 SQL；可在语句前写 @chart bar x=month y=count、@limit 50、@explain'}
              spellCheck={false}
              autoCapitalize="off"
              autoComplete="off"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function renderEntry(entry: ConsoleEntry) {
  switch (entry.kind) {
    case "info":
      return (
        <div key={entry.id} className={`sql-console-info ${entry.text.startsWith("[WARN]") ? "warn" : ""}`}>
          {entry.text}
        </div>
      );
    case "annotations":
      return <AnnotationBlock key={entry.id} plan={entry.plan} />;
    case "sql":
      return (
        <div key={entry.id} className="sql-console-stmt">
          <span className="sql-console-prompt-label">sql&gt;</span>
          <div className="sql-console-stmt-body">
            <pre className="sql-console-sql">{entry.sql}</pre>
            {entry.executableSql && (
              <details className="sql-console-rewritten">
                <summary>查看注解改写后的执行 SQL</summary>
                <pre>{entry.executableSql}</pre>
              </details>
            )}
          </div>
        </div>
      );
    case "error":
      return (
        <div key={entry.id} className="sql-console-error">
          <strong>ERROR</strong> {entry.message}
        </div>
      );
    case "result":
      return <ResultBlock key={entry.id} result={entry.result} plan={entry.plan} time={entry.time} />;
  }
}

function AnnotationBlock({ plan }: { plan: AnnotatedSqlPlan }) {
  const summary = summarizeAnnotations(plan);
  return (
    <div className="sql-console-annotation-block">
      <span className="sql-console-annotation-title">Annotations</span>
      {summary.length > 0 ? summary.map((item) => <span key={item} className="sql-console-annotation-chip">{item}</span>) : <span className="sql-console-annotation-muted">无有效注解</span>}
      {plan.warnings.map((warning) => <span key={warning} className="sql-console-annotation-warning">{warning}</span>)}
    </div>
  );
}

function ResultBlock({ result, plan, time }: { result: EngineSqlResult; plan?: AnnotatedSqlPlan; time: string }) {
  const canExport = Boolean(plan?.exportCsv && result.columns.length > 0);
  return (
    <div className="sql-console-result">
      <div className="sql-console-result-meta">
        <span>{result.rowCount} 行 · {result.latencyMs}ms · {time}{result.truncated ? " · 结果已截断" : ""}</span>
        {canExport && <button className="sql-console-export-btn" onClick={() => downloadCsv(result)}>导出 CSV</button>}
      </div>
      {result.columns.length > 0 ? (
        <>
          {plan?.chart && <ChartBlock result={result} chart={plan.chart} />}
          <div className="sql-console-table-wrap">
            <table className="sql-console-table">
              <thead>
                <tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr>
              </thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {result.columns.map((column) => {
                      const value = row[column];
                      if (isImageUrl(value)) {
                        return (
                          <td key={column}>
                            <ImageCell url={value} />
                          </td>
                        );
                      }
                      return (
                        <td key={column} title={valueToText(value)}>
                          {value ?? <span className="sql-console-null">NULL</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {result.rows.length === 0 && (
                  <tr><td colSpan={Math.max(result.columns.length, 1)} className="sql-console-empty">执行成功，无结果集。</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="sql-console-info">执行成功。</div>
      )}
    </div>
  );
}

function ChartBlock({ result, chart }: { result: EngineSqlResult; chart: SqlChartDirective }) {
  const series = buildChartSeries(result, chart);
  if (!series) {
    return (
      <div className="sql-console-chart sql-console-chart-empty">
        @chart 需要至少一个可数值化字段。可写：@chart bar x=名称字段 y=数值字段
      </div>
    );
  }

  return (
    <div className="sql-console-chart">
      <div className="sql-console-chart-head">
        <div>
          <strong>{chart.title || "SQL Result Chart"}</strong>
          <span>{series.xColumn} → {series.yColumn}</span>
        </div>
        <span className="sql-console-chart-type">{chart.type}</span>
      </div>
      {chart.type === "line" ? <LineChartPreview points={series.points} max={series.max} /> : null}
      {chart.type === "pie" ? <PieChartPreview points={series.points} total={series.total} /> : null}
      {chart.type === "bar" ? <BarChartPreview points={series.points} max={series.max} /> : null}
    </div>
  );
}

function BarChartPreview({ points, max }: { points: ChartPoint[]; max: number }) {
  return (
    <div className="sql-console-chart-bars">
      {points.map((point) => (
        <div className="sql-console-chart-row" key={point.label}>
          <span className="sql-console-chart-label" title={point.label}>{point.label}</span>
          <div className="sql-console-chart-track"><span style={{ width: `${max > 0 ? Math.max(2, (point.value / max) * 100) : 0}%` }} /></div>
          <span className="sql-console-chart-value">{formatChartNumber(point.value)}</span>
        </div>
      ))}
    </div>
  );
}

function LineChartPreview({ points, max }: { points: ChartPoint[]; max: number }) {
  const width = 520;
  const height = 140;
  const safeMax = max > 0 ? max : 1;
  const coords = points.map((point, index) => {
    const x = points.length <= 1 ? 0 : (index / (points.length - 1)) * width;
    const y = height - (point.value / safeMax) * height;
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="sql-console-chart-line">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="line chart">
        <polyline points={coords} fill="none" stroke="currentColor" strokeWidth="2" />
        {points.map((point, index) => {
          const x = points.length <= 1 ? 0 : (index / (points.length - 1)) * width;
          const y = height - (point.value / safeMax) * height;
          return <circle key={`${point.label}-${index}`} cx={x} cy={y} r="3" fill="currentColor" />;
        })}
      </svg>
      <div className="sql-console-chart-axis">
        <span>{points[0]?.label}</span>
        <span>{points[points.length - 1]?.label}</span>
      </div>
    </div>
  );
}

function PieChartPreview({ points, total }: { points: ChartPoint[]; total: number }) {
  return (
    <div className="sql-console-chart-pie-list">
      {points.map((point) => (
        <div key={point.label} className="sql-console-chart-pie-item">
          <span title={point.label}>{point.label}</span>
          <strong>{total > 0 ? `${Math.round((point.value / total) * 100)}%` : "0%"}</strong>
          <em>{formatChartNumber(point.value)}</em>
        </div>
      ))}
    </div>
  );
}

interface ChartPoint {
  label: string;
  value: number;
}

function buildChartSeries(result: EngineSqlResult, chart: SqlChartDirective) {
  const yColumn = chart.y && result.columns.includes(chart.y)
    ? chart.y
    : result.columns.find((column) => result.rows.some((row) => isNumericLike(row[column])));
  if (!yColumn) return null;

  const xColumn = chart.x && result.columns.includes(chart.x)
    ? chart.x
    : result.columns.find((column) => column !== yColumn) || yColumn;
  const limit = chart.limit || 12;
  const points = result.rows.slice(0, limit).map((row, index) => ({
    label: valueToText(row[xColumn]) || `row ${index + 1}`,
    value: toChartNumber(row[yColumn]),
  }));
  const max = Math.max(...points.map((point) => point.value), 0);
  const total = points.reduce((sum, point) => sum + point.value, 0);
  return { xColumn, yColumn, points, max, total };
}

function valueToText(value: unknown) {
  if (value == null) return "";
  return String(value);
}

function downloadCsv(result: EngineSqlResult) {
  const csv = [
    result.columns.join(","),
    ...result.rows.map((row) => result.columns.map((column) => escapeCsvCell(row[column])).join(",")),
  ].join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `databox-result-${Date.now()}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function escapeCsvCell(value: unknown) {
  const text = valueToText(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function withOptionalTimeout<T>(promise: Promise<T>, timeoutMs?: number) {
  if (!timeoutMs) return promise;
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      window.setTimeout(() => reject(new Error(`SQL 执行超过 @timeout ${timeoutMs}ms，已停止等待结果。`)), timeoutMs);
    }),
  ]);
}

function formatChartNumber(value: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
