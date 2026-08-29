import { useState } from "react";
import { AlertCircle, ChevronRight, Plus } from "lucide-react";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  ErrorDetails,
  SidebarGroup,
  SidebarGroupLabel,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import type { ResourceConnectorContribution } from "./types";

interface ResourceViewContainerProps {
  projectId: string;
  connectors: readonly ResourceConnectorContribution[];
  /**
   * Render the "资源" group label. Disabled inside project groups where the
   * connector sections sit directly under the project row.
   */
  showGroupLabel?: boolean;
}

/** Host-owned, persistent container for DLC-owned project resource views. */
export function ResourceViewContainer({
  projectId,
  connectors,
  showGroupLabel = true,
}: ResourceViewContainerProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [addingId, setAddingId] = useState<string | null>(null);
  const [addError, setAddError] = useState<unknown | null>(null);

  const addResource = async (connector: ResourceConnectorContribution) => {
    if (!connector.onAdd || addingId) return;
    setAddError(null);
    setAddingId(connector.id);
    try {
      await connector.onAdd({ projectId });
    } catch (error) {
      setAddError(error);
    } finally {
      setAddingId(null);
    }
  };

  return (
    <SidebarGroup className="resource-view-container" aria-label="项目资源">
      {showGroupLabel ? <SidebarGroupLabel>资源</SidebarGroupLabel> : null}
      {addError ? (
        <Alert className="product-sidebar__alert" variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>添加资源失败</AlertTitle>
          <AlertDescription>
            <span>{getUserErrorMessage(addError, "添加资源失败，请重试。")}</span>
            <ErrorDetails error={addError} />
          </AlertDescription>
        </Alert>
      ) : null}
      {connectors.length ? connectors.map((connector, index) => {
        const isExpanded = expanded[connector.id] ?? index === 0;
        return (
          <section className="resource-view" key={connector.id}>
            <div className="resource-view__header">
              <button
                type="button"
                className="resource-view__toggle"
                aria-expanded={isExpanded}
                onClick={() => setExpanded((current) => ({
                  ...current,
                  [connector.id]: !isExpanded,
                }))}
              >
                <ChevronRight
                  size={14}
                  className="resource-view__chevron"
                  aria-hidden="true"
                />
                <span className="resource-view__icon" aria-hidden="true">{connector.icon}</span>
                <span className="resource-view__title">{connector.title}</span>
              </button>
              {connector.onAdd ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      disabled={addingId !== null}
                      aria-label={connector.addLabel ?? `添加${connector.title}`}
                      onClick={() => void addResource(connector)}
                    >
                      <Plus size={14} aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{connector.addLabel ?? `添加${connector.title}`}</TooltipContent>
                </Tooltip>
              ) : null}
            </div>
            {isExpanded ? (
              <div className="resource-view__body">
                {connector.render({ projectId })}
              </div>
            ) : null}
          </section>
        );
      }) : null}
    </SidebarGroup>
  );
}
