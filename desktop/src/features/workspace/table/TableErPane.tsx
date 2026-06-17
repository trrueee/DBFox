import { useEffect, useState } from "react";
import { request } from "../../../lib/api/client";

interface TableErPaneProps {
  tableId: string;
  datasourceId: string;
}

interface ErNode {
  id: string;
  table: string;
  module: string;
  fields: Array<{
    name: string;
    type: string;
    is_pk: boolean;
    is_fk: boolean;
  }>;
}

interface ErEdge {
  id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
  edge_type: string;
}

interface ErDiagramData {
  nodes: ErNode[];
  edges: ErEdge[];
}

export function TableErPane({ tableId, datasourceId }: TableErPaneProps) {
  const [data, setData] = useState<ErDiagramData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadEr() {
      setLoading(true);
      setError("");
      try {
        const result = await request<ErDiagramData>(
          `/schema/er-diagram?datasource_id=${encodeURIComponent(datasourceId)}`
        );
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "无法加载 ER 关系图");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadEr();
    return () => { cancelled = true; };
  }, [datasourceId]);

  if (loading) {
    return <div className="p-4 text-[11px] text-slate-400">正在加载 ER 关系图...</div>;
  }

  if (error) {
    return <div className="p-4 text-[11px] text-red-500 bg-red-50 rounded-lg">{error}</div>;
  }

  if (!data || data.nodes.length === 0) {
    return <div className="p-4 text-[11px] text-slate-400">暂无 ER 关系图数据，请先同步 Schema。</div>;
  }

  // Filter to show the current table and its direct connections
  const activeTable = data.nodes.find((n) => n.table === tableId);
  const connectedEdges = data.edges.filter(
    (e) => e.source === tableId || e.target === tableId
  );
  const connectedTableNames = new Set(
    connectedEdges.flatMap((e) => [e.source, e.target])
  );
  connectedTableNames.delete(tableId);
  const connectedNodes = data.nodes.filter((n) => connectedTableNames.has(n.table));

  return (
    <div className="h-full w-full bg-[var(--color-bg)] relative overflow-auto flex flex-col p-4">
      <span className="text-[10px] text-[var(--color-text-muted)] block mb-2">
        ER 关系图 &gt; {tableId}{" "}
        <span className="text-slate-400">
          ({connectedEdges.length} 条关系, {connectedNodes.length} 个关联表)
        </span>
      </span>
      <div className="flex-1 relative border border-[var(--color-border)] bg-[var(--color-panel)] rounded-xl shadow-inner overflow-auto">
        <div className="relative p-6 flex flex-wrap gap-6 min-w-max">
          {/* Active Table Node */}
          <div className="bg-[var(--color-panel)] border-2 border-[var(--color-primary)] rounded-lg shadow-sm text-[10px] w-[160px]">
            <div className="bg-[var(--color-primary-soft)] border-b border-[var(--color-border)] px-2 py-1 font-bold text-[var(--color-text-primary)]">
              {tableId}
            </div>
            <div className="p-2 leading-relaxed text-[var(--color-text-secondary)] font-mono">
              {activeTable?.fields.map((f) => (
                <div key={f.name} className="flex justify-between gap-2">
                  <span className={f.is_pk ? "font-bold text-[var(--color-text-primary)]" : ""}>
                    {f.name}
                  </span>
                  <span className="text-[var(--color-text-muted)] text-[9px]">
                    {f.is_pk ? "PK" : f.is_fk ? "FK" : f.type.slice(0, 12)}
                  </span>
                </div>
              )) || <div className="text-slate-400">—</div>}
            </div>
          </div>

          {/* Connected Tables */}
          {connectedNodes.map((node) => {
            const edge = connectedEdges.find(
              (e) =>
                (e.source === tableId && e.target === node.table) ||
                (e.target === tableId && e.source === node.table)
            );
            const isIncoming = edge?.target === tableId;
            return (
              <div key={node.table} className="bg-[var(--color-panel)] border border-[var(--color-border)] rounded-lg shadow-sm text-[10px] w-[160px]">
                <div className="bg-[var(--color-warning-soft)] border-b border-[var(--color-border)] px-2 py-1 font-bold flex justify-between text-[var(--color-text-primary)]">
                  <span>{node.table}</span>
                  {edge && (
                    <span className="text-[9px] text-[var(--color-text-muted)]">
                      {isIncoming ? "← 被引用" : "→ 引用"}
                    </span>
                  )}
                </div>
                <div className="p-2 leading-relaxed text-[var(--color-text-secondary)] font-mono">
                  {node.fields.map((f) => (
                    <div key={f.name} className="flex justify-between gap-2">
                      <span className={f.is_pk ? "font-bold text-[var(--color-text-primary)]" : ""}>
                        {f.name}
                      </span>
                      <span className="text-[var(--color-text-muted)] text-[9px]">
                        {f.is_pk ? "PK" : f.type.slice(0, 12)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
