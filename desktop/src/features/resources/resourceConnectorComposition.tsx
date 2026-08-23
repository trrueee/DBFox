import type { ResourceConnectorContribution } from "./types";
import { useDlcStore } from "../dlc/extensionStore";

const DATA_CONNECTOR_ID = "dbfox.data";

export function productResourceConnectors(
  _toast: (message: string) => void,
  extraConnectors?: readonly ResourceConnectorContribution[],
): readonly ResourceConnectorContribution[] {
  return extraConnectors ?? useDlcStore.getState().contributions.connectors;
}

export function ResourceConnectorDialog() {
  return null;
}

export { DATA_CONNECTOR_ID };
