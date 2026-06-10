import { useEffect, useMemo, useState } from "react";
import { Bot, CheckCircle2, KeyRound, Link2, RefreshCw, Save, SlidersHorizontal } from "lucide-react";
import {
  getLlmConfig,
  listLlmProviders,
  resolveLlmConfig,
  saveLlmConfig,
  type LlmConfig,
  type LlmProviderPreset,
} from "../engine/engineApi";

interface LlmSettingsWorkspaceProps {
  onToast: (message: string) => void;
}

export function LlmSettingsWorkspace({ onToast }: LlmSettingsWorkspaceProps) {
  const [providers, setProviders] = useState<LlmProviderPreset[]>([]);
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("deepseek-chat");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const activeProvider = useMemo(() => providers.find((item) => item.provider === provider), [providers, provider]);
  const availableModels = activeProvider?.models || [];
  const isCustom = provider === "custom";

  const loadConfig = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextProviders, nextConfig] = await Promise.all([listLlmProviders(), getLlmConfig()]);
      setProviders(nextProviders);
      applyConfig(nextConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取 LLM 配置失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConfig();
  }, []);

  const applyConfig = (nextConfig: LlmConfig) => {
    setConfig(nextConfig);
    setProvider(nextConfig.provider);
    setModel(nextConfig.model);
    setBaseUrl(nextConfig.base_url);
    setTemperature(nextConfig.temperature);
    setMaxTokens(nextConfig.max_tokens);
    setEnabled(nextConfig.enabled);
    setApiKey("");
  };

  const handleProviderChange = async (nextProvider: string) => {
    const preset = providers.find((item) => item.provider === nextProvider);
    const nextModel = preset?.models[0] || model;
    setProvider(nextProvider);
    if (preset?.models.length) setModel(nextModel);
    if (nextProvider !== "custom") setBaseUrl(preset?.base_url || "");
    if (nextProvider === "custom") return;

    try {
      const resolved = await resolveLlmConfig(nextProvider, nextModel, preset?.base_url);
      setProvider(resolved.provider);
      setBaseUrl(resolved.base_url);
    } catch {
      setBaseUrl(preset?.base_url || "");
    }
  };

  const handleModelChange = async (nextModel: string) => {
    setModel(nextModel);
    try {
      const resolved = await resolveLlmConfig(provider, nextModel, baseUrl);
      setProvider(resolved.provider);
      setBaseUrl(resolved.base_url);
    } catch {
      // Keep local editing responsive even if engine resolution fails.
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const nextConfig = await saveLlmConfig({
        provider,
        model,
        base_url: baseUrl,
        api_key: apiKey || undefined,
        temperature,
        max_tokens: maxTokens,
        enabled,
      });
      applyConfig(nextConfig);
      onToast("LLM 配置已保存，后续 Agent 将使用该模型配置");
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存 LLM 配置失败";
      setError(message);
      onToast(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="hifi-tab-pane p-4 overflow-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 text-[14px] font-bold text-slate-900">
            <Bot size={17} className="text-purple-600" />
            LLM 模型配置
          </div>
          <div className="text-[10px] text-slate-400 mt-1">模型与 Base URL 联动，保存到本地 Engine，供后续 Agent 自动读取。</div>
        </div>
        <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "26px", fontSize: "10px" }} onClick={() => void loadConfig()}>
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          刷新
        </button>
      </div>

      {error && <div className="text-[11px] text-red-500 bg-red-50 rounded-xl p-3 mb-3">{error}</div>}

      <div className="grid grid-cols-[260px_1fr] gap-4">
        <div className="hifi-ai-card">
          <div className="hifi-ai-card-header flex items-center gap-1.5"><SlidersHorizontal size={12} />供应商</div>
          <div className="hifi-ai-card-body p-3 flex flex-col gap-2">
            {providers.map((item) => (
              <button
                key={item.provider}
                className={`text-left border rounded-xl p-3 transition-all ${provider === item.provider ? "border-purple-300 bg-purple-50" : "border-slate-200 bg-white hover:border-slate-300"}`}
                onClick={() => void handleProviderChange(item.provider)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-bold text-slate-800">{item.label}</span>
                  {provider === item.provider && <CheckCircle2 size={13} className="text-purple-600" />}
                </div>
                <div className="text-[9px] text-slate-400 mt-1 truncate">{item.base_url || "手动填写 Base URL"}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="hifi-ai-card">
          <div className="hifi-ai-card-header flex items-center justify-between">
            <span>当前配置</span>
            <span className="hifi-guide-chip-prod">{enabled ? "ENABLED" : "DISABLED"}</span>
          </div>
          <div className="hifi-ai-card-body p-4 flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-semibold">Provider</span>
                <select className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" value={provider} onChange={(event) => void handleProviderChange(event.target.value)}>
                  {providers.map((item) => <option key={item.provider} value={item.provider}>{item.label}</option>)}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-semibold">Model</span>
                {availableModels.length > 0 ? (
                  <select className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" value={model} onChange={(event) => void handleModelChange(event.target.value)}>
                    {availableModels.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                ) : (
                  <input className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" value={model} onChange={(event) => void handleModelChange(event.target.value)} placeholder="例如：gpt-4o-mini / qwen-plus" />
                )}
              </label>
            </div>

            <label className="flex flex-col gap-1">
              <span className="text-[10px] text-slate-500 font-semibold flex items-center gap-1"><Link2 size={10} /> Base URL</span>
              <input
                className={`border rounded-lg px-2 py-1.5 text-[11px] font-mono ${isCustom ? "border-slate-300 bg-white" : "border-slate-200 bg-slate-50 text-slate-500"}`}
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                readOnly={!isCustom}
                placeholder="https://api.example.com/v1"
              />
              <span className="text-[9px] text-slate-400">选择预设供应商时会自动切换 URL；自定义供应商可手动填写。</span>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-[10px] text-slate-500 font-semibold flex items-center gap-1"><KeyRound size={10} /> API Key</span>
              <input
                className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px] font-mono"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={config?.has_api_key ? `已保存：${config.api_key_preview}，留空则保留` : "请输入 API Key"}
              />
            </label>

            <div className="grid grid-cols-3 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-semibold">Temperature</span>
                <input className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(Number(event.target.value))} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-semibold">Max Tokens</span>
                <input className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" type="number" min="256" max="32768" step="256" value={maxTokens} onChange={(event) => setMaxTokens(Number(event.target.value))} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 font-semibold">启用状态</span>
                <select className="border border-slate-200 rounded-lg px-2 py-1.5 text-[11px]" value={enabled ? "1" : "0"} onChange={(event) => setEnabled(event.target.value === "1")}>
                  <option value="1">启用</option>
                  <option value="0">禁用</option>
                </select>
              </label>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 pt-3">
              <div className="text-[10px] text-slate-400">保存后 Agent 层应通过 `/api/v1/llm/config` 读取当前激活模型。</div>
              <button className="hifi-guide-btn-primary flex items-center gap-1" style={{ height: "28px", fontSize: "10px" }} onClick={handleSave} disabled={saving}>
                <Save size={11} />
                {saving ? "保存中..." : "保存配置"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
