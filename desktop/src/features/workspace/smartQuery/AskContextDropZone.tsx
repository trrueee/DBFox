import { GitMerge, X } from "lucide-react";
import "./AskContextDropZone.css";

interface AskContextDropZoneProps {
  contextTables: string[];
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
}

export function AskContextDropZone({ contextTables, onAddContextTable, onRemoveContextTable, onClearContextTables }: AskContextDropZoneProps) {
  return (
    <div
      className="ask-context-dropzone"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const tableName = event.dataTransfer.getData("text/plain");
        if (tableName) onAddContextTable(tableName);
      }}
    >
      <GitMerge size={12} className="ask-context-dropzone__icon" />
      <span className="ask-context-dropzone__label">问数上下文:</span>
      {contextTables.length === 0 ? (
        <span className="ask-context-dropzone__placeholder">拖拽左侧的表到这里以加载问数上下文</span>
      ) : (
        <div className="ask-context-dropzone__chips">
          {contextTables.map((tableName) => (
            <span key={tableName} className="ask-context-chip">
              <span>{tableName}</span>
              <button type="button" className="ask-context-chip__remove" onClick={() => onRemoveContextTable(tableName)} aria-label={`移除 ${tableName}`}>
                <X size={8} />
              </button>
            </span>
          ))}
          <button type="button" className="ask-context-dropzone__clear" onClick={onClearContextTables}>清除</button>
        </div>
      )}
    </div>
  );
}
