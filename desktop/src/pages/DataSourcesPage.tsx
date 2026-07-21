import { useEffect, useRef, useState } from "react";
import { Database, Plus } from "lucide-react";

import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";
import { useToast } from "../components/toastState";
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
import { getUserErrorMessage } from "../lib/api/client";
import type { DataSource, DataSourceActions, Project, SchemaSyncOptions, SchemaSyncResult } from "../lib/api";
import { stripSensitiveDatasourceForm } from "../lib/datasourceFormSecurity";
import {
  buildDatasourceCreatePayload,
  buildDatasourceTestPayload,
  buildDatasourceUpdatePayload,
  type DatasourceCredentialReferences,
  type DatasourceFormShape,
} from "../lib/datasourcePayload";
import { buildSchemaSyncOptions } from "../lib/llmConfig";
import {
  enrollCredentials,
  releaseCredentialLease,
  type CredentialEnrollmentInput,
} from "../lib/api/credentials";

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
  return buildSchemaSyncOptions(aiEnrich);
};

type DatasourceCredentialEnrollment = {
  references: DatasourceCredentialReferences;
  credentialLeaseId: string | null;
};

async function enrollDatasourceCredentials(
  form: DatasourceFormShape,
): Promise<DatasourceCredentialEnrollment> {
  const inputs: CredentialEnrollmentInput[] = [];
  if (form.password?.trim()) {
    inputs.push({ kind: "datasource_password", secret: form.password });
  }
  if (form.ssh_password?.trim()) {
    inputs.push({ kind: "ssh_password", secret: form.ssh_password });
  }
  if (form.ssh_pkey_passphrase?.trim()) {
    inputs.push({ kind: "ssh_key_passphrase", secret: form.ssh_pkey_passphrase });
  }
  const enrollment = await enrollCredentials(inputs);
  const enrolled = enrollment?.credentials ?? [];
  const password = enrolled.find((reference) => reference.kind === "datasource_password");
  const sshPassword = enrolled.find((reference) => reference.kind === "ssh_password");
  const sshPassphrase = enrolled.find((reference) => reference.kind === "ssh_key_passphrase");
  return {
    references: {
      ...(password ? { password_credential_id: password.id } : {}),
      ...(sshPassword ? { ssh_password_credential_id: sshPassword.id } : {}),
      ...(sshPassphrase ? { ssh_key_passphrase_credential_id: sshPassphrase.id } : {}),
    },
    credentialLeaseId: enrollment?.lease_id ?? null,
  };
}

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
    setFormError("");
    setTestResult((current) =>
      current.status === "idle" ? current : { status: "idle", message: "" },
    );
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
      toast.toast(getUserErrorMessage(err, "表结构同步失败，请重试。"), "error");
    } finally {
      setActionState("idle");
    }
  };

  const handleTestConnection = async (nextForm: DatasourceFormState = form) => {
    setFormError("");
    if (nextForm.db_type === "sqlite" && !nextForm.database_name) {
      setTestResult({ status: "error", message: "请先填写 SQLite 数据库文件路径。" });
      return;
    }
    if (nextForm.db_type !== "sqlite" && (!nextForm.host || !nextForm.database_name || !nextForm.username)) {
      setTestResult({ status: "error", message: "请先填写主机、数据库名和用户名。" });
      return;
    }
    setTestResult({ status: "testing", message: "正在测试连接…" });
    try {
      const enrollment = await enrollDatasourceCredentials(nextForm as DatasourceFormShape);
      try {
        const result = await api.testConnection(
          buildDatasourceTestPayload(
            nextForm as DatasourceFormShape,
            enrollment.references,
            enrollment.credentialLeaseId,
          ),
        );
        setTestResult({ status: "success", message: result.message ?? "连接成功。", details: result });
      } finally {
        if (enrollment.credentialLeaseId) {
          await releaseCredentialLease(enrollment.credentialLeaseId).catch(() => undefined);
        }
      }
    } catch (error: unknown) {
      setTestResult({ status: "error", message: getUserErrorMessage(error, "连接测试失败，请检查连接信息。") });
    }
  };

  const handleCreate = async (nextForm: DatasourceFormState = form) => {
    let credentialLeaseId: string | null = null;
    try {
      setActionState("saving");
      setFormError("");
      setTestResult({ status: "idle", message: "" });
      const createFn = createDatasource || api.createDatasource;
      const syncFn = syncSchema || api.syncSchema;
      const enrollment = await enrollDatasourceCredentials(nextForm as DatasourceFormShape);
      credentialLeaseId = enrollment.credentialLeaseId;
      const created = await createFn(
        buildDatasourceCreatePayload(
          nextForm as DatasourceFormShape,
          activeProject?.id,
          enrollment.references,
          enrollment.credentialLeaseId,
        ),
      );
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
        const message = getUserErrorMessage(syncError, "表结构同步失败，请重试。");
        setLastSyncFeedback(`表结构同步失败：${message}`);
        toast.toast(`数据源已保存，但表结构同步失败：${message}`, "warning");
        return;
      }

      const feedback = schemaSyncToast("数据源创建成功", syncResult);
      setLastSyncFeedback(feedback.inline);
      toast.toast(feedback.message, feedback.type);
    } catch (error: unknown) {
      setFormError(getUserErrorMessage(error, "保存失败，请重试。"));
    } finally {
      if (credentialLeaseId) {
        await releaseCredentialLease(credentialLeaseId).catch(() => undefined);
      }
      setActionState("idle");
    }
  };

  const handleUpdate = async (nextForm: DatasourceFormState = form) => {
    if (!selected) return;
    let credentialLeaseId: string | null = null;
    try {
      setActionState("saving");
      setFormError("");
      setTestResult({ status: "idle", message: "" });
      const updateFn = updateDatasource || api.updateDatasource;
      const enrollment = await enrollDatasourceCredentials(nextForm as DatasourceFormShape);
      credentialLeaseId = enrollment.credentialLeaseId;
      await updateFn(
        selected.id,
        buildDatasourceUpdatePayload(
          nextForm as DatasourceFormShape,
          enrollment.references,
          enrollment.credentialLeaseId,
        ),
      );
      setForm((current) => stripSensitiveDatasourceForm(current));
      setMode("detail");
      await loadDatasources(selected.id);
      await onRefreshDatasources();
      toast.toast("数据源已更新", "success");
    } catch (error: unknown) {
      setFormError(getUserErrorMessage(error, "更新失败，请重试。"));
    } finally {
      if (credentialLeaseId) {
        await releaseCredentialLease(credentialLeaseId).catch(() => undefined);
      }
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
      toast.toast(getUserErrorMessage(err, "删除数据源失败，请重试。"), "error");
    } finally {
      setActionState("idle");
    }
  };

  return (
    <div className={`hifi-tab-pane ds-page${chrome === "workspace" ? " ds-page--workspace" : ""}`}>
      {chrome === "workspace" ? (
        <div className="ds-page-toolbar">
          <span className="ds-page-toolbar__meta">
            {mode === "create" ? "正在创建连接" : datasources.length > 0 ? `${datasources.length} 个连接` : "尚未创建连接"}
          </span>
          {mode !== "create" ? (
            <Button type="button" onClick={startCreate}>
              <Plus size={13} />
              新建连接
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="ds-page-header">
          <div>
            <h2 className="ds-page-title">数据源管理</h2>
          </div>
          {mode !== "create" ? (
            <Button type="button" onClick={startCreate}>
              <Plus size={13} />
              新建连接
            </Button>
          ) : null}
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
        <div className={`ds-page-console${mode === "create" ? " ds-page-console--focused" : ""}`}>
          {mode !== "create" ? (
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
          ) : null}
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
