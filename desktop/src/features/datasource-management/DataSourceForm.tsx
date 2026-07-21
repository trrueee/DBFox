import { Database, Eye, EyeOff, FileCode2, Network, Server, ShieldCheck, Sparkles } from "lucide-react";
import { useState, type ChangeEvent } from "react";
import { useForm, useWatch, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import {
  SettingsActionBar,
  SettingsContent,
  SettingsSection,
  SettingsStatus,
  SettingsToggle,
} from "../../components/settings";
import { Button, Input, Select } from "../../components/ui";
import type { ActionState, ConnectionTestResultState, DatasourceFormState, PageMode } from "./formState";
import { SchemaSyncPanel } from "./SchemaSyncPanel";
import { datasourceFormSchema } from "./datasourceFormSchema";
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
  { id: "mysql", label: "MySQL", Icon: Database, port: 3306 },
  { id: "postgresql", label: "PostgreSQL", Icon: Server, port: 5432 },
  { id: "sqlite", label: "SQLite", Icon: FileCode2, port: 0 },
];

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
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({});

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

  const secretInput = (
    key: keyof DatasourceFormState,
    id: string,
    placeholder?: string,
  ) => {
    const visible = Boolean(visibleSecrets[id]);
    return (
      <div className="ds-form-secret-field">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          {...inputProps(key)}
          placeholder={placeholder}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="ds-form-secret-toggle"
          aria-label={visible ? "隐藏密码" : "显示密码"}
          title={visible ? "隐藏密码" : "显示密码"}
          onClick={() => setVisibleSecrets((current) => ({ ...current, [id]: !visible }))}
        >
          {visible ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
        </Button>
      </div>
    );
  };

  const status = validationError || formError ? (
    <SettingsStatus tone="danger" label={validationError || formError} />
  ) : testResult.status !== "idle" ? (
    <SettingsStatus
      tone={testResult.status === "success" ? "success" : testResult.status === "testing" ? "loading" : "danger"}
      label={testResult.message}
    />
  ) : (
    <span className="ds-form-action-hint">建议先测试连接，再保存并同步表结构。</span>
  );

  return (
    <form onSubmit={handleSubmit(submitValidForm)} className="hifi-card hifi-datasource-form ds-form settings-form">
      <header className="ds-form-intro">
        <div>
          <h3 className="hifi-card-title">{mode === "create" ? "建立数据连接" : "编辑数据连接"}</h3>
          <p>{mode === "create" ? "填写连接信息后，DBFox 会测试连接并读取数据库结构。" : "更新后可重新测试连接，确认凭据和网络配置有效。"}</p>
        </div>
        <span className="ds-form-intro__badge">{isSqlite ? "本地文件" : "远程数据库"}</span>
      </header>

      <div className="ds-form-scroll">
        <SettingsContent className="ds-form-content">
          <SettingsSection
            icon={Database}
            title="基础连接"
            description="选择数据库类型并填写访问地址与认证信息。"
          >
            <div className="ds-form-field">
              <label className="settings-field__label">数据库类型</label>
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
                      <item.Icon size={16} strokeWidth={1.75} aria-hidden="true" />
                      <span>{item.label}</span>
                    </Button>
                  );
                })}
              </div>
            </div>

            {isSqlite ? (
              <div className="ds-form-grid ds-form-grid--two">
                <div className="ds-form-field">
                  <label className="settings-field__label" htmlFor="ds-name">连接名称</label>
                  <Input id="ds-name" {...inputProps("name")} placeholder="例：本地 SQLite 数据库" />
                </div>
                <div className="ds-form-field">
                  <label className="settings-field__label" htmlFor="ds-sqlite-path">SQLite 数据库文件绝对路径</label>
                  <Input id="ds-sqlite-path" {...inputProps("database_name")} placeholder="C:\Users\...\mydb.sqlite" />
                </div>
              </div>
            ) : (
              <>
                <div className="ds-form-grid ds-form-grid--two">
                  <div className="ds-form-field">
                    <label className="settings-field__label" htmlFor="ds-name">连接名称</label>
                    <Input id="ds-name" {...inputProps("name")} placeholder="例：生产只读库" />
                  </div>
                  <div className="ds-form-field">
                    <label className="settings-field__label" htmlFor="ds-host">主机地址</label>
                    <Input id="ds-host" {...inputProps("host")} placeholder="db.example.com" autoComplete="url" />
                  </div>
                </div>
                <div className="ds-form-grid ds-form-grid--connection">
                  <div className="ds-form-field">
                    <label className="settings-field__label" htmlFor="ds-port">端口</label>
                    <Input id="ds-port" type="number" {...numberInputProps("port", 3306)} />
                  </div>
                  <div className="ds-form-field">
                    <label className="settings-field__label" htmlFor="ds-database">数据库名</label>
                    <Input id="ds-database" {...inputProps("database_name")} />
                  </div>
                  <div className="ds-form-field">
                    <label className="settings-field__label" htmlFor="ds-username">用户名</label>
                    <Input id="ds-username" {...inputProps("username")} autoComplete="username" />
                  </div>
                </div>
                <div className="ds-form-field">
                  <label className="settings-field__label" htmlFor="ds-password">密码</label>
                  {secretInput("password", "ds-password", mode === "edit" ? "留空则不修改" : "输入数据库密码")}
                  <p className="settings-field__message">凭据进入系统安全存储，不写入会话、日志或工件。</p>
                </div>
              </>
            )}
          </SettingsSection>

          <SettingsSection
            icon={ShieldCheck}
            title="访问边界"
            description="标记环境并限制 DBFox 对这个数据源的操作范围。"
          >
            <div className="ds-form-grid ds-form-grid--two ds-form-grid--access">
              <div className="ds-form-field">
                <label className="settings-field__label" htmlFor="ds-env">环境标签</label>
                <Select id="ds-env" value={values.env} onChange={(event) => setField("env", event.target.value)}>
                  <option value="dev">开发环境</option>
                  <option value="test">测试环境</option>
                  <option value="prod">生产环境</option>
                </Select>
              </div>
              <SettingsToggle
                checked={values.is_read_only}
                onCheckedChange={(checked) => setField("is_read_only", checked)}
                label="只读模式"
                description="阻止写入类操作，适合生产库和分析账号。"
              />
            </div>
          </SettingsSection>

          {!isSqlite ? (
            <SettingsSection
              icon={Network}
              title="安全与网络"
              description="仅在需要隧道或证书认证时开启对应能力。"
            >
              <SettingsToggle
                checked={values.ssh_enabled}
                onCheckedChange={(checked) => setField("ssh_enabled", checked)}
                label="SSH 隧道"
                description="通过跳板机建立加密隧道后再访问数据库。"
              />
              {values.ssh_enabled ? (
                <div className="ds-form-nested-panel" aria-label="SSH 隧道配置">
                  <div className="ds-form-grid ds-form-grid--ssh">
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-host">SSH 主机</label>
                      <Input id="ds-ssh-host" {...inputProps("ssh_host")} />
                    </div>
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-port">SSH 端口</label>
                      <Input id="ds-ssh-port" type="number" {...numberInputProps("ssh_port", 22)} />
                    </div>
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-username">SSH 用户名</label>
                      <Input id="ds-ssh-username" {...inputProps("ssh_username")} autoComplete="username" />
                    </div>
                  </div>
                  <div className="ds-form-grid ds-form-grid--two">
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-password">SSH 密码</label>
                      {secretInput("ssh_password", "ds-ssh-password")}
                    </div>
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-pkey-path">SSH 私钥路径</label>
                      <Input id="ds-ssh-pkey-path" {...inputProps("ssh_pkey_path")} />
                    </div>
                  </div>
                  {values.ssh_pkey_path ? (
                    <div className="ds-form-field">
                      <label className="settings-field__label" htmlFor="ds-ssh-pkey-passphrase">私钥密码</label>
                      {secretInput("ssh_pkey_passphrase", "ds-ssh-pkey-passphrase")}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {isMysql ? (
                <>
                  <SettingsToggle
                    checked={values.ssl_enabled}
                    onCheckedChange={(checked) => setField("ssl_enabled", checked)}
                    label="MySQL SSL/TLS"
                    description="使用 CA 和客户端证书校验数据库连接。"
                  />
                  {values.ssl_enabled ? (
                    <div className="ds-form-nested-panel" aria-label="MySQL SSL/TLS 配置">
                      <div className="ds-form-field">
                        <label className="settings-field__label" htmlFor="ds-ssl-ca-path">CA 证书路径</label>
                        <Input id="ds-ssl-ca-path" {...inputProps("ssl_ca_path")} />
                      </div>
                      <div className="ds-form-grid ds-form-grid--two">
                        <div className="ds-form-field">
                          <label className="settings-field__label" htmlFor="ds-ssl-cert-path">客户端证书</label>
                          <Input id="ds-ssl-cert-path" {...inputProps("ssl_cert_path")} />
                        </div>
                        <div className="ds-form-field">
                          <label className="settings-field__label" htmlFor="ds-ssl-key-path">客户端私钥</label>
                          <Input id="ds-ssl-key-path" {...inputProps("ssl_key_path")} />
                        </div>
                      </div>
                      <SettingsToggle
                        checked={values.ssl_verify_identity}
                        onCheckedChange={(checked) => setField("ssl_verify_identity", checked)}
                        label="校验证书主机名"
                        description="确认证书中的主机名与目标数据库一致。"
                        compact
                      />
                    </div>
                  ) : null}
                </>
              ) : null}
            </SettingsSection>
          ) : null}

          <SettingsSection
            icon={Sparkles}
            title="数据能力"
            description="控制结构同步时是否生成帮助 Agent 理解业务的数据语义。"
          >
            <SchemaSyncPanel
              checked={syncAiEnrich}
              onChange={onSyncAiEnrichChange}
              disabled={actionsDisabled}
            />
          </SettingsSection>
        </SettingsContent>
      </div>

      <SettingsActionBar status={status}>
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleSubmit(testValidForm)()}
          disabled={actionsDisabled || testResult.status === "testing"}
        >
          {testResult.status === "testing" ? "正在测试…" : "测试连接"}
        </Button>
        <Button type="submit" disabled={actionsDisabled || testResult.status === "testing"}>
          {actionState === "saving" ? "正在保存…" : mode === "create" ? "保存并同步表结构" : "保存修改"}
        </Button>
      </SettingsActionBar>
    </form>
  );
};

function firstFormError(errors: FieldErrors<DatasourceFormState>) {
  for (const value of Object.values(errors as Record<string, { message?: unknown }>)) {
    if (typeof value?.message === "string") return value.message;
  }
  return "";
}
