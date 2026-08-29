import type { ResourceConnectorContribution } from "./types";
import { useDlcStore } from "../dlc/extensionStore";

export function productResourceConnectors(
  _toast: (message: string) => void,
  extraConnectors?: readonly ResourceConnectorContribution[],
): readonly ResourceConnectorContribution[] {
  return extraConnectors ?? useDlcStore.getState().contributions.connectors;
}

export function ResourceConnectorDialog() {
  return null;
}
