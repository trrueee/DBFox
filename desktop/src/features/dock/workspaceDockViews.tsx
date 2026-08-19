import { lazy } from "react";
import { FileText } from "lucide-react";
import { DockSuspense } from "../appShell/dockViewContent";
import { useWorkspaceFileStore } from "../../stores/workspaceFileStore";
import type { DockViewContribution } from "./types";

const WorkspaceFileDockContent = lazy(() =>
  import("../workspace/WorkspaceFileDock").then((module) => ({
    default: module.WorkspaceFileDockContent,
  })),
);

const iconProps = { size: 13, "aria-hidden": true as const };

export const workspaceDockViews: readonly DockViewContribution[] = [
  {
    viewType: "dbfox.workspace.file",
    icon: () => <FileText {...iconProps} />,
    resolveTitle: (view) => {
      const fileState =
        useWorkspaceFileStore.getState().fileStateByKey[view.stateKey ?? view.viewKey];
      return fileState?.fileName ?? view.title;
    },
    isVisible: (view, context) => {
      const fileState =
        useWorkspaceFileStore.getState().fileStateByKey[view.stateKey ?? view.viewKey];
      const projectId = fileState?.projectId ?? view.projectId;
      return !projectId || projectId === context.activeProjectId;
    },
    render: (view) => (
      <DockSuspense>
        <WorkspaceFileDockContent tab={view} />
      </DockSuspense>
    ),
  },
];
