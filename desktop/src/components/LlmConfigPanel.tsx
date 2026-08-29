import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { CheckCircle2, Eye, EyeOff, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { ProviderIcon } from "./ProviderIcon";
import { getUserErrorMessage } from "../lib/api/client";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  SettingsContent,
  SettingsField,
  SettingsSection,
  SettingsStatus,
} from "./settings";
import type { LlmConfigDraft } from "../lib/api/types";
import {
  DEFAULT_LLM_API_BASE,
  LLM_PROVIDERS,
  applyModelPresetSelection,
  detectProviderFromBaseUrl,
  findProvider,
} from "../lib/llmProviders";
import { listDraftLlmModels } from "../features/appShell/llmDraftConnection";
import "./LlmConfigPanel.css";

interface LlmConfigPanelProps {
  config: LlmConfigDraft;
  onChange: (partial: Partial<LlmConfigDraft>) => void;
  onSave?: () => void | Promise<void>;
  onTestConnection?: () => boolean | void | Promise<boolean | void>;
}

const AUTO_MODEL_VALUE = "__auto__";
const CUSTOM_MODEL_VALUE = "__custom__";
const CUSTOM_ENDPOINT_VALUE = "__custom_endpoint__";

const llmConfigSchema = z.object({
  credentialId: z.string(),
  apiKey: z.string(),
  apiBase: z.string().trim().refine((value) => value === "" || isHttpUrl(value), {
    message: "API Base URL 必须是有效的 http(s) 地址",
  }),
  modelName: z.string(),
});

