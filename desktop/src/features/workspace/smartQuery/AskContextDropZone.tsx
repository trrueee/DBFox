import { GitMerge, X } from "lucide-react";

interface AskContextDropZoneProps {
  contextTables: string[];
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
}

export function AskContextDropZone({ contextTables, onAddContextTable, onRemoveContextTable, onClearContextTables }: AskContextDropZoneProps) {
  return (
    <div
      className="hifi-drop-zone"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const tableName = event.dataTransfer.getData("text/plain");
        if (tableName) onAddContextTable(tableName);
      }}
    >
      <GitMerge size={12} className="text-indigo-500 flex-shrink-0" />
      <span className="text-[10px] text-slate-500 font-semibold mr-1">问数上下文:</span>
      {contextTables.length === 0 ? (
        <span className="text-[10px] text-slate-400 italic">拖拽左侧的表到这里以加载问数上下文</span>
      ) : (
        <div className="flex gap-1.5 flex-wrap items-center">
          {contextTables.map((tableName) => (
            <span key={tableName} className="hifi-context-chip flex items-center gap-1 bg-indigo-50 border border-indigo-200 text-indigo-700 px-1.5 py-0.5 rounded text-[9px] font-mono">
              <span>{tableName}</span>
              <X size={8} className="cursor-pointer hover:bg-indigo-200 rounded-full p-0.5" onClick={() => onRemoveContextTable(tableName)} />
            </span>
          ))}
          <button className="text-[9px] text-red-500 hover:underline ml-1" onClick={onClearContextTables}>清除</button>
        </div>
      )}
    </div>
  );
}
