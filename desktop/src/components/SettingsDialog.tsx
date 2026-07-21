import { CheckCircle2, Zap } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { LlmConfigPanel } from "./LlmConfigPanel";
import type { LlmConfigDraft } from "../lib/api/types";
import "./SettingsDialog.css";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: LlmConfigDraft;
  onChange: (partial: Partial<LlmConfigDraft>) => void;
  onSave: () => void | Promise<void>;
  onCancel: () => void;
  saved: boolean;
}

export function SettingsDialog({ open, onOpenChange, config, onChange, onSave, onCancel, saved }: SettingsDialogProps) {
  const closeWithoutSaving = () => {
    onCancel();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (nextOpen) onOpenChange(true);
      else closeWithoutSaving();
    }}>
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
            凭据保存在系统安全存储中
          </p>
          <div className="settings-dialog-actions">
            <Button variant="outline" size="sm" onClick={closeWithoutSaving}>
              取消
            </Button>
            <Button size="sm" onClick={() => void onSave()} className="settings-dialog-save">
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
