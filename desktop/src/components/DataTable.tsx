import { useState } from "react";
import { Check, Copy, X } from "lucide-react";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  numericColumns?: string[];
  maxHeight?: string;
}

function isNumeric(val: unknown): boolean {
  return typeof val === "number";
}

function tryParseJson(str: unknown): any {
  if (typeof str !== "string") return null;
  const trimmed = str.trim();
  if (
    !(trimmed.startsWith("{") && trimmed.endsWith("}")) &&
    !(trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

// 🌳 Collapsible JSON Tree Viewer Component
const JsonTree: React.FC<{ data: any; depth?: number }> = ({ data, depth = 0 }) => {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggle = (key: string) => {
    setCollapsed((c) => ({ ...c, [key]: !c[key] }));
  };

  if (data === null) {
    return <span style={{ color: "var(--text-muted)" }}>null</span>;
  }
  if (typeof data === "boolean") {
    return (
      <span style={{ color: "var(--accent-indigo)", fontWeight: 600 }}>
        {String(data)}
      </span>
    );
  }
  if (typeof data === "number") {
    return (
      <span style={{ color: "var(--accent-green)", fontWeight: 600 }}>{data}</span>
    );
  }
  if (typeof data === "string") {
    return <span style={{ color: "var(--accent-amber)" }}>"{data}"</span>;
  }

  const isArray = Array.isArray(data);
  const keys = isArray ? data.map((_, i) => String(i)) : Object.keys(data);

  return (
    <div
      style={{
        paddingLeft: depth > 0 ? 12 : 0,
        fontFamily: "var(--font-mono)",
        fontSize: "0.82rem",
        lineHeight: "1.6",
      }}
    >
      <span style={{ color: "var(--text-muted)" }}>{isArray ? "[" : "{"}</span>
      <div
        style={{
          borderLeft: "1px dashed var(--border-light)",
          marginLeft: 6,
          paddingLeft: 8,
        }}
      >
        {keys.map((key) => {
          const val = isArray ? data[Number(key)] : data[key];
          const isObj = val && typeof val === "object";
          const isKeyCollapsed = collapsed[key];

          return (
            <div key={key} style={{ margin: "2px 0" }}>
              {!isArray && (
                <span style={{ color: "var(--text-secondary)", marginRight: 4, fontWeight: 500 }}>
                  "{key}":
                </span>
              )}
              {isObj ? (
                <>
                  <button
                    onClick={() => toggle(key)}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: "0 4px",
                      fontSize: "0.7rem",
                      fontFamily: "monospace",
                    }}
                  >
                    {isKeyCollapsed ? "▶" : "▼"}
                  </button>
                  {isKeyCollapsed ? (
                    <span style={{ color: "var(--text-muted)", fontSize: "0.76rem" }}>
                      {Array.isArray(val) ? `Array(${val.length}) [...]` : "Object {...}"}
                    </span>
                  ) : (
                    <JsonTree data={val} depth={depth + 1} />
                  )}
                </>
              ) : (
                <JsonTree data={val} depth={depth + 1} />
              )}
              {key !== keys[keys.length - 1] && (
                <span style={{ color: "var(--text-muted)" }}>,</span>
              )}
            </div>
          );
        })}
      </div>
      <span style={{ color: "var(--text-muted)" }}>{isArray ? "]" : "}"}</span>
    </div>
  );
};

export function DataTable({ columns, rows, numericColumns, maxHeight }: DataTableProps) {
  const numericSet = new Set(numericColumns ?? []);
  
  // Persistent inspector Modal state
  const [activeInspect, setActiveInspect] = useState<{
    col: string;
    val: string;
    isJson: boolean;
  } | null>(null);
  const [inspectMode, setInspectMode] = useState<"tree" | "raw">("tree");
  const [copied, setCopied] = useState(false);

  // Floating hover Preview Card state
  const [hoveredCell, setHoveredCell] = useState<{
    col: string;
    val: string;
    isJson: boolean;
    rect: DOMRect;
  } | null>(null);

  const handleOpenInspect = (col: string, val: string, isJson: boolean) => {
    setActiveInspect({ col, val, isJson });
    setInspectMode("tree");
    setCopied(false);
  };

  const handleCopyValue = async () => {
    if (!activeInspect) return;
    await navigator.clipboard.writeText(activeInspect.val);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleMouseEnterCell = (col: string, val: unknown, e: React.MouseEvent<HTMLTableCellElement>) => {
    const valStr = String(val);
    const jsonParsed = tryParseJson(val);
    const isJson = jsonParsed !== null;
    
    // Only show hovered preview card if it is complex JSON or long text (> 25 characters)
    if (isJson || valStr.length > 25) {
      const rect = e.currentTarget.getBoundingClientRect();
      setHoveredCell({
        col,
        val: valStr,
        isJson,
        rect
      });
    } else {
      setHoveredCell(null);
    }
  };

  return (
    <div className="select-text" style={{ overflow: "auto", maxHeight: maxHeight ?? "100%", position: "relative", userSelect: "text" }}>
      {/* Dynamic CSS injection for anti-串行 hover row highlights and crisp borders */}
      <style>{`
        .data-table-premium {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.82rem;
        }
        .data-table-premium th {
          position: sticky;
          top: 0;
          z-index: 10;
          background: var(--bg-secondary);
          border-bottom: 2px solid var(--border-medium);
          border-right: 1px solid var(--border-light);
          padding: 8px 12px;
          text-align: left;
          color: var(--text-secondary);
          font-weight: 600;
        }
        .data-table-premium td {
          padding: 6px 12px;
          border-bottom: 1px solid var(--border-light);
          border-right: 1px solid var(--border-light);
          color: var(--text-primary);
          transition: background-color 0.1s ease;
        }
        .data-table-premium tr:hover td {
          background-color: rgba(74, 91, 192, 0.05) !important;
        }
        .data-table-premium tr:nth-child(even) td {
          background-color: rgba(255, 255, 255, 0.015);
        }
        .row-counter-cell {
          color: var(--text-muted) !important;
          font-size: 0.74rem;
          font-weight: 600;
          text-align: center !important;
          background: var(--bg-secondary) !important;
          width: 44px;
          user-select: none;
          border-right: 2px solid var(--border-medium) !important;
        }
      `}</style>

      <table className="data-table-premium">
        <thead>
          <tr>
            <th className="row-counter-cell">#</th>
            {columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              <td className="row-counter-cell">{ri + 1}</td>
              {columns.map((col) => {
                const val = row[col];
                const isNum = numericSet.has(col) || isNumeric(val);

                if (val === null || val === undefined) {
                  return (
                    <td
                      key={`${ri}-${col}`}
                      className="cell-null"
                      onMouseEnter={(e) => handleMouseEnterCell(col, "NULL", e)}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      NULL
                    </td>
                  );
                }

                // Try JSON detection
                const jsonParsed = tryParseJson(val);
                if (jsonParsed !== null) {
                  return (
                    <td
                      key={`${ri}-${col}`}
                      style={{ whiteSpace: "nowrap" }}
                      onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span
                          className="status-badge"
                          style={{
                            background: "rgba(74, 91, 192, 0.12)",
                            color: "var(--accent-indigo)",
                            border: "1px solid rgba(74, 91, 192, 0.3)",
                            fontSize: "0.7rem",
                            padding: "1px 5px",
                            fontWeight: 600,
                          }}
                        >
                          JSON
                        </span>
                        <span
                          className="text-mono"
                          style={{
                            fontSize: "0.78rem",
                            color: "var(--text-secondary)",
                            textOverflow: "ellipsis",
                            overflow: "hidden",
                            maxWidth: 180,
                            display: "inline-block",
                          }}
                        >
                          {String(val)}
                        </span>
                        <button
                          onClick={() => handleOpenInspect(col, String(val), true)}
                          style={{
                            border: "none",
                            background: "rgba(74, 91, 192, 0.08)",
                            color: "var(--accent-indigo)",
                            padding: "2px 6px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.72rem",
                            fontWeight: 600,
                          }}
                        >
                          展开 🔍
                        </button>
                      </div>
                    </td>
                  );
                }

                // Long text detection (> 80 characters)
                const valStr = String(val);
                if (valStr.length > 80) {
                  return (
                    <td
                      key={`${ri}-${col}`}
                      onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span
                          style={{
                            fontSize: "0.8rem",
                            color: "var(--text-primary)",
                            textOverflow: "ellipsis",
                            overflow: "hidden",
                            whiteSpace: "nowrap",
                            maxWidth: 240,
                            display: "inline-block",
                          }}
                        >
                          {valStr}
                        </span>
                        <button
                          onClick={() => handleOpenInspect(col, valStr, false)}
                          style={{
                            border: "none",
                            background: "rgba(100, 116, 139, 0.08)",
                            color: "var(--text-secondary)",
                            padding: "2px 6px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.72rem",
                            fontWeight: 600,
                          }}
                        >
                          更多 🔍
                        </button>
                      </div>
                    </td>
                  );
                }

                return (
                  <td
                    key={`${ri}-${col}`}
                    className={isNum ? "cell-number" : undefined}
                    onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                    onMouseLeave={() => setHoveredCell(null)}
                  >
                    {valStr}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* 🔮 SLICK FLOATING HOVER PREVIEW CARD */}
      {hoveredCell && (
        <div
          style={{
            position: "fixed",
            top: window.innerHeight - hoveredCell.rect.top < 220 ? hoveredCell.rect.top - 180 : hoveredCell.rect.bottom + 6,
            left: Math.min(window.innerWidth - 360, Math.max(16, hoveredCell.rect.left)),
            width: "340px",
            maxHeight: "160px",
            background: "rgba(30, 41, 59, 0.95)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(255, 255, 255, 0.15)",
            borderRadius: "8px",
            padding: "10px 14px",
            boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)",
            zIndex: 99999,
            pointerEvents: "none", // Ensures hover is completely transparent and smooth to scan!
            overflow: "auto",
            animation: "fadeIn 0.1s ease-out",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255, 255, 255, 0.1)", paddingBottom: 4, marginBottom: 6 }}>
            <span style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--accent-indigo)" }}>
              ⚡ Hover 实时预览
            </span>
            <span style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.4)", fontFamily: "monospace" }}>
              字段: {hoveredCell.col}
            </span>
          </div>
          <pre
            style={{
              margin: 0,
              padding: 0,
              background: "transparent",
              border: "none",
              fontFamily: "var(--font-mono)",
              fontSize: "0.74rem",
              color: "rgba(255, 255, 255, 0.95)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
              lineHeight: "1.4",
            }}
          >
            {(() => {
              if (hoveredCell.isJson) {
                try {
                  const parsed = JSON.parse(hoveredCell.val);
                  return JSON.stringify(parsed, null, 2);
                } catch {
                  return hoveredCell.val;
                }
              }
              return hoveredCell.val;
            })()}
          </pre>
        </div>
      )}

      {/* ═ PERSISTENT INSPECTOR MODAL ═ */}
      {activeInspect && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.6)",
            backdropFilter: "blur(6px)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
          }}
          onClick={() => setActiveInspect(null)}
        >
          <div
            className="lab-card"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-medium)",
              borderRadius: 12,
              width: "min(680px, 92vw)",
              maxHeight: "82vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "var(--shadow-lg)",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "16px 20px",
                borderBottom: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {activeInspect.isJson ? (
                  <span
                    className="status-badge"
                    style={{
                      background: "rgba(74, 91, 192, 0.12)",
                      color: "var(--accent-indigo)",
                      border: "1px solid rgba(74, 91, 192, 0.3)",
                      fontWeight: 700,
                    }}
                  >
                    JSON 格式化查看器
                  </span>
                ) : (
                  <span
                    className="status-badge"
                    style={{
                      background: "rgba(100, 116, 139, 0.12)",
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border-light)",
                      fontWeight: 700,
                    }}
                  >
                    长文本查看器
                  </span>
                )}
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  字段: <code style={{ color: "var(--accent-indigo)" }}>{activeInspect.col}</code>
                </span>
              </div>
              <button
                onClick={() => setActiveInspect(null)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* View tab select (JSON only) */}
            {activeInspect.isJson && (
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  padding: "8px 20px",
                  borderBottom: "1px solid var(--border-light)",
                  background: "var(--bg-surface)",
                }}
              >
                <button
                  className={inspectMode === "tree" ? "btn-primary" : "btn-secondary"}
                  style={{ padding: "4px 12px", fontSize: "0.76rem" }}
                  onClick={() => setInspectMode("tree")}
                >
                  🌳 树状展开
                </button>
                <button
                  className={inspectMode === "raw" ? "btn-primary" : "btn-secondary"}
                  style={{ padding: "4px 12px", fontSize: "0.76rem" }}
                  onClick={() => setInspectMode("raw")}
                >
                  📝 美化文本
                </button>
              </div>
            )}

            {/* Body */}
            <div
              style={{
                flex: 1,
                padding: 20,
                overflow: "auto",
                background: "var(--bg-active)",
                minHeight: 200,
              }}
            >
              {activeInspect.isJson && inspectMode === "tree" ? (
                <div
                  style={{
                    background: "var(--bg-surface)",
                    padding: 20,
                    borderRadius: 8,
                    border: "1px solid var(--border-light)",
                    minHeight: "100%",
                  }}
                >
                  <JsonTree data={tryParseJson(activeInspect.val)} />
                </div>
              ) : (
                <pre
                  style={{
                    margin: 0,
                    padding: 16,
                    background: "var(--bg-surface)",
                    borderRadius: 8,
                    border: "1px solid var(--border-light)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.82rem",
                    color: "var(--text-primary)",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                    minHeight: "100%",
                    lineHeight: "1.5",
                  }}
                >
                  {activeInspect.isJson
                    ? JSON.stringify(tryParseJson(activeInspect.val), null, 2)
                    : activeInspect.val}
                </pre>
              )}
            </div>

            {/* Footer */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 20px",
                borderTop: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
              }}
            >
              <button
                className="btn-secondary"
                style={{
                  padding: "5px 12px",
                  fontSize: "0.8rem",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
                onClick={handleCopyValue}
              >
                {copied ? (
                  <>
                    <Check size={14} style={{ color: "var(--accent-green)" }} /> 已复制
                  </>
                ) : (
                  <>
                    <Copy size={14} /> 复制全部内容
                  </>
                )}
              </button>
              <button
                className="btn-primary"
                style={{ padding: "5px 16px", fontSize: "0.8rem" }}
                onClick={() => setActiveInspect(null)}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