interface FetchedModels {
  apiBase: string;
  models: string[];
}

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
  const [operationError, setOperationError] = useState<{
    label: string;
    error: unknown;
  } | null>(null);
  const [customModelMode, setCustomModelMode] = useState(false);
  const [fetched, setFetched] = useState<FetchedModels | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchHint, setFetchHint] = useState<string>("");
  const fetchKeyRef = useRef("");
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
  const detectedProvider = detectProviderFromBaseUrl(values.apiBase);
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

  const fetchModels = async () => {
    if (fetching) return;
    const apiBase = (values.apiBase || DEFAULT_LLM_API_BASE).trim();
    if (!isHttpUrl(apiBase)) {
      setFetchHint("API Base 无效，无法获取模型列表。");
      return;
    }
    setFetching(true);
    setFetchHint("");
    try {
      const result = await listDraftLlmModels({ ...values, apiBase });
      if (result.ok && result.models.length) {
        setFetched({ apiBase, models: result.models });
        setFetchHint(`已获取 ${result.models.length} 个模型。`);
      } else {
        setFetched(null);
        setFetchHint(result.message || "该服务未提供模型列表，可自定义模型名称。");
      }
    } catch (error) {
      setFetchHint(getUserErrorMessage(error, "获取模型列表失败，请检查网络与凭据。"));
    } finally {
      setFetching(false);
    }
  };

  // Auto-fetch once per endpoint+credential combination so the selector fills
  // itself for returning users; the button covers manual refresh.
  const autoFetchKey = `${values.credentialId || values.apiKey ? "k" : "n"}:${values.apiBase}`;
  useEffect(() => {
    if (fetching) return;
    if (fetchKeyRef.current === autoFetchKey) return;
    fetchKeyRef.current = autoFetchKey;
    if (!autoFetchKey.startsWith("k")) return;
    void fetchModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFetchKey]);

  const submitValidConfig = async () => {
    setSaving(true);
    setOperationError(null);
    try {
      await onSave?.();
    } catch (error) {
      setOperationError({ label: "模型服务配置保存失败", error });
    } finally {
      setSaving(false);
    }
  };

  const testValidConfig = async () => {
    if (!onTestConnection) return;
    setTesting(true);
    setTestState("idle");
    setOperationError(null);
    try {
      const result = await onTestConnection();
      setTestState(result === false ? "error" : "success");
    } catch (error) {
      setTestState("error");
      setOperationError({ label: "模型连接测试失败", error });
    } finally {
      setTesting(false);
    }
  };

  const fetchedModels = fetched && fetched.apiBase === (values.apiBase || DEFAULT_LLM_API_BASE).trim()
    ? fetched.models
    : [];
  const selectedProviderId = detectedProvider?.id ?? CUSTOM_ENDPOINT_VALUE;
  const groupedProviders = [
    { region: "global" as const, label: "海外服务商" },
    { region: "cn" as const, label: "国内服务商" },
    { region: "local" as const, label: "本地" },
  ];

  return (
    <form
      onSubmit={handleSubmit(submitValidConfig)}
      className="llm-settings-form"
    >
      <SettingsContent className="llm-settings-content">
        <SettingsSection
          title="连接与模型"
          description="连接 OpenAI 兼容服务；凭据保存在本机安全存储，模型列表从服务端实时获取。"
        >
          <SettingsField label="服务商" htmlFor="llm-provider">
            <Select
              value={selectedProviderId}
              onValueChange={(providerId) => {
                const provider = findProvider(providerId);
                if (provider) applyConfigPatch({ apiBase: provider.baseUrl });
              }}
            >
              <SelectTrigger id="llm-provider" className="llm-model-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {groupedProviders.map(({ region, label }) => (
                  <SelectGroup key={region}>
                    <SelectLabel>{label}</SelectLabel>
                    {LLM_PROVIDERS.filter((provider) => provider.region === region).map((provider) => (
                      <SelectItem key={provider.id} value={provider.id} textValue={provider.label}>
                        <span className="llm-provider-option">
                          <ProviderIcon provider={provider.id} size={14} />
                          <span>{provider.label}</span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
                <SelectGroup>
                  <SelectLabel>其他</SelectLabel>
                  <SelectItem value={CUSTOM_ENDPOINT_VALUE} textValue="自定义端点">
                    <span className="llm-provider-option">
                      <span className="llm-provider-option__badge">…</span>
                      <span>自定义端点</span>
                    </span>
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </SettingsField>

          <SettingsField label="API Key" htmlFor="llm-api-key" hint="由系统安全存储管理，不会进入 Agent 上下文。">
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
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </SettingsField>

          <SettingsField label="API Base URL" htmlFor="llm-api-base"
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

          <SettingsField label="默认模型" htmlFor="llm-model-preset">
            <div className="llm-model-control">
              <Select
                value={customModelMode ? CUSTOM_MODEL_VALUE : values.modelName || AUTO_MODEL_VALUE}
                onValueChange={(selected) => {
                  if (selected === CUSTOM_MODEL_VALUE) {
                    setCustomModelMode(true);
                    applyConfigPatch({ modelName: "" });
                    return;
                  }
                  setCustomModelMode(false);
                  const modelName = selected === AUTO_MODEL_VALUE ? "" : selected;
                  applyConfigPatch({ modelName, apiBase: (values.apiBase || DEFAULT_LLM_API_BASE).trim() });
                }}
              >
                <SelectTrigger
                  id="llm-model-preset"
                  className="llm-model-select"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO_MODEL_VALUE} textValue="自动检测">自动检测</SelectItem>
                  {fetchedModels.length ? (
                    <SelectGroup>
                      <SelectLabel>服务返回 · {fetchedModels.length}</SelectLabel>
                      {fetchedModels.map((model) => (
                        <SelectItem key={model} value={model} textValue={model}>
                          <span className="llm-provider-option">
                            <ProviderIcon provider={modelProviderId(model, detectedProvider?.id)} size={14} />
                            <span>{model}</span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ) : null}
                  <SelectGroup>
                    <SelectLabel>其他</SelectLabel>
                    <SelectItem value={CUSTOM_MODEL_VALUE}>自定义模型…</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="llm-model-fetch-btn"
                disabled={fetching || Boolean(formState.errors.apiBase)}
                onClick={() => void fetchModels()}
              >
                <RefreshCw size={14} className={fetching ? "animate-spin" : undefined} />
                {fetching ? "获取中…" : "获取模型列表"}
              </Button>
            </div>
            {customModelMode ? (
              <input
                id="llm-model-custom"
                aria-label="自定义模型名称"
                placeholder="输入模型名称，例如 deepseek-chat"
                value={values.modelName}
                onChange={(event) => {
                  const name = event.target.value;
                  applyConfigPatch({
                    modelName: name,
                    apiBase: resolveApiBaseForCustomInput(name, values.apiBase),
                  });
                }}
                className="hifi-settings-input hifi-settings-input--mono llm-model-custom-input"
              />
            ) : null}
            {fetchHint ? <p className="llm-fetch-hint">{fetchHint}</p> : null}
          </SettingsField>

          <div className="llm-settings-inline-actions">
            <div className="llm-settings-inline-status" aria-live="polite">
              {testing ? (
                <SettingsStatus tone="loading" label="正在测试模型连接…" />
              ) : testState === "success" ? (
                <SettingsStatus tone="success" label="模型连接可用" />
              ) : operationError ? (
                <SettingsStatus
                  tone="danger"
                  label={operationError.label}
                  description={getUserErrorMessage(operationError.error, `${operationError.label}，请重试`)}
                  error={operationError.error}
                />
              ) : testState === "error" ? (
                <SettingsStatus
                  tone="danger"
                  label="模型连接不可用"
                  description="请检查凭据、端点和模型名称。"
                />
              ) : null}
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
                  <CheckCircle2 size={14} />
                  {saving ? "正在保存…" : "保存配置"}
                </Button>
              ) : null}
            </div>
          </div>
        </SettingsSection>
      </SettingsContent>
    </form>
  );
}

function modelProviderId(modelId: string, fallback?: string): string {
  const lower = modelId.toLowerCase();
  if (lower.includes("deepseek")) return "deepseek";
  if (lower.startsWith("qwen") || lower.startsWith("qwq")) return "qwen";
  if (lower.includes("kimi") || lower.startsWith("moonshot")) return "moonshot";
  if (lower.startsWith("glm")) return "zhipu";
  if (lower.includes("claude") || lower.startsWith("anthropic")) return "anthropic";
  if (lower.startsWith("gemini")) return "google";
  if (lower.startsWith("grok")) return "xai";
  if (lower.startsWith("gpt") || lower.startsWith("o1") || lower.startsWith("o3")) return "openai";
  if (lower.includes("mistral")) return "mistral";
  if (lower.includes("doubao")) return "doubao";
  if (lower.includes("minimax")) return "minimax";
  if (lower.includes("hunyuan")) return "hunyuan";
  if (lower.includes("mimo")) return "xiaomi";
  return fallback ?? "";
}

function resolveApiBaseForCustomInput(modelName: string, currentApiBase: string): string {
  const lower = modelName.toLowerCase();
  if (detectedModelPrefixes.some((prefix) => lower.startsWith(prefix))) {
    return applyModelPresetSelection(modelName, currentApiBase).apiBase;
  }
  return currentApiBase;
}

const detectedModelPrefixes = [
  "qwen", "qwq", "deepseek", "kimi", "moonshot", "glm", "gemini", "grok", "mimo",
] as const;

function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
