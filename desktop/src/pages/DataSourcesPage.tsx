import { useEffect, useRef, useState } from "react";
import { Database, Plus } from "lucide-react";

import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";
import { getStoredApiConfig } from "../components/SettingsDialog";
import { useToast } from "../components/Toast";
import { Button, EmptyState } from "../components/ui";
import {
  DataSourceDetail,
  DataSourceForm,
  DataSourceList,
} from "../features/datasource-management";
import "../features/datasource-management/DataSourceManagement.css";
import {
  emptyDatasourceForm,
  formFromDataSource,
  type ActionState,
  type ConnectionTestResultState,
  type DatasourceFormState,
  type PageMode,
  type ToastType,
} from "../features/datasource-management/formState";
import { api } from "../lib/api";
import type { DataSource, DataSourceActions, Project, SchemaSyncOptions, SchemaSyncResult } from "../lib/api";
import { stripSensitiveDatasourceForm } from "../lib/datasourceFormSecurity";
import {
  buildDatasourceCreatePayload,
  buildDatasourceTestPayload,
  buildDatasourceUpdatePayload,
  type DatasourceFormShape,
} from "../lib/datasourcePayload";

interface DataSourcesPageProps {
  onSelectDataSource: (ds: DataSource | null) => void;
  activeDataSource: DataSource | null;
  activeProject: Project | null;
  onRefreshDatasources: () => Promise<void>;
  initialShowAddForm?: boolean;
  datasources: DataSource[];
  actions?: DataSourceActions;
  chrome?: "page" | "workspace";
}

const firstSchemaSyncWarning = (result: unknown): string | null => {
  const syncResult = result as SchemaSyncResult | null | undefined;
  if (syncResult?.warnings?.length) return syncResult.warnings[0];
  return null;
};

const aiEnrichSyncMessage = (result: unknown): { text: string; type: ToastType } | null => {
  const syncResult = result as SchemaSyncResult | null | undefined;
  const enrich = syncResult?.aiEnrich;
  if (!enrich) return null;

  const count = Number(enrich.enriched_count || 0);
  if (enrich.ai_enriched) {
    return { text: `AI 语义增强 ${count} 张表`, type: "success" };
  }

  const reason = String(enrich.reason || "").trim();
  if (!reason || reason === "no structural changes") {
    return { text: "AI 语义增强无需更新", type: "info" };
  }
  return { text: `AI 语义增强未完成：${reason}`, type: "warning" };
};

const schemaSyncToast = (
  baseMessage: string,
  result: unknown,
): { message: string; type: ToastType; inline: string | null } => {
  const warning = firstSchemaSyncWarning(result);
  const enrich = aiEnrichSyncMessage(result);
  const type = warning || enrich?.type === "warning" ? "warning" : "success";
  const detail = warning || enrich?.text || "";
  return {
    message: detail ? `${baseMessage}；${detail}` : baseMessage,
    type,
    inline: enrich?.text || warning || null,
  };
};

const schemaSyncOptions = (aiEnrich: boolean): SchemaSyncOptions | undefined => {
  if (!aiEnrich) return undefined;
  const llm = getStoredApiConfig();
  const options: SchemaSyncOptions = { ai_enrich: true };
  const apiKey = llm.apiKey.trim();
  const apiBase = llm.apiBase.trim();
  const modelName = llm.modelName.trim();
  if (apiKey) options.api_key = apiKey;
  if (apiKey || modelName) {
    if (apiBase) options.api_base = apiBase;
    if (modelName) options.model_name = modelName;
  }
  return options;
};

