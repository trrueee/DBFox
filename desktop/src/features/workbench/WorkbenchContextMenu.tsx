interface TableContextMenuState {
  tableName: string;
  x: number;
  y: number;
}

interface WorkbenchContextMenuProps {
  menu: TableContextMenuState | null;
  onClose: () => void;
  onOpenData: (tableName: string) => void;
  onOpenSchema: (tableName: string) => void;
  onOpenEr: (tableName: string) => void;
  onNewQuery: (tableName: string) => void;
  onGenerateSelect: (tableName: string) => void;
  onCopyTableName: (tableName: string) => void;
  onExplainTable: (tableName: string) => void;
}

export function WorkbenchContextMenu({
  menu,
  onClose,
  onOpenData,
  onOpenSchema,
  onOpenEr,
  onNewQuery,
  onGenerateSelect,
  onCopyTableName,
  onExplainTable,
}: WorkbenchContextMenuProps) {
  if (!menu) return null;

  const run = (action: (tableName: string) => void) => {
    action(menu.tableName);
    onClose();
  };

  return (
    <>
      <div
        onClick={onClose}
        onContextMenu={(event) => {
          event.preventDefault();
          onClose();
        }}
        style={{ position: "fixed", inset: 0, zIndex: 1999 }}
      />
      <div className="wb-menu-surface" style={{ top: menu.y, left: menu.x }} onClick={(event) => event.stopPropagation()}>
        <div className="wb-menu-title">数据表: {menu.tableName}</div>
        <button className="data-table-menu-item" type="button" onClick={() => run(onOpenData)}>打开数据</button>
        <button className="data-table-menu-item" type="button" onClick={() => run(onOpenSchema)}>打开结构字段</button>
        <button className="data-table-menu-item" type="button" onClick={() => run(onOpenEr)}>查看 ER 图</button>
        <button className="data-table-menu-item" type="button" onClick={() => run(onNewQuery)}>新建 SQL 查询</button>
        <button className="data-table-menu-item" type="button" onClick={() => run(onGenerateSelect)}>生成 SELECT SQL</button>
        <div className="h-px bg-[var(--border-light)] my-1" />
        <button className="data-table-menu-item" type="button" onClick={() => run(onCopyTableName)}>复制表名</button>
        <button className="data-table-menu-item" type="button" onClick={() => run(onExplainTable)}>解释表结构</button>
      </div>
    </>
  );
}
