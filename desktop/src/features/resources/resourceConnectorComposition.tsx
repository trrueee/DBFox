import { lazy, Suspense } from "react";
import type { ResourceConnectorContribution } from "./types";
import { createDataContribution, DATA_CONNECTOR_ID } from "./DataConnector";
import { createWorkspaceContribution, WORKSPACE_CONNECTOR_ID } from "./WorkspaceConnector";
import {
  createGithubContribution,
  GITHUB_CONNECTOR_ID,
  AddGithubRepoDialog,
} from "./GithubConnector";
import { useConnectionDialogStore } from "./connectionDialogStore";

const ConnectionDialog = lazy(() =>
  import("../datasource/ConnectionDialog").then((module) => ({
    default: module.ConnectionDialog,
  })),
);

export function productResourceConnectors(
  toast: (message: string) => void,
): readonly ResourceConnectorContribution[] {
  return [
    createDataContribution(toast),
    createWorkspaceContribution(),
    createGithubContribution(toast),
  ];
}

export function ResourceConnectorDialog() {
  const { open, createMode, close } = useConnectionDialogStore();
  return (
    <>
      {open ? (
        <Suspense fallback={null}>
          <ConnectionDialog
            open
            createMode={createMode}
            onOpenChange={(isOpen) => { if (!isOpen) close(); }}
          />
        </Suspense>
      ) : null}
      <AddGithubRepoDialog />
    </>
  );
}

export { DATA_CONNECTOR_ID, WORKSPACE_CONNECTOR_ID, GITHUB_CONNECTOR_ID };
