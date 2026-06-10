import { Eye, Network, TableProperties } from "lucide-react";
import type { ReactNode } from "react";
import type { SchemaTable } from "../../lib/api";

export type SchemaBrowserTab = "fields" | "er" | "data";

interface SchemaBrowserHeaderProps {
  selectedTable: SchemaTable | null;
  viewTab: SchemaBrowserTab;
  embedded?: boolean;
  onTabChange: (tab: SchemaBrowserTab) => void;
}

const tabs: Array<{ id: SchemaBrowserTab; label: string; icon?: ReactNode }> = [
  { id: "fields", label: "字段", icon: <TableProperties size={13} /> },
  { id: "er", label: "关系图", icon: <Network size={13} /> },
  { id: "data", label: "数据预览", icon: <Eye size={13} /> },
];

export function SchemaBrowserHeader({ selectedTable, viewTab, embedded, onTabChange }: SchemaBrowserHeaderProps) {
  if (embedded) return null;

  return (
    <header className="schema-browser-header">
      <div className="schema-browser-title">
        <div className="schema-browser-name">{selectedTable?.table_name ?? "Schema"}</div>
        {selectedTable?.table_comment && <div className="schema-browser-comment">{selectedTable.table_comment}</div>}
      </div>
      <nav className="schema-browser-tabs">
        {tabs.map((tab) => (
          <button key={tab.id} type="button" data-active={viewTab === tab.id} onClick={() => onTabChange(tab.id)}>
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </nav>
    </header>
  );
}
