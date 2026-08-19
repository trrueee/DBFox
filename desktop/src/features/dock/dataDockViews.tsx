import { lazy } from "react";
import { GitMerge, Table2, Terminal } from "lucide-react";
import {
  ConsoleDockContent,
  DockSuspense,
  TableDockContent,
} from "../appShell/dockViewContent";
import { useSqlConsoleStore } from "../../stores/sqlConsoleStore";
import { useTableWorkspaceStore } from "../../stores/tableWorkspaceStore";
import type { DockViewContribution } from "./types";

const MultiTableWorkspace = lazy(() =>
  import("../workspace/MultiTableWorkspace").then((module) => ({
    default: module.MultiTableWorkspace,
  })),
);

const iconProps = { size: 13, "aria-hidden": true as const };

export const dataDockViews: readonly DockViewContribution[] = [
  {
    viewType: "dbfox.data.sql-console",
    icon: () => <Terminal {...iconProps} />,
    resolveTitle: () => "SQL 控制台",
    isVisible: (view, context) => {
      const stateKey = view.stateKey ?? view.viewKey;
      const dsId =
        (view.target?.type === "resource" && view.target.kind === "database"
          ? view.target.id
          : "")
        || useSqlConsoleStore.getState().sqlConsoleState[stateKey]?.datasourceId;
      return !dsId || dsId === context.activeDatasourceId;
    },
    render: (view, context) => (
      <DockSuspense>
        <ConsoleDockContent
          tab={view}
          activeDatasourceId={context.activeDatasourceId}
          showToast={context.showToast}
        />
      </DockSuspense>
    ),
  },
  {
    viewType: "dbfox.data.table",
    icon: () => <Table2 {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => {
      const stateKey = view.stateKey ?? view.viewKey;
      const dsId =
        (view.target?.type === "resource" && view.target.kind === "database"
          ? view.target.id
          : "")
        || useTableWorkspaceStore.getState().tableStateByTabId[stateKey]?.datasourceId;
      return !dsId || dsId === context.activeDatasourceId;
    },
    render: (view, context) => (
      <DockSuspense>
        <TableDockContent tab={view} showToast={context.showToast} />
      </DockSuspense>
    ),
  },
  {
    viewType: "dbfox.data.multi-table",
    icon: () => <GitMerge {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => {
      const stateKey = view.stateKey ?? view.viewKey;
      const dsId =
        (view.target?.type === "resource" && view.target.kind === "database"
          ? view.target.id
          : "")
        || useTableWorkspaceStore.getState().multiTableStateByTabId[stateKey]?.datasourceId;
      return !dsId || dsId === context.activeDatasourceId;
    },
    render: (view, context) => {
      const stateKey = view.stateKey ?? view.viewKey;
      const tables =
        useTableWorkspaceStore.getState().multiTableStateByTabId[stateKey]?.tables ?? [];
      return (
        <DockSuspense>
          <MultiTableWorkspace
            tables={tables}
            onOpenQueryResult={context.onOpenQueryResult}
            onToast={context.showToast}
          />
        </DockSuspense>
      );
    },
  },
];
