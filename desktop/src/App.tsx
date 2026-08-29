import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialogContainer";
import { setToastRoot, useToast } from "./components/toastState";
import { installClientErrorLogging, recordClientLog } from "./lib/diagnostics/clientLog";
import {
  selectActiveConversationId,
  selectActiveDockOpen,
  useWorkspaceStore,
} from "./stores/workspaceStore";
import { openArtifactsDock } from "./stores/artifactDockStore";
import { useConversationStore } from "./stores/conversationStore";
import { DesktopLifecycleMonitor } from "./features/appShell/DesktopLifecycleMonitor";
import { LoadingState } from "./components/ui";
import { ConversationCenter } from "./features/appShell/ConversationCenter";
import { ConversationWorkspaceLayout } from "./features/appShell/ConversationWorkspaceLayout";
import { ResizableWorkspaceLayout } from "./features/appShell/ResizableWorkspaceLayout";
import { ProjectResourceSidebar } from "./features/resources/ProjectResourceSidebar";
import { productResourceConnectors } from "./features/resources/resourceConnectorComposition";
import { useProductDockBootstrap } from "./features/dock/useProductDockBootstrap";
import { useDlcStore } from "./features/dlc/extensionStore";
import {
  fetchAndLoadActiveExtensions,
  invalidateActiveFrontendExtensions,
} from "./features/dlc/extensionLoader";
import { getRuntimeSession, subscribeEngineState } from "./lib/api/client";

