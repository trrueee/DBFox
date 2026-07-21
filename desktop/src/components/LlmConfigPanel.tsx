import { useState, type ChangeEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { AlertCircle, CheckCircle2, Cpu, Eye, EyeOff, Server, Zap } from "lucide-react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import {
  SettingsActionBar,
  SettingsContent,
  SettingsField,
  SettingsSection,
  SettingsStatus,
} from "./settings";
import type { LlmConfigDraft } from "../lib/api/types";
import {
  DEFAULT_LLM_API_BASE,
  LLM_MODEL_PRESETS,
  applyModelPresetSelection,
  findModelPreset,
} from "../lib/llmPresets";
import "./LlmConfigPanel.css";

interface LlmConfigPanelProps {
  config: LlmConfigDraft;
  onChange: (partial: Partial<LlmConfigDraft>) => void;
  onSave?: () => void | Promise<void>;
  onTestConnection?: () => boolean | void | Promise<boolean | void>;
  saved?: boolean;
  variant?: "dialog" | "page";
  chrome?: "page" | "workspace";
}

const llmConfigSchema = z.object({
  credentialId: z.string(),
  apiKey: z.string(),
  apiBase: z.string().trim().refine((value) => value === "" || isHttpUrl(value), {
    message: "API Base URL 必须是有效的 http(s) 地址",
  }),
  modelName: z.string(),
});

