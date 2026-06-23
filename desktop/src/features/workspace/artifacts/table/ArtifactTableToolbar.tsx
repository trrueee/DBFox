import { ArrowUpDown, Copy, Download, Filter, RefreshCw, Search } from "lucide-react";

interface ArtifactTableToolbarProps {
  mode: "inline" | "workspace";
  artifactId: string;
  search: string;
  onSearchChange: (value: string) => void;
  isLoading: boolean;
  isSqlBackedWorkspace: boolean;
  onRefresh: () => void;
  onFilter: () => void;
  onSortNotice: () => void;
  onExport: () => void;
  onCopy: () => void;
  canToggleLoadedRows: boolean;
  expanded: boolean;
  loadedRowCount: number;
  onToggleExpanded: () => void;
}

export function ArtifactTableToolbar({
  mode,
  artifactId,
  search,
  onSearchChange,
  isLoading,
  isSqlBackedWorkspace,
  onRefresh,
  onFilter,
  onSortNotice,
  onExport,
  onCopy,
  canToggleLoadedRows,
  expanded,
  loadedRowCount,
  onToggleExpanded,
}: ArtifactTableToolbarProps) {
  if (mode === "workspace") {
    return (
      <div className="hifi-panel-toolbar hifi-result-toolbar px-2">
        <div className="hifi-toolbar-left flex items-center gap-1">
          <button className="hifi-toolbar-btn" onClick={onRefresh} disabled={isLoading || !isSqlBackedWorkspace}>
            <RefreshCw size={10} className={isLoading ? "animate-spin" : ""} /> 刷新
          </button>
          <button className="hifi-toolbar-btn" onClick={onFilter}>
            <Filter size={10} /> 筛选
          </button>
          <button className="hifi-toolbar-btn" onClick={onSortNotice}>
            <ArrowUpDown size={10} /> 排序
          </button>
          <button className="hifi-toolbar-btn" onClick={onExport}>
            <Download size={10} /> 导出
          </button>
          <button className="hifi-toolbar-btn" onClick={onCopy}>
            <Copy size={10} /> 复制
          </button>
        </div>
        <div className="hifi-toolbar-right flex items-center gap-2">
          <div className="relative flex items-center">
            <Search size={12} className="hifi-result-search-icon absolute left-2" />
            <input
              className="hifi-input hifi-result-search h-6 w-32 pl-6 pr-2 rounded text-[var(--ui-font-label)]"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="本地搜索..."
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor={`${artifactId}-table-search`}>
        搜索结果
      </label>
      <input
        id={`${artifactId}-table-search`}
        className="hifi-input h-7 min-w-[180px] flex-1 rounded px-2 text-[var(--ui-font-label)]"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="搜索结果"
      />
      {canToggleLoadedRows && (
        <button type="button" className="hifi-guide-btn-secondary hifi-artifact-action-btn" onClick={onToggleExpanded}>
          {expanded ? "收起预览" : `查看全部已载入 ${loadedRowCount} 行`}
        </button>
      )}
    </div>
  );
}
