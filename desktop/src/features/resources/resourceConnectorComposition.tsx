import type { ResourceConnectorContribution } from "./types";
import { createDataContribution, DATA_CONNECTOR_ID } from "./DataConnector";
import { createWorkspaceContribution, WORKSPACE_CONNECTOR_ID } from "./WorkspaceConnector";

export function productResourceConnectors(
  toast: (message: string) => void,
): readonly ResourceConnectorContribution[] {
  return [
    createDataContribution(toast),
    createWorkspaceContribution(),
  ];
}

export { DATA_CONNECTOR_ID, WORKSPACE_CONNECTOR_ID };