export function LlmConfigPanel({
  config,
  onChange,
  onSave,
  onTestConnection,
  saved = false,
  variant = "page",
  chrome = "page",
}: LlmConfigPanelProps) {
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testState, setTestState] = useState<"idle" | "success" | "error">("idle");
  const {
    formState,
    handleSubmit,
    register,
    setValue,
    control,
  } = useForm<LlmConfigDraft>({
    values: config,
    mode: "onChange",
    resolver: zodResolver(llmConfigSchema),
  });
  const values = useWatch({ control }) as LlmConfigDraft;
  const presetValues = LLM_MODEL_PRESETS.map((m) => m.value);
  const isCustomModel = Boolean(values.modelName) && !presetValues.includes(values.modelName);
  const activePreset = findModelPreset(values.modelName);
  const embeddedWorkspace = chrome === "workspace";

  const applyConfigPatch = (partial: Partial<LlmConfigDraft>) => {
    for (const [key, value] of Object.entries(partial) as Array<[keyof LlmConfigDraft, string]>) {
      setValue(key, value, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
    }
    onChange(partial);
  };

  const inputProps = (key: keyof LlmConfigDraft) => {
    const field = register(key);
    return {
      ...field,
      value: values[key] ?? "",
      onChange: (event: ChangeEvent<HTMLInputElement>) => {
        field.onChange(event);
        onChange({ [key]: event.target.value });
      },
    };
  };

  const submitValidConfig = async () => {
    if (variant === "page") {
      setSaving(true);
      try {
        await onSave?.();
      } finally {
        setSaving(false);
      }
    }
  };

  const testValidConfig = async () => {
    if (!onTestConnection) return;
    setTesting(true);
    setTestState("idle");
    try {
      const result = await onTestConnection();
      setTestState(result === false ? "error" : "success");
    } catch {
      setTestState("error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit(submitValidConfig)}
      className={variant === "page" ? `llm-settings-form hifi-settings-page${embeddedWorkspace ? " hifi-settings-page--workspace" : ""}` : "llm-settings-form llm-settings-form--dialog hifi-settings-dialog-body"}
    >
      {variant === "page" && !embeddedWorkspace ? (
        <header className="llm-settings-intro hifi-settings-page-header">
          <div className="llm-settings-intro__icon hifi-settings-page-icon">
            <Zap size={16} />
          </div>
          <div>
            <h2 className="hifi-settings-page-title">LLM 配置</h2>
            <p className="hifi-settings-page-desc">
              配置智能问数使用的模型服务。凭据进入系统安全存储，不写入会话、日志或工件。
            </p>
          </div>
        </header>
      ) : null}

      <div className="llm-settings-scroll hifi-settings-body">
        <SettingsContent className="llm-settings-content">
        <SettingsSection
          icon={Cpu}
          title="LLM 服务配置"
          description="连接 OpenAI 兼容端点，包括 OpenAI、Qwen、DeepSeek 和 OpenRouter。"
        >

        <SettingsField label="API Key" htmlFor="llm-api-key" hint="凭据由系统安全存储管理，不会进入 Agent 上下文。">
          <div className="hifi-settings-secret-field">
            <input
              id="llm-api-key"
              type={showKey ? "text" : "password"}
              autoComplete="new-password"
              placeholder="输入 LLM API Key"
              {...inputProps("apiKey")}
              className="hifi-settings-input hifi-settings-input--secret hifi-settings-input--mono"
            />
            <button
              type="button"
              onClick={() => setShowKey((p) => !p)}
              className="hifi-settings-eye-btn"
              aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}
              title={showKey ? "隐藏 API Key" : "显示 API Key"}
            >
              {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </SettingsField>

        <SettingsField label="API Base URL" htmlFor="llm-api-base"
          hint={activePreset ? `已匹配 ${activePreset.label} 的推荐端点，可手动覆盖。` : "填写完整的 http(s) API 地址。"}
          error={formState.errors.apiBase?.message}>
          <input
            id="llm-api-base"
            type="text"
            autoComplete="url"
            placeholder={DEFAULT_LLM_API_BASE}
            aria-invalid={Boolean(formState.errors.apiBase)}
            {...inputProps("apiBase")}
            className="hifi-settings-input hifi-settings-input--mono"
          />
        </SettingsField>

        <SettingsField label="模型" htmlFor="llm-model"
          hint={isCustomModel ? "使用自定义模型名称" : activePreset ? `${activePreset.label} · ${activePreset.provider}` : undefined}>
          <div className="hifi-model-chips">
            {LLM_MODEL_PRESETS.filter((m) => m.value !== "").map((m) => {
              const active = values.modelName === m.value;
              return (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => {
                    if (active) {
                      applyConfigPatch({ modelName: "" });
                    } else {
                      applyConfigPatch(applyModelPresetSelection(m.value, values.apiBase));
                    }
                  }}
                  className={`hifi-model-chip${active ? " active" : ""}`}
                  title={m.apiBase}
                >
                  {active ? <CheckCircle2 size={10} /> : null}
                  {m.label}
                </button>
              );
            })}
          </div>
          <input
            id="llm-model"
            placeholder="或输入自定义模型名称…"
            value={isCustomModel ? values.modelName : ""}
            onChange={(e) => {
              const name = e.target.value;
              if (!name) {
                applyConfigPatch({ modelName: "" });
                return;
              }
              applyConfigPatch({
                modelName: name,
                apiBase: resolveApiBaseForCustomInput(name, values.apiBase),
              });
            }}
            className="hifi-settings-input hifi-settings-input-compact hifi-settings-input--mono hifi-settings-input--custom-model"
          />
        </SettingsField>

        </SettingsSection>

        <SettingsSection icon={Server} title="当前配置" description="保存前确认凭据、端点和模型选择。">
        <div className="hifi-settings-status-list">
          <div className="hifi-settings-status-row">
            <span>API Key</span>
            {values.apiKey ? (
              <Badge variant="success" className="hifi-settings-status-badge">
                <CheckCircle2 size={9} />已配置
              </Badge>
            ) : (
              <Badge variant="secondary" className="hifi-settings-status-badge">
                <AlertCircle size={9} />未设置
              </Badge>
            )}
          </div>
          <div className="hifi-settings-status-row">
            <span>Endpoint</span>
            <span className="hifi-settings-mono hifi-settings-status-value">
              {values.apiBase || DEFAULT_LLM_API_BASE}
            </span>
          </div>
          <div className="hifi-settings-status-row">
            <span>Model</span>
            <span className="hifi-settings-mono">{values.modelName || "自动检测"}</span>
          </div>
        </div>

        {saved ? (
          <SettingsStatus tone="success" label="配置已保存" description="新的模型设置会用于后续智能问数。" />
        ) : null}
        </SettingsSection>
        </SettingsContent>
      </div>

      {variant === "page" && (onSave || onTestConnection) ? (
        <SettingsActionBar
          className="hifi-settings-footer"
          status={testing ? (
            <SettingsStatus tone="loading" label="正在测试模型连接…" />
          ) : testState === "success" ? (
            <SettingsStatus tone="success" label="模型连接可用" />
          ) : testState === "error" ? (
            <SettingsStatus tone="danger" label="模型连接不可用" description="请检查凭据、端点和模型名称。" />
          ) : (
            <span className="llm-settings-action-hint">测试连接不会保存当前修改。</span>
          )}
        >
          {onTestConnection ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={testing || saving}
              onClick={() => void handleSubmit(testValidConfig)()}
            >
              {testing ? "测试中…" : "测试连接"}
            </Button>
          ) : <span />}
          {onSave ? (
            <Button type="submit" size="sm" className="hifi-settings-submit-btn" disabled={testing || saving}>
              <CheckCircle2 size={13} />
              {saving ? "正在保存…" : "保存配置"}
            </Button>
          ) : null}
        </SettingsActionBar>
      ) : null}
    </form>
  );
}

function resolveApiBaseForCustomInput(modelName: string, currentApiBase: string): string {
  const preset = findModelPreset(modelName);
  if (preset) return preset.apiBase;
  const knownBases = LLM_MODEL_PRESETS.map((p) => p.apiBase);
  if (!currentApiBase || knownBases.includes(currentApiBase)) {
    return applyModelPresetSelection(modelName, currentApiBase).apiBase;
  }
  return currentApiBase;
}

function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
