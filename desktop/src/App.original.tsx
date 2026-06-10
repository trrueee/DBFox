import { useCallback, useEffect, useState } from "react";
import { api } from "./lib/api";
import type { DataSource, Project, SchemaTable } from "./lib/api";
import { WorkbenchPage } from "./pages/WorkbenchPage";

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeDataSource, setActiveDataSource] = useState<DataSource | null>(null);
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [schemaTables, setSchemaTables] = useState<SchemaTable[]>([]);

  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingObjects, setLoadingObjects] = useState(false);

  const refreshProjects = useCallback(async () => {
    const items = await api.listProjects();
    setProjects(items);
    setActiveProject((current) => {
      if (!current) return items[0] ?? null;
      return items.find((item) => item.id === current.id) ?? items[0] ?? null;
    });
  }, []);

  const refreshDatasources = useCallback(async () => {
    try {
      setLoadingTree(true);
      const items = await api.listDatasources(activeProject?.id);
      setDatasources(items);
      if (items.length === 0) {
        setSchemaTables([]);
      }
      setActiveDataSource((current) => {
        if (!current) return items[0] ?? null;
        return items.find((item) => item.id === current.id) ?? items[0] ?? null;
      });
    } finally {
      setLoadingTree(false);
    }
  }, [activeProject?.id]);

  const refreshSchemaTables = useCallback(async (datasourceId: string) => {
    try {
      setLoadingObjects(true);
      const items = await api.listTables(datasourceId);
      setSchemaTables(items);
    } finally {
      setLoadingObjects(false);
    }
  }, []);

  const handleCreateProject = useCallback(async (name: string) => {
    const created = await api.createProject({ name });
    await refreshProjects();
    setActiveProject(created);
    setActiveDataSource(null);
    setSchemaTables([]);
  }, [refreshProjects]);

  const handleSelectDataSource = useCallback((ds: DataSource | null) => {
    setActiveDataSource(ds);
    if (!ds) {
      setSchemaTables([]);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await refreshProjects();
    })();
  }, [refreshProjects]);

  useEffect(() => {
    void (async () => {
      await refreshDatasources();
    })();
  }, [refreshDatasources]);

  useEffect(() => {
    if (!activeDataSource) return;
    void (async () => {
      await refreshSchemaTables(activeDataSource.id);
    })();
  }, [activeDataSource, refreshSchemaTables]);

  return (
    <div
      style={{
        height: "100vh",
        width: "100vw",
        background: "var(--bg-primary)",
        overflow: "hidden",
      }}
    >
      <WorkbenchPage
        projects={projects}
        activeProject={activeProject}
        datasources={datasources}
        activeDataSource={activeDataSource}
        setActiveDataSource={handleSelectDataSource}
        schemaTables={schemaTables}
        loadingObjects={loadingObjects}
        loadingTree={loadingTree}
        onRefreshSchemaTables={refreshSchemaTables}
        onRefreshDatasources={refreshDatasources}
        onCreateProject={handleCreateProject}
      />
    </div>
  );
}
