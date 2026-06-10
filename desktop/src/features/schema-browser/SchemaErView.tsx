import { HardDrive } from "lucide-react";
import type { ERDiagramData } from "../../lib/api";
import { ErDiagram } from "../../components/ErDiagram";
import { ErrorBoundary } from "../../components/ErrorBoundary";

interface SchemaErViewProps {
  data: ERDiagramData;
  focusTable: string | null;
  viewMode: "focus" | "module" | "full";
  depth: 1 | 2;
  showInferred: boolean;
  onFocusTableChange: (tableName: string) => void;
  onViewModeChange: (mode: "focus" | "module" | "full") => void;
  onDepthChange: (depth: 1 | 2) => void;
  onShowInferredChange: (show: boolean) => void;
}

export function SchemaErView({
  data,
  focusTable,
  viewMode,
  depth,
  showInferred,
  onFocusTableChange,
  onViewModeChange,
  onDepthChange,
  onShowInferredChange,
}: SchemaErViewProps) {
  if (data.nodes.length === 0) {
    return (
      <div className="schema-empty">
        <div className="schema-empty-card">
          <HardDrive size={34} className="text-[var(--accent-indigo)]" />
          <div className="schema-empty-title">ER 关系图</div>
          <div className="schema-empty-copy">当前数据库暂无外键约束或尚未同步 Schema。</div>
        </div>
      </div>
    );
  }

  return (
    <div className="schema-er-view">
      <div className="schema-er-toolbar">
        <div className="schema-er-toolbar-group">
          <button type="button" data-active={viewMode === "focus"} onClick={() => onViewModeChange("focus")}>当前表关系</button>
          <button type="button" data-active={viewMode === "module"} onClick={() => onViewModeChange("module")}>业务模块</button>
          <button type="button" data-active={viewMode === "full"} onClick={() => onViewModeChange("full")}>全库关系</button>
        </div>
        {viewMode === "focus" && (
          <div className="schema-er-toolbar-group">
            <button type="button" data-active={depth === 1} onClick={() => onDepthChange(1)}>1 跳</button>
            <button type="button" data-active={depth === 2} onClick={() => onDepthChange(2)}>2 跳</button>
          </div>
        )}
        <label className="ml-auto flex items-center gap-1.5 text-[0.72rem] font-bold text-[var(--text-secondary)] cursor-pointer">
          <input type="checkbox" checked={showInferred} onChange={(event) => onShowInferredChange(event.target.checked)} />
          显示推断关系
        </label>
      </div>
      <div className="schema-er-canvas">
        <ErrorBoundary title="ER 图渲染异常">
          <ErDiagram
            data={data}
            focusTable={focusTable}
            depth={depth}
            viewMode={viewMode}
            showInferred={showInferred}
            onNodeClick={onFocusTableChange}
          />
        </ErrorBoundary>
      </div>
    </div>
  );
}
