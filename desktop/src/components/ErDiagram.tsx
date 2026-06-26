import { useMemo, useCallback, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  BaseEdge,
  getBezierPath,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ERDiagramData } from "../lib/api";
import "./ErDiagram.css";

/* ═══════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════ */

interface ErDiagramProps {
  data: Partial<ERDiagramData> | null | undefined;
  focusTable?: string | null;
  depth?: 1 | 2;
  viewMode?: "focus" | "full";
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
  viewMode: "focus" | "full",
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
  viewMode: "focus" | "full",
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

  const columnCount = Math.max(1, Math.ceil(Math.sqrt(safeNodes.length)));
  const columnHeights = Array.from({ length: columnCount }, () => 40);
  const columnWidth = NODE_W + 220;

  for (const node of safeNodes) {
    const shortestHeight = Math.min(...columnHeights);
    const columnIndex = columnHeights.indexOf(shortestHeight);
    const nodeHeight = getNodeHeight(node);

    positions.set(node.label, {
      x: 40 + columnIndex * columnWidth,
      y: shortestHeight,
    });
    columnHeights[columnIndex] += nodeHeight + GRID_ROW_GAP;
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
  const cardClassName = [
    "er-card",
    isFocus ? "er-card--focus" : "",
    isSecondary ? "er-card--secondary" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={cardClassName}>
      <Handle type="target" position={Position.Left} className="er-card__handle" />
      <Handle type="source" position={Position.Right} className="er-card__handle" />

      <div className="er-card__header">
        <span className="er-card__status" />
        <span className="er-card__title">
          {label}
        </span>
        {onAnnotate && (
          <button
            type="button"
            className="er-card__annotate"
            onClick={(e) => {
              e.stopPropagation();
              onAnnotate();
            }}
            title="添加设计批注"
          >
            批注
          </button>
        )}
      </div>

      <div className="er-card__fields">
        {safeFields.map((f) => (
          <div key={f.name} className="er-card__field">
            <span
              className={[
                "er-card__field-marker",
                f.is_pk ? "er-card__field-marker--pk" : "",
                f.is_fk && !f.is_pk ? "er-card__field-marker--fk" : "",
              ].filter(Boolean).join(" ")}
            >
              {f.is_pk ? "PK" : f.is_fk ? "FK" : ""}
            </span>
            <span
              className={[
                "er-card__field-name",
                f.is_pk ? "er-card__field-name--primary" : "",
              ].filter(Boolean).join(" ")}
            >
              {f.name}
            </span>
            <span className="er-card__field-type">
              {f.type}
            </span>
          </div>
        ))}
      </div>

      {hasToggleRow && onToggle && (
        <button
          type="button"
          className="er-card__toggle"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          {isCollapsed ? `展开全部 (${totalFieldCount})` : "折叠非关键字段"}
        </button>
      )}

      {comment && !isCollapsed && (
        <div className="er-card__comment">
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
  const edgeClassName = [
    "er-edge",
    isInferred ? "er-edge--inferred" : "",
    isSecondary ? "er-edge--secondary" : "",
  ].filter(Boolean).join(" ");
  const labelClassName = [
    "er-edge-label",
    isInferred ? "er-edge-label--inferred" : "",
    isSecondary ? "er-edge-label--secondary" : "",
  ].filter(Boolean).join(" ");

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        className={edgeClassName}
        markerEnd={markerEnd}
      />
      {displayLabel && (
        <text
          className={labelClassName}
          x={labelX}
          y={labelY}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          <title>{`${displayLabel}${isInferred ? " (系统推断关联)" : ""}`}</title>
          {isInferred ? `推断 ${displayLabel}` : displayLabel}
        </text>
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
    <div className="er-diagram">
      <div className="er-diagram__viewport">
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
          <Controls className="er-flow-controls" />
          <MiniMap
            className="er-flow-minimap"
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
