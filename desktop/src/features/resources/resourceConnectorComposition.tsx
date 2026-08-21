import { lazy, Suspense } from "react";
import type { ResourceConnectorContribution } from "./types";
import { createDataContribution, DATA_CONNECTOR_ID } from "./DataConnector";
import { createWorkspaceContribution, WORKSPACE_CONNECTOR_ID } from "./WorkspaceConnector";
import { useConnectionDialogStore } from "./connectionDialogStore";
import { useDlcStore } from "../dlc/extensionStore";

const ConnectionDialog = lazy(() =>
  import("../datasource/ConnectionDialog").then((module) => ({
    default: module.ConnectionDialog,
  })),
);

export function productResourceConnectors(
  toast: (message: string) => void,
  extraConnectors?: readonly ResourceConnectorContribution[],
): readonly ResourceConnectorContribution[] {
  const dlcConnectors = extraConnectors ?? useDlcStore.getState().contributions.connectors;
  return [
    createDataContribution(toast),
    createWorkspaceContribution(),
    ...dlcConnectors,
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
    </>
  );
}

export { DATA_CONNECTOR_ID, WORKSPACE_CONNECTOR_ID };
