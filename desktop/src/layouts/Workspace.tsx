import type { Dispatch, MouseEvent, SetStateAction } from "react";
import WorkspaceTabs from "../features/workspace/WorkspaceTabs";
import type { ContextDrawerType, TableSubTab, WorkspaceTab } from "../types/workspace";

type WorkspaceProps = {
  tabs: WorkspaceTab[];
  activeTab: WorkspaceTab;
  activeTabId: string;
  ask: string;
  queryContextTables: string[];
  selectedTables: string[];
  onAskChange: (value: string) => void;
  onActiveTabChange: (id: string) => void;
  onCloseTab: (event: MouseEvent, id: string) => void;
  onOpenTable: (tableName: string, initialSubTab?: TableSubTab) => void;
  onOpenSql: () => void;
  onOpenQueryResult: () => void;
  onOpenDrawer: (
    type: ContextDrawerType,
    payload?: { tableName?: string; tableNames?: string[]; query?: string },
    title?: string,
  ) => void;
  onSetQueryContextTables: Dispatch<SetStateAction<string[]>>;
};

export default function Workspace(props: WorkspaceProps) {
  return (
    <section className="app-workspace">
      <WorkspaceTabs {...props} />
    </section>
  );
}
