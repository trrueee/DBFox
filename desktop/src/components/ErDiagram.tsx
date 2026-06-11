import { useMemo, useCallback, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ERDiagramData } from "../lib/api";

/* ═══════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════ */

interface ErDiagramProps {
  data: Partial<ERDiagramData> | null | undefined;
  focusTable?: string | null;
  depth?: 1 | 2;
  viewMode?: "focus" | "module" | "full";
  showInferred?: boolean;
  onNodeClick?: (tableName: string) => void;
  onAnnotateTable?: (tableName: string) => void;
}

interface FieldData {
  name: string;
  type: string;
  is_pk: boolean;
  is_fk: boolean;
}

interface TableNodeData {
  label: string;
  comment: string;
  fields: FieldData[];
  module_tag: string;
  isFocus: boolean;
  isCollapsed?: boolean;
  totalFieldCount?: number;
  isSecondary?: boolean;
  onToggle?: () => void;
  onAnnotate?: () => void;
}

interface ErEdgeData {
  label: string;
  edge_type: "real" | "inferred";
}

type ERNode = ERDiagramData["nodes"][number];
type EREdge = ERDiagramData["edges"][number];

/* ═══════════════════════════════════════════════
   Layout Constants
   ═══════════════════════════════════════════════ */

const NODE_W = 210;
const ROW_H = 22;
const HEADER_H = 36;
const FOCUS_RADIUS = 320;
const GRID_ROW_GAP = 60;

function estimateNodeHeight(fieldCount: number, hasToggle: boolean): number {
  return HEADER_H + fieldCount * ROW_H + (hasToggle ? ROW_H : 0) + 12;
}

function normalizeDiagramData(data: Partial<ERDiagramData> | null | undefined): ERDiagramData {
  const rawNodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const nodes: ERNode[] = rawNodes.map((node, index) => {
    const label = String(node?.label || node?.id || `table_${index + 1}`);
    return {
      id: String(node?.id || label),
      label,
      comment: String(node?.comment || ""),
      module_tag: String(node?.module_tag || "通用模块"),
      fields: Array.isArray(node?.fields)
        ? node.fields.map((field) => ({
            name: String(field?.name || ""),
            type: String(field?.type || ""),
            is_pk: Boolean(field?.is_pk),
            is_fk: Boolean(field?.is_fk),
            comment: String(field?.comment || ""),
          }))
        : [],
    };
  });

  const nodeLabels = new Set(nodes.map((node) => node.label));
  const rawEdges = Array.isArray(data?.edges) ? data.edges : [];
  const edges: EREdge[] = rawEdges
    .map((edge, index) => {
      const source = String(edge?.source || "");
      const target = String(edge?.target || "");
      const edgeType: "real" | "inferred" = edge?.edge_type === "inferred" ? "inferred" : "real";
      return {
        id: String(edge?.id || `edge_${index + 1}`),
        source,
        sourceHandle: String(edge?.sourceHandle || ""),
        target,
        targetHandle: String(edge?.targetHandle || ""),
        label: String(edge?.label || ""),
        edge_type: edgeType,
      };
    })
    .filter((edge) => nodeLabels.has(edge.source) && nodeLabels.has(edge.target));

  return { nodes, edges };
}

/* ═══════════════════════════════════════════════
   Layout Calculator
   ═══════════════════════════════════════════════ */

function getConnectedNodes(
  focusTable: string,
  edges: ERDiagramData["edges"],
  depth: 1 | 2,
): { direct: Set<string>; secondary: Set<string> } {
  const direct = new Set<string>();
  const secondary = new Set<string>();

  for (const edge of edges) {
    if (edge.source === focusTable) {
      direct.add(edge.target);
    } else if (edge.target === focusTable) {
      direct.add(edge.source);
    }
  }

  if (depth === 2) {
    for (const edge of edges) {
      if (direct.has(edge.source) && edge.target !== focusTable) {
        secondary.add(edge.target);
      }
      if (direct.has(edge.target) && edge.source !== focusTable) {
        secondary.add(edge.source);
      }
    }
    secondary.delete(focusTable);
    for (const d of direct) secondary.delete(d);
  }

  return { direct, secondary };
}

