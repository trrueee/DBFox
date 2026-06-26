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
import "./SettingsDialog.css";

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
      <DialogContent className="settings-dialog-content">
        <DialogHeader className="settings-dialog-header">
          <DialogTitle className="settings-dialog-title">
            <div className="settings-dialog-title-icon">
              <Zap size={13} className="settings-dialog-title-glyph" />
            </div>
            设置
          </DialogTitle>
          <DialogDescription className="settings-dialog-description">
            配置 LLM 服务连接与模型偏好
          </DialogDescription>
        </DialogHeader>

        <LlmConfigPanel
          variant="dialog"
          config={config}
          onChange={onChange}
          saved={saved}
        />

        <div className="settings-dialog-footer">
          <p className="settings-dialog-caption">
            配置保存在本地浏览器
          </p>
          <div className="settings-dialog-actions">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button size="sm" onClick={onSave} className="settings-dialog-save">
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
      <div className="settings-button-status" data-configured={isConfigured ? "true" : "false"}>
        <Zap size={14} className="settings-button-icon" />
        {isConfigured && (
          <span className="settings-button-indicator" />
        )}
      </div>
    </Button>
  );
}
