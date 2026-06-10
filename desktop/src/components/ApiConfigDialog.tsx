import { useState, useCallback } from "react";
import { Settings, Key, Globe, Cpu, CheckCircle2, AlertCircle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Select, SelectItem } from "./ui/select";

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

interface ApiConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ApiConfig;
  onChange: (partial: Partial<ApiConfig>) => void;
  onSave: () => void;
  saved: boolean;
}

export function ApiConfigDialog({ open, onOpenChange, config, onChange, onSave, saved }: ApiConfigDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Settings size={16} className="text-[hsl(var(--primary))]" />
            API Configuration
          </DialogTitle>
          <DialogDescription>
            Configure the LLM provider connection. Settings are stored locally.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* API Key */}
          <div className="space-y-1.5">
            <Label htmlFor="api-key" className="flex items-center gap-1.5 text-xs">
              <Key size={12} className="text-[hsl(var(--muted-foreground))]" /> API Key
            </Label>
            <Input id="api-key" type="password" placeholder="sk-..."
              value={config.apiKey} onChange={(e) => onChange({ apiKey: e.target.value })} />
            <p className="text-[0.62rem] text-[hsl(var(--muted-foreground))]">
              Your LLM provider API key. Stored locally.
            </p>
          </div>

          {/* API Base URL */}
          <div className="space-y-1.5">
            <Label htmlFor="api-base" className="flex items-center gap-1.5 text-xs">
              <Globe size={12} className="text-[hsl(var(--muted-foreground))]" /> API Base URL
            </Label>
            <Input id="api-base" type="text" placeholder={DEFAULT_CONFIG.apiBase}
              value={config.apiBase} onChange={(e) => onChange({ apiBase: e.target.value })} />
          </div>

          {/* Model */}
          <div className="space-y-1.5">
            <Label htmlFor="model-name" className="flex items-center gap-1.5 text-xs">
              <Cpu size={12} className="text-[hsl(var(--muted-foreground))]" /> Model
            </Label>
            <Select value={config.modelName} onValueChange={(v) => onChange({ modelName: v })} placeholder="Auto-detect">
              {PRESET_MODELS.map((m) => (
                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
              ))}
            </Select>
            <Input
              placeholder="Or type custom model name..."
              value={PRESET_MODELS.some((m) => m.value === config.modelName) ? "" : config.modelName}
              onChange={(e) => onChange({ modelName: e.target.value })}
              className="h-7 text-[0.7rem] mt-1"
            />
          </div>

          {/* Status */}
          <div className="flex items-center gap-2 min-h-[20px]">
            {saved && (
              <Badge variant="success" className="gap-1"><CheckCircle2 size={10} />Saved</Badge>
            )}
            {!config.apiKey && !config.modelName && (
              <Badge variant="secondary" className="gap-1"><AlertCircle size={10} />Using engine defaults</Badge>
            )}
            {config.apiKey && (
              <Badge variant="success" className="gap-1"><CheckCircle2 size={10} />API Key set</Badge>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onSave}><CheckCircle2 size={14} />Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ApiConfigButtonProps {
  onClick: () => void;
  isConfigured: boolean;
}

export function ApiConfigButton({ onClick, isConfigured }: ApiConfigButtonProps) {
  return (
    <Button
      variant={isConfigured ? "secondary" : "ghost"}
      size="icon-sm"
      onClick={onClick}
      title="API Configuration"
    >
      <Settings size={14} className={isConfigured ? "text-[hsl(var(--success))]" : "text-[hsl(var(--muted-foreground))]"} />
    </Button>
  );
}
