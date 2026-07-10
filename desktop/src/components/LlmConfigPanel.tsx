import { useState, type ChangeEvent, type ComponentType, type ReactNode } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
  Key, Globe, Layers, CheckCircle2, AlertCircle, Eye, EyeOff, Cpu, Server, Zap,
} from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
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
  onSave?: () => void;
  onTestConnection?: () => void | Promise<void>;
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

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="hifi-settings-section-head">
      <div className="hifi-settings-section-icon">
        <Icon size={14} />
      </div>
      <div>
        <h3 className="hifi-settings-section-title">{title}</h3>
        <p className="hifi-settings-section-subtitle">{subtitle}</p>
      </div>
    </div>
  );
}

function FieldRow({
  icon: Icon,
  label,
  htmlFor,
  hint,
  children,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="hifi-settings-field">
      <Label htmlFor={htmlFor} className="hifi-settings-label">
        <Icon size={11} />
        {label}
      </Label>
      {children}
      {hint ? <p className="hifi-settings-hint">{hint}</p> : null}
    </div>
  );
}

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
  const validationMessage = formState.errors.apiBase?.message || formState.errors.apiKey?.message || formState.errors.modelName?.message || "";

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

  const submitValidConfig = () => {
    if (variant === "page") {
      onSave?.();
    }
  };

  const testValidConfig = async () => {
    if (!onTestConnection) return;
    setTesting(true);
    try {
      await onTestConnection();
    } finally {
      setTesting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit(submitValidConfig)}
      className={variant === "page" ? `hifi-settings-page${embeddedWorkspace ? " hifi-settings-page--workspace" : ""}` : "hifi-settings-dialog-body"}
    >
      {variant === "page" && !embeddedWorkspace ? (
        <header className="hifi-settings-page-header">
          <div className="hifi-settings-page-icon">
            <Zap size={16} />
          </div>
          <div>
            <h2 className="hifi-settings-page-title">LLM 配置</h2>
            <p className="hifi-settings-page-desc">
              配置智能问数底层大语言模型的连接参数。凭证仅保存在本地，不会上传至第三方服务器。
            </p>
          </div>
        </header>
      ) : null}

      <div className="hifi-settings-body">
        <SectionHeader
          icon={Cpu}
          title="LLM 服务配置"
          subtitle="连接 OpenAI 兼容的 API 端点（OpenAI / Qwen / DeepSeek / OpenRouter 等）"
        />

        <FieldRow icon={Key} label="API Key" htmlFor="llm-api-key" hint="接口密钥，仅存储在本地浏览器。">
          <div className="hifi-settings-secret-field">
            <input
              id="llm-api-key"
              type={showKey ? "text" : "password"}
              placeholder="sk-••••••••••••••••"
              {...inputProps("apiKey")}
              className="hifi-settings-input hifi-settings-input--secret hifi-settings-input--mono"
            />
            <button
              type="button"
              onClick={() => setShowKey((p) => !p)}
              className="hifi-settings-eye-btn"
              tabIndex={-1}
            >
              {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </FieldRow>

        <FieldRow icon={Globe} label="API Base URL" htmlFor="llm-api-base"
          hint={activePreset ? `已匹配 ${activePreset.label} 的推荐端点，可手动覆盖` : undefined}>
          <input
            id="llm-api-base"
            type="text"
            placeholder={DEFAULT_LLM_API_BASE}
            aria-invalid={Boolean(formState.errors.apiBase)}
            {...inputProps("apiBase")}
            className="hifi-settings-input hifi-settings-input--mono"
          />
        </FieldRow>

        <FieldRow icon={Layers} label="模型" htmlFor="llm-model"
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
        </FieldRow>

        {validationMessage ? (
          <div className="hifi-settings-validation" role="alert">
            <AlertCircle size={12} />
            {validationMessage}
          </div>
        ) : null}

        <div className="hifi-settings-divider" />

        <SectionHeader icon={Server} title="连接状态" subtitle="当前配置摘要" />
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
          <div className="hifi-settings-saved">
            <CheckCircle2 size={12} />
            配置已保存
          </div>
        ) : null}
      </div>

      {variant === "page" && (onSave || onTestConnection) ? (
        <footer className="hifi-settings-footer">
          {onTestConnection ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={testing}
              onClick={() => void handleSubmit(testValidConfig)()}
            >
              {testing ? "测试中…" : "测试连接"}
            </Button>
          ) : <span />}
          {onSave ? (
            <Button type="submit" size="sm" className="hifi-settings-submit-btn">
              <CheckCircle2 size={13} />
              保存配置
            </Button>
          ) : null}
        </footer>
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