function filterVisible(
  data: ERDiagramData,
  focusTable: string | null,
  depth: 1 | 2,
  viewMode: "focus" | "module" | "full",
  showInferred: boolean,
): { nodes: ERDiagramData["nodes"]; edges: ERDiagramData["edges"] } {
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const filteredEdges = showInferred
    ? edges
    : edges.filter((e) => e.edge_type === "real");

  if (viewMode === "full") {
    return { nodes, edges: filteredEdges };
  }

  if (viewMode === "module" && focusTable) {
    const focusNode = nodes.find((n) => n.label === focusTable);
    const moduleTag = focusNode?.module_tag;
    if (moduleTag) {
      const moduleNodes = nodes.filter((n) => n.module_tag === moduleTag);
      const moduleLabels = new Set(moduleNodes.map((n) => n.label));
      const moduleEdges = filteredEdges.filter(
        (e) => moduleLabels.has(e.source) && moduleLabels.has(e.target),
      );
      return { nodes: moduleNodes, edges: moduleEdges };
    }
  }

  if (viewMode === "focus" && focusTable) {
    if (!nodes.some((node) => node.label === focusTable)) {
      return { nodes, edges: filteredEdges };
    }
    const { direct, secondary } = getConnectedNodes(focusTable, filteredEdges, depth);
    const visibleLabels = new Set<string>([focusTable, ...direct, ...secondary]);
    const visibleNodes = nodes.filter((n) => visibleLabels.has(n.label));
    const visibleEdges = filteredEdges.filter(
      (e) => visibleLabels.has(e.source) && visibleLabels.has(e.target),
    );
    return { nodes: visibleNodes, edges: visibleEdges };
  }

  return { nodes, edges: filteredEdges };
}

function computeLayout(
  nodes: ERDiagramData["nodes"],
  focusTable: string | null,
  viewMode: "focus" | "module" | "full",
  getNodeHeight: (node: ERNode) => number,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const safeNodes = Array.isArray(nodes) ? nodes : [];

  if (viewMode === "focus" && focusTable) {
    // Focus node at center
    const focusNode = safeNodes.find((n) => n.label === focusTable);
    const others = safeNodes.filter((n) => n.label !== focusTable);

    const fx = 400;
    const fy = 350;
    if (focusNode) {
      positions.set(focusNode.label, { x: fx, y: fy });
    }

    const count = others.length;
    others.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      const radius = count <= 8 ? FOCUS_RADIUS : Math.max(FOCUS_RADIUS, count * 40);
      positions.set(node.label, {
        x: fx + radius * Math.cos(angle),
        y: fy + radius * Math.sin(angle),
      });
    });
    return positions;
  }

  if (viewMode === "module" && focusTable) {
    // Group by module, arrange in columns
    const focusNode = safeNodes.find((n) => n.label === focusTable);
    const others = safeNodes.filter((n) => n.label !== focusTable);

    if (focusNode) {
      positions.set(focusNode.label, { x: 80, y: 60 });
    }

    let y = 60;
    let col = 0;
    const colX = [490, 920, 1350, 1780];

    others.forEach((node) => {
      const nodeH = getNodeHeight(node);
      const x = colX[col] || 490 + col * (NODE_W + 220);
      positions.set(node.label, { x, y });
      y += nodeH + GRID_ROW_GAP;
      if (y > 600) {
        y = 60;
        col++;
      }
    });
    return positions;
  }

  // Full mode: grid by module groups
  const moduleGroups = new Map<string, ERDiagramData["nodes"]>();
  for (const node of safeNodes) {
    const tag = node.module_tag || "通用";
    if (!moduleGroups.has(tag)) moduleGroups.set(tag, []);
    moduleGroups.get(tag)!.push(node);
  }

  let colX = 40;
  for (const [, groupNodes] of moduleGroups) {
    let rowY = 40;
    for (const node of groupNodes) {
      const nodeH = getNodeHeight(node);
      positions.set(node.label, { x: colX, y: rowY });
      rowY += nodeH + 70;
    }
    colX += NODE_W + 220;
  }

  return positions;
}

/* ═══════════════════════════════════════════════
   Custom Node: TableCard
   ═══════════════════════════════════════════════ */

