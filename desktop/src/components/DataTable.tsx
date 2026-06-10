import { useEffect, useRef, useState } from "react";
import { Check, Copy, Database, EyeOff, FileJson, ListPlus, MoreVertical, X, Filter } from "lucide-react";
import { buildInsertSql, buildRowJson, normalizeCopyValue } from "../lib/sqlCopy";
import { useDataTableView } from "../hooks/useDataTableView";
import gsap from "gsap";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  numericColumns?: string[];
  maxHeight?: string;
  tableName?: string;
  databaseName?: string;
  columnTypes?: Record<string, { dataType: string; isPrimaryKey: boolean; isForeignKey: boolean }>;
}

function isNumeric(val: unknown): boolean {
  return typeof val === "number";
}

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function tryParseJson(str: unknown): JsonValue | null {
  if (typeof str !== "string") return null;
  const trimmed = str.trim();
  if (
    !(trimmed.startsWith("{") && trimmed.endsWith("}")) &&
    !(trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    return null;
  }
  try {
    return JSON.parse(trimmed) as JsonValue;
  } catch {
    return null;
  }
}

// 🌳 Collapsible JSON Tree Viewer Component
const JsonTree: React.FC<{ data: JsonValue; depth?: number }> = ({ data, depth = 0 }) => {
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

export function DataTable({ columns, rows, numericColumns, maxHeight, tableName, databaseName, columnTypes }: DataTableProps) {
  const numericSet = new Set(numericColumns ?? []);
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const tbodyRef = useRef<HTMLTableSectionElement>(null);

  const {
    visibleColumns,
    visibleRows,
    sortState,
    setSortState,
    filters,
    setFilter,
    clearFilter,
    clearAllFilters,
    hiddenColumns,
    toggleHideColumn,
    showAllColumns,
  } = useDataTableView({ columns, rows });

  // Stagger row animation when visibleRows changes
  useEffect(() => {
    if (!tbodyRef.current) return;
    const rows = tbodyRef.current.querySelectorAll("tr");
    gsap.fromTo(
      rows,
      { opacity: 0, y: 4 },
      { opacity: 1, y: 0, duration: 0.18, stagger: 0.03, ease: "power1.out" },
    );
  }, [visibleRows]);

  const [toast, setToast] = useState<string | null>(null);
  const [openColumnMenu, setOpenColumnMenu] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ rowIndex: number; column?: string; x: number; y: number } | null>(null);
  const [isCompact, setIsCompact] = useState(true);
  
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

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 1500);
  };

  const copyText = async (text: string, message: string) => {
    await navigator.clipboard.writeText(text);
    showToast(message);
  };

  const handleCopyValue = async () => {
    if (!activeInspect) return;
    await copyText(activeInspect.val, "已复制完整内容");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleCopyCell = async (value: unknown) => {
    await copyText(normalizeCopyValue(value), "已复制单元格");
  };

  const handleCopyRowJson = async (row: Record<string, unknown>) => {
    await copyText(buildRowJson(columns, row), "已复制行 JSON");
  };

  const handleCopyInsert = async (row: Record<string, unknown>) => {
    if (!tableName) {
      showToast("缺少表名，无法生成 INSERT");
      return;
    }
    await copyText(buildInsertSql(tableName, columns, row, databaseName), "已复制 INSERT SQL");
  };

  const handleCopyColumnName = async (col: string) => {
    await copyText(col, "已复制列名");
    setOpenColumnMenu(null);
  };

  const handleCopySelectColumn = async (col: string) => {
    if (!tableName) {
      showToast("缺少表名，无法生成 SELECT");
      return;
    }
    const qualifiedTable = databaseName ? `\`${databaseName}\`.\`${tableName}\`` : `\`${tableName}\``;
    await copyText(`SELECT \`${col}\`\nFROM ${qualifiedTable}\nLIMIT 100;`, "已复制 SELECT 当前列");
    setOpenColumnMenu(null);
  };

  const handleHideColumn = (col: string) => {
    toggleHideColumn(col);
    setOpenColumnMenu(null);
    showToast(`已隐藏列 ${col}`);
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

      {toast && (
        <div
          style={{
            position: "fixed",
            top: 8,
            left: "50%",
            transform: "translateX(-50%)",
            width: "fit-content",
            zIndex: 8000,
            background: "rgba(13, 115, 119, 0.94)",
            color: "#fff",
            borderRadius: 999,
            padding: "6px 12px",
            fontSize: "0.76rem",
            fontWeight: 700,
            boxShadow: "var(--shadow-md)",
          }}
        >
          {toast}
        </div>
      )}

      {/* 📊 TABLE VIEWPORT METADATA & ACTIONS DASHBOARD */}
      {(Object.keys(filters).length > 0 || hiddenColumns.size > 0 || sortState) ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "8px 16px",
            borderBottom: "1px solid var(--border-medium)",
            background: "var(--bg-secondary)",
            fontSize: "0.76rem",
            color: "var(--text-secondary)",
            flexWrap: "wrap",
          }}
        >
          {/* Left section: Filter & Sort Indicators */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            {Object.keys(filters).length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontWeight: 600, color: "var(--accent-indigo)" }}>已启用筛选:</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {Object.keys(filters).map((col) => {
                    const filter = filters[col];
                    let text = `${col}`;
                    if (filter.mode === "is_null") text += " 为 NULL";
                    else if (filter.mode === "is_not_null") text += " 非 NULL";
                    else if (filter.mode === "contains") text += ` 包含 "${filter.value}"`;

                    return (
                      <span
                        key={col}
                        style={{
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border-light)",
                          borderRadius: 4,
                          padding: "2px 6px",
                          fontSize: "0.7rem",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        {text}
                        <button
                          onClick={() => clearFilter(col)}
                          style={{
                            border: "none",
                            background: "transparent",
                            color: "var(--text-muted)",
                            cursor: "pointer",
                            padding: "0 2px",
                            fontWeight: "bold",
                          }}
                          title="清除该列筛选"
                        >
                          ✕
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {sortState && (
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontWeight: 600, color: "var(--accent-indigo)" }}>已排序:</span>
                <span
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-light)",
                    borderRadius: 4,
                    padding: "2px 6px",
                    fontSize: "0.7rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  {sortState.column} {sortState.direction === "asc" ? "升序 ▲" : "降序 ▼"}
                  <button
                    onClick={() => setSortState(null)}
                    style={{
                      border: "none",
                      background: "transparent",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: "0 2px",
                      fontWeight: "bold",
                    }}
                    title="取消排序"
                  >
                    ✕
                  </button>
                </span>
              </div>
            )}

            {hiddenColumns.size > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>隐藏列:</span>
                <span
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-light)",
                    borderRadius: 4,
                    padding: "2px 6px",
                    fontSize: "0.7rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  已隐藏 {hiddenColumns.size} 列
                  <button
                    onClick={showAllColumns}
                    style={{
                      border: "none",
                      background: "transparent",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: "0 2px",
                      fontWeight: "bold",
                    }}
                    title="显示所有列"
                  >
                    ✕
                  </button>
                </span>
              </div>
            )}
          </div>

          {/* Right section: Count & Warning */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "0.74rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
              显示 <strong>{visibleRows.length}</strong> / {rows.length} 行
              <span
                style={{
                  background: "rgba(245, 158, 11, 0.12)",
                  color: "var(--accent-amber)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  borderRadius: 4,
                  padding: "1px 5px",
                  fontSize: "0.68rem",
                  fontWeight: 500,
                }}
                title="所有排序和筛选均仅在本地已加载的预览数据中执行，不影响数据库源数据。"
              >
                ⚠️ 当前仅筛选已加载的预览结果
              </span>
            </span>

            <button
              className="inline-flex items-center gap-1 px-2 py-1 text-[0.72rem] font-medium text-[hsl(var(--muted-foreground))] bg-transparent border border-[hsl(var(--border))] rounded cursor-pointer hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--foreground))] transition-colors"
              onClick={() => setIsCompact(!isCompact)}
              style={{
                padding: "3px 10px",
                fontSize: "0.72rem",
                color: "var(--text-secondary)",
                fontWeight: 600,
                border: "1px solid var(--border-light)",
                borderRadius: 4,
                background: "var(--bg-surface)",
              }}
            >
              {isCompact ? "舒适模式" : "紧凑模式"}
            </button>

            <button
              className="inline-flex items-center gap-1 px-2 py-1 text-[0.72rem] font-medium text-[hsl(var(--muted-foreground))] bg-transparent border border-[hsl(var(--border))] rounded cursor-pointer hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--foreground))] transition-colors"
              onClick={() => {
                clearAllFilters();
                showAllColumns();
                setSortState(null);
              }}
              style={{
                padding: "3px 10px",
                fontSize: "0.72rem",
                color: "var(--accent-indigo)",
                fontWeight: 600,
                border: "1px solid var(--border-light)",
                borderRadius: 4,
                background: "var(--bg-surface)",
              }}
            >
              清除所有过滤/排序
            </button>
          </div>
        </div>
      ) : (
        /* Default small indicator when no filters are active */
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 16px",
            borderBottom: "1px solid var(--border-light)",
            background: "var(--bg-secondary)",
            fontSize: "0.74rem",
            color: "var(--text-muted)",
          }}
        >
          <span>共 {rows.length} 行数据</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              className="inline-flex items-center gap-1 px-2 py-1 text-[0.72rem] font-medium text-[hsl(var(--muted-foreground))] bg-transparent border border-[hsl(var(--border))] rounded cursor-pointer hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--foreground))] transition-colors"
              onClick={() => setIsCompact(!isCompact)}
              style={{
                padding: "2px 8px",
                fontSize: "0.72rem",
                color: "var(--text-secondary)",
                fontWeight: 600,
                border: "1px solid var(--border-light)",
                borderRadius: 4,
                background: "var(--bg-surface)",
              }}
            >
              {isCompact ? "舒适模式" : "紧凑模式"}
            </button>
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", opacity: 0.8 }}>
              💡 可点击列头右侧菜单进行本地排序/筛选，右键单元格过滤或复制
            </span>
          </div>
        </div>
      )}

      {/* Dynamic CSS injection for anti-串行 hover row highlights and crisp borders */}
      <style>{`
        .data-table-premium {
          width: 100%;
          border-collapse: collapse;
          font-size: ${isCompact ? "0.78rem" : "0.85rem"};
        }
        .data-table-premium th {
          position: sticky;
          top: 0;
          z-index: 10;
          background: var(--bg-secondary);
          border-bottom: 2px solid var(--border-medium);
          border-right: 1px solid var(--border-light);
          padding: ${isCompact ? "5px 8px" : "10px 14px"};
          text-align: left;
          color: var(--text-secondary);
          font-weight: 600;
        }
        .data-table-premium td {
          padding: ${isCompact ? "4px 8px" : "8px 14px"};
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
          font-size: 0.72rem;
          font-weight: 600;
          text-align: center !important;
          background: var(--bg-secondary) !important;
          width: 40px;
          user-select: none;
          border-right: 2px solid var(--border-medium) !important;
          padding: ${isCompact ? "4px 6px" : "8px 10px"} !important;
        }
        tr:hover .row-number-text {
          display: none;
        }
        .row-menu-trigger {
          display: none;
        }
        tr:hover .row-menu-trigger {
          display: inline-flex !important;
        }
        .data-table-menu-item {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 7px;
          border: none;
          border-radius: 6px;
          background: transparent;
          color: var(--text-secondary);
          cursor: pointer;
          font-size: 0.74rem;
          padding: 7px 8px;
          text-align: left;
        }
        .data-table-menu-item:hover {
          background: var(--bg-active);
          color: var(--accent-indigo);
        }
        tr.row-selected td {
          background-color: rgba(74, 91, 192, 0.09) !important;
        }
        tr.row-selected td.row-counter-cell {
          background-color: rgba(74, 91, 192, 0.16) !important;
          color: var(--accent-indigo) !important;
          font-weight: 700;
        }
        td.cell-selected-outline {
          outline: 2px solid var(--accent-indigo) !important;
          outline-offset: -2px !important;
          background-color: rgba(74, 91, 192, 0.14) !important;
        }
      `}</style>

      <table className="data-table-premium">
        <thead>
          <tr>
            {/* First Row Counter Column # */}
            <th className="row-counter-cell" style={{ width: 44 }}>#</th>
            {visibleColumns.map((col) => {
              const currentFilter = filters[col];
              const filterVal = currentFilter?.mode === "contains" ? currentFilter.value || "" : "";

              return (
                <th key={col} style={{ minWidth: 120 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, position: "relative", width: "100%" }}>
                    
                    {/* Top Row: Column Name + Sort & Filter Indicators & Action Button */}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4, width: "100%" }}>
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: isCompact ? "0.76rem" : "0.82rem",
                          color: "var(--text-primary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          flex: 1,
                        }}
                      >
                        {col}
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
                        {sortState?.column === col && (
                          <span style={{ color: "var(--accent-indigo)", fontSize: "0.7rem", fontWeight: "bold" }}>
                            {sortState.direction === "asc" ? "▲" : "▼"}
                          </span>
                        )}
                        {filters[col] && (
                          <span
                            title="该列已启用筛选"
                            style={{
                              color: "var(--accent-teal)",
                              fontSize: "0.8rem",
                              lineHeight: 1,
                              flexShrink: 0,
                            }}
                          >
                            ●
                          </span>
                        )}
                        <button
                          className="inline-flex items-center gap-1 px-2 py-1 text-[0.72rem] font-medium text-[hsl(var(--muted-foreground))] bg-transparent border border-[hsl(var(--border))] rounded cursor-pointer hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--foreground))] transition-colors"
                          onClick={(event) => {
                            event.stopPropagation();
                            setOpenColumnMenu((current) => (current === col ? null : col));
                          }}
                          style={{
                            padding: 2,
                            flexShrink: 0,
                            background: openColumnMenu === col ? "var(--bg-active)" : undefined,
                          }}
                          title="列操作"
                        >
                          <MoreVertical size={12} />
                        </button>
                      </div>
                    </div>

                    {/* Bottom Row: Navicat Type Icon + Type Name */}
                    {columnTypes?.[col] ? (() => {
                      const typeInfo = columnTypes[col];
                      const isPk = typeInfo.isPrimaryKey;
                      const isFk = typeInfo.isForeignKey;
                      const typeName = typeInfo.dataType.toLowerCase();
                      
                      let IconNode = <span style={{ fontSize: "0.64rem", color: "var(--text-muted)", fontWeight: 700, marginRight: 3, fontFamily: "monospace" }}>abc</span>;
                      
                      if (isPk) {
                        IconNode = <span style={{ fontSize: "0.68rem", marginRight: 3 }} title="主键">🔑</span>;
                      } else if (isFk) {
                        IconNode = <span style={{ fontSize: "0.68rem", marginRight: 3 }} title="外键">🔗</span>;
                      } else if (typeName.includes("int") || typeName.includes("decimal") || typeName.includes("double") || typeName.includes("float") || typeName.includes("number")) {
                        IconNode = <span style={{ fontSize: "0.64rem", color: "var(--accent-teal)", fontWeight: 800, marginRight: 3, fontFamily: "monospace" }}>#</span>;
                      } else if (typeName.includes("json")) {
                        IconNode = <span style={{ fontSize: "0.62rem", color: "var(--accent-indigo)", fontWeight: 800, marginRight: 3, fontFamily: "monospace" }}>{"{}"}</span>;
                      } else if (typeName.includes("date") || typeName.includes("time")) {
                        IconNode = <span style={{ fontSize: "0.64rem", color: "var(--accent-amber)", marginRight: 3 }}>📅</span>;
                      } else if (typeName.includes("enum") || typeName.includes("set")) {
                        IconNode = <span style={{ fontSize: "0.62rem", color: "var(--accent-indigo)", fontWeight: 800, marginRight: 3 }}>⚙️</span>;
                      }
                      
                      return (
                        <div style={{ display: "flex", alignItems: "center", fontSize: "0.66rem", color: "var(--text-muted)", fontWeight: 500, userSelect: "none" }}>
                          {IconNode}
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {typeName}
                          </span>
                        </div>
                      );
                    })() : (
                      <div style={{ display: "flex", alignItems: "center", fontSize: "0.66rem", color: "var(--text-muted)", fontWeight: 500, userSelect: "none" }}>
                        <span style={{ fontSize: "0.64rem", color: "var(--text-muted)", fontWeight: 700, marginRight: 3, fontFamily: "monospace" }}>abc</span>
                        <span>varchar</span>
                      </div>
                    )}

                    {openColumnMenu === col && (
                      <div
                        style={{
                          position: "absolute",
                          top: 28,
                          right: 0,
                          minWidth: 175,
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border-light)",
                          borderRadius: 8,
                          boxShadow: "var(--shadow-lg)",
                          padding: 6,
                          zIndex: 40,
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {/* 1. Sort Section */}
                        <div style={{ borderBottom: "1px solid var(--border-light)", paddingBottom: 4, marginBottom: 4 }}>
                          <button
                            className="data-table-menu-item"
                            onClick={() => {
                              setSortState({ column: col, direction: "asc" });
                              setOpenColumnMenu(null);
                            }}
                            style={{
                              fontWeight: sortState?.column === col && sortState.direction === "asc" ? "bold" : "normal",
                              color: sortState?.column === col && sortState.direction === "asc" ? "var(--accent-indigo)" : undefined,
                            }}
                          >
                            <span style={{ fontSize: "10px", width: 14 }}>▲</span> 升序排序
                          </button>
                          <button
                            className="data-table-menu-item"
                            onClick={() => {
                              setSortState({ column: col, direction: "desc" });
                              setOpenColumnMenu(null);
                            }}
                            style={{
                              fontWeight: sortState?.column === col && sortState.direction === "desc" ? "bold" : "normal",
                              color: sortState?.column === col && sortState.direction === "desc" ? "var(--accent-indigo)" : undefined,
                            }}
                          >
                            <span style={{ fontSize: "10px", width: 14 }}>▼</span> 降序排序
                          </button>
                          {sortState?.column === col && (
                            <button
                              className="data-table-menu-item"
                              onClick={() => {
                                setSortState(null);
                                setOpenColumnMenu(null);
                              }}
                              style={{ color: "var(--text-muted)" }}
                            >
                              <span style={{ fontSize: "12px", width: 14 }}>✕</span> 取消排序
                            </button>
                          )}
                        </div>

                        {/* 2. Filter Section */}
                        <div style={{ borderBottom: "1px solid var(--border-light)", paddingBottom: 4, marginBottom: 4 }}>
                          {/* Search Input Box */}
                          <div style={{ padding: "2px 4px 6px 4px" }}>
                            <input
                              type="text"
                              value={filterVal}
                              placeholder="搜索当前列值..."
                              onChange={(e) => {
                                const val = e.target.value;
                                if (val) {
                                  setFilter(col, "contains", val);
                                } else {
                                  clearFilter(col);
                                }
                              }}
                              style={{
                                width: "100%",
                                padding: "4px 8px",
                                fontSize: "0.72rem",
                                borderRadius: 4,
                                border: "1px solid var(--border-medium)",
                                background: "var(--bg-surface)",
                                color: "var(--text-primary)",
                                outline: "none",
                              }}
                            />
                          </div>

                          <button
                            className="data-table-menu-item"
                            onClick={() => {
                              setFilter(col, "is_null");
                              setOpenColumnMenu(null);
                            }}
                            style={{
                              fontWeight: currentFilter?.mode === "is_null" ? "bold" : "normal",
                              color: currentFilter?.mode === "is_null" ? "var(--accent-indigo)" : undefined,
                            }}
                          >
                            <span style={{ width: 14 }}>◇</span> 只看 NULL
                          </button>
                          <button
                            className="data-table-menu-item"
                            onClick={() => {
                              setFilter(col, "is_not_null");
                              setOpenColumnMenu(null);
                            }}
                            style={{
                              fontWeight: currentFilter?.mode === "is_not_null" ? "bold" : "normal",
                              color: currentFilter?.mode === "is_not_null" ? "var(--accent-indigo)" : undefined,
                            }}
                          >
                            <span style={{ width: 14 }}>◆</span> 只看非 NULL
                          </button>
                          {currentFilter && (
                            <button
                              className="data-table-menu-item"
                              onClick={() => {
                                clearFilter(col);
                                setOpenColumnMenu(null);
                              }}
                              style={{ color: "var(--text-muted)" }}
                            >
                              <span style={{ fontSize: "12px", width: 14 }}>✕</span> 清除筛选
                            </button>
                          )}
                        </div>

                        {/* 3. Base Actions Section */}
                        <div>
                          <button className="data-table-menu-item" onClick={() => void handleCopyColumnName(col)}>
                            <Copy size={12} /> 复制列名
                          </button>
                          <button className="data-table-menu-item" onClick={() => void handleCopySelectColumn(col)}>
                            <Database size={12} /> 复制 SELECT 当前列
                          </button>
                          <button className="data-table-menu-item" onClick={() => handleHideColumn(col)}>
                            <EyeOff size={12} /> 隐藏列
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody ref={tbodyRef}>
          {visibleRows.map((row, ri) => {
            const isRowSelected = selectedCell?.rowIndex === ri;
            return (
              <tr 
                key={ri} 
                className={isRowSelected ? "row-selected" : undefined}
              >
                {/* 1. Counter Column # Cell */}
                <td 
                  className="row-counter-cell"
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setContextMenu({ rowIndex: ri, x: e.clientX, y: e.clientY });
                  }}
                >
                  <span className="row-number-text">{ri + 1}</span>
                  <button
                    className="hidden group-hover:inline-flex items-center p-0.5 text-[hsl(var(--muted-foreground))] cursor-pointer bg-transparent border-none"
                    style={{ padding: 1, color: "var(--text-muted)" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      const rect = e.currentTarget.getBoundingClientRect();
                      setContextMenu({ rowIndex: ri, x: rect.left, y: rect.bottom + 4 });
                    }}
                  >
                    <MoreVertical size={11} />
                  </button>
                </td>

                {visibleColumns.map((col) => {
                  const val = row[col];
                  const isNum = numericSet.has(col) || isNumeric(val);
                  const isCellSelected = selectedCell?.rowIndex === ri && selectedCell?.column === col;
                  
                  const cellClick = () => {
                    setSelectedCell({ rowIndex: ri, column: col });
                    void handleCopyCell(val);
                  };

                  const handleCellContextMenu = (e: React.MouseEvent) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setSelectedCell({ rowIndex: ri, column: col });
                    setContextMenu({ rowIndex: ri, column: col, x: e.clientX, y: e.clientY });
                  };

                  if (val === null || val === undefined) {
                    return (
                      <td
                        key={`${ri}-${col}`}
                        className={`cell-null ${isCellSelected ? "cell-selected-outline" : ""}`}
                        tabIndex={0}
                        title="右键可快捷过滤或排除值"
                        onClick={cellClick}
                        onContextMenu={handleCellContextMenu}
                        onMouseEnter={(e) => handleMouseEnterCell(col, "NULL", e)}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        <span style={{
                          display: "inline-block",
                          padding: "1px 5px",
                          background: "rgba(100, 116, 139, 0.08)",
                          color: "var(--text-muted)",
                          fontSize: "0.68rem",
                          borderRadius: 3,
                          fontFamily: "var(--font-mono)",
                          userSelect: "none"
                        }}>
                          NULL
                        </span>
                      </td>
                    );
                  }

                  // Try JSON detection
                  const jsonParsed = tryParseJson(val);
                  if (jsonParsed !== null) {
                    return (
                      <td
                        key={`${ri}-${col}`}
                        className={isCellSelected ? "cell-selected-outline" : undefined}
                        style={{ whiteSpace: "nowrap" }}
                        tabIndex={0}
                        onClick={cellClick}
                        onContextMenu={handleCellContextMenu}
                        onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 text-[0.66rem] font-semibold rounded-sm bg-primary/10 text-primary border border-primary/20"
                            style={{
                              background: "rgba(74, 91, 192, 0.12)",
                              color: "var(--accent-indigo)",
                              border: "1px solid rgba(74, 91, 192, 0.3)",
                              fontSize: "0.66rem",
                              padding: "0px 4px",
                              fontWeight: 600,
                            }}
                          >
                            JSON
                          </span>
                          <span
                            className="text-mono"
                            style={{
                              fontSize: "0.74rem",
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
                            onClick={(event) => {
                              event.stopPropagation();
                              handleOpenInspect(col, String(val), true);
                            }}
                            style={{
                              border: "none",
                              background: "rgba(74, 91, 192, 0.08)",
                              color: "var(--accent-indigo)",
                              padding: "1px 5px",
                              borderRadius: 4,
                              cursor: "pointer",
                              fontSize: "0.68rem",
                              fontWeight: 600,
                            }}
                          >
                            展开
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
                        className={isCellSelected ? "cell-selected-outline" : undefined}
                        tabIndex={0}
                        onClick={cellClick}
                        onContextMenu={handleCellContextMenu}
                        onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span
                            style={{
                              fontSize: "0.76rem",
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
                            onClick={(event) => {
                              event.stopPropagation();
                              handleOpenInspect(col, valStr, false);
                            }}
                            style={{
                              border: "none",
                              background: "rgba(100, 116, 139, 0.08)",
                              color: "var(--text-secondary)",
                              padding: "1px 5px",
                              borderRadius: 4,
                              cursor: "pointer",
                              fontSize: "0.68rem",
                              fontWeight: 600,
                            }}
                          >
                            更多
                          </button>
                        </div>
                      </td>
                    );
                  }

                  return (
                    <td
                      key={`${ri}-${col}`}
                      className={`${isNum ? "cell-number" : ""} ${isCellSelected ? "cell-selected-outline" : ""}`.trim() || undefined}
                      tabIndex={0}
                      onClick={cellClick}
                      onContextMenu={handleCellContextMenu}
                      onMouseEnter={(e) => handleMouseEnterCell(col, val, e)}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      {valStr}
                    </td>
                  );
                })}
              </tr>
            );
          })}
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
            className="bg-card border border-border rounded-lg"
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
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-[0.66rem] font-semibold rounded-sm bg-primary/10 text-primary border border-primary/20"
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
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-[0.66rem] font-semibold rounded-sm bg-primary/10 text-primary border border-primary/20"
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
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[0.78rem] font-medium border border-[hsl(var(--border))] bg-transparent rounded cursor-pointer hover:bg-[hsl(var(--accent))] text-[hsl(var(--foreground))] transition-colors"
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
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-[0.78rem] font-semibold bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] rounded cursor-pointer border-none hover:brightness-110 transition-colors"
                style={{ padding: "5px 16px", fontSize: "0.8rem" }}
                onClick={() => setActiveInspect(null)}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {contextMenu && (
        <>
          <div
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setContextMenu(null);
            }}
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 9999,
              background: "transparent",
            }}
          />
          <div
            style={{
              position: "fixed",
              top: contextMenu.y,
              left: contextMenu.x,
              minWidth: 175,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-light)",
              borderRadius: 8,
              boxShadow: "var(--shadow-lg)",
              padding: 6,
              zIndex: 10000,
              textAlign: "left",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {contextMenu.column ? (
              <>
                <div style={{ padding: "4px 8px", fontSize: "0.7rem", color: "var(--text-muted)", borderBottom: "1px solid var(--border-light)", marginBottom: 4, fontWeight: 600 }}>
                  单元格操作 ({contextMenu.column})
                </div>
                <button
                  className="data-table-menu-item"
                  onClick={(e) => {
                    e.stopPropagation();
                    const val = visibleRows[contextMenu.rowIndex][contextMenu.column!];
                    void handleCopyCell(val);
                    setContextMenu(null);
                  }}
                >
                  <Copy size={12} /> 复制单元格值
                </button>
                <button
                  className="data-table-menu-item"
                  onClick={(e) => {
                    e.stopPropagation();
                    const val = visibleRows[contextMenu.rowIndex][contextMenu.column!];
                    if (val !== null && val !== undefined) {
                      setFilter(contextMenu.column!, "contains", String(val));
                    } else {
                      setFilter(contextMenu.column!, "is_null");
                    }
                    setContextMenu(null);
                  }}
                >
                  <Filter size={12} /> 按此值本地筛选
                </button>
                <button
                  className="data-table-menu-item"
                  onClick={(e) => {
                    e.stopPropagation();
                    // Custom Exclude filter
                    setFilter(contextMenu.column!, "is_not_null");
                    setContextMenu(null);
                  }}
                >
                  <EyeOff size={12} /> 排除此列 NULL 值
                </button>
                <div style={{ height: 1, background: "var(--border-light)", margin: "4px 0" }} />
              </>
            ) : null}

            <div style={{ padding: "4px 8px", fontSize: "0.7rem", color: "var(--text-muted)", borderBottom: "1px solid var(--border-light)", marginBottom: 4, fontWeight: 600 }}>
              整行操作 #{contextMenu.rowIndex + 1}
            </div>
            <button
              className="data-table-menu-item"
              onClick={(e) => {
                e.stopPropagation();
                void handleCopyRowJson(visibleRows[contextMenu.rowIndex]);
                setContextMenu(null);
              }}
            >
              <FileJson size={12} /> 复制行 JSON
            </button>
            <button
              className="data-table-menu-item"
              onClick={(e) => {
                e.stopPropagation();
                void handleCopyInsert(visibleRows[contextMenu.rowIndex]);
                setContextMenu(null);
              }}
              disabled={!tableName}
            >
              <ListPlus size={12} /> 复制为 INSERT SQL
            </button>
          </div>
        </>
      )}
    </div>
  );
}
