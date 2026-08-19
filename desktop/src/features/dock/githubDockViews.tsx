import { lazy } from "react";
import { GitBranch } from "lucide-react";
import { DockSuspense } from "../appShell/dockViewContent";
import { useGithubStore } from "../github/githubStore";
import type { DockViewContribution } from "./types";

const GithubFileDockContent = lazy(() =>
  import("./GithubFileDock").then((module) => ({
    default: module.GithubFileDockContent,
  })),
);

const iconProps = { size: 13, "aria-hidden": true as const };

export const githubDockViews: readonly DockViewContribution[] = [
  {
    viewType: "dbfox.github.file",
    icon: () => <GitBranch {...iconProps} />,
    resolveTitle: (view) => {
      const fileState =
        useGithubStore.getState().fileStateByKey[view.stateKey ?? view.viewKey];
      return fileState?.fileName ?? view.title;
    },
    isVisible: (view, context) => {
      const fileState =
        useGithubStore.getState().fileStateByKey[view.stateKey ?? view.viewKey];
      const projectId = fileState?.projectId ?? view.projectId;
      return !projectId || projectId === context.activeProjectId;
    },
    render: (view) => (
      <DockSuspense>
        <GithubFileDockContent tab={view} />
      </DockSuspense>
    ),
  },
];
