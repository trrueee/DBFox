import { Table2 } from "lucide-react";
import type { SchemaTable } from "../../lib/api";
import type { WorkbenchSubTab } from "./types";

interface WorkbenchTableHeaderProps {
  tableName: string;
  table?: SchemaTable | null;
  activeSubTab: WorkbenchSubTab;
  onSwitchSubTab: (subTab: WorkbenchSubTab) => void;
}

const SUB_TABS: Array<{ id: WorkbenchSubTab; label: string }> = [
  { id: "data", label: "Data" },
  { id: "schema", label: "Schema" },
  { id: "er", label: "ER" },
];

export function WorkbenchTableHeader({ tableName, table, activeSubTab, onSwitchSubTab }: WorkbenchTableHeaderProps) {
  return (
    <header className="wb-table-header">
      <div className="wb-table-title-block">
        <div className="wb-table-title">
          <Table2 size={15} />
          <span className="wb-table-name">{tableName}</span>
        </div>
        <div className="wb-table-comment">
          {table?.table_comment || "暂无表备注"}
        </div>
      </div>

      <div className="wb-table-meta">
        <span>{table?.columns_count ?? 0} columns</span>
        <span>·</span>
        <span>{table?.row_count_estimate ?? 0} rows est.</span>
      </div>

      <div className="wb-segmented">
        {SUB_TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            data-active={activeSubTab === item.id}
            onClick={() => onSwitchSubTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </header>
  );
}
