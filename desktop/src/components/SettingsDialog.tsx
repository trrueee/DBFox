import { useState, useCallback } from "react";
import {
  Key, Globe, Cpu, CheckCircle2, AlertCircle, Eye, EyeOff,
  Zap, Server, Layers,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";

export interface ApiConfig {
  apiKey: string;
  apiBase: string;
  modelName: string;
}

const DEFAULT_CONFIG: ApiConfig = {
  apiKey: "",
  apiBase: "http://127.0.0.1:18625/api/v1",
  modelName: "",
};

const STORAGE_KEY = "databox-api-config";

function loadConfig(): ApiConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { ...DEFAULT_CONFIG };
}

function saveConfig(config: ApiConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

/** Read the persisted LLM config without subscribing to React state. */
export function getStoredApiConfig(): ApiConfig {
  return loadConfig();
}

export function useApiConfig() {
  const [config, setConfig] = useState<ApiConfig>(loadConfig);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);

  const updateConfig = useCallback((partial: Partial<ApiConfig>) => {
    setConfig((prev) => {
      const next = { ...prev, ...partial };
      saveConfig(next);
      return next;
    });
  }, []);

  const handleSave = useCallback(() => {
    saveConfig(config);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    setOpen(false);
  }, [config]);

  const isConfigured = Boolean(config.apiKey || config.modelName);

  return { config, updateConfig, open, setOpen, saved, handleSave, isConfigured } as const;
}

