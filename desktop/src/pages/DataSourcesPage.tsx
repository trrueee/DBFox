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
import { useDatasourceState } from "../features/datasource/useDatasourceState";
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
import type { DataSource, SchemaSyncOptions, SchemaSyncResult } from "../lib/api";
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
  initialShowAddForm?: boolean;
  chrome?: "page" | "workspace";
}

const firstSchemaSyncIssue = (result: SchemaSyncResult | null): string | null => {
  return result?.aiEnrich?.errors?.[0] ?? null;
};

const aiEnrichSyncMessage = (result: SchemaSyncResult | null): { text: string; type: ToastType } | null => {
  const enrich = result?.aiEnrich;
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
  result: SchemaSyncResult | null,
): { message: string; type: ToastType; inline: string | null } => {
  const warning = firstSchemaSyncIssue(result);
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
  initialShowAddForm,
  chrome = "page",
}: DataSourcesPageProps) => {
  const toast = useToast();
  const {
    datasources,
    activeDatasource,
    setActiveDatasourceId,
    createDatasource,
    updateDatasource,
    deleteDatasource,
    syncSchema,
  } = useDatasourceState();

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
      if (activeDatasource && datasources.some((item) => item.id === activeDatasource.id)) return activeDatasource.id;
      return datasources[0]?.id || "";
    });
  }, [datasources, activeDatasource]);

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

  const cancelForm = () => {
    setMode("detail");
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
      const syncResult = await syncSchema(selectedId, schemaSyncOptions(syncAiEnrich));
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
        setTestResult({
          status: "success",
          message: result.message ?? "连接成功。",
          details: {
            serverVersion: result.serverVersion ?? undefined,
            readonly: result.readonly ?? undefined,
            tablesCount: result.tablesCount ?? undefined,
          },
        });
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
      const enrollment = await enrollDatasourceCredentials(nextForm as DatasourceFormShape);
      credentialLeaseId = enrollment.credentialLeaseId;
      const created = await createDatasource(
        buildDatasourceCreatePayload(
          nextForm as DatasourceFormShape,
          undefined,
          enrollment.references,
          enrollment.credentialLeaseId,
        ),
      );
      setMode("detail");
      setForm(emptyDatasourceForm());

      let syncResult: SchemaSyncResult | null = null;
      let syncError: unknown = null;
      try {
        syncResult = await syncSchema(created.id, schemaSyncOptions(syncAiEnrich));
      } catch (error: unknown) {
        syncError = error;
      }

      preferredIdRef.current = created.id;
      setSelectedId(created.id);
      setActiveDatasourceId(created.id);
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
      const enrollment = await enrollDatasourceCredentials(nextForm as DatasourceFormShape);
      credentialLeaseId = enrollment.credentialLeaseId;
      await updateDatasource(
        selected.id,
        buildDatasourceUpdatePayload(
          nextForm as DatasourceFormShape,
          enrollment.references,
          enrollment.credentialLeaseId,
        ),
      );
      setForm((current) => stripSensitiveDatasourceForm(current));
      setMode("detail");
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
      const res = await deleteDatasource(selected.id);
      if ("requires_confirmation" in res) {
        setConfirmDetails({
          confirm_token: res.confirm_token,
          impact_summary: res.impact_summary,
          expected_confirm_text: res.expected_confirm_text,
          onConfirm: async (text: string) => {
            await deleteDatasource(selected.id, {
              confirm_token: res.confirm_token,
              confirm_text: text,
            });
            setConfirmDetails(null);
            toast.toast("数据源已删除", "success");
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      toast.toast("数据源已删除", "success");
    } catch (err: unknown) {
      toast.toast(getUserErrorMessage(err, "删除数据源失败，请重试。"), "error");
    } finally {
      setActionState("idle");
    }
  };

  return (
    <div className={`hifi-tab-pane ds-page${chrome === "workspace" ? " ds-page--workspace" : ""}`}>
      {chrome === "workspace" ? mode === "detail" ? (
        <div className="ds-page-toolbar">
          <span className="ds-page-toolbar__meta">
            {datasources.length > 0 ? `${datasources.length} 个连接` : "尚未创建连接"}
          </span>
          <Button type="button" onClick={startCreate}>
            <Plus size={13} />
            新建连接
          </Button>
        </div>
      ) : null : (
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
        <div className={`ds-page-console${mode !== "detail" ? " ds-page-console--focused" : ""}`}>
          {mode === "detail" ? (
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
                  setActiveDatasourceId(datasource.id);
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
                onCancel={cancelForm}
              />
            )}
          </div>
        </div>
      )}

      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
