import type { FC } from "react";

interface ExplainVisualizerProps {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

function cellText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

export const ExplainVisualizer: FC<ExplainVisualizerProps> = ({ columns, rows }) => {
  const isSQLite = columns.includes("detail") || columns.includes("selectid");

  if (isSQLite) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "8px 4px" }}>
        <div
          style={{
            padding: "8px 12px",
            background: "var(--bg-secondary)",
            borderRadius: 6,
            fontSize: "0.82rem",
            color: "var(--text-secondary)",
            marginBottom: 8,
            border: "1px solid var(--border-light)",
          }}
        >
          ℹ️ SQLite 查询执行计划树（由上至下执行）：
        </div>
        {rows.map((row, idx) => {
          const detailText = String(row.detail || row.detailText || "");
          const isScan = detailText.toLowerCase().includes("scan");
          const isSearch = detailText.toLowerCase().includes("search");

          return (
            <div
              key={idx}
              className="bg-card border border-border rounded-lg hover-lift animate-slide-down"
              style={{
                padding: "12px 16px",
                borderLeft: isScan
                  ? "4px solid var(--accent-red)"
                  : isSearch
                  ? "4px solid var(--accent-green)"
                  : "4px solid var(--border-medium)",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span
                  className="text-mono"
                  style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-muted)" }}
                >
                  步骤 #{idx + 1}
                </span>
                <span
                  className="tag"
                  style={{
                    background: isScan ? "rgba(220, 38, 38, 0.1)" : isSearch ? "rgba(16, 185, 129, 0.1)" : "var(--bg-active)",
                    color: isScan ? "var(--accent-red)" : isSearch ? "var(--accent-green)" : "var(--text-secondary)",
                    fontWeight: 700,
                    fontSize: "0.72rem",
                  }}
                >
                  {isScan ? "⚠️ 全表/全索引扫描 (SCAN)" : isSearch ? "⚡ 索引查找 (SEARCH)" : "其它操作"}
                </span>
              </div>
              <p
                style={{
                  fontSize: "0.84rem",
                  color: "var(--text-secondary)",
                  fontFamily: "var(--font-mono)",
                  wordBreak: "break-all",
                  margin: 0,
                }}
              >
                {detailText}
              </p>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "8px 4px" }}>
      <div
        style={{
          padding: "8px 12px",
          background: "var(--bg-secondary)",
          borderRadius: 6,
          fontSize: "0.82rem",
          color: "var(--text-secondary)",
          border: "1px solid var(--border-light)",
        }}
      >
        ℹ️ MySQL 优化器执行计划 analysis：
      </div>
      {rows.map((row, idx) => {
        const selectType = cellText(row.select_type, "SIMPLE");
        const tableName = cellText(row.table, "-");
        const joinType = cellText(row.type, "ALL");
        const activeKey = cellText(row.key) || null;
        const possibleKeys = cellText(row.possible_keys) || null;
        const rowsScanned = Number(row.rows) || 0;
        const filtered = row.filtered ? `${String(row.filtered)}%` : null;
        const extra = cellText(row.Extra);

        let cardBorder = "4px solid var(--border-medium)";
        let typeBadgeBg = "var(--bg-active)";
        let typeBadgeColor = "var(--text-secondary)";
        let methodDesc = "未知操作";

        if (["system", "const", "eq_ref"].includes(joinType)) {
          cardBorder = "4px solid var(--accent-green)";
          typeBadgeBg = "rgba(16, 185, 129, 0.12)";
          typeBadgeColor = "var(--accent-green)";
          methodDesc = "⚡ 极速 (常量或唯一键查找)";
        } else if (["ref", "ref_or_null", "index_merge"].includes(joinType)) {
          cardBorder = "4px solid var(--accent-indigo)";
          typeBadgeBg = "rgba(74, 91, 192, 0.12)";
          typeBadgeColor = "var(--accent-indigo)";
          methodDesc = "🔑 索引扫描 (非唯一索引查找)";
        } else if (["range", "index"].includes(joinType)) {
          cardBorder = "4px solid var(--accent-amber)";
          typeBadgeBg = "rgba(217, 119, 6, 0.12)";
          typeBadgeColor = "var(--accent-amber)";
          methodDesc = "⚠️ 索引全扫描 / 范围扫描";
        } else if (joinType === "ALL") {
          cardBorder = "4px solid var(--accent-red)";
          typeBadgeBg = "rgba(220, 38, 38, 0.12)";
          typeBadgeColor = "var(--accent-red)";
          methodDesc = "🚨 全表扫描 (无索引/性能高危)";
        }

        const isFilesort = extra.toLowerCase().includes("using filesort");
        const isTemp = extra.toLowerCase().includes("using temporary");

        return (
          <div
            key={idx}
            className="bg-card border border-border rounded-lg hover-lift animate-slide-down"
            style={{
              padding: "16px 20px",
              borderLeft: cardBorder,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 700,
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  步骤 #{idx + 1}
                </span>
                <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  表: <code style={{ color: "var(--accent-indigo)" }}>{tableName}</code>
                </span>
                <span className="tag" style={{ fontSize: "0.74rem" }}>
                  {selectType}
                </span>
              </div>
              <span
                className="tag"
                style={{
                  background: typeBadgeBg,
                  color: typeBadgeColor,
                  fontWeight: 700,
                  fontSize: "0.78rem",
                }}
              >
                {joinType} — {methodDesc}
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                    marginBottom: 4,
                  }}
                >
                  <span>扫描估算行数 (rows)</span>
                  <strong>{rowsScanned} 行</strong>
                </div>
                <div style={{ height: 6, background: "var(--bg-active)", borderRadius: 3, overflow: "hidden" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.min(100, Math.max(5, (rowsScanned / 10000) * 100))}%`,
                      background: joinType === "ALL" ? "var(--accent-red)" : "var(--accent-indigo)",
                      borderRadius: 3,
                    }}
                  />
                </div>
                {filtered && (
                  <div style={{ marginTop: 4, fontSize: "0.74rem", color: "var(--text-muted)" }}>
                    过滤率 (filtered):{" "}
                    <strong style={{ color: "var(--text-secondary)" }}>{filtered}</strong>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8rem" }}>
                <div style={{ display: "flex", gap: 4 }}>
                  <span style={{ color: "var(--text-muted)", width: 68 }}>实际使用键:</span>
                  <span
                    className="text-mono"
                    style={{
                      color: activeKey ? "var(--accent-green)" : "var(--accent-red)",
                      fontWeight: activeKey ? 600 : 400,
                    }}
                  >
                    {activeKey || "⚠️ 未使用索引"}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <span style={{ color: "var(--text-muted)", width: 68 }}>候选键:</span>
                  <span className="text-mono" style={{ color: "var(--text-secondary)" }}>
                    {possibleKeys || "无"}
                  </span>
                </div>
              </div>
            </div>

            {(extra || isFilesort || isTemp) && (
              <div
                style={{
                  marginTop: 4,
                  paddingTop: 8,
                  borderTop: "1px dashed var(--border-light)",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>诊断特征:</span>
                {isFilesort && (
                  <span
                    className="tag tag-error"
                    style={{
                      fontSize: "0.72rem",
                      background: "rgba(220, 38, 38, 0.08)",
                      border: "1px solid rgba(220, 38, 38, 0.2)",
                      padding: "2px 6px",
                    }}
                  >
                    ⚠️ Filesort (文件排序)
                  </span>
                )}
                {isTemp && (
                  <span
                    className="tag tag-error"
                    style={{
                      fontSize: "0.72rem",
                      background: "rgba(220, 38, 38, 0.08)",
                      border: "1px solid rgba(220, 38, 38, 0.2)",
                      padding: "2px 6px",
                    }}
                  >
                    ⚠️ Temporary (临时表)
                  </span>
                )}
                <span className="text-mono" style={{ fontSize: "0.74rem", color: "var(--text-secondary)" }}>
                  {extra}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
