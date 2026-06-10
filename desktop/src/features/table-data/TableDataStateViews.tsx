interface TableDataStateViewsProps {
  error?: string | null;
  loading?: boolean;
  appliedFilter?: string;
  onRetry?: () => void;
  onClearFilter?: () => void;
}

export function TableDataErrorState({ error, onRetry }: TableDataStateViewsProps) {
  return (
    <div className="table-data-state">
      <div className="table-data-state-card">
        <div className="table-data-state-title text-[var(--accent-red)]">加载出错</div>
        <div className="table-data-state-copy">{error || "数据加载失败，请检查权限、网络或 SQL 过滤条件。"}</div>
        {onRetry && (
          <button className="table-data-button table-data-button--primary" type="button" onClick={onRetry}>
            重试加载
          </button>
        )}
      </div>
    </div>
  );
}

export function TableDataLoadingState() {
  return (
    <div className="table-data-skeleton">
      <div className="table-data-skeleton-line bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />
      {[1, 2, 3, 4, 5, 6, 7].map((item) => (
        <div key={item} className="table-data-skeleton-line bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />
      ))}
    </div>
  );
}

export function TableDataNoRowsState({ appliedFilter, onClearFilter }: TableDataStateViewsProps) {
  return (
    <div className="table-data-state">
      <div className="table-data-state-card">
        <div className="table-data-state-title">没有找到任何行</div>
        <div className="table-data-state-copy">
          {appliedFilter ? "没有与搜索过滤匹配的记录，请尝试更改搜索词。" : "该表目前没有任何行数据。"}
        </div>
        {appliedFilter && onClearFilter && (
          <button className="table-data-button" type="button" onClick={onClearFilter}>
            清除搜索词
          </button>
        )}
      </div>
    </div>
  );
}
