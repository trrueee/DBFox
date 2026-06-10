import type { ReactNode } from "react";
import { Copy, FileText, GitMerge, Info, Layers, RefreshCw, Sparkles, Terminal, Trash2, X } from "lucide-react";
import type { ContextMenuState } from "../../mock/databoxMock";

interface DataSourceContextMenuProps {
  contextMenu: ContextMenuState;
  selectedTables: string[];
  onOpenSqlConsole: () => void;
  onOpenTable: (tableName: string, subTab?: string) => void;
  onOpenMultiTableWorkspace: (tables: string[]) => void;
  onAddContextTable: (tableName: string) => void;
  onSetContextTables: (tables: string[]) => void;
  onClearSelectedTables: () => void;
  onClose: () => void;
  onToast: (message: string) => void;
  onOpenProps: () => void;
}

export function DataSourceContextMenu({
  contextMenu,
  selectedTables,
  onOpenSqlConsole,
  onOpenTable,
  onOpenMultiTableWorkspace,
  onAddContextTable,
  onSetContextTables,
  onClearSelectedTables,
  onClose,
  onToast,
  onOpenProps,
}: DataSourceContextMenuProps) {
  if (!contextMenu.visible) return null;

  const run = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <div className="hifi-context-menu" style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }} onClick={(event) => event.stopPropagation()}>
      {contextMenu.type === "database" && (
        <>
          <Item icon={<Terminal size={11} className="text-slate-500" />} label="打开 SQL 控制台" onClick={() => run(onOpenSqlConsole)} />
          <Item icon={<RefreshCw size={11} className="text-slate-500" />} label="刷新数据源" onClick={() => run(() => onToast("连接刷新中..."))} />
          <div className="hifi-context-menu-divider" />
          <Item icon={<Info size={11} className="text-slate-500" />} label="查看数据源属性" onClick={() => run(onOpenProps)} />
        </>
      )}

      {contextMenu.type === "schema" && (
        <>
          <Item icon={<Terminal size={11} className="text-slate-500" />} label="新建 SQL Console" onClick={() => run(onOpenSqlConsole)} />
          <Item icon={<FileText size={11} className="text-slate-500" />} label="查看所有表结构" onClick={() => run(() => onOpenTable("id_users", "schema"))} />
          <Item icon={<GitMerge size={11} className="text-slate-500" />} label="生成库级 ER 图" onClick={() => run(() => onOpenTable("id_users", "er"))} />
          <div className="hifi-context-menu-divider" />
          <Item icon={<RefreshCw size={11} className="text-slate-500" />} label="刷新 Schema" onClick={() => run(() => onToast("架构缓存已刷新"))} />
        </>
      )}

      {contextMenu.type === "table" && (
        <>
          <Item icon={<FileText size={11} className="text-slate-500" />} label="预览表数据" onClick={() => run(() => onOpenTable(contextMenu.targetNode, "preview"))} />
          <Item icon={<Info size={11} className="text-slate-500" />} label="查看表字段结构" onClick={() => run(() => onOpenTable(contextMenu.targetNode, "schema"))} />
          <Item icon={<Sparkles size={11} className="text-indigo-500" />} label="作为问数上下文" onClick={() => run(() => onAddContextTable(contextMenu.targetNode))} />
          <Item icon={<GitMerge size={11} className="text-slate-500" />} label="生成表级 ER 关系图" onClick={() => run(() => onOpenTable(contextMenu.targetNode, "er"))} />
          <div className="hifi-context-menu-divider" />
          <Item icon={<Copy size={11} className="text-slate-500" />} label="复制物理表名" onClick={() => run(() => { navigator.clipboard.writeText(contextMenu.targetNode); onToast(`已成功复制表名: ${contextMenu.targetNode}`); })} />
          <Item danger icon={<Trash2 size={11} />} label="物理删除表" onClick={() => run(() => onToast(`已成功物理删除表 ${contextMenu.targetNode}`))} />
        </>
      )}

      {contextMenu.type === "multi-table" && (
        <>
          <Item icon={<GitMerge size={11} className="text-orange-500" />} label="作为联合 Workspace 打开" onClick={() => run(() => onOpenMultiTableWorkspace(selectedTables))} />
          <Item icon={<Sparkles size={11} className="text-purple-500" />} label="基于选择的多表智能问数" onClick={() => run(() => onSetContextTables(selectedTables))} />
          <Item icon={<Layers size={11} className="text-blue-500" />} label="生成选定表联合 ER 图" onClick={() => run(() => onOpenTable(selectedTables[0], "er"))} />
          <div className="hifi-context-menu-divider" />
          <Item icon={<X size={11} className="text-slate-500" />} label="取消选择" onClick={() => run(onClearSelectedTables)} />
        </>
      )}
    </div>
  );
}

function Item({ icon, label, danger, onClick }: { icon: ReactNode; label: string; danger?: boolean; onClick: () => void }) {
  return (
    <div className={`hifi-context-menu-item ${danger ? "danger" : ""}`} onClick={onClick}>
      {icon}
      <span>{label}</span>
    </div>
  );
}
