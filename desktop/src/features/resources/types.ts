import type { ReactNode } from "react";

export interface ConnectorContext {
  projectId: string;
}

export interface ResourceConnectorContribution {
  id: string;
  title: string;
  icon: ReactNode;
  render(context: ConnectorContext): ReactNode;
  addLabel?: string;
  onAdd?: (context: ConnectorContext) => void;
}