const PRESET_MODELS = [
  { value: "", label: "Auto-detect" },
  { value: "gpt-4o", label: "GPT-4o" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { value: "claude-opus-4-8", label: "Claude Opus 4.8" },
  { value: "claude-haiku-4-5", label: "Claude Haiku 4.5" },
  { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
  { value: "qwen3-max", label: "Qwen3 Max" },
  { value: "qwen3-coder", label: "Qwen3 Coder" },
];

/* ------------------------------------------------------------------ */
/*  SettingsDialog — polished, section-based config panel             */
/* ------------------------------------------------------------------ */

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ApiConfig;
  onChange: (partial: Partial<ApiConfig>) => void;
  onSave: () => void;
  saved: boolean;
}

function SectionHeader({ icon: Icon, title, subtitle }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-start gap-3 mb-5">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
        style={{ background: "linear-gradient(135deg, hsl(var(--primary)/0.12), hsl(var(--primary)/0.06))" }}>
        <Icon size={14} className="text-[hsl(var(--primary))]" />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">{title}</h3>
        <p className="text-[0.7rem] text-[hsl(var(--muted-foreground))] mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

function FieldRow({ icon: Icon, label, htmlFor, hint, children }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <Label htmlFor={htmlFor} className="flex items-center gap-1.5 text-[0.72rem] font-medium text-[hsl(var(--foreground))] mb-1.5">
        <Icon size={11} className="text-[hsl(var(--muted-foreground))]" />
        {label}
      </Label>
      {children}
      {hint && (
        <p className="text-[0.62rem] text-[hsl(var(--muted-foreground))] mt-1">{hint}</p>
      )}
    </div>
  );
}

export function SettingsDialog({ open, onOpenChange, config, onChange, onSave, saved }: SettingsDialogProps) {
  const [showKey, setShowKey] = useState(false);
  const isCustomModel = !PRESET_MODELS.some((m) => m.value === config.modelName);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] p-0 gap-0 overflow-hidden">
        {/* ---- Header ---- */}
        <DialogHeader className="px-6 pt-6 pb-5 border-b border-[hsl(var(--border))]">
          <DialogTitle className="flex items-center gap-2.5 text-[0.95rem] font-semibold tracking-tight text-[hsl(var(--foreground))]">
            <div className="w-7 h-7 rounded-md flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary)/0.8))" }}>
              <Zap size={13} className="text-white" />
            </div>
            设置
          </DialogTitle>
          <DialogDescription className="text-[0.72rem] text-[hsl(var(--muted-foreground))] mt-1">
            Configure your LLM provider and connection preferences
          </DialogDescription>
        </DialogHeader>

        {/* ---- Body ---- */}
        <div className="px-6 py-5 space-y-6 max-h-[60vh] overflow-y-auto">
          {/* Section: LLM Provider */}
          <div>
            <SectionHeader
              icon={Cpu}
              title="LLM 服务配置"
              subtitle="Connect to an OpenAI-compatible API endpoint"
            />

            {/* API Key */}
            <FieldRow icon={Key} label="API Key" htmlFor="settings-api-key"
              hint="Your provider API key. Never shared or logged.">
              <div className="relative">
                <Input
                  id="settings-api-key"
                  type={showKey ? "text" : "password"}
                  placeholder="sk-••••••••••••••••"
                  value={config.apiKey}
                  onChange={(e) => onChange({ apiKey: e.target.value })}
                  className="pr-9 font-mono text-[0.72rem] tracking-tight"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((p) => !p)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors"
                  tabIndex={-1}
                >
                  {showKey
                    ? <EyeOff size={13} className="text-[hsl(var(--muted-foreground))]" />
                    : <Eye size={13} className="text-[hsl(var(--muted-foreground))]" />
                  }
                </button>
              </div>
            </FieldRow>

            {/* API Base URL */}
            <FieldRow icon={Globe} label="API Base URL" htmlFor="settings-api-base">
              <Input
                id="settings-api-base"
                type="text"
                placeholder={DEFAULT_CONFIG.apiBase}
                value={config.apiBase}
                onChange={(e) => onChange({ apiBase: e.target.value })}
                className="font-mono text-[0.7rem]"
              />
            </FieldRow>

            {/* Model Selection */}
            <FieldRow icon={Layers} label="Model" htmlFor="settings-model"
              hint={isCustomModel ? "Using custom model name" : undefined}>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {PRESET_MODELS.filter((m) => m.value !== "").map((m) => {
                  const active = config.modelName === m.value;
                  return (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => onChange({ modelName: active ? "" : m.value })}
                      className={`
                        inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[0.67rem] font-medium
                        transition-all duration-150 border cursor-pointer
                        ${active
                          ? "border-[hsl(var(--primary)/0.4)] bg-[hsl(var(--primary)/0.1)] text-[hsl(var(--primary))] shadow-sm"
                          : "border-[hsl(var(--border))] bg-transparent text-[hsl(var(--muted-foreground))] hover:border-[hsl(var(--primary)/0.25)] hover:text-[hsl(var(--foreground))]"
                        }
                      `}
                    >
                      {active && <CheckCircle2 size={10} />}
                      {m.label}
                    </button>
                  );
                })}
              </div>
              <Input
                id="settings-model"
                placeholder="Or type a custom model name..."
                value={isCustomModel ? config.modelName : ""}
                onChange={(e) => onChange({ modelName: e.target.value })}
                className="h-7 text-[0.65rem] font-mono"
              />
            </FieldRow>
          </div>

          {/* Divider */}
          <div className="h-px bg-[hsl(var(--border))]" />

          {/* Section: Connection Status */}
          <div>
            <SectionHeader
              icon={Server}
              title="连接状态"
              subtitle="Current configuration summary"
            />
            <div className="space-y-2">
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[0.72rem] text-[hsl(var(--muted-foreground))]">API Key</span>
                {config.apiKey ? (
                  <Badge variant="success" className="gap-1 text-[0.62rem]">
                    <CheckCircle2 size={9} />Configured
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="gap-1 text-[0.62rem]">
                    <AlertCircle size={9} />Not set
                  </Badge>
                )}
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[0.72rem] text-[hsl(var(--muted-foreground))]">Endpoint</span>
                <span className="font-mono text-[0.65rem] text-[hsl(var(--foreground))] max-w-[260px] truncate">
                  {config.apiBase || DEFAULT_CONFIG.apiBase}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[0.72rem] text-[hsl(var(--muted-foreground))]">Model</span>
                <span className="font-mono text-[0.65rem] text-[hsl(var(--foreground))]">
                  {config.modelName || "Auto-detect"}
                </span>
              </div>
            </div>
          </div>

          {/* Saved indicator */}
          <div
            className={`
              overflow-hidden transition-all duration-300
              ${saved ? "max-h-8 opacity-100" : "max-h-0 opacity-0"}
            `}
          >
            <div className="flex items-center gap-2 text-[0.7rem] text-[hsl(var(--success))]">
              <CheckCircle2 size={12} />
              Settings saved successfully
            </div>
          </div>
        </div>

        {/* ---- Footer ---- */}
        <div className="px-6 py-4 border-t border-[hsl(var(--border))] flex items-center justify-between bg-[hsl(var(--muted)/0.3)]">
          <p className="text-[0.62rem] text-[hsl(var(--muted-foreground))]">
            Settings stored locally in your browser
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={onSave} className="gap-1.5">
              <CheckCircle2 size={13} />
              Save
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/*  Compact trigger button for toolbar placement                      */
/* ------------------------------------------------------------------ */

interface SettingsButtonProps {
  onClick: () => void;
  isConfigured: boolean;
}

export function SettingsButton({ onClick, isConfigured }: SettingsButtonProps) {
  return (
    <Button
      variant={isConfigured ? "secondary" : "ghost"}
      size="icon-sm"
      onClick={onClick}
      title="设置"
    >
      <div className="relative">
        <Zap
          size={14}
          className={isConfigured ? "text-[hsl(var(--success))]" : "text-[hsl(var(--muted-foreground))]"}
        />
        {isConfigured && (
          <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-[hsl(var(--success))]" />
        )}
      </div>
    </Button>
  );
}