const AppCommandPalette = lazy(() =>
  import("./features/appShell/AppCommandPalette").then((module) => ({
    default: module.AppCommandPalette,
  })),
);
const SettingsPage = lazy(() =>
  import("./features/settings/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const ProjectCreateDialog = lazy(() =>
  import("./features/projects/ProjectCreateDialog").then((module) => ({
    default: module.ProjectCreateDialog,
  })),
);
const WorkspaceDock = lazy(() =>
  import("./features/appShell/WorkspaceDock").then((module) => ({
    default: module.WorkspaceDock,
  })),
);
const SettingsSidebar = lazy(() =>
  import("./features/settings/SettingsSidebar").then((module) => ({
    default: module.SettingsSidebar,
  })),
);
const TitleBar = lazy(() => import("./components/TitleBar"));

function TitleBarFallback() {
  return <div className="app-titlebar-fallback" aria-hidden="true" />;
}

function WorkspaceDockFallback() {
  return (
    <div className="app-dock-fallback" role="status" aria-label="正在载入工作区">
      <LoadingState label="正在载入工作区" />
    </div>
  );
}

function SidebarFallback() {
  return (
    <div className="app-sidebar-fallback" role="status" aria-label="正在载入主导航">
      <span className="app-skeleton app-skeleton--heading" />
      <span className="app-skeleton app-skeleton--control" />
      <span className="app-skeleton app-skeleton--control" />
      <span className="app-skeleton app-skeleton--row" />
      <span className="app-skeleton app-skeleton--row" />
      <span className="app-skeleton app-skeleton--row-short" />
    </div>
  );
}

function AppLayoutFallback() {
  return (
    <div className="app-layout-fallback">
      <SidebarFallback />
      <div className="app-layout-fallback__workspace">
        <LoadingState label="正在载入工作区" />
      </div>
    </div>
  );
}


export default function App() {
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const loadedEngineGenerationRef = useRef(0);

  const { toast } = useToast();

  // ── Store initialization (mount once) ──
  useEffect(() => {
    installClientErrorLogging();
    void useConversationStore.getState().initConversations().catch((error) => {
      recordClientLog("error", "初始化对话列表失败", error);
    });
    void fetchAndLoadActiveExtensions().catch((error) => {
      recordClientLog("warning", "加载 DLC 扩展失败", error);
    });

    loadedEngineGenerationRef.current = getRuntimeSession().generation;
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void subscribeEngineState((status) => {
      if (disposed) return;
      if (status.state !== "ready") {
        invalidateActiveFrontendExtensions();
        return;
      }
      const generation = status.generation ?? 0;
      if (generation <= loadedEngineGenerationRef.current) return;
      loadedEngineGenerationRef.current = generation;
      void fetchAndLoadActiveExtensions().catch((error) => {
        recordClientLog("warning", "重新加载 DLC 扩展失败", error);
      });
    }).then((cleanup) => {
      if (disposed) cleanup();
      else unsubscribe = cleanup;
    });

    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, []);

  // ── Store selectors ──
  const activeConversationId = useWorkspaceStore(selectActiveConversationId);
  const dockOpen = useWorkspaceStore(selectActiveDockOpen);
  const setDockOpen = useWorkspaceStore((s) => s.setDockOpen);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const settingsOpen = useWorkspaceStore((s) => s.settingsOpen);
  const settingsSection = useWorkspaceStore((s) => s.settingsSection);
  const openSettings = useWorkspaceStore((s) => s.openSettings);
  const closeSettings = useWorkspaceStore((s) => s.closeSettings);
  const setSettingsSection = useWorkspaceStore((s) => s.setSettingsSection);

  // Product-level Dock bootstrap (Console for active datasource, Artifacts for active conversation)
  useProductDockBootstrap(activeConversationId);

  const openConversationFromPalette = useCallback(
    (conversationId: string) => {
      void useConversationStore.getState()
        .openConversation(conversationId)
        .then(() => openConversationCenter(conversationId));
    },
    [openConversationCenter],
  );

  // Resource connector composition
  const dlcConnectors = useDlcStore((s) => s.contributions.connectors);
  const connectors = productResourceConnectors(toast, dlcConnectors);

  // Layout UI states
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const toggleSidebarCollapse = useCallback(() => setSidebarCollapsed((value) => !value), []);
  const handleOpenSettings = useCallback(() => {
    setSidebarCollapsed(false);
    openSettings("appearance");
  }, [openSettings]);

  // ── V3 快捷键：焦点与 Dock，不再承担全局搜索 ──
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) return;

      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShowCommandPalette((value) => !value);
      }
      if (event.key === "1") {
        event.preventDefault();
        if (activeConversationId) openConversationCenter(activeConversationId);
        else showSmartQueryHome();
      }
      if (event.key === "4" && activeConversationId) {
        event.preventDefault();
        openArtifactsDock(activeConversationId);
      }
      if (event.key === "\\") {
        event.preventDefault();
        setDockOpen(!dockOpen);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [
    activeConversationId,
    dockOpen,
    openConversationCenter,
    setDockOpen,
    showSmartQueryHome,
  ]);

  return (
    <div className="app-shell">
      <div
        className="app-shell-inner"
        ref={useCallback((el: HTMLDivElement | null) => { setDialogContainer(el); setToastRoot(el); }, [])}
      >
        <DesktopLifecycleMonitor showToast={toast} />
        <Suspense fallback={<TitleBarFallback />}>
          <TitleBar />
        </Suspense>
        {/* Window body: left tree | center conversation | right dock */}
        <main className="app-body">
          <Suspense fallback={<AppLayoutFallback />}>
            <ResizableWorkspaceLayout
              key={settingsOpen ? "settings" : "workspace"}
              sidebarCollapsed={sidebarCollapsed && !settingsOpen}
              settingsOpen={settingsOpen}
              sidebar={settingsOpen ? (
                <Suspense fallback={<SidebarFallback />}>
                  <SettingsSidebar
                    section={settingsSection}
                    onSectionChange={setSettingsSection}
                    onClose={closeSettings}
                  />
                </Suspense>
              ) : (
                <ProjectResourceSidebar
                  connectors={connectors}
                  collapsed={sidebarCollapsed && !settingsOpen}
                  onToggleCollapse={toggleSidebarCollapse}
                  onNewProject={() => useWorkspaceStore.getState().openProjectCreate()}
                  onOpenSettings={handleOpenSettings}
                  onOpenExtensions={() => {
                    setSidebarCollapsed(false);
                    openSettings("dlc");
                  }}
                />
              )}
              workspace={
                settingsOpen ? (
                  <section className="app-main app-main--settings">
                    <Suspense fallback={<LoadingState label="正在载入设置" />}>
                      <div className="app-main-scroll">
                        <SettingsPage section={settingsSection} showToast={toast} />
                      </div>
                    </Suspense>
                  </section>
                ) : (
                  <ConversationWorkspaceLayout
                    dockOpen={dockOpen}
                    conversation={(
                      <section className="app-main app-main--conversation">
                        <div className="app-main-scroll">
                          <ConversationCenter
                            onNewProject={() => useWorkspaceStore.getState().openProjectCreate()}
                          />
                        </div>
                      </section>
                    )}
                    dock={(
                      <Suspense fallback={<WorkspaceDockFallback />}>
                        <WorkspaceDock
                          activeConversationId={activeConversationId}
                          showToast={toast}
                        />
                      </Suspense>
                    )}
                  />
                )
              }
            />
          </Suspense>

          <Suspense fallback={null}>
            <ProjectCreateDialog />
          </Suspense>

          {showCommandPalette && (
            <Suspense fallback={null}>
              <AppCommandPalette
                showSmartQueryHome={showSmartQueryHome}
                showProjectOverview={() => useWorkspaceStore.getState().showProjectOverview()}
                openConversation={openConversationFromPalette}
                openSettings={openSettings}
                onClose={() => setShowCommandPalette(false)}
              />
            </Suspense>
          )}

        </main>
      </div>
    </div>
  );
}
