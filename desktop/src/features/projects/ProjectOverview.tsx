import { useCallback, useEffect, useState } from "react";
import { FolderKanban, Plus, RefreshCw, Trash2 } from "lucide-react";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  EmptyState,
  ErrorDetails,
  ErrorState,
  LoadingState,
} from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDlcStore } from "../dlc/extensionStore";
import { useProjectState } from "./useProjectState";
import type { ConnectorProjectResource } from "../resources/types";
import "./ProjectOverview.css";

interface InventoryState {
  loading: boolean;
  entries: ConnectorProjectResource[];
  error: unknown | null;
}

const EMPTY_INVENTORY: InventoryState = { loading: false, entries: [], error: null };

/**
 * Project management surface — Core owns the frame: which DLCs contribute
 * per-project capabilities, the inventory of what they configured, and where
 * their configuration is reached from. Configuration itself stays inside each
 * DLC via its connector contribution (onAdd / listResources / removeResource
 * scoped to this project).
 */
export function ProjectOverview() {
  const projectId = useWorkspaceStore((state) => state.activeProjectId);
  const showSmartQueryHome = useWorkspaceStore((state) => state.showSmartQueryHome);
  const connectors = useDlcStore((state) => state.contributions.connectors);
  const { activeProject, loadingProjects, projectError, refreshProjects } = useProjectState(projectId);
  const [inventory, setInventory] = useState<Record<string, InventoryState>>({});
  const [addingId, setAddingId] = useState<string | null>(null);
  const [addError, setAddError] = useState<unknown | null>(null);
  const [removingKey, setRemovingKey] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<{ connectorId: string; error: unknown } | null>(null);

  const loadInventory = useCallback(async () => {
    if (!projectId) return;
    for (const connector of connectors) {
      if (!connector.listResources) continue;
      setInventory((current) => ({ ...current, [connector.id]: { loading: true, entries: [], error: null } }));
      try {
        const entries = (await connector.listResources({ projectId })) ?? [];
        setInventory((current) => ({ ...current, [connector.id]: { loading: false, entries, error: null } }));
      } catch (error) {
        setInventory((current) => ({ ...current, [connector.id]: { loading: false, entries: [], error } }));
      }
    }
  }, [connectors, projectId]);

  useEffect(() => {
    void loadInventory();
  }, [loadInventory]);

  if (loadingProjects) return <LoadingState label="正在载入项目" />;
  if (projectError) {
    return (
      <ErrorState
        title="项目不可用"
        description={getUserErrorMessage(projectError, "读取项目失败，请重试。")}
        error={projectError}
        onRetry={() => void refreshProjects()}
      />
    );
  }
  if (!activeProject) {
    return (
      <EmptyState
        title="项目不可用"
        description="选择一个项目后可管理它的资源。"
      />
    );
  }

  const configureResource = async (
    connectorId: string,
    onAdd: (input: { projectId: string }) => Promise<void> | void,
  ) => {
    if (addingId) return;
    setAddError(null);
    setAddingId(connectorId);
    try {
      await onAdd({ projectId: activeProject.id });
    } catch (error) {
      setAddError(error);
    } finally {
      setAddingId(null);
      await loadInventory();
    }
  };

  const removeResource = async (
    connectorId: string,
    removeResource: (context: { projectId: string }, resource: ConnectorProjectResource) => Promise<void> | void,
    resource: ConnectorProjectResource,
  ) => {
    const key = `${connectorId}:${resource.id}`;
    if (removingKey) return;
    setRemoveError(null);
    setRemovingKey(key);
    try {
      await removeResource({ projectId: activeProject.id }, resource);
    } catch (error) {
      setRemoveError({ connectorId, error });
    } finally {
      setRemovingKey(null);
      await loadInventory();
    }
  };

  return (
    <article className="project-overview">
      <header className="project-overview__header">
        <div className="project-overview__identity">
          <span className="project-overview__icon" aria-hidden="true">
            <FolderKanban size={20} />
          </span>
          <div>
            <h1>{activeProject.name}</h1>
            {activeProject.description ? <p>{activeProject.description}</p> : null}
          </div>
        </div>
        <Button type="button" size="sm" onClick={() => showSmartQueryHome()}>
          <Plus size={16} aria-hidden="true" />
          新任务
        </Button>
      </header>

      <div className="project-overview__body">
        <section className="project-overview__section" aria-labelledby="project-resources-title">
          <div className="project-overview__section-header">
            <div>
              <h2 id="project-resources-title">资源</h2>
            </div>
            {connectors.length ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => void loadInventory()}>
                <RefreshCw size={14} aria-hidden="true" />
                刷新
              </Button>
            ) : null}
          </div>
          {addError ? (
            <Alert className="project-overview__alert" variant="destructive">
              <AlertTitle>配置资源失败</AlertTitle>
              <AlertDescription>
                <span>{getUserErrorMessage(addError, "配置资源失败，请重试。")}</span>
                <ErrorDetails error={addError} />
              </AlertDescription>
            </Alert>
          ) : null}
          {removeError ? (
            <Alert className="project-overview__alert" variant="destructive">
              <AlertTitle>移除资源失败</AlertTitle>
              <AlertDescription>
                <span>{getUserErrorMessage(removeError.error, "移除资源失败，请重试。")}</span>
                <ErrorDetails error={removeError.error} />
              </AlertDescription>
            </Alert>
          ) : null}
          {connectors.length ? (
            <div className="project-overview__resource-list">
              {connectors.map((connector) => {
                const state = inventory[connector.id] ?? EMPTY_INVENTORY;
                return (
                  <div className="project-overview__connector" key={connector.id}>
                    <div className="project-overview__resource-row project-overview__resource-row--head">
                      <span className="project-overview__resource-icon" aria-hidden="true">
                        {connector.icon}
                      </span>
                      <span className="project-overview__resource-copy">
                        <span className="project-overview__resource-title">{connector.title}</span>
                        <small className="project-overview__resource-desc">
                          由 {connector.title} 扩展提供，配置仅作用于当前项目。
                        </small>
                      </span>
                      {connector.onAdd ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={addingId !== null}
                          onClick={() => void configureResource(connector.id, connector.onAdd!)}
                        >
                          <Plus size={14} aria-hidden="true" />
                          {connector.addLabel ?? "配置"}
                        </Button>
                      ) : null}
                    </div>
                    {connector.listResources ? (
                      <div className="project-overview__inventory">
                        {state.loading ? (
                          <p className="project-overview__inventory-empty">正在载入资源…</p>
                        ) : state.error ? (
                          <p className="project-overview__inventory-empty">
                            资源列表载入失败：{getUserErrorMessage(state.error, "请稍后重试。")}
                          </p>
                        ) : state.entries.length ? (
                          state.entries.map((entry) => (
                            <div
                              className="project-overview__inventory-row"
                              key={entry.id}
                            >
                              <span className="project-overview__inventory-name" title={entry.name}>
                                {entry.name}
                              </span>
                              {entry.detail ? (
                                <span className="project-overview__inventory-detail" title={entry.detail}>
                                  {entry.detail}
                                </span>
                              ) : null}
                              {connector.removeResource ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label={`移除 ${entry.name}`}
                                  disabled={removingKey !== null}
                                  onClick={() =>
                                    void removeResource(connector.id, connector.removeResource!, entry)
                                  }
                                >
                                  <Trash2 size={14} aria-hidden="true" />
                                </Button>
                              ) : null}
                            </div>
                          ))
                        ) : (
                          <p className="project-overview__inventory-empty">这个扩展还没有配置资源。</p>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              <p className="project-overview__resource-hint">
                每个扩展在此项目中的连接与配置相互独立；已配置的资源常驻左侧边栏，可从任意任务访问。
              </p>
            </div>
          ) : (
            <p className="project-overview__empty">
              安装并启用 DLC 后，可在这里为项目配置数据、文件等资源。
            </p>
          )}
        </section>
      </div>
    </article>
  );
}
