import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { ChangeEvent } from "react";
import { useForm, useWatch, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { StatusIndicator } from "../../components/StatusIndicator";
import { Button, Input, Select } from "../../components/ui";
import type { ActionState, ConnectionTestResultState, DatasourceFormState, PageMode } from "./formState";
import { SchemaSyncPanel } from "./SchemaSyncPanel";
import "./DataSourceManagement.css";

interface DataSourceFormProps {
  mode: Exclude<PageMode, "detail">;
  form: DatasourceFormState;
  formError: string;
  testResult: ConnectionTestResultState;
  actionState: ActionState;
  syncAiEnrich: boolean;
  onSyncAiEnrichChange: (checked: boolean) => void;
  updateForm: (key: keyof DatasourceFormState, value: string | number | boolean) => void;
  onTestConnection: (form: DatasourceFormState) => void;
  onSubmit: (form: DatasourceFormState) => void;
}

const dbTypeOptions = [
  { id: "mysql", label: "MySQL", icon: "🐬", port: 3306 },
  { id: "postgresql", label: "PostgreSQL", icon: "🐘", port: 5432 },
  { id: "sqlite", label: "SQLite", icon: "📁", port: 0 },
];

const requiredMySqlFieldsMessage = "请完整填写连接名称、主机、数据库名和用户名。";
const requiredSqliteFieldsMessage = "请完整填写连接名称和数据库路径。";

export const datasourceFormSchema = z.object({
  db_type: z.string(),
  name: z.string(),
  host: z.string(),
  port: z.number().int().min(0).max(65535),
  database_name: z.string(),
  username: z.string(),
  password: z.string(),
  is_read_only: z.boolean(),
  env: z.string(),
  ssh_enabled: z.boolean(),
  ssh_host: z.string(),
  ssh_port: z.number().int().min(0).max(65535),
  ssh_username: z.string(),
  ssh_password: z.string(),
  ssh_pkey_path: z.string(),
  ssh_pkey_passphrase: z.string(),
  ssl_enabled: z.boolean(),
  ssl_ca_path: z.string(),
  ssl_cert_path: z.string(),
  ssl_key_path: z.string(),
  ssl_verify_identity: z.boolean(),
}).superRefine((value, context) => {
  if (value.db_type === "sqlite") {
    if (!value.name.trim() || !value.database_name.trim()) {
      context.addIssue({ code: "custom", path: ["name"], message: requiredSqliteFieldsMessage });
    }
    return;
  }

  if (!value.name.trim() || !value.host.trim() || !value.database_name.trim() || !value.username.trim()) {
    context.addIssue({ code: "custom", path: ["name"], message: requiredMySqlFieldsMessage });
  }
});

export const DataSourceForm = ({
  mode,
  form,
  formError,
  testResult,
  actionState,
  syncAiEnrich,
  onSyncAiEnrichChange,
  updateForm,
  onTestConnection,
  onSubmit,
}: DataSourceFormProps) => {
  const {
    clearErrors,
    formState,
    handleSubmit,
    register,
    setValue,
    control,
  } = useForm<DatasourceFormState>({
    values: form,
    resolver: zodResolver(datasourceFormSchema),
  });
  const values = useWatch({ control }) as DatasourceFormState;
  const validationError = firstFormError(formState.errors);
  const actionsDisabled = actionState !== "idle";
  const isSqlite = values.db_type === "sqlite";
  const isMysql = values.db_type === "mysql";

  const setField = <K extends keyof DatasourceFormState>(key: K, value: DatasourceFormState[K]) => {
    setValue(key, value as never, { shouldDirty: true, shouldTouch: true });
    updateForm(key, value);
  };

  const inputProps = (key: keyof DatasourceFormState) => {
    const field = register(key);
    return {
      ...field,
      value: String(values[key] ?? ""),
      onChange: (event: ChangeEvent<HTMLInputElement>) => setField(key, event.target.value as never),
    };
  };

  const numberInputProps = (key: keyof DatasourceFormState, fallback: number) => {
    const field = register(key, { valueAsNumber: true });
    return {
      ...field,
      value: Number(values[key] ?? fallback),
      onChange: (event: ChangeEvent<HTMLInputElement>) => {
        const nextValue = Number(event.target.value);
        setField(key, (Number.isFinite(nextValue) ? nextValue : fallback) as never);
      },
    };
  };

  const submitValidForm = (nextForm: DatasourceFormState) => {
    onSubmit(nextForm);
  };

  const testValidForm = (nextForm: DatasourceFormState) => {
    onTestConnection(nextForm);
  };

  return (
    <form onSubmit={handleSubmit(submitValidForm)} className="hifi-card hifi-datasource-form ds-form">
      <h3 className="hifi-card-title">{mode === "create" ? "新增数据源" : "编辑数据源"}</h3>

      <div className="ds-form-section">
        <label className="field-label ds-form-label">数据库类型</label>
        <div className="ds-form-db-grid">
          {dbTypeOptions.map((item) => {
            const active = values.db_type === item.id;
            return (
              <Button
                key={item.id}
                type="button"
                variant="outline"
                className={`ds-form-db-option${active ? " is-active" : ""}`}
                aria-pressed={active}
                onClick={() => {
                  setField("db_type", item.id);
                  setField("port", item.port);
                  clearErrors();
                }}
              >
                <span className="ds-form-db-option__icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </Button>
            );
          })}
        </div>
      </div>

      {isSqlite ? (
        <div className="ds-form-grid ds-form-grid--two">
          <div className="ds-form-field">
            <label className="field-label ds-form-label" htmlFor="ds-name">
              连接名称
            </label>
            <Input
              id="ds-name"
              {...inputProps("name")}
              placeholder="例：本地 SQLite 数据库"
            />
          </div>
          <div className="ds-form-field">
            <label className="field-label ds-form-label" htmlFor="ds-sqlite-path">
              SQLite 数据库文件绝对路径
            </label>
            <Input
              id="ds-sqlite-path"
              {...inputProps("database_name")}
              placeholder="C:\Users\...\mydb.sqlite"
            />
          </div>
        </div>
      ) : (
        <>
          <div className="ds-form-grid ds-form-grid--two">
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-name">
                连接名称
              </label>
              <Input
                id="ds-name"
                {...inputProps("name")}
                placeholder="例：生产只读库"
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-host">
                主机地址
              </label>
              <Input
                id="ds-host"
                {...inputProps("host")}
                placeholder="db.example.com"
              />
            </div>
          </div>

          <div className="ds-form-grid ds-form-grid--connection">
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-port">
                端口
              </label>
              <Input
                id="ds-port"
                type="number"
                {...numberInputProps("port", 3306)}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-database">
                数据库名
              </label>
              <Input
                id="ds-database"
                {...inputProps("database_name")}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-username">
                用户名
              </label>
              <Input
                id="ds-username"
                {...inputProps("username")}
              />
            </div>
          </div>

          <div className="ds-form-field ds-form-section">
            <label className="field-label ds-form-label" htmlFor="ds-password">
              密码
            </label>
            <Input
              id="ds-password"
              type="password"
              {...inputProps("password")}
              placeholder="留空则不修改"
            />
          </div>
        </>
      )}

      <div className="ds-form-inline-row">
        <div className="ds-form-field ds-form-grow-field">
          <label className="field-label ds-form-label" htmlFor="ds-env">
            环境标签
          </label>
          <Select id="ds-env" value={values.env} onChange={(event) => setField("env", event.target.value)}>
            <option value="dev">💻 开发环境 (DEV)</option>
            <option value="test">🔬 测试环境 (TEST)</option>
            <option value="prod">🚨 生产环境 (PROD)</option>
          </Select>
        </div>
        <div className="ds-form-checkbox-align">
          <label className="field-label ds-form-checkbox-row">
            <input
              type="checkbox"
              className="ds-form-checkbox"
              checked={values.is_read_only}
              onChange={(event) => setField("is_read_only", event.target.checked)}
            />
            启用只读模式
          </label>
        </div>
      </div>

      {!isSqlite && (
        <div className="ds-form-section ds-form-section--divided">
          <label className="field-label ds-form-checkbox-row">
            <input
              type="checkbox"
              className="ds-form-checkbox"
              checked={values.ssh_enabled}
              onChange={(event) => setField("ssh_enabled", event.target.checked)}
            />
            启用 SSH 隧道连接
          </label>
        </div>
      )}

      {!isSqlite && values.ssh_enabled && (
        <div className="ds-form-nested-panel">
          <div className="ds-form-grid ds-form-grid--ssh">
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-host">
                SSH 主机
              </label>
              <Input
                id="ds-ssh-host"
                {...inputProps("ssh_host")}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-port">
                SSH 端口
              </label>
              <Input
                id="ds-ssh-port"
                type="number"
                {...numberInputProps("ssh_port", 22)}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-username">
                SSH 用户名
              </label>
              <Input
                id="ds-ssh-username"
                {...inputProps("ssh_username")}
              />
            </div>
          </div>
          <div className="ds-form-grid ds-form-grid--two">
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-password">
                SSH 密码
              </label>
              <Input
                id="ds-ssh-password"
                type="password"
                {...inputProps("ssh_password")}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-pkey-path">
                SSH 私钥路径
              </label>
              <Input
                id="ds-ssh-pkey-path"
                {...inputProps("ssh_pkey_path")}
              />
            </div>
          </div>
          {values.ssh_pkey_path && (
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssh-pkey-passphrase">
                私钥密码
              </label>
              <Input
                id="ds-ssh-pkey-passphrase"
                type="password"
                {...inputProps("ssh_pkey_passphrase")}
              />
            </div>
          )}
        </div>
      )}

      {isMysql && (
        <div className="ds-form-section ds-form-section--divided">
          <label className="field-label ds-form-checkbox-row">
            <input
              type="checkbox"
              className="ds-form-checkbox"
              checked={values.ssl_enabled}
              onChange={(event) => setField("ssl_enabled", event.target.checked)}
            />
            启用 MySQL SSL/TLS
          </label>
        </div>
      )}

      {isMysql && values.ssl_enabled && (
        <div className="ds-form-nested-panel">
          <div className="ds-form-field">
            <label className="field-label ds-form-label" htmlFor="ds-ssl-ca-path">
              CA 证书路径
            </label>
            <Input
              id="ds-ssl-ca-path"
              {...inputProps("ssl_ca_path")}
            />
          </div>
          <div className="ds-form-grid ds-form-grid--two">
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssl-cert-path">
                客户端证书
              </label>
              <Input
                id="ds-ssl-cert-path"
                {...inputProps("ssl_cert_path")}
              />
            </div>
            <div className="ds-form-field">
              <label className="field-label ds-form-label" htmlFor="ds-ssl-key-path">
                客户端私钥
              </label>
              <Input
                id="ds-ssl-key-path"
                {...inputProps("ssl_key_path")}
              />
            </div>
          </div>
          <label className="ds-form-checkbox-row ds-form-checkbox-row--compact">
            <input
              type="checkbox"
              className="ds-form-checkbox ds-form-checkbox--compact"
              checked={values.ssl_verify_identity}
              onChange={(event) => setField("ssl_verify_identity", event.target.checked)}
            />
            校验证书主机名
          </label>
        </div>
      )}

      {(validationError || formError) && (
        <div className="ds-form-error">
          <StatusIndicator type="error" label={validationError || formError} />
        </div>
      )}

      {testResult.status !== "idle" && (
        <div className={`ds-form-test-result ds-form-test-result--${testResult.status}`}>
          <div className="ds-form-test-result__content">
            {testResult.status === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            {testResult.message}
          </div>
        </div>
      )}

      <div className="ds-form-sync-section">
        <SchemaSyncPanel
          checked={syncAiEnrich}
          onChange={onSyncAiEnrichChange}
          disabled={actionsDisabled}
        />
      </div>

      <div className="ds-form-actions">
        <Button type="button" variant="outline" onClick={() => void handleSubmit(testValidForm)()} disabled={actionsDisabled}>
          测试连接
        </Button>
        <Button type="submit" disabled={actionsDisabled}>
          {actionState === "saving" ? "保存中..." : mode === "create" ? "保存并同步 Schema" : "保存修改"}
        </Button>
      </div>
    </form>
  );
};

function firstFormError(errors: FieldErrors<DatasourceFormState>) {
  for (const value of Object.values(errors as Record<string, { message?: unknown }>)) {
    if (typeof value?.message === "string") return value.message;
  }
  return "";
}
