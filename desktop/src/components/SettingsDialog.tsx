import { useState, useCallback } from "react";
import { CheckCircle2, Zap } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { LlmConfigPanel } from "./LlmConfigPanel";
import { DEFAULT_LLM_API_BASE } from "../lib/llmPresets";
import { validateApiConfig } from "../lib/api/types";
import type { ApiConfig } from "../lib/api/types";

const DEFAULT_CONFIG: ApiConfig = {
  apiKey: "",
  apiBase: DEFAULT_LLM_API_BASE,
  modelName: "",
};

const STORAGE_KEY = "dbfox-api-config";

function loadConfig(): ApiConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (validateApiConfig(parsed)) return parsed;
    }
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

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ApiConfig;
  onChange: (partial: Partial<ApiConfig>) => void;
  onSave: () => void;
  saved: boolean;
}

export function SettingsDialog({ open, onOpenChange, config, onChange, onSave, saved }: SettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px] p-0 gap-0 overflow-hidden border-[hsl(var(--border))]">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-[hsl(var(--border))]">
          <DialogTitle className="flex items-center gap-2.5 text-[var(--ui-font-section-title)] font-semibold">
            <div className="w-7 h-7 rounded-md flex items-center justify-center bg-[hsl(var(--primary))]">
              <Zap size={13} className="text-white" />
            </div>
            设置
          </DialogTitle>
          <DialogDescription className="text-[var(--ui-font-label)] text-[hsl(var(--muted-foreground))] mt-1">
            配置 LLM 服务连接与模型偏好
          </DialogDescription>
        </DialogHeader>

        <LlmConfigPanel
          variant="dialog"
          config={config}
          onChange={onChange}
          saved={saved}
        />

        <div className="px-6 py-4 border-t border-[hsl(var(--border))] flex items-center justify-between bg-[hsl(var(--secondary)/0.4)]">
          <p className="text-[var(--ui-font-caption)] text-[hsl(var(--muted-foreground))]">
            配置保存在本地浏览器
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button size="sm" onClick={onSave} className="gap-1.5">
              <CheckCircle2 size={13} />
              保存
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

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
