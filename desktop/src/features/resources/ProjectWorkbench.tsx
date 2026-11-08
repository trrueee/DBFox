import { useState } from "react";
import {
  PlusIcon,
} from "@/components/icons";
import { Button, EmptyState, Alert, AlertDescription } from "../../components/ui";
import { useDlcStore } from "../dlc/extensionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { getUserErrorMessage } from "../../lib/api/client";
import type { ResourceConnectorContribution } from "./types";
import "./project-workbench.css";

export const PROJECT_WORKBENCH_VIEW = "core.project-workbench";

export function openProjectWorkbench(connector: ResourceConnectorContribution, projectId: string): void | Promise<void> {
  if (connector.onOpen) return connector.onOpen({ projectId });
  useWorkspaceStore.getState().openDockTab({ viewKey: `project-workbench:${projectId}:${connector.id}`,
    viewType: PROJECT_WORKBENCH_VIEW, title: connector.title, closeable: true, projectId, stateKey: connector.id });
}

/** The Host owns the frame; every domain view stays inside its registered DLC. */
export function ProjectWorkbench({ connectorId, projectId }: { connectorId: string; projectId: string }) {
  const connector = useDlcStore(state => state.contributions.connectors.find(item => item.id === connectorId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  if (!connector) return <EmptyState title="此工作台暂不可用" description="对应扩展尚未启用或不可用。"
    action={<Button type="button" variant="secondary" onClick={() => useWorkspaceStore.getState().openSettings("dlc")}>管理扩展</Button>} />;
  return <section className="project-workbench" aria-label={`${connector.title}工作台`}>
    <header className="project-workbench__header"><span className="project-workbench__identity">{connector.icon}<span>{connector.title}</span></span>
      {connector.onAdd ? <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={async () => {
        if (busy) return;
        setBusy(true); setError(undefined);
        try { await connector.onAdd?.({ projectId }); } catch (reason) { setError(reason); } finally { setBusy(false); }
      }}><PlusIcon size={16} aria-hidden="true" />{connector.addLabel ?? "添加"}</Button> : null}</header>
    {error ? <Alert variant="destructive"><AlertDescription>{getUserErrorMessage(error, "操作失败，请重试。")}</AlertDescription></Alert> : null}
    <div className="project-workbench__body">{connector.render({ projectId })}</div>
  </section>;
}