function TableCardNode({ data }: NodeProps) {
  const {
    label,
    fields,
    comment,
    isFocus,
    isCollapsed = false,
    totalFieldCount = 0,
    isSecondary = false,
    onToggle,
    onAnnotate,
  } = data as unknown as TableNodeData;
  const safeFields: FieldData[] = Array.isArray(fields) ? fields : [];
  const hasToggleRow = totalFieldCount > 5 && !isFocus;
  const nodeH = estimateNodeHeight(safeFields.length, hasToggleRow);

  return (
    <div
      className="er-card"
      style={{
        width: NODE_W,
        height: nodeH,
        borderRadius: 8,
        background: "#FFFFFF",
        border: isFocus ? "2px solid var(--accent-indigo)" : "1px solid var(--border-medium)",
        boxShadow: isFocus ? "0 4px 20px rgba(45, 59, 140, 0.15)" : "0 2px 8px rgba(0,0,0,0.06)",
        fontSize: "0.78rem",
        overflow: "hidden",
        transition: "box-shadow 0.15s, border-color 0.15s, opacity 0.2s",
        opacity: isSecondary ? 0.55 : 1,
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        if (isSecondary) {
          e.currentTarget.style.opacity = "1";
        }
      }}
      onMouseLeave={(e) => {
        if (isSecondary) {
          e.currentTarget.style.opacity = "0.55";
        }
      }}
    >
      <Handle type="target" position={Position.Left} style={{ visibility: "hidden" }} />
      <Handle type="source" position={Position.Right} style={{ visibility: "hidden" }} />

      {/* Header */}
      <div
        style={{
          height: HEADER_H,
          padding: "0 12px",
          display: "flex",
          alignItems: "center",
          background: isFocus ? "var(--accent-indigo-light)" : "var(--bg-secondary)",
          borderBottom: "1px solid var(--border-light)",
          fontWeight: 700,
          fontSize: "0.8rem",
          color: "var(--text-primary)",
          fontFamily: "var(--font-mono)",
          gap: 6,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: isFocus ? "var(--accent-indigo)" : "var(--accent-teal)",
            flexShrink: 0,
          }}
        />
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {label}
        </span>
        {onAnnotate && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAnnotate();
            }}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "2px 4px",
              display: "grid",
              placeItems: "center",
              color: "var(--accent-indigo)",
              fontSize: "0.75rem",
            }}
            title="添加设计批注修改该表架构"
          >
            <span>🪄</span>
          </button>
        )}
      </div>

      {/* Fields */}
      <div style={{ padding: "2px 0" }}>
        {safeFields.map((f) => (
          <div
            key={f.name}
            style={{
              height: ROW_H,
              padding: "0 12px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ width: 14, textAlign: "center", flexShrink: 0 }}>
              {f.is_pk && <span style={{ color: "var(--accent-amber)", fontSize: "0.65rem" }}>◆</span>}
              {f.is_fk && !f.is_pk && <span style={{ color: "var(--accent-teal)", fontSize: "0.65rem" }}>◇</span>}
            </span>
            <span
              style={{
                flex: 1,
                fontFamily: "var(--font-mono)",
                fontSize: "0.7rem",
                fontWeight: f.is_pk ? 600 : 400,
                color: f.is_pk ? "var(--text-primary)" : "var(--text-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {f.name}
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.62rem",
                color: "var(--text-muted)",
              }}
            >
              {f.type}
            </span>
          </div>
        ))}
      </div>

      {/* Toggle button */}
      {hasToggleRow && onToggle && (
        <div
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          style={{
            height: ROW_H,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-secondary)",
            borderTop: "1px dashed var(--border-light)",
            color: "var(--accent-indigo)",
            fontWeight: 600,
            fontSize: "0.68rem",
            cursor: "pointer",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--border-light)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "var(--bg-secondary)";
          }}
        >
          {isCollapsed ? `🔍 展开全部 (${totalFieldCount})` : `▲ 折叠非关键字段`}
        </div>
      )}

      {/* Comment footer */}
      {comment && !isCollapsed && (
        <div
          style={{
            height: 20,
            padding: "0 12px",
            display: "flex",
            alignItems: "center",
            background: "var(--bg-secondary)",
            borderTop: "1px solid var(--border-light)",
            fontSize: "0.62rem",
            color: "var(--text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {comment}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Custom Edge: Labeled + Dashed for inferred
   ═══════════════════════════════════════════════ */

function ErEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeData = data as unknown as (ErEdgeData & { isSecondary?: boolean }) | undefined;
  const isInferred = edgeData?.edge_type === "inferred";
  const isSecondary = edgeData?.isSecondary;
  const displayLabel = edgeData?.label || "";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: isInferred ? "#B45309" : "#0D7377",
          strokeWidth: isInferred ? 1.2 : 2,
          strokeDasharray: isInferred ? "5,4" : undefined,
          opacity: isSecondary ? 0.3 : 1,
        }}
        markerEnd={markerEnd}
      />
      {displayLabel && (
        <EdgeLabelRenderer>
          <div
            className="er-edge-label nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              fontSize: "0.62rem",
              fontFamily: "var(--font-mono)",
              color: isInferred ? "#B45309" : "#0D7377",
              background: "rgba(255,255,255,0.96)",
              padding: "2px 6px",
              borderRadius: 3,
              border: `1px solid ${isInferred ? "#FCD34D" : "#ccf0f0"}`,
              pointerEvents: "all",
              whiteSpace: "nowrap",
              maxWidth: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
              boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
              zIndex: 10,
            }}
            title={`${displayLabel}${isInferred ? " (系统推断关联)" : ""}`}
          >
            {isInferred ? `✨ ${displayLabel}` : displayLabel}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════ */

const nodeTypes = { tableCard: TableCardNode };
const edgeTypes = { erEdge: ErEdge };

export function ErDiagram({
  data,
  focusTable = null,
  depth = 1,
  viewMode = "full",
  showInferred = true,
  onNodeClick,
  onAnnotateTable,
}: ErDiagramProps) {
  const safeData = useMemo(() => normalizeDiagramData(data), [data]);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

  const { nodes: visibleNodes, edges: visibleEdges } = useMemo(
    () => filterVisible(safeData, focusTable, depth, viewMode, showInferred),
    [safeData, focusTable, depth, viewMode, showInferred],
  );

  const { directSet } = useMemo(() => {
    if (!focusTable) return { directSet: new Set<string>() };
    const { direct } = getConnectedNodes(focusTable, visibleEdges, depth);
    return { directSet: direct };
  }, [focusTable, visibleEdges, depth]);

  const isTableCollapsed = useCallback(
    (n: ERNode): boolean => {
      if (n.label === focusTable) return false;
      if (n.fields.length <= 5) return false;
      return !expandedTables.has(n.label);
    },
    [focusTable, expandedTables]
  );

  const getVisibleFields = useCallback(
    (n: ERNode): FieldData[] => {
      if (isTableCollapsed(n)) {
        const keyFields = n.fields.filter((f) => f.is_pk || f.is_fk);
        if (keyFields.length > 0) return keyFields;
        return n.fields.slice(0, 2);
      }
      return n.fields;
    },
    [isTableCollapsed]
  );

  const positions = useMemo(
    () =>
      computeLayout(visibleNodes, focusTable, viewMode, (node) => {
        const fields = getVisibleFields(node);
        const hasToggle = node.fields.length > 5 && node.label !== focusTable;
        return estimateNodeHeight(fields.length, hasToggle);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleNodes, focusTable, viewMode, isTableCollapsed, getVisibleFields],
  );

  const rfNodes: Node[] = useMemo(
    () =>
      visibleNodes.map((n) => {
        const pos = positions.get(n.label) || { x: 0, y: 0 };
        const collapsed = isTableCollapsed(n);
        const visibleFields = getVisibleFields(n);
        const isSecondary =
          viewMode === "focus" &&
          focusTable !== null &&
          n.label !== focusTable &&
          !directSet.has(n.label);

        return {
          id: n.id,
          type: "tableCard",
          position: pos,
          data: {
            label: n.label,
            comment: n.comment,
            fields: visibleFields,
            module_tag: n.module_tag,
            isFocus: n.label === focusTable,
            isCollapsed: collapsed,
            totalFieldCount: n.fields.length,
            isSecondary,
            onToggle: () => {
              setExpandedTables((prev) => {
                const next = new Set(prev);
                if (next.has(n.label)) {
                  next.delete(n.label);
                } else {
                  next.add(n.label);
                }
                return next;
              });
            },
            onAnnotate: onAnnotateTable ? () => onAnnotateTable(n.label) : undefined,
          } satisfies TableNodeData,
        };
      }),
    [visibleNodes, positions, focusTable, viewMode, directSet, isTableCollapsed, getVisibleFields, onAnnotateTable],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      visibleEdges
        .filter((e) => positions.has(e.source) && positions.has(e.target))
        .map((e) => {
          const isSecondaryEdge =
            viewMode === "focus" &&
            focusTable !== null &&
            e.source !== focusTable &&
            e.target !== focusTable;
          return {
            id: e.id,
            type: "erEdge",
            source: e.source,
            target: e.target,
            data: {
              label: `${e.sourceHandle} → ${e.targetHandle}`,
              edge_type: e.edge_type || "real",
              isSecondary: isSecondaryEdge,
            } satisfies ErEdgeData & { isSecondary: boolean },
          };
        }),
    [visibleEdges, positions, focusTable, viewMode],
  );

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.data.label as string);
    },
    [onNodeClick],
  );

  const fitViewOptions = useMemo(
    () => ({
      padding: 0.3,
      maxZoom: 1.5,
    }),
    [],
  );

  if (safeData.nodes.length === 0) return null;

  return (
    <div style={{ width: "100%", height: "100%", position: "relative", background: "#FAF9F6" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={fitViewOptions}
          minZoom={0.15}
          maxZoom={2}
          defaultEdgeOptions={{
            type: "erEdge",
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#E8E6E1" gap={20} />
          <Controls
            style={{
              background: "rgba(255,255,255,0.85)",
              borderRadius: 8,
              border: "1px solid var(--border-light)",
              boxShadow: "var(--shadow-sm)",
            }}
          />
          <MiniMap
            style={{
              background: "var(--bg-secondary)",
              borderRadius: 8,
              border: "1px solid var(--border-light)",
            }}
            nodeColor={(n) => {
              const d = n.data as unknown as TableNodeData;
              return d.isFocus ? "#2D3B8C" : "#0D7377";
            }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
