import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Button, EmptyState, ErrorState, LoadingState, Select, Toolbar, ToolbarGroup } from "../../../components/ui";
import type { ERDiagramData } from "../../../lib/api";
import { request } from "../../../lib/api/client";
import "./TableErPane.css";

interface TableErPaneProps {
  tableId: string;
  datasourceId: string;
}

type ErViewMode = "focus" | "full";

const ErDiagram = lazy(async () => {
  const module = await import("../../../components/ErDiagram");
  return { default: module.ErDiagram };
});

export function TableErPane({ tableId, datasourceId }: TableErPaneProps) {
  const [data, setData] = useState<ERDiagramData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [focusTable, setFocusTable] = useState(tableId);
  const [viewMode, setViewMode] = useState<ErViewMode>("focus");
  const [depth, setDepth] = useState<1 | 2>(1);
  const [showInferred, setShowInferred] = useState(true);

  useEffect(() => {
    setFocusTable(tableId);
    setViewMode("focus");
    setDepth(1);
    setShowInferred(true);
  }, [datasourceId, tableId]);

  useEffect(() => {
    let cancelled = false;

    async function loadEr() {
      setLoading(true);
      setError("");
      try {
        const result = await request<ERDiagramData>(
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

  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const edges = Array.isArray(data?.edges) ? data.edges : [];
  const inferredEdgeCount = useMemo(
    () => edges.filter((edge) => edge.edge_type === "inferred").length,
    [edges],
  );
  const resolvedFocusTable = nodes.some((node) => node.label === focusTable) ? focusTable : tableId;

  if (loading) {
    return (
      <div className="table-er-pane table-er-pane__state">
        <LoadingState label="正在加载 ER 关系图..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="table-er-pane table-er-pane__state">
        <ErrorState title="无法加载 ER 关系图" description={error} />
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="table-er-pane table-er-pane__state">
        <EmptyState title="暂无 ER 关系图数据" description="请先同步 Schema 后再查看表关系。" />
      </div>
    );
  }

  if (edges.length === 0) {
    return (
      <div className="table-er-pane table-er-pane__state">
        <EmptyState
          title="暂无可视化关系"
          description="没有同步到外键，也没有推断出可用的 *_id 表关系；字段结构页会保留表结构事实。"
        />
      </div>
    );
  }

  return (
    <div className="table-er-pane">
      <div className="table-er-pane__header">
        <div>
          <span className="table-er-pane__caption">ER 关系图 &gt; {resolvedFocusTable}</span>
          <span className="table-er-pane__meta">
            {nodes.length} 张表 · {edges.length} 条关系 · {inferredEdgeCount} 条推断
          </span>
        </div>
        <Toolbar className="table-er-pane__toolbar" aria-label="ER 图控制栏">
          <ToolbarGroup>
            <label className="table-er-pane__control">
              <span>视图范围</span>
              <Select
                className="table-er-pane__select"
                value={viewMode}
                onChange={(event) => setViewMode(event.target.value as ErViewMode)}
                aria-label="视图范围"
              >
                <option value="focus">聚焦</option>
                <option value="full">全库</option>
              </Select>
            </label>
            <label className="table-er-pane__control">
              <span>关系深度</span>
              <Select
                className="table-er-pane__select"
                value={String(depth)}
                onChange={(event) => setDepth(event.target.value === "2" ? 2 : 1)}
                aria-label="关系深度"
                disabled={viewMode !== "focus"}
              >
                <option value="1">一跳</option>
                <option value="2">两跳</option>
              </Select>
            </label>
            <Button
              className="table-er-pane__toggle"
              size="sm"
              variant={showInferred ? "secondary" : "outline"}
              onClick={() => setShowInferred((value) => !value)}
            >
              {showInferred ? "隐藏推断关系" : "显示推断关系"}
            </Button>
          </ToolbarGroup>
        </Toolbar>
      </div>
      <div className="table-er-pane__canvas">
        <Suspense fallback={<LoadingState className="table-er-pane__diagram-loading" label="正在载入关系图..." />}>
          <ErDiagram
            data={data}
            focusTable={resolvedFocusTable}
            viewMode={viewMode}
            depth={depth}
            showInferred={showInferred}
            onNodeClick={setFocusTable}
          />
        </Suspense>
      </div>
    </div>
  );
}
