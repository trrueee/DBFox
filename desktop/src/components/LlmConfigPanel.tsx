import { useState } from "react";
import {
  Key, Globe, Layers, CheckCircle2, AlertCircle, Eye, EyeOff, Cpu, Server, Zap,
} from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import type { ApiConfig } from "../lib/api/types";
import {
  DEFAULT_LLM_API_BASE,
  LLM_MODEL_PRESETS,
  applyModelPresetSelection,
  findModelPreset,
} from "../lib/llmPresets";

interface LlmConfigPanelProps {
  config: ApiConfig;
  onChange: (partial: Partial<ApiConfig>) => void;
  onSave?: () => void;
  onTestConnection?: () => void | Promise<void>;
  saved?: boolean;
  variant?: "dialog" | "page";
}

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
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
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
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
}: LlmConfigPanelProps) {
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const presetValues = LLM_MODEL_PRESETS.map((m) => m.value);
  const isCustomModel = Boolean(config.modelName) && !presetValues.includes(config.modelName);
  const activePreset = findModelPreset(config.modelName);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (variant === "page") {
          onSave?.();
        }
      }}
      className={variant === "page" ? "hifi-settings-page" : "hifi-settings-dialog-body"}
    >
      {variant === "page" ? (
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
          <div className="relative">
            <input
              id="llm-api-key"
              type={showKey ? "text" : "password"}
              placeholder="sk-••••••••••••••••"
              value={config.apiKey}
              onChange={(e) => onChange({ apiKey: e.target.value })}
              className="hifi-settings-input pr-9 font-mono"
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
            value={config.apiBase}
            onChange={(e) => onChange({ apiBase: e.target.value })}
            className="hifi-settings-input font-mono"
          />
        </FieldRow>

        <FieldRow icon={Layers} label="模型" htmlFor="llm-model"
          hint={isCustomModel ? "使用自定义模型名称" : activePreset ? `${activePreset.label} · ${activePreset.provider}` : undefined}>
          <div className="hifi-model-chips">
            {LLM_MODEL_PRESETS.filter((m) => m.value !== "").map((m) => {
              const active = config.modelName === m.value;
              return (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => {
                    if (active) {
                      onChange({ modelName: "" });
                    } else {
                      onChange(applyModelPresetSelection(m.value, config.apiBase));
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
            value={isCustomModel ? config.modelName : ""}
            onChange={(e) => {
              const name = e.target.value;
              if (!name) {
                onChange({ modelName: "" });
                return;
              }
              onChange({
                modelName: name,
                apiBase: resolveApiBaseForCustomInput(name, config.apiBase),
              });
            }}
            className="hifi-settings-input font-mono mt-2"
            style={{ height: 30, fontSize: "0.65rem" }}
          />
        </FieldRow>

        <div className="hifi-settings-divider" />

        <SectionHeader icon={Server} title="连接状态" subtitle="当前配置摘要" />
        <div className="hifi-settings-status-list">
          <div className="hifi-settings-status-row">
            <span>API Key</span>
            {config.apiKey ? (
              <Badge variant="success" className="gap-1 text-[0.62rem]">
                <CheckCircle2 size={9} />已配置
              </Badge>
            ) : (
              <Badge variant="secondary" className="gap-1 text-[0.62rem]">
                <AlertCircle size={9} />未设置
              </Badge>
            )}
          </div>
          <div className="hifi-settings-status-row">
            <span>Endpoint</span>
            <span className="hifi-settings-mono truncate max-w-[280px]">
              {config.apiBase || DEFAULT_LLM_API_BASE}
            </span>
          </div>
          <div className="hifi-settings-status-row">
            <span>Model</span>
            <span className="hifi-settings-mono">{config.modelName || "自动检测"}</span>
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
              onClick={async () => {
                setTesting(true);
                try {
                  await onTestConnection();
                } finally {
                  setTesting(false);
                }
              }}
            >
              {testing ? "测试中…" : "测试连接"}
            </Button>
          ) : <span />}
          {onSave ? (
            <Button type="submit" size="sm" className="gap-1.5">
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
