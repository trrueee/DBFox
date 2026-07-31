import { useState, type ChangeEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { CheckCircle2, Eye, EyeOff } from "lucide-react";
import { Button } from "./ui/button";
import { Select } from "./ui/select";
import {
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
}

const AUTO_MODEL_VALUE = "__auto__";
const CUSTOM_MODEL_VALUE = "__custom__";

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
}: LlmConfigPanelProps) {
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testState, setTestState] = useState<"idle" | "success" | "error">("idle");
  const [customModelMode, setCustomModelMode] = useState(
    () => Boolean(config.modelName) && !LLM_MODEL_PRESETS.some((preset) => preset.value === config.modelName),
  );
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
  const activePreset = findModelPreset(values.modelName);
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
    setSaving(true);
    try {
      await onSave?.();
    } finally {
      setSaving(false);
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
      className="llm-settings-form"
    >
      <SettingsContent className="llm-settings-content">
        <SettingsSection
          title="服务连接"
          description="连接 OpenAI 兼容服务，凭据只保存在本机安全存储中。"
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

        </SettingsSection>

        <SettingsSection
          title="模型选择"
          description="选择默认模型；服务端使用自定义名称时可单独填写。"
        >
          <SettingsField
            label="默认模型"
            htmlFor="llm-model-preset"
            hint={
              customModelMode
                ? "使用服务端提供的模型标识。"
                : activePreset
                  ? `${activePreset.label} · ${activePreset.provider}`
                  : "自动检测可用模型。"
            }
          >
            <div className="llm-model-control">
              <Select
                id="llm-model-preset"
                aria-label="默认模型"
                value={customModelMode ? CUSTOM_MODEL_VALUE : values.modelName || AUTO_MODEL_VALUE}
                onChange={(event) => {
                  const selected = event.target.value;
                  if (selected === CUSTOM_MODEL_VALUE) {
                    setCustomModelMode(true);
                    applyConfigPatch({ modelName: "" });
                    return;
                  }
                  setCustomModelMode(false);
                  const modelName = selected === AUTO_MODEL_VALUE ? "" : selected;
                  applyConfigPatch(applyModelPresetSelection(modelName, values.apiBase));
                }}
                className="llm-model-select"
              >
                {LLM_MODEL_PRESETS.map((preset) => (
                  <option
                    key={preset.value || AUTO_MODEL_VALUE}
                    value={preset.value || AUTO_MODEL_VALUE}
                  >
                    {preset.label}
                  </option>
                ))}
                <option value={CUSTOM_MODEL_VALUE}>自定义模型…</option>
              </Select>
              {customModelMode ? (
                <input
                  id="llm-model-custom"
                  aria-label="自定义模型名称"
                  placeholder="输入模型名称，例如 gpt-4.1"
                  value={values.modelName}
                  onChange={(event) => {
                    const name = event.target.value;
                    applyConfigPatch({
                      modelName: name,
                      apiBase: resolveApiBaseForCustomInput(name, values.apiBase),
                    });
                  }}
                  className="hifi-settings-input hifi-settings-input--mono"
                />
              ) : null}
            </div>
          </SettingsField>

        {onSave || onTestConnection ? (
          <div className="llm-settings-inline-actions">
            <div className="llm-settings-inline-status" aria-live="polite">
              {testing ? (
                <SettingsStatus tone="loading" label="正在测试模型连接…" />
              ) : testState === "success" ? (
                <SettingsStatus tone="success" label="模型连接可用" />
              ) : testState === "error" ? (
                <SettingsStatus
                  tone="danger"
                  label="模型连接不可用"
                  description="请检查凭据、端点和模型名称。"
                />
              ) : (
                <span className="llm-settings-action-hint">测试连接不会保存当前修改。</span>
              )}
            </div>
            <div className="llm-settings-inline-buttons">
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
              ) : null}
              {onSave ? (
                <Button type="submit" size="sm" className="hifi-settings-submit-btn" disabled={testing || saving}>
                  <CheckCircle2 size={13} />
                  {saving ? "正在保存…" : "保存配置"}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}

        </SettingsSection>
      </SettingsContent>
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