export const DataSourcesPage = ({
  onSelectDataSource,
  activeDataSource,
  activeProject,
  onRefreshDatasources,
  initialShowAddForm,
  datasources,
  actions,
  chrome = "page",
}: DataSourcesPageProps) => {
  const toast = useToast();
  const createDatasource = actions?.createDatasource;
  const updateDatasource = actions?.updateDatasource;
  const deleteDatasource = actions?.deleteDatasource;
  const syncSchema = actions?.syncSchema;

  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<PageMode>(initialShowAddForm ? "create" : "detail");
  const [form, setForm] = useState<DatasourceFormState>(emptyDatasourceForm());
  const [search, setSearch] = useState("");
  const [formError, setFormError] = useState("");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [syncAiEnrich, setSyncAiEnrich] = useState(false);
  const [lastSyncFeedback, setLastSyncFeedback] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ConnectionTestResultState>({ status: "idle", message: "" });
  const [confirmDetails, setConfirmDetails] = useState<ConfirmationDetails | null>(null);
  const [prevInitialShowAddForm, setPrevInitialShowAddForm] = useState(initialShowAddForm);
  const preferredIdRef = useRef<string | null>(null);

  const selected = datasources.find((datasource) => datasource.id === selectedId) || null;

  const loadDatasources = async (preferredId?: string) => {
    if (preferredId) {
      preferredIdRef.current = preferredId;
    }
    await onRefreshDatasources();
  };

  if (initialShowAddForm !== prevInitialShowAddForm) {
    setPrevInitialShowAddForm(initialShowAddForm);
    if (initialShowAddForm) {
      setMode("create");
      setForm(emptyDatasourceForm());
      setFormError("");
      setTestResult({ status: "idle", message: "" });
    } else {
      setMode("detail");
    }
  }

  useEffect(() => {
    let preferredId: string | null = null;
    if (preferredIdRef.current !== null) {
      preferredId = preferredIdRef.current;
      preferredIdRef.current = null;
    }
    setSelectedId((current) => {
      if (preferredId !== null && datasources.some((item) => item.id === preferredId)) return preferredId;
      if (current && datasources.some((item) => item.id === current)) return current;
      if (activeDataSource && datasources.some((item) => item.id === activeDataSource.id)) return activeDataSource.id;
      return datasources[0]?.id || "";
    });
  }, [datasources, activeDataSource]);

  useEffect(() => {
    void onRefreshDatasources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const startCreate = () => {
    setMode("create");
    setForm(emptyDatasourceForm());
    setFormError("");
    setTestResult({ status: "idle", message: "" });
  };

  const startEdit = (datasource: DataSource) => {
    setMode("edit");
    setForm(formFromDataSource(datasource));
    setFormError("");
    setTestResult({ status: "idle", message: "" });
  };

  const updateForm = (key: keyof DatasourceFormState, value: string | number | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSyncSchema = async () => {
    if (!selectedId || actionState !== "idle") return;
    try {
      setActionState("syncing");
      const syncFn = syncSchema || api.syncSchema;
      const syncResult = await syncFn(selectedId, schemaSyncOptions(syncAiEnrich));
      await loadDatasources(selectedId);
      await onRefreshDatasources();
      const feedback = schemaSyncToast("表结构已同步", syncResult);
      setLastSyncFeedback(feedback.inline);
      toast.toast(feedback.message, feedback.type);
    } catch (err: unknown) {
      toast.toast((err as Error).message || "表结构同步失败", "error");
    } finally {
      setActionState("idle");
    }
  };

  const handleTestConnection = async (nextForm: DatasourceFormState = form) => {
    if (nextForm.db_type === "sqlite" && !nextForm.database_name) {
      setTestResult({ status: "error", message: "请先填写 SQLite 数据库文件路径。" });
      return;
    }
    if (nextForm.db_type !== "sqlite" && (!nextForm.host || !nextForm.database_name || !nextForm.username)) {
      setTestResult({ status: "error", message: "请先填写主机、数据库名和用户名。" });
      return;
    }
    setTestResult({ status: "testing", message: "正在测试连接..." });
    try {
      const result = await api.testConnection(buildDatasourceTestPayload(nextForm as DatasourceFormShape));
      setTestResult({ status: "success", message: result.message ?? "连接成功。", details: result });
    } catch (error: unknown) {
      setTestResult({ status: "error", message: (error as Error).message ?? "连接测试失败。" });
    }
  };

  const handleCreate = async (nextForm: DatasourceFormState = form) => {
    try {
      setActionState("saving");
      setFormError("");
      const createFn = createDatasource || api.createDatasource;
      const syncFn = syncSchema || api.syncSchema;
      const created = await createFn(buildDatasourceCreatePayload(nextForm as DatasourceFormShape, activeProject?.id));
      setMode("detail");
      setForm(emptyDatasourceForm());

      let syncResult: unknown = null;
      let syncError: unknown = null;
      try {
        syncResult = await syncFn(created.id, schemaSyncOptions(syncAiEnrich));
      } catch (error: unknown) {
        syncError = error;
      }

      await loadDatasources(created.id);
      await onRefreshDatasources();
      onSelectDataSource(created);
      if (syncError) {
        const message = (syncError as Error).message || "Schema 同步失败";
        setLastSyncFeedback(`Schema 同步失败：${message}`);
        toast.toast(`数据源已保存，但 Schema 同步失败：${message}`, "warning");
        return;
      }

      const feedback = schemaSyncToast("数据源创建成功", syncResult);
      setLastSyncFeedback(feedback.inline);
      toast.toast(feedback.message, feedback.type);
    } catch (error: unknown) {
      setFormError((error as Error).message ?? "保存失败。");
    } finally {
      setActionState("idle");
    }
  };

  const handleUpdate = async (nextForm: DatasourceFormState = form) => {
    if (!selected) return;
    try {
      setActionState("saving");
      setFormError("");
      const updateFn = updateDatasource || api.updateDatasource;
      await updateFn(selected.id, buildDatasourceUpdatePayload(nextForm as DatasourceFormShape));
      setForm((current) => stripSensitiveDatasourceForm(current));
      setMode("detail");
      await loadDatasources(selected.id);
      await onRefreshDatasources();
      toast.toast("数据源已更新", "success");
    } catch (error: unknown) {
      setFormError((error as Error).message ?? "更新失败。");
    } finally {
      setActionState("idle");
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    try {
      setActionState("deleting");
      const deleteFn = deleteDatasource || api.deleteDatasource;
      const res = await deleteFn(selected.id);
      const raw = res as Record<string, unknown> | null;
      if (raw && raw.requires_confirmation) {
        setConfirmDetails({
          confirm_token: raw.confirm_token as string,
          impact_summary: raw.impact_summary as string,
          expected_confirm_text: raw.expected_confirm_text as string,
          onConfirm: async (text: string) => {
            await deleteFn(selected.id, { token: raw.confirm_token as string, text });
            setConfirmDetails(null);
            await loadDatasources();
            await onRefreshDatasources();
            if (activeDataSource?.id === selected.id) onSelectDataSource(null);
            toast.toast("数据源已删除", "success");
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      await loadDatasources();
      await onRefreshDatasources();
      if (activeDataSource?.id === selected.id) onSelectDataSource(null);
      toast.toast("数据源已删除", "success");
    } catch (err: unknown) {
      toast.toast((err as Error).message || "删除数据源失败", "error");
    } finally {
      setActionState("idle");
    }
  };

  return (
    <div className={`hifi-tab-pane ds-page${chrome === "workspace" ? " ds-page--workspace" : ""}`}>
      {chrome === "workspace" ? (
        <div className="ds-page-toolbar">
          <span className="ds-page-toolbar__meta">
            {datasources.length > 0 ? `${datasources.length} 个连接` : "尚未创建连接"}
          </span>
          <Button type="button" onClick={startCreate}>
            <Plus size={13} />
            新建连接
          </Button>
        </div>
      ) : (
        <div className="ds-page-header">
          <div>
            <h2 className="ds-page-title">数据源管理</h2>
          </div>
          <Button type="button" onClick={startCreate}>
            <Plus size={13} />
            新建连接
          </Button>
        </div>
      )}

      {datasources.length === 0 && mode !== "create" ? (
        <EmptyState
          className="ds-page-empty"
          icon={<Database size={18} />}
          title="暂无数据源连接"
          description="添加一个数据库连接以开始使用"
          action={
            <Button type="button" onClick={startCreate}>
              <Plus size={13} />
              新建连接
            </Button>
          }
        />
      ) : (
        <div className="ds-page-console">
          <DataSourceList
            datasources={datasources}
            selectedId={selectedId}
            search={search}
            onSearchChange={setSearch}
            onSelect={(id) => {
              setMode("detail");
              setSelectedId(id);
            }}
          />
          <div className="ds-page-detail-shell">
            {mode === "detail" && (
              <DataSourceDetail
                selected={selected}
                actionState={actionState}
                syncAiEnrich={syncAiEnrich}
                lastSyncFeedback={lastSyncFeedback}
                onSyncAiEnrichChange={setSyncAiEnrich}
                onActivate={(datasource) => {
                  onSelectDataSource(datasource);
                  toast.toast(`已激活: ${datasource.name}`, "success");
                }}
                onEdit={startEdit}
                onSyncSchema={handleSyncSchema}
                onDelete={handleDelete}
              />
            )}
            {(mode === "create" || mode === "edit") && (
              <DataSourceForm
                mode={mode}
                form={form}
                formError={formError}
                testResult={testResult}
                actionState={actionState}
                syncAiEnrich={syncAiEnrich}
                onSyncAiEnrichChange={setSyncAiEnrich}
                updateForm={updateForm}
                onTestConnection={handleTestConnection}
                onSubmit={mode === "create" ? handleCreate : handleUpdate}
              />
            )}
          </div>
        </div>
      )}

      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
