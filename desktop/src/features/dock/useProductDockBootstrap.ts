import { useEffect } from "react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useSqlConsoleStore } from "../../stores/sqlConsoleStore";
import { useArtifactDockStore } from "../../stores/artifactDockStore";
import { useDatasourceState } from "../datasource/useDatasourceState";
import { useDatasourceSelectionStore } from "../../stores/datasourceSelectionStore";

/**
 * Product-level Dock bootstrap:
 * Ensures a persistent SQL Console exists for the active datasource,
 * and an Artifacts tab exists for the active conversation.
 */
export function useProductDockBootstrap(activeConversationId: string | null) {
  const dockTabs = useWorkspaceStore((s) => s.dockTabs);
  const openDockConsole = useSqlConsoleStore((s) => s.openConsole);
  const openDockArtifacts = useArtifactDockStore((s) => s.openArtifacts);
  const activeDatasourceId = useDatasourceSelectionStore((s) => s.activeDatasourceId);
  const { activeDatasource } = useDatasourceState();

  // 每个项目预备一个持久 Console Tab，但切换项目不能强行展开 Dock。
  useEffect(() => {
    if (
      activeDatasourceId
      && !dockTabs.some(
        (tab) =>
          tab.viewType === "dbfox.data.sql-console"
          && tab.target?.type === "resource"
          && tab.target.id === activeDatasourceId,
      )
    ) {
      openDockConsole(activeDatasourceId, activeDatasource?.db_type ?? null, undefined, false);
    }
  }, [activeDatasource?.db_type, activeDatasourceId, dockTabs, openDockConsole]);

  // 当前对话保证有「✦ 工件」Tab，但不抢走用户当前打开的 Tab。
  useEffect(() => {
    if (
      activeConversationId
      && !dockTabs.some(
        (tab) =>
          tab.viewType === "core.artifacts"
          && tab.target?.type === "conversation"
          && tab.target.id === activeConversationId,
      )
    ) {
      openDockArtifacts(activeConversationId, false);
    }
  }, [activeConversationId, dockTabs, openDockArtifacts]);
}
