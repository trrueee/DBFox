import type { FC } from "react";

interface ExplainVisualizerProps {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

type ExplainTone = "neutral" | "success" | "index" | "warning" | "danger";

function cellText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function sqliteTone(detail: string): ExplainTone {
  const normalized = detail.toLowerCase();
  if (normalized.includes("scan")) return "danger";
  if (normalized.includes("search")) return "success";
  return "neutral";
}

function mysqlJoinPresentation(joinType: string): { tone: ExplainTone; description: string } {
  if (["system", "const", "eq_ref"].includes(joinType)) {
    return { tone: "success", description: "极优（常量或唯一键查找）" };
  }
  if (["ref", "ref_or_null", "index_merge"].includes(joinType)) {
    return { tone: "index", description: "索引扫描（非唯一索引查找）" };
  }
  if (["range", "index"].includes(joinType)) {
    return { tone: "warning", description: "索引全扫描 / 范围扫描" };
  }
  if (joinType === "ALL") {
    return { tone: "danger", description: "全表扫描（无索引，性能高风险）" };
  }
  return { tone: "neutral", description: "未知操作" };
}

function scanPercent(rowsScanned: number): number {
  return Math.min(100, Math.max(5, (rowsScanned / 10_000) * 100));
}

export const ExplainVisualizer: FC<ExplainVisualizerProps> = ({ columns, rows }) => {
  const isSQLite = columns.includes("detail") || columns.includes("selectid");

  if (isSQLite) {
    return (
      <div className="explain-visualizer">
        <div className="explain-visualizer__intro explain-visualizer__intro--sqlite">
          ℹ️ SQLite 查询执行计划树（由上至下执行）：
        </div>
        {rows.map((row, index) => {
          const detail = cellText(row.detail ?? row.detailText);
          const tone = sqliteTone(detail);
          const typeLabel = tone === "danger" ? "全表或全索引扫描" : tone === "success" ? "索引查找" : "其他操作";
          return (
            <div key={index} className={`explain-visualizer__card explain-visualizer__card--${tone} bg-card border border-border rounded-lg hover-lift animate-slide-down`}>
              <div className="explain-visualizer__card-header">
                <span className="explain-visualizer__step">步骤 #{index + 1}</span>
                <span className={`explain-visualizer__tag explain-visualizer__tag--${tone}`}>{typeLabel}</span>
              </div>
              <p className="explain-visualizer__detail">{detail}</p>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="explain-visualizer">
      <div className="explain-visualizer__intro">ℹ️ MySQL 优化器执行计划分析：</div>
      {rows.map((row, index) => {
        const selectType = cellText(row.select_type, "SIMPLE");
        const tableName = cellText(row.table, "-");
        const joinType = cellText(row.type, "ALL");
        const activeKey = cellText(row.key) || null;
        const possibleKeys = cellText(row.possible_keys) || null;
        const rowsScanned = Number(row.rows) || 0;
        const filtered = row.filtered === null || row.filtered === undefined || row.filtered === "" ? null : `${String(row.filtered)}%`;
        const extra = cellText(row.Extra);
        const presentation = mysqlJoinPresentation(joinType);
        const hasFilesort = extra.toLowerCase().includes("using filesort");
        const hasTemporary = extra.toLowerCase().includes("using temporary");

        return (
          <div key={index} className={`explain-visualizer__card explain-visualizer__card--${presentation.tone} bg-card border border-border rounded-lg hover-lift animate-slide-down`}>
            <div className="explain-visualizer__card-header">
              <div className="explain-visualizer__header-identity">
                <span className="explain-visualizer__step">步骤 #{index + 1}</span>
                <span className="explain-visualizer__table">表: <code>{tableName}</code></span>
                <span className="explain-visualizer__tag explain-visualizer__select-type">{selectType}</span>
              </div>
              <span className={`explain-visualizer__tag explain-visualizer__tag--${presentation.tone}`}>
                {joinType} — {presentation.description}
              </span>
            </div>

            <div className="explain-visualizer__metrics">
              <div>
                <div className="explain-visualizer__metric-header">
                  <span>扫描估算行数（rows）</span>
                  <strong>{rowsScanned} 行</strong>
                </div>
                <progress
                  className={`explain-visualizer__meter explain-visualizer__meter--${presentation.tone}`}
                  max={100}
                  value={scanPercent(rowsScanned)}
                  aria-label={`扫描估算行数 ${rowsScanned}`}
                />
                {filtered && <div className="explain-visualizer__filtered">过滤率（filtered）: <strong>{filtered}</strong></div>}
              </div>

              <div className="explain-visualizer__keys">
                <div className="explain-visualizer__key-row">
                  <span>实际使用键:</span>
                  <span className={`text-mono explain-visualizer__key-value ${activeKey ? "explain-visualizer__key-value--present" : "explain-visualizer__key-value--missing"}`}>
                    {activeKey || "⚠️ 未使用索引"}
                  </span>
                </div>
                <div className="explain-visualizer__key-row">
                  <span>候选键:</span>
                  <span className="text-mono explain-visualizer__key-value">{possibleKeys || "无"}</span>
                </div>
              </div>
            </div>

            {(extra || hasFilesort || hasTemporary) && (
              <div className="explain-visualizer__diagnostics">
                <span className="explain-visualizer__diagnostic-label">诊断特征:</span>
                {hasFilesort && <span className="explain-visualizer__diagnostic-flag">⚠️ Filesort（文件排序）</span>}
                {hasTemporary && <span className="explain-visualizer__diagnostic-flag">⚠️ Temporary（临时表）</span>}
                <span className="text-mono explain-visualizer__extra">{extra}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
